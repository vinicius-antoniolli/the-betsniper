from __future__ import annotations

from html import escape
from typing import Iterable

import pandas as pd
import streamlit as st


TAB_LABELS = {
    "Barbadas do Dia": "Barbadas do Dia",
    "Palpites": "Palpites",
    "Estatisticas dos Times": "Estatisticas dos Times",
    "Estatisticas jogadores": "Estatisticas jogadores",
}


CARBON_IFRAME_CSS = """
    :root {
      color-scheme: dark;
      --carbon-bg: #080b0d;
      --carbon-panel: #101519;
      --carbon-panel-2: #151d21;
      --carbon-line: rgba(218, 241, 233, 0.16);
      --carbon-line-strong: rgba(218, 241, 233, 0.28);
      --carbon-text: #f3f7f5;
      --carbon-soft: #d2ddd8;
      --carbon-muted: #91a19c;
      --carbon-green: #35d287;
      --carbon-lime: #b8ec5a;
      --carbon-cyan: #4cc7e8;
      --carbon-red: #ff6969;
    }

    html,
    body {
      background: transparent;
      color: var(--carbon-text);
      font-family: Inter, "Segoe UI", sans-serif;
      margin: 0;
      padding: 0;
    }

    .predictions-feed {
      display: grid;
      gap: 0.65rem;
    }

    .predictions-match,
    .predictions-section {
      background: linear-gradient(180deg, rgba(255,255,255,0.025), transparent), var(--carbon-panel);
      border: 1px solid var(--carbon-line);
      border-radius: 8px;
    }

    .predictions-section {
      background: var(--carbon-panel-2);
      margin-top: 0.55rem;
    }

    .predictions-match > summary,
    .predictions-section > summary {
      color: var(--carbon-text);
      cursor: pointer;
      font-weight: 750;
      list-style: none;
      padding: 0.58rem 0.7rem;
    }

    .predictions-match > summary::-webkit-details-marker,
    .predictions-section > summary::-webkit-details-marker {
      display: none;
    }

    .predictions-match > summary::before,
    .predictions-section > summary::before {
      color: var(--carbon-green);
      content: "[+] ";
    }

    .predictions-match[open] > summary::before,
    .predictions-section[open] > summary::before {
      content: "[-] ";
    }

    .predictions-body {
      padding: 0 0.7rem 0.7rem;
    }

    .predictions-grid {
      display: grid;
      gap: 0.55rem;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }

    .predictions-table-wrap {
      border: 1px solid var(--carbon-line);
      border-radius: 8px;
      max-height: none;
      overflow-x: auto;
      overflow-y: visible;
    }

    .predictions-table {
      border-collapse: collapse;
      font-size: 0.76rem;
      min-width: 800px;
      width: 100%;
    }

    .predictions-table th,
    .predictions-table td {
      border-bottom: 1px solid var(--carbon-line);
      border-right: 1px solid var(--carbon-line);
      overflow-wrap: anywhere;
      padding: 0.38rem 0.44rem;
      text-align: left;
      vertical-align: top;
      white-space: normal;
    }

    .predictions-table td:last-child,
    .predictions-table th:last-child {
      border-right: 0;
    }

    .predictions-table tr:last-child td {
      border-bottom: 0;
    }

    .predictions-table td.predictions-cell-reason {
      color: var(--carbon-soft);
      min-width: 280px;
      white-space: pre-line;
    }

    .predictions-table th {
      background: var(--carbon-panel-2);
      color: var(--carbon-muted);
      font-weight: 750;
      position: sticky;
      top: 0;
      white-space: nowrap;
      z-index: 1;
    }

    .predictions-sort-button {
      align-items: center;
      background: transparent;
      border: 0;
      color: inherit;
      cursor: pointer;
      display: inline-flex;
      font: inherit;
      gap: 0.25rem;
      justify-content: flex-start;
      padding: 0;
      width: 100%;
    }

    .predictions-sort-button:hover {
      color: var(--carbon-text);
    }

    .predictions-sort-indicator {
      color: var(--carbon-green);
      display: inline-block;
      min-width: 0.7rem;
    }

    .predictions-empty {
      color: var(--carbon-muted);
      font-size: 0.85rem;
      margin: 0.45rem 0 0;
    }

    @media (max-width: 1100px) {
      .predictions-grid {
        grid-template-columns: 1fr;
      }
    }
"""


