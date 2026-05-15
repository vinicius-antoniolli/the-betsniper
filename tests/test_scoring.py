from __future__ import annotations

import math
import unittest

from src.domain.scoring import expected_point_from_text, hit_score, line_hit, line_pick, score_parts


class ScoringTests(unittest.TestCase):
    def test_ou_mais_line_uses_half_point_threshold(self) -> None:
        self.assertEqual(expected_point_from_text("Jogador da 2 ou mais chutes no gol"), 1.5)

    def test_score_parts_counts_over_hits(self) -> None:
        self.assertEqual(score_parts([2, 1, 3], "Over", "1.5"), ("66.7", 2, 3, "valor > 1.5"))

    def test_line_pick_detects_portuguese_over_under(self) -> None:
        self.assertEqual(line_pick("2 ou mais"), "Over")
        self.assertEqual(line_pick("menos de 3"), "Under")

    def test_line_hit_handles_missing_values(self) -> None:
        self.assertIsNone(line_hit(math.nan, "Over", "1.5"))
        self.assertTrue(line_hit(2, "Over", "1.5"))
        self.assertFalse(line_hit(1, "Over", "1.5"))

    def test_hit_score(self) -> None:
        self.assertEqual(hit_score(3, 4), "75.0")
        self.assertEqual(hit_score(0, 0), "N/D")


if __name__ == "__main__":
    unittest.main()
