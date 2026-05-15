from __future__ import annotations

import math
import unittest

from src.domain.reasons import clean_reason_for_display


class ReasonDisplayTests(unittest.TestCase):
    def test_removes_criterion_from_reason(self) -> None:
        reason = (
            "Criterio: gols totais entre 2-6 | "
            "Chapecoense (mandante) - Acertos 7/8 | "
            "Botafogo (visitante) - Acertos 8/10"
        )

        self.assertEqual(
            clean_reason_for_display(reason),
            "Chapecoense (mandante) - Acertos 7/8 | Botafogo (visitante) - Acertos 8/10",
        )

    def test_removes_espn_source_and_accented_criterion(self) -> None:
        reason = "Fonte: ESPN | Filtro: jogos como mandante | Crit\u00e9rio: chutes | Vitoria - Acertos 7/7"

        self.assertEqual(
            clean_reason_for_display(reason),
            "Filtro: jogos como mandante | Vitoria - Acertos 7/7",
        )

    def test_keeps_missing_value(self) -> None:
        self.assertTrue(math.isnan(clean_reason_for_display(math.nan)))


if __name__ == "__main__":
    unittest.main()
