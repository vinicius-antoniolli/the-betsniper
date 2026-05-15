from __future__ import annotations

import unittest

from src.collectors.betfair_web import BetfairMatch, BetfairWebClient


class BetfairMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = BetfairWebClient.__new__(BetfairWebClient)

    def test_event_text_matches_reversed_home_away(self) -> None:
        match = BetfairMatch("1", "Vasco da Gama", "Paysandu", None)
        self.assertTrue(self.client._event_text_matches("Paysandu x Vasco da Gama", match))

    def test_event_text_matches_team_alias_tokens(self) -> None:
        match = BetfairMatch("1", "Ceará", "Atlético-MG", None)
        self.assertTrue(self.client._event_text_matches("Atlético-MG x Ceará", match))

    def test_event_url_detection_accepts_apostas_paths(self) -> None:
        self.assertTrue(
            self.client._looks_like_event_url(
                "https://www.betfair.bet.br/apostas/futebol/copa-do-brasil/palmeiras-x-jacuipense-ba/e-35516053"
            )
        )

    def test_home_team_goal_total_is_team_market(self) -> None:
        match = BetfairMatch("1", "Home FC", "Away FC", None)
        row = self.client._row_from_market_runner(
            {"name": "Home team over/under 0.5 goals", "marketType": "HOME_TEAM_OVER/UNDER_0.5_GOALS"},
            {"name": "Over", "handicap": 0.5},
            1.44,
            match,
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["market_key"], "teamtotals-goals-team1")
        self.assertEqual(row["team_name"], "Home FC")
        self.assertEqual(row["team_side"], "home")

    def test_match_goal_total_stays_game_market(self) -> None:
        self.assertEqual(self.client._market_key("Over/Under 2.5 Goals", "Over"), "totals")


if __name__ == "__main__":
    unittest.main()
