from __future__ import annotations

import unittest

import pandas as pd

from src.domain.x_posts import build_best_bet_x_posts


class XPostDraftTests(unittest.TestCase):
    def test_builds_one_post_per_bet_line(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "_source_match_id": "m1",
                    "Data": "14/05 - 21:30",
                    "Liga": "Copa Betano do Brasil",
                    "Casa": "Vitória",
                    "Fora": "Flamengo",
                    "Tipo": "Time",
                    "Time": "Vitória",
                    "Jogador": "",
                    "Mercado": "Time com mais chutes no gol",
                    "Pick": "Vitória",
                    "Linha": "",
                    "ODD": "4.33",
                    "Score": "100",
                    "Motivo": (
                        "Fonte: ESPN | Filtro: jogos como mandante | Criterio: mais chutes no gol | "
                        "Vitória - Acertos 7/7"
                    ),
                },
                {
                    "_source_match_id": "m1",
                    "Data": "14/05",
                    "Liga": "Serie A",
                    "Casa": "Casa FC",
                    "Fora": "Fora FC",
                    "Tipo": "Jogador",
                    "Time": "Casa FC",
                    "Jogador": "Atacante",
                    "Mercado": "Finalizacoes",
                    "Pick": "Over",
                    "Linha": "0.5",
                    "ODD": 1.7,
                    "Score": 75,
                    "Motivo": "Fonte: ESPN | Criterio: finalizacoes | Atacante - Acertos 5/7",
                },
                {
                    "_source_match_id": "m2",
                    "Data": "14/05",
                    "Liga": "Serie A",
                    "Casa": "Outro",
                    "Fora": "Rival",
                    "Tipo": "Time",
                    "Time": "Outro",
                    "Jogador": "",
                    "Mercado": "Escanteios",
                    "Pick": "Over",
                    "Linha": "4.5",
                    "ODD": 1.9,
                    "Score": 90,
                    "Motivo": "Fonte: ESPN | Filtro: jogos como mandante | Outro - Acertos 6/7",
                },
            ]
        )

        drafts = build_best_bet_x_posts(rows)

        self.assertEqual(len(drafts), 3)
        self.assertEqual(
            drafts[0].text,
            "\n".join(
                [
                    "🔴⚫ Vitória x Flamengo 🔴⚫",
                    "",
                    "14/05 - 21:30 - Copa Betano do Brasil",
                    "",
                    "Time com mais chutes no gol - VITÓRIA - ODD - 4.33",
                    "",
                    "Motivo: jogos como mandante | Vitória - Acertos 7/7 (100%)",
                ]
            ),
        )
        self.assertNotIn("Barbadas do Dia", drafts[0].text)
        self.assertNotIn("Atacante Finalizacoes", drafts[0].text)
        self.assertIn("Finalizacoes - ATACANTE OVER 0.5 - ODD - 1.70", drafts[1].text)
        self.assertIn("Motivo: Atacante - Acertos 5/7 (71.4%)", drafts[1].text)
        self.assertEqual(drafts[0].market_count, 1)

    def test_compact_fallback_keeps_post_under_limit(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "_source_match_id": "m1",
                    "Data": "14/05 - 21:30",
                    "Liga": "Liga Muito Longa Para Teste",
                    "Casa": "Clube Mandante Com Nome Muito Grande",
                    "Fora": "Clube Visitante Com Nome Muito Grande",
                    "Tipo": "Jogador",
                    "Time": "Clube Mandante Com Nome Muito Grande",
                    "Jogador": "Jogador Com Nome Muito Grande",
                    "Mercado": "Mercado Muito Longo Sem Abreviacao Configurada",
                    "Pick": "Selecao Muito Longa Sem Abreviacao",
                    "Linha": "123.5",
                    "ODD": "1.80",
                    "Score": "80",
                    "Motivo": (
                        "Fonte: ESPN | Filtro: jogos como mandante | Criterio: criterio muito longo | "
                        "Jogador Com Nome Muito Grande - Acertos 4/5"
                    ),
                },
            ]
        )

        drafts = build_best_bet_x_posts(rows, max_chars=120)

        self.assertEqual(len(drafts), 1)
        self.assertLessEqual(drafts[0].char_count, 120)

    def test_empty_rows_return_no_posts(self) -> None:
        self.assertEqual(build_best_bet_x_posts(pd.DataFrame()), [])


if __name__ == "__main__":
    unittest.main()
