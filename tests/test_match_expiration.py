from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from config import FootballLeagueConfig
from src.collectors.betfair_web import BetfairWebClient
from src.db.migrations import run_sqlite_migrations
from src.db.models import AnalysisResult, Match, OddsSnapshot, PlayerLineup
from src.etl.daily import collect_fixtures_and_history
from src.time_utils import app_now, match_kickoff_is_expired


def _create_engine(path: Path):
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        run_sqlite_migrations(conn)
    return engine


def _espn_event(event_id: str, kickoff_at: datetime, home: str = "Home FC", away: str = "Away FC") -> dict:
    kickoff = kickoff_at.isoformat()
    return {
        "id": event_id,
        "date": kickoff,
        "league": {"id": "1", "name": "Liga"},
        "season": {"year": 2026},
        "competitions": [
            {
                "id": event_id,
                "date": kickoff,
                "status": {"type": {"description": "Scheduled", "shortDetail": "Agendado"}},
                "competitors": [
                    {"homeAway": "home", "id": f"{event_id}-home", "team": {"id": f"{event_id}-home", "displayName": home}},
                    {"homeAway": "away", "id": f"{event_id}-away", "team": {"id": f"{event_id}-away", "displayName": away}},
                ],
            }
        ],
    }


class MatchExpirationTests(unittest.TestCase):
    def test_kickoff_expires_after_two_hours(self) -> None:
        now = datetime(2026, 5, 17, 18, 0, 0)

        self.assertTrue(match_kickoff_is_expired(now - timedelta(hours=2), now))
        self.assertTrue(match_kickoff_is_expired(now - timedelta(hours=2, seconds=1), now))
        self.assertFalse(match_kickoff_is_expired(now - timedelta(hours=1, minutes=59), now))
        self.assertFalse(match_kickoff_is_expired(None, now))

    def test_timezone_aware_kickoff_is_compared_in_app_timezone(self) -> None:
        now = datetime(2026, 5, 17, 18, 0, 0)
        kickoff_utc = datetime(2026, 5, 17, 17, 0, 0, tzinfo=UTC)

        self.assertTrue(match_kickoff_is_expired(kickoff_utc, now))

    def test_betfair_targets_only_non_expired_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = _create_engine(Path(tmp) / "betsniper.db")
            try:
                with Session(engine) as session:
                    now = app_now()
                    session.add(
                        Match(
                            source="espn",
                            source_match_id="expired",
                            league_id=1,
                            league_name="Liga",
                            season=2026,
                            target_date=now.date().isoformat(),
                            kickoff_at=now - timedelta(hours=3),
                            home_team="Expired Home",
                            away_team="Expired Away",
                        )
                    )
                    session.add(
                        Match(
                            source="espn",
                            source_match_id="active",
                            league_id=1,
                            league_name="Liga",
                            season=2026,
                            target_date=now.date().isoformat(),
                            kickoff_at=now + timedelta(hours=1),
                            home_team="Active Home",
                            away_team="Active Away",
                        )
                    )
                    session.commit()

                    client = BetfairWebClient(session, now.date().isoformat(), "Liga")
                    matches = client._target_matches()

                    self.assertEqual([match.source_match_id for match in matches], ["active"])
            finally:
                engine.dispose()

    def test_espn_collection_discards_expired_fixture_and_cleans_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "betsniper.db"
            engine = _create_engine(db_path)
            try:
                now = app_now()
                stale_event = _espn_event("stale-1", now - timedelta(hours=3), "Old Home", "Old Away")
                fresh_event = _espn_event("fresh-1", now + timedelta(hours=1), "New Home", "New Away")

                with closing(sqlite3.connect(db_path)) as conn:
                    conn.execute(
                        """
                        INSERT INTO matches
                        (source, source_match_id, league_id, league_name, season, target_date, kickoff_at, home_team, away_team, created_at, updated_at)
                        VALUES ('espn', 'stale-1', 1, 'Liga', 2026, ?, ?, 'Old Home', 'Old Away', ?, ?)
                        """,
                        (
                            now.date().isoformat(),
                            (now - timedelta(hours=3)).isoformat(sep=" "),
                            now.isoformat(sep=" "),
                            now.isoformat(sep=" "),
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO analysis_results
                        (target_date, source_match_id, league_name, home_team, away_team, market_key, pick, score, sample_size, created_at)
                        VALUES (?, 'stale-1', 'Liga', 'Old Home', 'Old Away', 'over_25', 'over', 80.0, 10, ?)
                        """,
                        (now.date().isoformat(), now.isoformat(sep=" ")),
                    )
                    conn.execute(
                        """
                        INSERT INTO odds_snapshots
                        (source, source_match_id, bookmaker, market_key, outcome_name, price, fetched_at)
                        VALUES ('betfair-web', 'stale-1', 'Betfair', 'over_25', 'over', 2.0, ?)
                        """,
                        (now.isoformat(sep=" "),),
                    )
                    conn.execute(
                        """
                        INSERT INTO player_lineups
                        (source, source_match_id, player_name, team_name, starter, created_at)
                        VALUES ('espn', 'stale-1', 'Jogador', 'Old Home', 1, ?)
                        """,
                        (now.isoformat(sep=" "),),
                    )
                    conn.commit()

                league = FootballLeagueConfig("Liga", "BR", "test", 2026)
                with Session(engine) as session:
                    with patch("src.etl.daily.football_leagues", return_value=(league,)):
                        with patch("src.etl.daily.EspnClient") as client_type:
                            client_type.return_value.scoreboard_by_date.return_value = [stale_event, fresh_event]
                            with patch("src.etl.daily._store_espn_lineups"):
                                with patch("src.etl.daily._espn_all_competition_history", return_value=[]):
                                    matches = collect_fixtures_and_history(session, now.date().isoformat())

                    self.assertEqual([match.source_match_id for match in matches], ["fresh-1"])
                    self.assertIsNone(session.exec(select(Match).where(Match.source_match_id == "stale-1")).first())
                    self.assertIsNone(session.exec(select(AnalysisResult).where(AnalysisResult.source_match_id == "stale-1")).first())
                    self.assertIsNone(session.exec(select(OddsSnapshot).where(OddsSnapshot.source_match_id == "stale-1")).first())
                    self.assertIsNone(session.exec(select(PlayerLineup).where(PlayerLineup.source_match_id == "stale-1")).first())
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
