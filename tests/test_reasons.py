from __future__ import annotations

import math
import unittest

from src.domain.reasons import clean_reason_for_display, format_hits_with_samples


class ReasonDisplayTests(unittest.TestCase):
    def test_removes_criterion_from_reason(self) -> None:
        reason = (
            "Criterio: gols totais entre 2-6 | "
            "Chapecoense (mandante) - Acertos 7/8 | "
            "Botafogo (visitante) - Acertos 8/10"
        )

        self.assertEqual(
            clean_reason_for_display(reason),
            "Chapecoense (mandante) - Acertos 7/8\nBotafogo (visitante) - Acertos 8/10",
        )

    def test_removes_espn_source_and_accented_criterion(self) -> None:
        reason = "Fonte: ESPN | Filtro: jogos como mandante | Crit\u00e9rio: chutes | Vitoria - Acertos 7/7"

        self.assertEqual(
            clean_reason_for_display(reason),
            "Filtro: jogos como mandante | Vitoria - Acertos 7/7",
        )

    def test_breaks_long_two_team_reason_lines(self) -> None:
        reason = (
            "Fonte: ESPN | Criterio: BTTS | "
            "Aston Villa (mandante) - Acertos 7/10 [ 4-0 - 1-2 ] | "
            "Liverpool (visitante) - Acertos 6/10 [ 3-2 - 1-2 ]"
        )

        self.assertEqual(
            clean_reason_for_display(reason),
            (
                "Aston Villa (mandante) - Acertos 7/10 [ 4-0 - 1-2 ]\n"
                "Liverpool (visitante) - Acertos 6/10 [ 3-2 - 1-2 ]"
            ),
        )

    def test_keeps_missing_value(self) -> None:
        self.assertTrue(math.isnan(clean_reason_for_display(math.nan)))

    def test_formats_hits_with_sample_values(self) -> None:
        self.assertEqual(
            format_hits_with_samples(5, 5, [2, 1.0, 1.5, "0-0"]),
            "Acertos 5/5 [ 2 - 1 - 1.5 - 0-0 ]",
        )


if __name__ == "__main__":
    unittest.main()
