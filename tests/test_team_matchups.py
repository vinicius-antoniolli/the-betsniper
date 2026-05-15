from __future__ import annotations

import unittest

import pandas as pd

from src.domain import team_matchups


class TeamMatchupTests(unittest.TestCase):
    def test_matchup_score_combines_pick_team_and_opponent_support(self) -> None:
        team_rows = pd.DataFrame(
            [
                {"source": "espn", "shots_on_target_for": 5, "shots_on_target_against": 2},
                {"source": "espn", "shots_on_target_for": 4, "shots_on_target_against": 1},
                {"source": "espn", "shots_on_target_for": 1, "shots_on_target_against": 3},
            ]
        )
        opponent_rows = pd.DataFrame(
            [
                {"source": "espn", "shots_on_target_for": 1, "shots_on_target_against": 4},
                {"source": "espn", "shots_on_target_for": 2, "shots_on_target_against": 6},
                {"source": "espn", "shots_on_target_for": 7, "shots_on_target_against": 2},
            ]
        )

        result = team_matchups.matchup_score(
            team_rows,
            lambda row: team_matchups.greater_than(row, "shots_on_target_for", "shots_on_target_against"),
            opponent_rows,
            lambda row: team_matchups.less_than(row, "shots_on_target_for", "shots_on_target_against"),
            min_samples=3,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.score, "66.7")
        self.assertEqual((result.team_hits, result.team_total), (2, 3))
        self.assertEqual((result.opponent_hits, result.opponent_total), (2, 3))
        self.assertEqual(result.sources, frozenset({"espn"}))

    def test_matchup_score_requires_samples_on_both_sides(self) -> None:
        rows = pd.DataFrame([{"source": "espn", "corners_for": 5, "corners_against": 2}])

        result = team_matchups.matchup_score(
            rows,
            lambda row: team_matchups.greater_than(row, "corners_for", "corners_against"),
            rows,
            lambda row: team_matchups.less_than(row, "corners_for", "corners_against"),
            min_samples=3,
        )

        self.assertIsNone(result)

    def test_half_and_lead_predicates_use_opponent_perspective(self) -> None:
        row = pd.Series(
            {
                "first_half_goals_for": 0,
                "first_half_goals_against": 1,
                "goals_for": 2,
                "goals_against": 1,
            }
        )

        self.assertTrue(team_matchups.won_any_half(row))
        self.assertTrue(team_matchups.lost_any_half(row))
        self.assertTrue(team_matchups.led_at_half_or_won_match(row))
        self.assertTrue(team_matchups.trailed_at_half_or_lost_match(row))

    def test_goal_handicap_opponent_support_uses_inverse_margin(self) -> None:
        selected = pd.Series({"goals_for": 3, "goals_against": 1})
        opponent = pd.Series({"goals_for": 0, "goals_against": 2})

        self.assertTrue(team_matchups.covers_goal_handicap(selected, -1.5))
        self.assertTrue(team_matchups.opponent_supports_goal_handicap(opponent, -1.5))


if __name__ == "__main__":
    unittest.main()
