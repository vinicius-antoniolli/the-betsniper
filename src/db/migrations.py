from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _columns(conn: Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}


def _add_missing_columns(conn: Connection, table: str, columns: Mapping[str, str]) -> None:
    existing = _columns(conn, table)
    for column, column_type in columns.items():
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


def _create_schema_migrations(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _record(conn: Connection, name: str) -> None:
    conn.execute(text("INSERT OR IGNORE INTO schema_migrations (name) VALUES (:name)"), {"name": name})


def run_sqlite_migrations(conn: Connection) -> None:
    _create_schema_migrations(conn)
    _add_missing_columns(
        conn,
        "team_stats",
        {
            "cards_for": "INTEGER",
            "cards_against": "INTEGER",
            "shots_total_for": "INTEGER",
            "shots_total_against": "INTEGER",
            "shots_on_target_for": "INTEGER",
            "shots_on_target_against": "INTEGER",
            "offsides_for": "INTEGER",
            "offsides_against": "INTEGER",
            "throw_ins_for": "INTEGER",
            "first_half_goals_for": "INTEGER",
            "first_half_goals_against": "INTEGER",
            "first_half_corners_for": "INTEGER",
            "first_half_corners_against": "INTEGER",
            "xg_for": "REAL",
            "xg_against": "REAL",
            "fouls_committed": "INTEGER",
            "fouls_suffered": "INTEGER",
        },
    )
    _record(conn, "001_team_stats_extended")

    _add_missing_columns(
        conn,
        "player_stats",
        {
            "goals": "INTEGER",
            "assists": "INTEGER",
            "fouls_suffered": "INTEGER",
            "yellow_cards": "INTEGER",
            "red_cards": "INTEGER",
        },
    )
    _record(conn, "002_player_stats_extended")

    _add_missing_columns(
        conn,
        "odds_snapshots",
        {
            "raw_home_team": "TEXT",
            "raw_away_team": "TEXT",
            "commence_time": "TEXT",
            "market_name": "TEXT",
            "market_type": "TEXT",
            "market_category": "TEXT",
            "team_side": "TEXT",
            "team_name": "TEXT",
            "player_name": "TEXT",
            "player_id": "TEXT",
            "main_line": "TEXT",
            "market_id": "TEXT",
            "market_type_raw": "TEXT",
            "selection_id": "TEXT",
            "runner_name": "TEXT",
            "runner_handicap": "REAL",
        },
    )
    conn.execute(
        text(
            """
            UPDATE odds_snapshots
            SET
              raw_home_team = COALESCE(raw_home_team, json_extract(raw_json, '$.home_team')),
              raw_away_team = COALESCE(raw_away_team, json_extract(raw_json, '$.away_team')),
              commence_time = COALESCE(commence_time, json_extract(raw_json, '$.commence_time')),
              market_name = COALESCE(market_name, json_extract(raw_json, '$.market_name')),
              market_type = COALESCE(market_type, json_extract(raw_json, '$.market_type')),
              market_category = COALESCE(market_category, json_extract(raw_json, '$.market_category')),
              team_side = COALESCE(team_side, json_extract(raw_json, '$.team_side')),
              team_name = COALESCE(team_name, json_extract(raw_json, '$.team_name')),
              player_name = COALESCE(player_name, json_extract(raw_json, '$.player_name')),
              player_id = COALESCE(player_id, json_extract(raw_json, '$.player_id')),
              main_line = COALESCE(main_line, json_extract(raw_json, '$.main_line')),
              market_id = COALESCE(market_id, json_extract(raw_json, '$.market_id')),
              market_type_raw = COALESCE(market_type_raw, json_extract(raw_json, '$.market_type_raw')),
              selection_id = COALESCE(selection_id, json_extract(raw_json, '$.selection_id')),
              runner_name = COALESCE(runner_name, json_extract(raw_json, '$.runner_name')),
              runner_handicap = COALESCE(runner_handicap, json_extract(raw_json, '$.runner_handicap'))
            WHERE raw_json IS NOT NULL
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_odds_snapshots_raw_teams ON odds_snapshots (raw_home_team, raw_away_team)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_odds_snapshots_player_name ON odds_snapshots (player_name)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_odds_snapshots_team_name ON odds_snapshots (team_name)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_odds_snapshots_market_name ON odds_snapshots (market_name)"))
    _record(conn, "003_odds_snapshots_materialized_fields")
