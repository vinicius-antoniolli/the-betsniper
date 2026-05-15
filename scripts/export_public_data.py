from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlmodel import SQLModel

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import ROOT_DIR, settings  # noqa: E402
from src.db.migrations import run_sqlite_migrations  # noqa: E402
from src.db.models import (  # noqa: F401,E402
    AnalysisResult,
    EntityAlias,
    FetchCache,
    Match,
    OddsSnapshot,
    Player,
    PlayerLineup,
    PlayerStat,
    Team,
    TeamStat,
)


PUBLIC_DIR = ROOT_DIR / "public_data"
DEFAULT_OUTPUT = PUBLIC_DIR / "betsniper_public.db"
DEFAULT_METADATA = PUBLIC_DIR / "public_snapshot.json"


def _today() -> str:
    return datetime.now(ZoneInfo(settings.app_timezone)).date().isoformat()


def date_window(base_date: str | None, days: int) -> list[str]:
    base = datetime.fromisoformat(base_date or _today()).date()
    return [(base + timedelta(days=offset)).isoformat() for offset in range(max(days, 1))]


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA {_quote_ident(schema)}.table_info({_quote_ident(table)})")]


def _create_empty_db(output_db: Path) -> None:
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()
    engine = create_engine(_sqlite_url(output_db), echo=False, connect_args={"check_same_thread": False})
    try:
        SQLModel.metadata.create_all(engine)
        with engine.begin() as conn:
            run_sqlite_migrations(conn)
    finally:
        engine.dispose()


def _copy_selected(
    conn: sqlite3.Connection,
    table: str,
    where_sql: str = "",
    params: tuple[object, ...] = (),
) -> int:
    dest_columns = _columns(conn, "main", table)
    source_columns = set(_columns(conn, "src", table))
    columns = [column for column in dest_columns if column in source_columns]
    if not columns:
        return 0
    column_sql = ", ".join(_quote_ident(column) for column in columns)
    sql = (
        f"INSERT INTO main.{_quote_ident(table)} ({column_sql}) "
        f"SELECT {column_sql} FROM src.{_quote_ident(table)} {where_sql}"
    )
    cursor = conn.execute(sql, params)
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _placeholders(values: list[object]) -> str:
    return ", ".join("?" for _ in values)


def _fetch_column(conn: sqlite3.Connection, sql: str, params: tuple[object, ...]) -> list[str]:
    return [str(row[0]) for row in conn.execute(sql, params).fetchall() if row[0] not in (None, "")]


def _shrink_public_raw_json(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE main.team_stats
        SET raw_json = json_object(
          'league',
          json_object('name', json_extract(raw_json, '$.league.name'))
        )
        WHERE raw_json IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE main.player_stats
        SET raw_json = json_object(
          'starter', json_extract(raw_json, '$.starter'),
          'position', json_extract(raw_json, '$.position'),
          'jersey', json_extract(raw_json, '$.jersey')
        )
        WHERE raw_json IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE main.odds_snapshots
        SET raw_json = json_object(
          'home_team', raw_home_team,
          'away_team', raw_away_team,
          'commence_time', commence_time,
          'market_type', coalesce(market_type, market_key),
          'market_key', market_key,
          'market_name', market_name,
          'market_type_raw', market_type_raw,
          'market_category', market_category,
          'team_side', team_side,
          'team_name', team_name,
          'player_name', player_name,
          'player_id', player_id,
          'main_line', main_line,
          'runner_name', runner_name,
          'runner_handicap', runner_handicap,
          'outcome_name', outcome_name,
          'point', point,
          'price', price
        )
        WHERE raw_json IS NOT NULL
        """
    )


def export_public_snapshot(
    source_db: Path,
    output_db: Path = DEFAULT_OUTPUT,
    metadata_path: Path = DEFAULT_METADATA,
    base_date: str | None = None,
    days: int = 2,
) -> dict[str, object]:
    source_db = source_db.resolve()
    output_db = output_db.resolve()
    metadata_path = metadata_path.resolve()

    if not source_db.exists():
        raise FileNotFoundError(f"Banco fonte nao encontrado: {source_db}")
    if source_db == output_db:
        raise ValueError("Banco fonte e banco publico nao podem ser o mesmo arquivo.")

    dates = date_window(base_date, days)
    date_params = tuple(dates)
    date_sql = _placeholders(dates)

    _create_empty_db(output_db)

    counts: dict[str, int] = {}
    with closing(sqlite3.connect(output_db)) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ATTACH DATABASE ? AS src", (str(source_db),))

        counts["matches"] = _copy_selected(
            conn,
            "matches",
            f"WHERE target_date IN ({date_sql})",
            date_params,
        )
        match_ids = _fetch_column(
            conn,
            f"SELECT source_match_id FROM src.matches WHERE target_date IN ({date_sql})",
            date_params,
        )
        teams = _fetch_column(
            conn,
            f"""
            SELECT home_team FROM src.matches WHERE target_date IN ({date_sql})
            UNION
            SELECT away_team FROM src.matches WHERE target_date IN ({date_sql})
            """,
            date_params + date_params,
        )

        counts["analysis_results"] = _copy_selected(
            conn,
            "analysis_results",
            f"WHERE target_date IN ({date_sql})",
            date_params,
        )

        if match_ids:
            match_sql = _placeholders(match_ids)
            counts["player_lineups"] = _copy_selected(
                conn,
                "player_lineups",
                f"WHERE source_match_id IN ({match_sql})",
                tuple(match_ids),
            )
            counts["odds_snapshots"] = _copy_selected(
                conn,
                "odds_snapshots",
                (
                    "WHERE source = 'betfair-web' AND "
                    f"(source_match_id IN ({match_sql}) OR date(commence_time) IN ({date_sql}))"
                ),
                tuple(match_ids) + date_params,
            )
        else:
            counts["player_lineups"] = 0
            counts["odds_snapshots"] = _copy_selected(
                conn,
                "odds_snapshots",
                f"WHERE source = 'betfair-web' AND date(commence_time) IN ({date_sql})",
                date_params,
            )

        if teams:
            team_sql = _placeholders(teams)
            counts["team_stats"] = _copy_selected(
                conn,
                "team_stats",
                f"WHERE source = 'espn' AND team_name IN ({team_sql})",
                tuple(teams),
            )
            counts["player_stats"] = _copy_selected(
                conn,
                "player_stats",
                f"WHERE source = 'espn' AND team_name IN ({team_sql})",
                tuple(teams),
            )
        else:
            counts["team_stats"] = 0
            counts["player_stats"] = 0

        _shrink_public_raw_json(conn)
        conn.commit()
        conn.execute("DETACH DATABASE src")
        conn.execute("VACUUM")

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "generated_at": datetime.now(ZoneInfo(settings.app_timezone)).isoformat(timespec="seconds"),
        "base_date": dates[0],
        "days": len(dates),
        "dates": dates,
        "source_db": _display_path(source_db),
        "output_db": _display_path(output_db),
        "output_size_bytes": output_db.stat().st_size,
        "counts": counts,
    }
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta snapshot publico read-only para deploy online.")
    parser.add_argument("--date", help="YYYY-MM-DD. Default: hoje em APP_TIMEZONE.")
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--source-db", default=str(ROOT_DIR / "data" / "betsniper.db"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    args = parser.parse_args()

    payload = export_public_snapshot(
        source_db=Path(args.source_db),
        output_db=Path(args.output),
        metadata_path=Path(args.metadata),
        base_date=args.date,
        days=args.days,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
