from __future__ import annotations

import unittest

from sqlmodel import Session, SQLModel, create_engine, select

from src.db.models import OddsSnapshot
from src.etl.helpers import insert_odds_snapshot


class OddsSnapshotTests(unittest.TestCase):
    def test_insert_materializes_raw_fields(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        raw = {
            "home_team": "Team A",
            "away_team": "Team B",
            "commence_time": "2026-05-12T20:00:00",
        }
        market = {
            "key": "betfair-player-shots-on-target",
            "name": "Player X da 2 ou mais chutes no gol",
            "player_prop": True,
            "outcomes": [
                {
                    "name": "Over",
                    "price": 2.7,
                    "point": 1.5,
                    "player_name": "Player X",
                    "team_name": "Team A",
                    "market_id": "m1",
                    "selection_id": "s1",
                }
            ],
        }

        with Session(engine) as session:
            insert_odds_snapshot(session, "match-1", "Betfair", market, raw)
            row = session.exec(select(OddsSnapshot)).one()

        self.assertEqual(row.raw_home_team, "Team A")
        self.assertEqual(row.raw_away_team, "Team B")
        self.assertEqual(row.market_name, "Player X da 2 ou mais chutes no gol")
        self.assertEqual(row.market_category, "player")
        self.assertEqual(row.player_name, "Player X")
        self.assertEqual(row.team_name, "Team A")
        self.assertEqual(row.market_id, "m1")
        self.assertEqual(row.selection_id, "s1")


if __name__ == "__main__":
    unittest.main()