def _fmt_int(value: int | float | str | None) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    return f"{number:,}".replace(",", ".")


def _safe_count(rows: pd.DataFrame | None) -> int:
    return 0 if rows is None or rows.empty else int(len(rows))


def _chip(label: str, kind: str = "") -> str:
    class_name = f"carbon-chip {kind}".strip()
    return f'<span class="{class_name}">{escape(label)}</span>'


def tab_display_label(tab: str) -> str:
    if "Time" in tab:
        return "Estatisticas dos Times"
    if "jogadores" in tab:
        return "Estatisticas jogadores"
    return TAB_LABELS.get(tab, tab)


def render_carbon_theme_css(toolbar_unlocked: bool) -> None:
    toolbar_display = "flex" if toolbar_unlocked else "none"
    st.markdown(
        f"""
        <style>
        :root {{
          --carbon-bg: #080b0d;
          --carbon-bg-2: #0d1215;
          --carbon-panel: #101519;
          --carbon-panel-2: #151d21;
          --carbon-panel-3: #1c282b;
          --carbon-line: rgba(218, 241, 233, 0.16);
          --carbon-line-strong: rgba(218, 241, 233, 0.30);
          --carbon-text: #f3f7f5;
          --carbon-soft: #d2ddd8;
          --carbon-muted: #91a19c;
          --carbon-green: #35d287;
          --carbon-lime: #b8ec5a;
          --carbon-cyan: #4cc7e8;
          --carbon-amber: #edbd4f;
          --carbon-red: #ff6969;
          --carbon-shadow: 0 22px 72px rgba(0, 0, 0, 0.42);
          --carbon-radius: 8px;
        }}

        .stApp {{
          background:
            linear-gradient(130deg, rgba(53, 210, 135, 0.075), transparent 34%),
            linear-gradient(310deg, rgba(76, 199, 232, 0.075), transparent 30%),
            var(--carbon-bg) !important;
          color: var(--carbon-text);
        }}

        [data-testid="stHeader"] {{
          background: transparent !important;
        }}

        [data-testid="stToolbar"] {{
          display: {toolbar_display} !important;
        }}

        [data-testid="stAppViewContainer"] .block-container {{
          max-width: 100%;
          padding: 1.1rem 1.25rem 2rem;
        }}

        .carbon-hero,
        .carbon-card,
        .st-key-carbon_left_panel,
        .st-key-carbon_main_panel,
        .st-key-carbon_right_panel,
        .st-key-carbon_nav_panel {{
          background: linear-gradient(180deg, rgba(255,255,255,0.025), transparent), var(--carbon-panel);
          border: 1px solid var(--carbon-line);
          border-radius: var(--carbon-radius);
          box-shadow: var(--carbon-shadow);
        }}

        .carbon-hero {{
          display: grid;
          grid-template-columns: minmax(0, 1fr) 520px;
          gap: 0.9rem;
          margin-bottom: 0.85rem;
          padding: 1rem 1.05rem;
        }}

        .carbon-kicker {{
          align-items: center;
          color: var(--carbon-green);
          display: inline-flex;
          font-size: 0.76rem;
          font-weight: 850;
          gap: 0.45rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }}

        .carbon-dot {{
          background: var(--carbon-green);
          border-radius: 999px;
          box-shadow: 0 0 0 4px rgba(53, 210, 135, 0.14);
          display: inline-block;
          height: 0.5rem;
          width: 0.5rem;
        }}

        .carbon-title {{
          color: var(--carbon-text);
          font-size: clamp(1.7rem, 2.4vw, 2.25rem);
          font-weight: 850;
          letter-spacing: 0;
          line-height: 1.05;
          margin-top: 0.45rem;
        }}

        .carbon-summary {{
          color: var(--carbon-muted);
          font-size: 0.98rem;
          line-height: 1.45;
          margin-top: 0.55rem;
          max-width: 900px;
        }}

        .carbon-metrics {{
          display: grid;
          gap: 0.65rem;
          grid-template-columns: repeat(4, minmax(0, 1fr));
        }}

        .carbon-metric {{
          background: var(--carbon-panel-2);
          border: 1px solid var(--carbon-line);
          border-radius: var(--carbon-radius);
          min-height: 6.3rem;
          padding: 0.75rem;
        }}

        .carbon-metric-label,
        .carbon-card-label {{
          color: var(--carbon-muted);
          font-size: 0.76rem;
        }}

        .carbon-metric-value {{
          color: var(--carbon-text);
          font-size: 1.65rem;
          font-weight: 850;
          line-height: 1.05;
          margin-top: 0.32rem;
        }}

        .carbon-metric-detail {{
          color: var(--carbon-muted);
          font-size: 0.72rem;
          margin-top: 0.45rem;
        }}

        .carbon-filterbar,
        .carbon-legend {{
          display: grid;
          gap: 0.55rem;
          margin-bottom: 0.85rem;
        }}

        .carbon-filterbar {{
          background: var(--carbon-panel);
          border: 1px solid var(--carbon-line);
          border-radius: var(--carbon-radius);
          grid-template-columns: 190px 190px 210px minmax(220px, 1fr);
          padding: 0.75rem;
        }}

        .carbon-filter {{
          background: var(--carbon-panel-2);
          border: 1px solid var(--carbon-line-strong);
          border-radius: 7px;
          color: var(--carbon-soft);
          font-size: 0.8rem;
          min-height: 2.2rem;
          padding: 0.55rem 0.7rem;
        }}

        .carbon-legend {{
          grid-template-columns: repeat(5, minmax(0, 1fr));
        }}

        .carbon-card {{
          min-height: 4.8rem;
          padding: 0.75rem;
        }}

        .carbon-card strong {{
          color: var(--carbon-text);
          display: block;
          font-size: 1.18rem;
          margin-top: 0.22rem;
        }}

        .carbon-card span {{
          color: var(--carbon-muted);
          display: block;
          font-size: 0.72rem;
          margin-top: 0.2rem;
        }}

        .st-key-carbon_left_panel,
        .st-key-carbon_main_panel,
        .st-key-carbon_right_panel,
        .st-key-carbon_nav_panel {{
          padding: 0.85rem;
        }}

        .carbon-panel-kicker {{
          color: var(--carbon-green);
          font-size: 0.75rem;
          font-weight: 850;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }}

        .carbon-panel-title {{
          color: var(--carbon-text);
          font-size: 1.25rem;
          font-weight: 850;
          line-height: 1.15;
          margin-top: 0.25rem;
        }}

        .carbon-panel-copy {{
          color: var(--carbon-muted);
          font-size: 0.86rem;
          line-height: 1.45;
          margin: 0.3rem 0 0.75rem;
        }}

        .carbon-presets {{
          display: grid;
          gap: 0.45rem;
          margin-top: 0.8rem;
        }}

        .carbon-preset {{
          align-items: center;
          border: 1px solid transparent;
          border-radius: 7px;
          color: var(--carbon-soft);
          display: flex;
          font-size: 0.82rem;
          font-weight: 700;
          justify-content: space-between;
          padding: 0.55rem 0.62rem;
        }}

        .carbon-preset.active {{
          background: var(--carbon-panel-2);
          border-color: var(--carbon-line-strong);
          color: var(--carbon-text);
        }}

        .carbon-preset-count {{
          color: var(--carbon-muted);
          font-variant-numeric: tabular-nums;
        }}

        .carbon-state-list {{
          display: grid;
          gap: 0.5rem;
          margin-top: 0.8rem;
        }}

        .carbon-state {{
          background: var(--carbon-panel-2);
          border: 1px solid var(--carbon-line);
          border-radius: 7px;
          color: var(--carbon-soft);
          font-size: 0.78rem;
          padding: 0.58rem 0.65rem;
        }}

        .carbon-state b {{
          color: var(--carbon-text);
          display: block;
          margin-bottom: 0.15rem;
        }}

        .carbon-chip {{
          align-items: center;
          background: var(--carbon-panel-2);
          border: 1px solid var(--carbon-line);
          border-radius: 999px;
          color: var(--carbon-soft);
          display: inline-flex;
          font-size: 0.76rem;
          gap: 0.35rem;
          min-height: 1.65rem;
          padding: 0.32rem 0.65rem;
        }}

        .carbon-chip.good {{
          background: rgba(53, 210, 135, 0.12);
          border-color: rgba(53, 210, 135, 0.58);
          color: var(--carbon-text);
        }}

        .carbon-chip.warn {{
          background: rgba(237, 189, 79, 0.12);
          border-color: rgba(237, 189, 79, 0.58);
          color: #ffe2a4;
        }}

        .carbon-chip.bad {{
          background: rgba(255, 105, 105, 0.12);
          border-color: rgba(255, 105, 105, 0.58);
          color: #ffc6c6;
        }}

        .carbon-chip-row {{
          display: flex;
          flex-wrap: wrap;
          gap: 0.45rem;
          margin: 0.5rem 0 0.8rem;
        }}

        div[data-testid="stSegmentedControl"] {{
          background: var(--carbon-panel);
          border: 1px solid var(--carbon-line);
          border-radius: var(--carbon-radius);
          margin-bottom: 0.85rem;
          padding: 0.55rem;
        }}

        div[data-testid="stSegmentedControl"] label {{
          color: var(--carbon-soft) !important;
        }}

        div[data-testid="stSegmentedControl"] [aria-checked="true"],
        div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {{
          border-color: rgba(53, 210, 135, 0.6) !important;
          color: var(--carbon-text) !important;
        }}

        div[data-testid="stExpander"] {{
          background: var(--carbon-panel);
          border: 1px solid var(--carbon-line) !important;
          border-radius: var(--carbon-radius) !important;
          box-shadow: none;
        }}

        div[data-testid="stExpander"] summary {{
          color: var(--carbon-text);
          font-weight: 800;
        }}

        div[data-testid="stDataFrame"],
        div[data-testid="stIFrame"] {{
          border-radius: var(--carbon-radius);
        }}

        .stDataFrame [data-testid="stTable"] {{
          color: var(--carbon-text);
        }}

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] button {{
          background: var(--carbon-panel-2);
          border: 1px solid var(--carbon-line-strong);
          border-radius: 7px;
          color: var(--carbon-text);
          font-weight: 750;
        }}

        .stButton > button[kind="primary"],
        .stButton > button:hover,
        [data-testid="stFormSubmitButton"] button:hover {{
          border-color: rgba(53, 210, 135, 0.65);
          color: var(--carbon-text);
        }}

        .st-key-x_publish_unlock_slot button,
        .st-key-x_publish_unlock_button button {{
          background: var(--carbon-panel-2) !important;
          border: 1px solid rgba(53, 210, 135, 0.62) !important;
          border-radius: 7px !important;
          color: var(--carbon-text) !important;
          min-height: 1.9rem !important;
        }}

        .team-stats-team,
        .team-stats-split details,
        .predictions-match,
        .predictions-section {{
          background: var(--carbon-panel) !important;
          border-color: var(--carbon-line) !important;
          border-radius: var(--carbon-radius) !important;
        }}

        .team-stats-table,
        .predictions-table {{
          color: var(--carbon-text);
          font-size: 0.76rem;
        }}

        .team-stats-table th,
        .predictions-table th {{
          background: var(--carbon-panel-2) !important;
          color: var(--carbon-muted) !important;
        }}

        .team-stats-table td,
        .predictions-table td {{
          border-color: var(--carbon-line) !important;
          color: var(--carbon-soft);
        }}

        @media (max-width: 1200px) {{
          .carbon-hero,
          .carbon-filterbar,
          .carbon-legend {{
            grid-template-columns: 1fr;
          }}

          .carbon-metrics {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(
    *,
    active_tab: str,
    palpites: int,
    jogos: int,
    odds_snapshots: int,
    odds_stale: int,
) -> None:
    stale_kind = "warn" if odds_stale else "good"
    html = f"""
    <section class="carbon-hero">
      <div>
        <div class="carbon-kicker"><span class="carbon-dot"></span>Carbon Exchange | Front-end ativo</div>
        <div class="carbon-title">Data Grid Pro - {escape(tab_display_label(active_tab))}</div>
        <div class="carbon-summary">
          Interface densa para odds, scores, mercados, motivos, estatisticas e publicacao X.
          A camada visual foi trocada; a coleta, o scoring e as integracoes continuam nas funcoes existentes.
        </div>
        <div class="carbon-chip-row">
          {_chip("Hoje", "good")}
          {_chip("Amanha")}
          {_chip(f"Odds stale {odds_stale}", stale_kind)}
          {_chip("X conectado" if st.session_state.get("x_publish_unlocked") else "X bloqueado", "good" if st.session_state.get("x_publish_unlocked") else "warn")}
        </div>
      </div>
      <div class="carbon-metrics">
        <div class="carbon-metric"><div class="carbon-metric-label">Palpites</div><div class="carbon-metric-value">{_fmt_int(palpites)}</div><div class="carbon-metric-detail">linhas scoreadas</div></div>
        <div class="carbon-metric"><div class="carbon-metric-label">Jogos</div><div class="carbon-metric-value">{_fmt_int(jogos)}</div><div class="carbon-metric-detail">Hoje + Amanha</div></div>
        <div class="carbon-metric"><div class="carbon-metric-label">Odds</div><div class="carbon-metric-value">{_fmt_int(odds_snapshots)}</div><div class="carbon-metric-detail">snapshots Betfair</div></div>
        <div class="carbon-metric"><div class="carbon-metric-label">Score min</div><div class="carbon-metric-value">75</div><div class="carbon-metric-detail">Barbadas do Dia</div></div>
      </div>
    </section>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_filterbar(active_tab: str) -> None:
    if "jogadores" in active_tab:
        type_filter = "Tipo: Jogador"
        market_filter = "Mercado: props + historico"
    elif "Time" in active_tab:
        type_filter = "Tipo: Times"
        market_filter = "Grupo: historico ESPN"
    elif active_tab == "Palpites":
        type_filter = "Tipo: Jogo + Time + Jogador"
        market_filter = "Mercado: todos"
    else:
        type_filter = "Tipo: todos"
        market_filter = "Mercado: Score >= 75"
    st.markdown(
        f"""
        <section class="carbon-filterbar">
          <div class="carbon-filter">Data: Hoje + Amanha</div>
          <div class="carbon-filter">{escape(type_filter)}</div>
          <div class="carbon-filter">{escape(market_filter)}</div>
          <div class="carbon-filter">Busca: use ordenacao, expansores e tabelas atuais</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_legend(items: Iterable[tuple[str, str, str]]) -> None:
    cards = []
    for label, value, detail in items:
        cards.append(
            '<div class="carbon-card">'
            f'<div class="carbon-card-label">{escape(label)}</div>'
            f"<strong>{escape(value)}</strong>"
            f"<span>{escape(detail)}</span>"
            "</div>"
        )
    st.markdown(f'<section class="carbon-legend">{"".join(cards)}</section>', unsafe_allow_html=True)


def render_sidebar(active_tab: str, counts: dict[str, int], odds_stale: int) -> None:
    presets = []
    for tab, count in counts.items():
        active = " active" if tab == active_tab else ""
        presets.append(
            f'<div class="carbon-preset{active}">'
            f"<span>{escape(tab_display_label(tab))}</span>"
            f'<span class="carbon-preset-count">{_fmt_int(count)}</span>'
            "</div>"
        )
    stale_text = f"{odds_stale} odds stale" if odds_stale else "odds frescas"
    st.markdown(
        f"""
        <div class="carbon-panel-kicker">Abas refatoradas</div>
        <div class="carbon-panel-title">Presets</div>
        <div class="carbon-presets">{"".join(presets)}</div>
        <div class="carbon-panel-kicker" style="margin-top:1rem">Estados</div>
        <div class="carbon-state-list">
          <div class="carbon-state"><b>Hoje/Amanha</b>expansores conectados ao filtro de data atual</div>
          <div class="carbon-state"><b>{escape(stale_text)}</b>mesma regra ODDS_STALE_AFTER_HOURS</div>
          <div class="carbon-state"><b>N/D preservado</b>sem odds, scores ou historico nao sao descartados</div>
          <div class="carbon-state"><b>X</b>login, senha, publicar todas e publicar individual</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_detail_panel(active_tab: str, items: Iterable[tuple[str, str, str]]) -> None:
    rows = []
    for label, value, kind in items:
        safe_kind = "good" if kind == "good" else "warn" if kind == "warn" else "bad" if kind == "bad" else ""
        rows.append(
            '<div class="carbon-state">'
            f"<b>{escape(label)}</b>"
            f'<span class="carbon-chip {safe_kind}">{escape(value)}</span>'
            "</div>"
        )
    st.markdown(
        f"""
        <div class="carbon-panel-kicker">Detalhe lateral</div>
        <div class="carbon-panel-title">{escape(tab_display_label(active_tab))}</div>
        <div class="carbon-panel-copy">Motivos, estatisticas, X e diagnostico continuam acessiveis no fluxo atual.</div>
        <div class="carbon-state-list">{"".join(rows)}</div>
        """,
        unsafe_allow_html=True,
    )


def render_main_heading(active_tab: str, summary: str) -> None:
    st.markdown(
        f"""
        <div class="carbon-panel-kicker">Grid mestre</div>
        <div class="carbon-panel-title">{escape(tab_display_label(active_tab))}</div>
        <div class="carbon-panel-copy">{escape(summary)}</div>
        """,
        unsafe_allow_html=True,
    )


def day_legend(rows: pd.DataFrame, column: str) -> list[tuple[str, str, str]]:
    if rows.empty or column not in rows.columns:
        return [("Hoje", "0", "sem dados"), ("Amanha", "0", "sem dados")]
    output = []
    labels = [("Hoje", 0), ("Amanha", 1)]
    dates = list(dict.fromkeys(rows[column].astype(str).tolist()))
    for label, offset in labels:
        date_value = dates[offset] if offset < len(dates) else ""
        count = int((rows[column].astype(str) == date_value).sum()) if date_value else 0
        output.append((label, _fmt_int(count), "linhas no fluxo"))
    return output


def best_bet_detail_items(rows: pd.DataFrame, x_unlocked: bool, odds_stale: int) -> list[tuple[str, str, str]]:
    total = _safe_count(rows)
    groups = {}
    if not rows.empty and "Tipo" in rows.columns:
        groups = rows["Tipo"].astype(str).value_counts().to_dict()
    return [
        ("Linhas", _fmt_int(total), "good" if total else "warn"),
        ("Jogos", _fmt_int(groups.get("Jogo", 0)), "good"),
        ("Times", _fmt_int(groups.get("Time", 0)), "good"),
        ("Jogadores", _fmt_int(groups.get("Jogador", 0)), "good"),
        ("Publicacao X", "liberada" if x_unlocked else "bloqueada", "good" if x_unlocked else "warn"),
        ("Odds stale", _fmt_int(odds_stale), "warn" if odds_stale else "good"),
    ]


def generic_detail_items(rows: pd.DataFrame, label: str, odds_stale: int = 0) -> list[tuple[str, str, str]]:
    return [
        (label, _fmt_int(_safe_count(rows)), "good" if _safe_count(rows) else "warn"),
        ("Hoje/Amanha", "ativo", "good"),
        ("Estados vazios", "preservados", "good"),
        ("Odds stale", _fmt_int(odds_stale), "warn" if odds_stale else "good"),
    ]
