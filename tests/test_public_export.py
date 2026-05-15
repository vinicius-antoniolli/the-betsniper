from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import SQLModel

from scripts.export_public_data import export_public_snapshot
from src.db.migrations import run_sqlite_migrations
from src.db.models import (  # noqa: F401
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


def _create_db(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    try:
        SQLModel.metadata.create_all(engine)
        with engine.begin() as conn:
            run_sqlite_migrations(conn)
    finally:
        engine.dispose()


class PublicExportTests(unittest.TestCase):
    def test_export_keeps_public_dashboard_rows_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.db"
            output = root / "public.db"
            metadata = root / "meta.json"
            _create_db(source)

            with closing(sqlite3.connect(source)) as conn:
                conn.execute(
                    """
                    INSERT INTO matches
                    (source, source_match_id, league_id, league_name, season, target_date, home_team, away_team, created_at, updated_at)
                    VALUES
                    ('espn', 'target-1', 1, 'Liga', 2026, '2026-05-15', 'A', 'B', '2026-05-15 10:00:00', '2026-05-15 10:00:00'),
                    ('espn', 'other-1', 1, 'Liga', 2026, '2026-05-20', 'C', 'D', '2026-05-15 10:00:00', '2026-05-15 10:00:00')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO analysis_results
                    (target_date, source_match_id, league_name, home_team, away_team, market_key, pick, score, sample_size, created_at)
                    VALUES ('2026-05-15', 'target-1', 'Liga', 'A', 'B', 'over_25', 'over', 82.0, 10, '2026-05-15 10:00:00')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO odds_snapshots
                    (source, source_match_id, bookmaker, market_key, outcome_name, price, raw_json, fetched_at)
                    VALUES
                    ('betfair-web', 'target-1', 'Betfair', 'over_25', 'over', 2.1, '{"home_team":"A","away_team":"B"}', '2026-05-15 10:00:00'),
                    ('betfair-web', 'other-1', 'Betfair', 'over_25', 'over', 1.7, '{"home_team":"C","away_team":"D"}', '2026-05-15 10:00:00')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO team_stats
                    (source, source_match_id, team_name, opponent_name, match_date, is_home, goals_for, goals_against, created_at)
                    VALUES
                    ('espn', 'hist-a', 'A', 'X', '2026-05-01', 1, 2, 0, '2026-05-15 10:00:00'),
                    ('espn', 'hist-c', 'C', 'Y', '2026-05-01', 1, 1, 1, '2026-05-15 10:00:00')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO player_stats
                    (source, source_match_id, player_name, team_name, match_date, raw_json, created_at)
                    VALUES
                    ('espn', 'hist-a', 'Jogador A', 'A', '2026-05-01', '{"starter":true}', '2026-05-15 10:00:00'),
                    ('espn', 'hist-c', 'Jogador C', 'C', '2026-05-01', '{"starter":true}', '2026-05-15 10:00:00')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO fetch_cache (source, cache_key, endpoint_or_url, params_hash, body, fetched_at)
                    VALUES ('espn', 'secret-cache', 'url', 'hash', 'body', '2026-05-15 10:00:00')
                    """
                )
                conn.commit()

            payload = export_public_snapshot(source, output, metadata, base_date="2026-05-15", days=2)

            self.assertEqual(payload["base_date"], "2026-05-15")
            with closing(sqlite3.connect(output)) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM matches").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM analysis_results").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM odds_snapshots").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM team_stats").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM player_stats").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM fetch_cache").fetchone()[0], 0)
            self.assertTrue(metadata.exists())


if __name__ == "__main__":
    unittest.main()
