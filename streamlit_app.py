from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PUBLIC_DB = ROOT_DIR / "public_data" / "betsniper_public.db"

# os.environ["PUBLIC_VIEWER_MODE"] = "true"
# os.environ["BETFAIR_WEB_ENABLED"] = "false"
# os.environ["X_AUTO_PUBLISH_ENABLED"] = "false"

if PUBLIC_DB.exists():
    os.environ.setdefault("APP_DB_URL", "sqlite:///public_data/betsniper_public.db")


import hashlib
import hmac
import json
import logging
import re
from base64 import b64encode
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any
from unicodedata import normalize
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.dashboard.carbon_ui import (
    CARBON_IFRAME_CSS,
    render_carbon_theme_css,
    render_filterbar,
    render_header,
    render_legend,
    render_main_heading,
)
from config import ROOT_DIR, ensure_runtime_dirs, settings
from src.dashboard.data import read_sql_frame
from src.db.session import init_db, sqlite_db_path
from src.domain import scoring as score_logic
from src.domain import team_matchups as matchup_logic
from src.domain.reasons import clean_reason_for_display, format_hits_with_samples, format_sample_value
from src.domain.x_posts import XPostDraft, build_best_bet_x_posts
from src.integrations.x_api import XCredentials, XPostError, publish_x_posts


ensure_runtime_dirs()
if not settings.public_viewer_mode:
    init_db()
DB_PATH = sqlite_db_path()
log = logging.getLogger(__name__)


def _rooted_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def _public_snapshot_base_date() -> str | None:
    if not settings.public_viewer_mode:
        return None
    metadata_path = _rooted_path(settings.public_snapshot_metadata)
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    base_date = str(payload.get("base_date") or "").strip()
    if not base_date:
        return None
    try:
        datetime.fromisoformat(base_date)
    except ValueError:
        return None
    return base_date


def dashboard_base_date():
    if settings.dashboard_base_date:
        try:
            return datetime.fromisoformat(settings.dashboard_base_date).date()
        except ValueError:
            log.warning("DASHBOARD_BASE_DATE invalido: %s", settings.dashboard_base_date)
    public_base_date = _public_snapshot_base_date()
    if public_base_date:
        return datetime.fromisoformat(public_base_date).date()
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


BASE_DATE = dashboard_base_date()
TODAY_DATE = BASE_DATE.isoformat()
TOMORROW_DATE = (BASE_DATE + timedelta(days=1)).isoformat()
X_PUBLISH_UNLOCKED_KEY = "x_publish_unlocked"
X_PUBLISH_UNLOCK_REQUESTED_KEY = "x_publish_unlock_requested"
X_PUBLISH_PASSWORD_INPUT_KEY = "x_publish_password_input"


def is_x_publish_unlocked() -> bool:
    return bool(st.session_state.get(X_PUBLISH_UNLOCKED_KEY))


def ensure_x_publish_unlocked() -> bool:
    if is_x_publish_unlocked():
        return True
    st.error("Publicacao no X bloqueada. Libere com a senha antes de publicar.")
    return False


def render_x_publish_unlock_control() -> None:
    if is_x_publish_unlocked():
        return

    with st.container(key="x_publish_unlock_slot"):
        if st.button("Login", key="x_publish_unlock_button"):
            st.session_state[X_PUBLISH_UNLOCK_REQUESTED_KEY] = True

    if not st.session_state.get(X_PUBLISH_UNLOCK_REQUESTED_KEY):
        return

    with st.form("x_publish_unlock_form", clear_on_submit=False):
        password = st.text_input(
            "Senha para liberar publicacao no X",
            type="password",
            key=X_PUBLISH_PASSWORD_INPUT_KEY,
        )
        submitted = st.form_submit_button("Liberar X")

    if not submitted:
        return

    configured_password = settings.x_publish_password or ""
    if not configured_password:
        st.error("Configure X_PUBLISH_PASSWORD no .env para liberar publicacao no X.")
        return
    if hmac.compare_digest(password or "", configured_password):
        st.session_state[X_PUBLISH_UNLOCKED_KEY] = True
        st.session_state[X_PUBLISH_UNLOCK_REQUESTED_KEY] = False
        st.rerun()
        return

    st.error("Senha incorreta.")

DASHBOARD_DAYS = ((TODAY_DATE, "Hoje"), (TOMORROW_DATE, "Amanhã"))


def render_x_publish_auth_css() -> None:
    toolbar_display = "flex" if is_x_publish_unlocked() else "none"
    st.markdown(
        f"""
        <style>
        [data-testid="stToolbar"] {{
          display: {toolbar_display} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Betsniper", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
      height: auto;
    }

    [data-testid="stAppViewContainer"] > .main {
      height: auto;
    }

    [data-testid="stAppViewContainer"] .block-container {
      height: auto;
      max-height: none;
      overflow-y: visible;
      overflow-x: hidden;
      padding-top: 0.75rem;
      padding-bottom: 2rem;
    }

    [data-testid="stElementContainer"]:has(h1) {
      position: sticky;
      top: 0;
      z-index: 1003;
      background: rgb(14, 17, 23);
      padding-top: 0.25rem;
    }

    [data-testid="stElementContainer"]:has(.st-key-x_publish_unlock_slot) {
      height: 1.75rem;
      margin: 0;
      overflow: visible;
      position: relative;
      z-index: 1000001;
    }

    .st-key-x_publish_unlock_slot {
      height: 1.75rem;
      overflow: visible;
      position: relative;
      z-index: 1000001;
    }

    .st-key-x_publish_unlock_slot button,
    .st-key-x_publish_unlock_button button {
      width: 8rem;
      min-height: 1.75rem;
      height: 1.75rem;
      padding: 0;
      border: 1px solid rgba(255, 255, 255, 0.5);
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.1);
      color: white;
      font-size: 0.8rem;
      position: relative;
      z-index: 1000002;
    }

    .st-key-x_publish_unlock_slot button:hover,
    .st-key-x_publish_unlock_slot button:focus,
    .st-key-x_publish_unlock_button button:hover,
    .st-key-x_publish_unlock_button button:focus {
      background: rgba(255, 255, 255, 0.2);
      border-color: white;
    }

    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
      position: sticky;
      top: 58px;
      z-index: 1002;
      background: rgb(14, 17, 23);
      padding: 0.25rem 0 0.75rem;
    }

    [data-testid="stTabs"] [data-baseweb="tab-list"] {
      position: sticky;
      top: 143px;
      z-index: 1001;
      background: rgb(14, 17, 23);
      border-bottom: 1px solid rgba(250, 250, 250, 0.16);
    }

    [data-testid="stTabs"] [role="tabpanel"] {
      height: auto;
      overflow-y: visible;
      overflow-x: hidden;
      padding-right: 0.5rem;
      padding-bottom: 2rem;
    }

    header[data-testid="stHeader"] {
      background: transparent;
    }

    .team-stats-match-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 0.75rem;
      align-items: start;
    }

    .team-stats-team,
    .team-stats-split details {
      border: 1px solid rgba(250, 250, 250, 0.18);
      border-radius: 0.45rem;
      margin: 0.35rem 0;
      background: rgb(14, 17, 23);
    }

    .team-stats-team > summary,
    .team-stats-split summary {
      cursor: pointer;
      font-weight: 700;
      padding: 0.5rem 0.65rem;
      text-align: center;
      list-style: none;
    }

    .team-stats-team > summary::-webkit-details-marker,
    .team-stats-split summary::-webkit-details-marker {
      display: none;
    }

    .team-stats-team > summary::before,
    .team-stats-split summary::before {
      content: "[+] ";
    }

    .team-stats-team[open] > summary::before,
    .team-stats-split details[open] > summary::before {
      content: "[-] ";
    }

    .team-stats-body {
      padding: 0 0.55rem 0.55rem;
      overflow-x: auto;
    }

    .team-stats-split {
      display: grid;
      grid-template-columns: 1fr;
      gap: 0.35rem;
    }

    .team-stats-table {
      width: 100%;
      min-width: 860px;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 0.78rem;
    }

    .team-stats-table th,
    .team-stats-table td {
      border: 1px solid rgba(250, 250, 250, 0.12);
      padding: 0.32rem 0.38rem;
      white-space: normal;
      overflow-wrap: anywhere;
      vertical-align: middle;
    }

    .team-stats-table th {
      color: rgba(250, 250, 250, 0.72);
      font-weight: 500;
      background: rgba(250, 250, 250, 0.04);
      white-space: nowrap;
    }

    .team-stats-table td:first-child,
    .team-stats-table th:first-child {
      width: 24%;
      text-align: left;
    }

    .team-stats-table td:not(:first-child),
    .team-stats-table th:not(:first-child) {
      text-align: center;
    }

    @media (max-width: 1100px) {
      .team-stats-match-grid {
        grid-template-columns: 1fr;
      }
    }

    .predictions-feed {
      display: grid;
      gap: 0.65rem;
    }

    .predictions-match,
    .predictions-section {
      border: 1px solid rgba(250, 250, 250, 0.18);
      border-radius: 0.45rem;
      background: rgb(14, 17, 23);
    }

    .predictions-section {
      margin-top: 0.55rem;
      background: rgba(250, 250, 250, 0.02);
    }

    .predictions-match > summary,
    .predictions-section > summary {
      cursor: pointer;
      font-weight: 700;
      padding: 0.5rem 0.65rem;
      list-style: none;
    }

    .predictions-match > summary::-webkit-details-marker,
    .predictions-section > summary::-webkit-details-marker {
      display: none;
    }

    .predictions-match > summary::before,
    .predictions-section > summary::before {
      content: "[+] ";
    }

    .predictions-match[open] > summary::before,
    .predictions-section[open] > summary::before {
      content: "[-] ";
    }

    .predictions-body {
      padding: 0 0.65rem 0.65rem;
    }

    .predictions-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 0.55rem;
    }

    .predictions-table-wrap {
      overflow-x: auto;
      max-height: none;
      overflow-y: visible;
    }

    .predictions-table {
      width: 100%;
      min-width: 800px;
      border-collapse: collapse;
      font-size: 0.8rem;
    }

    .predictions-table th,
    .predictions-table td {
      border: 1px solid rgba(250, 250, 250, 0.12);
      padding: 0.34rem 0.42rem;
      text-align: center;
      vertical-align: middle;
      white-space: normal;
      overflow-wrap: anywhere;
    }

    .predictions-table td.predictions-cell-reason {
      text-align: left;
      white-space: pre-line;
    }

    .predictions-table th {
      color: rgba(250, 250, 250, 0.72);
      font-weight: 500;
      background: rgba(250, 250, 250, 0.04);
      white-space: nowrap;
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
      justify-content: center;
      padding: 0;
      width: 100%;
    }

    .predictions-sort-button:hover {
      color: rgb(250, 250, 250);
    }

    .predictions-sort-indicator {
      display: inline-block;
      min-width: 0.7rem;
      opacity: 0.75;
    }

    .predictions-empty {
      margin: 0.45rem 0 0;
      color: rgba(250, 250, 250, 0.62);
      font-size: 0.85rem;
    }

    @media (max-width: 1100px) {
      .predictions-grid {
        grid-template-columns: 1fr;
      }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
render_carbon_theme_css(is_x_publish_unlocked())
render_x_publish_unlock_control()
render_carbon_theme_css(is_x_publish_unlocked())


SqlParams = dict[str, Any] | tuple[Any, ...] | list[Any] | None


@st.cache_data(ttl=60, show_spinner=False)
def _read_sql_cached(query: str, params: SqlParams = None, db_mtime_ns: int = 0) -> pd.DataFrame:
    return read_sql_frame(DB_PATH, query, params)


def db_mtime_ns() -> int:
    try:
        return DB_PATH.stat().st_mtime_ns
    except OSError:
        return 0


def read_sql(query: str, params: SqlParams = None) -> pd.DataFrame:
    try:
        return _read_sql_cached(query, params, db_mtime_ns())
    except Exception as exc:
        log.exception("Dashboard SQL failed")
        st.error(f"Erro ao carregar dados: {exc}")
        with st.expander("SQL com erro", expanded=False):
            st.code(query, language="sql")
        return pd.DataFrame()


@lru_cache(maxsize=20000)
def _plain_text_cached(text: str) -> str:
    # Normalize unicode (NFKD) and remove non-ascii, then lowercase
    text = normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    # Replace all non-alphanumeric with spaces and collapse spaces
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def plain_text(value: object) -> str:
    return _plain_text_cached("" if value is None else str(value))


TEAM_TOKEN_ALIASES = {
    "mg": "mineiro",
    "pr": "paranaense",
}
TEAM_TOKEN_STOPWORDS = {"ac", "club", "clube", "ec", "fc", "sc", "da", "de", "do", "das", "dos"}


@lru_cache(maxsize=20000)
def _team_tokens_cached(value: str) -> tuple[str, ...]:
    text = re.sub(r"[^a-z0-9]+", " ", plain_text(value))
    return tuple(
        TEAM_TOKEN_ALIASES.get(token, token)
        for token in text.split()
        if token and token not in TEAM_TOKEN_STOPWORDS
    )


def team_tokens(value: object) -> set[str]:
    return set(_team_tokens_cached("" if value is None else str(value)))


def parse_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def odds_freshness_counts(rows: pd.DataFrame) -> tuple[int, int]:
    if rows.empty or "odds_stale" not in rows.columns:
        return 0, 0
    stale = pd.to_numeric(rows["odds_stale"], errors="coerce").fillna(0).astype(int)
    stale_count = int(stale.sum())
    return len(rows) - stale_count, stale_count


def format_match_date(row: pd.Series) -> str:
    kickoff = row.get("kickoff_at")
    if pd.notna(kickoff):
        if not hasattr(kickoff, "strftime"):
            kickoff = pd.to_datetime(kickoff, errors="coerce")
    if pd.notna(kickoff):
        return kickoff.strftime("%d/%m - %H:%M")
    target_date = row.get("target_date")
    parsed = pd.to_datetime(target_date, errors="coerce")
    return parsed.strftime("%d/%m") if pd.notna(parsed) else str(target_date)


def market_targets(row: pd.Series) -> list[tuple[str, str, float | None]]:
    market_key = row.get("market_key")
    pick = plain_text(row.get("pick"))
    if market_key == "btts":
        return [("btts", "yes" if pick in {"sim", "yes"} else pick, None)]
    if market_key == "over_15":
        return [("alternate_totals", "over", 1.5), ("totals", "over", 1.5)]
    if market_key == "over_25":
        return [("totals", "over", 2.5), ("alternate_totals", "over", 2.5)]
    return [(str(market_key), pick, None)]


def team_goal_market_side(raw: dict | None = None, market_name: object = None, market_type_raw: object = None) -> str | None:
    raw = raw or {}
    raw_type = str(market_type_raw or raw.get("market_type_raw") or "").upper()
    text = plain_text(market_name or raw.get("market_name") or "")
    if not (raw_type.endswith("_GOALS") or "goal" in text or "gol" in text):
        return None
    if raw_type.startswith("HOME_TEAM_OVER/UNDER") or "time da casa com mais/menos" in text or "home team over/under" in text:
        return "home"
    if raw_type.startswith("AWAY_TEAM_OVER/UNDER") or "time visitante com mais/menos" in text or "away team over/under" in text:
        return "away"
    return None


def team_goal_market_key(side: str | None) -> str | None:
    if side == "home":
        return "teamtotals-goals-team1"
    if side == "away":
        return "teamtotals-goals-team2"
    return None


@lru_cache(maxsize=50000)
def _teams_match_cached(left: str, right: str) -> bool:
    a = plain_text(left)
    b = plain_text(right)
    if not a or not b:
        return False
    if a == b:
        return True
    left_tokens = team_tokens(left)
    right_tokens = team_tokens(right)
    return bool(left_tokens and right_tokens and (left_tokens <= right_tokens or right_tokens <= left_tokens))


def teams_match(left: object, right: object) -> bool:
    return _teams_match_cached("" if left is None else str(left), "" if right is None else str(right))


def teams_pair_match(left_home: object, left_away: object, right_home: object, right_away: object) -> bool:
    direct = teams_match(left_home, right_home) and teams_match(left_away, right_away)
    reverse = teams_match(left_home, right_away) and teams_match(left_away, right_home)
    return direct or reverse


def snapshot_raw(row: pd.Series) -> dict:
    try:
        return json.loads(row.get("raw_json") or "{}")
    except json.JSONDecodeError:
        return {}


def snapshot_matches_game(row: pd.Series, match: pd.Series) -> bool:
    raw = snapshot_raw(row)
    home = raw.get("home_team")
    away = raw.get("away_team")
    if not home:
        home = row.get("raw_home_team")
    if not away:
        away = row.get("raw_away_team")
    return teams_pair_match(home, away, match.get("home_team"), match.get("away_team"))


def odds_match_index(snapshots_df: pd.DataFrame) -> dict[tuple[str, str, str, str, float | None], float]:
    odds_by_line: dict[tuple[str, str, str, str, float | None], float] = {}
    if snapshots_df.empty:
        return odds_by_line

    snapshots_df = snapshots_df.copy()
    snapshots_df["fetched_at"] = parse_datetime(snapshots_df["fetched_at"])
    snapshots_df = snapshots_df.sort_values("fetched_at")

    for _, row in snapshots_df.iterrows():
        try:
            raw = json.loads(row.get("raw_json") or "{}")
        except json.JSONDecodeError:
            continue

        home = plain_text(raw.get("home_team"))
        away = plain_text(raw.get("away_team"))
        market = str(row.get("market_key") or "")
        outcome = plain_text(row.get("outcome_name"))
        if market == "totals" and team_goal_market_side(raw, row.get("market_name"), row.get("market_type_raw")):
            continue
        point = row.get("point")
        point_key = None if pd.isna(point) else float(point)
        price = row.get("price")
        if pd.isna(price):
            continue

        key = (home, away, market, outcome, point_key)
        odds_by_line[key] = max(float(price), odds_by_line.get(key, 0.0))
        reverse_key = (away, home, market, outcome, point_key)
        odds_by_line[reverse_key] = max(float(price), odds_by_line.get(reverse_key, 0.0))

    return odds_by_line


def add_display_columns(results_df: pd.DataFrame, odds_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return results_df

    display = results_df.copy()
    display["kickoff_at"] = parse_datetime(display["kickoff_at"])
    odds_by_line = odds_match_index(odds_df)

    def odd_for(row: pd.Series) -> str:
        home = plain_text(row.get("home_team"))
        away = plain_text(row.get("away_team"))
        for market, outcome, point in market_targets(row):
            value = odds_by_line.get((home, away, market, outcome, point))
            if value is not None:
                return f"{value:.2f}"
        return "N/D"

    display.insert(0, "Data", display.apply(format_match_date, axis=1))
    display["ODD"] = display.apply(odd_for, axis=1)
    return display.rename(
        columns={
            "league_name": "Liga",
            "home_team": "Casa",
            "away_team": "Fora",
            "pick": "Pick",
            "score": "Score",
            "reason": "Motivo",
        }
    )


def public_results(display: pd.DataFrame) -> pd.DataFrame:
    if display.empty:
        return display
    return display[["Data", "Liga", "Casa", "Fora", "Pick", "ODD", "Score", "Motivo"]]


GAME_COLUMNS = ["Data", "Liga", "Casa", "Fora", "Time", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
GAME_MARKET_COLUMNS = ["Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
TEAM_COLUMNS = ["Time", "Mercado", "Pick", "Linha", "Odd", "Score", "Motivo"]
TEAM_PREDICTION_COLUMNS = ["Time", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
TEAM_MARKET_COLUMNS = ["Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
PLAYER_COLUMNS = ["Jogador", "Time", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
PLAYER_MARKET_COLUMNS = ["Jogador", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
BEST_BETS_COLUMNS = [
    "Data",
    "Liga",
    "Casa",
    "Fora",
    "Tipo",
    "Time",
    "Jogador",
    "Mercado",
    "Pick",
    "Linha",
    "ODD",
    "Score",
    "Motivo",
]
PLAYER_REQUESTED_MARKETS = ["Faltas cometidas", "Faltas sofridas", "Finalizações", "Chutes a gol"]
TABLE_5_ROWS_HEIGHT = 215


PLAYER_MARKETS = {
    "players-shots": "Finalizações",
    "playertotals-shots": "Finalizações",
    "betfair-player-shots": "Finalizações",
    "players-shotsongoal": "Chutes a gol",
    "playertotals-shotsongoal": "Chutes a gol",
    "betfair-player-shots-on-target": "Chutes a gol",
    "players-foulscommitted": "Faltas cometidas",
    "playertotals-foulscommitted": "Faltas cometidas",
    "betfair-player-fouls-committed": "Faltas cometidas",
    "betfair-player-fouls-suffered": "Faltas sofridas",
}

POPULAR_PLAYER_MARKETS = {
    "betfair-popular-marcador-a-qualquer-momento": ("Gols", "goals"),
    "betfair-popular-primeiro-jogador-a-marcar": ("Gols", "goals"),
    "betfair-popular-primeiro-marcador-do-gol": ("Gols", "goals"),
    "betfair-popular-assistencia-a-qualquer-momento": ("Assistencias", "assists"),
    "betfair-popular-recebe-um-cartao": ("Cartoes", "cards"),
    "betfair-popular-marca-ou-faz-assistencia": ("Gol ou assistencia", "goals_or_assists"),
}

MODEL_LINES = {
    "over_15": "1.5",
    "over_25": "2.5",
    "btts": "Sim",
}

TEAM_SCORE_ATTRS = {
    "Gols marcados": "goals_for",
    "Gols sofridos": "goals_against",
    "Escanteios a favor": "corners_for",
    "Escanteios contra": "corners_against",
    "Escanteios totais": "corners_total",
    "Cartões a favor": "cards_for",
    "Cartões contra": "cards_against",
    "Cartões totais": "cards_total",
    "Finalizações Totais": "shots_total_for",
    "Finalizações Contra": "shots_total_against",
    "Finalizações por time": "shots_total_for",
    "Chutes no gol a favor": "shots_on_target_for",
    "Chutes no gol contra": "shots_on_target_against",
    "Chutes no gol por time": "shots_on_target_for",
    "Impedimentos a favor": "offsides_for",
    "Impedimentos contra": "offsides_against",
    "Arremessos Laterais": "throw_ins_for",
    "Gols no 1º Tempo a favor": "first_half_goals_for",
    "Gols no 1º Tempo contra": "first_half_goals_against",
    "Escanteios no 1º Tempo a favor": "first_half_corners_for",
    "Escanteios no 1º Tempo contra": "first_half_corners_against",
    "xG a favor": "xg_for",
    "xG contra": "xg_against",
    "Faltas cometidas": "fouls_committed",
    "Faltas sofridas": "fouls_suffered",
}

TEAM_STAT_CATEGORIES = [
    ("Gols marcados", "goals_for"),
    ("Gols Sofridos", "goals_against"),
    ("Gols no 1º Tempo a favor", "first_half_goals_for"),
    ("Gols no 1º Tempo contra", "first_half_goals_against"),
    ("Escanteios a favor", "corners_for"),
    ("Escanteios contra", "corners_against"),
    ("Escanteios no 1º Tempo a favor", "first_half_corners_for"),
    ("Escanteios no 1º Tempo contra", "first_half_corners_against"),
    ("Cartões a favor", "cards_for"),
    ("Cartões contra", "cards_against"),
    ("Finalizações Totais", "shots_total_for"),
    ("Finalizações Contra", "shots_total_against"),
    ("Chutes no gol a favor", "shots_on_target_for"),
    ("Chutes no gol contra", "shots_on_target_against"),
    ("Impedimentos a favor", "offsides_for"),
    ("Impedimentos contra", "offsides_against"),
    ("Arremessos Laterais", "throw_ins_for"),
    ("Faltas cometidas", "fouls_committed"),
    ("Faltas sofridas", "fouls_suffered"),
    ("xG a favor", "xg_for"),
    ("xG contra", "xg_against"),
]

PLAYER_SCORE_ATTRS = {
    "Gols": "goals",
    "Gol ou assistencia": "goals_or_assists",
    "Assistências": "assists",
    "Finalizações": "shots",
    "Chutes a gol": "shots_on_target",
    "Faltas cometidas": "fouls",
    "Faltas sofridas": "fouls_suffered",
    "Envolvimentos em faltas": "foul_involvements",
    "Cartoes": "cards",
    "Cartão Amarelo": "yellow_cards",
    "Cartão Vermelho": "red_cards",
}

PLAYER_STAT_CATEGORIES = [
    ("Gols", "goals"),
    ("Assistências", "assists"),
    ("Finalizações", "shots"),
    ("Chutes a gol", "shots_on_target"),
    ("Faltas cometidas", "fouls"),
    ("Faltas sofridas", "fouls_suffered"),
    ("Cartão Amarelo", "yellow_cards"),
    ("Cartão Vermelho", "red_cards"),
]

GAME_MARKETS = {
    "totals": "Gols totais",
    "teamtotals-goals-team1": "Gols marcados",
    "teamtotals-goals-team2": "Gols marcados",
    "btts": "Ambas marcam",
    "betfair-result": "Resultado final",
    "betfair-double-chance": "Chance dupla",
    "betfair-draw-no-bet": "Empate sem aposta",
    "betfair-goalkeeper-saves": "Defesas do goleiro",
    "betfair-team-shots": "Finalizações por time",
    "betfair-team-shots-on-target": "Chutes no gol por time",
    "totals-corners": "Escanteios totais",
    "teamtotals-corners-team1": "Escanteios a favor",
    "teamtotals-corners-team2": "Escanteios a favor",
    "totals-bookings": "Cartões totais",
    "teamtotals-bookings-team1": "Cartões a favor",
    "teamtotals-bookings-team2": "Cartões a favor",
}

GAME_SECTIONS = ["Gols", "Escanteios", "Cartões", "Outros"]
SOURCE_PRIORITY = {"espn": 0}
SOURCE_LABELS = {"espn": "ESPN"}
MIN_SCORE_SAMPLES = 3
SCORE_SAMPLE_LIMIT = 10
STATS_DISPLAY_GAMES = SCORE_SAMPLE_LIMIT
UNSUPPORTED_COMPOUND_MARKET_TOKENS = (
    "cotacoes aumentadas",
    "combinadas",
    "combinadas especiais",
    "escanteios e cartoes",
    "cabec",
    "fora da area",
)
UNSUPPORTED_PLAYER_PERIOD_TOKENS = (
    "1o tempo",
    "1 tempo",
    "primeiro tempo",
    "2o tempo",
    "2 tempo",
    "segundo tempo",
)


def format_point(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def expected_point_from_text(value: object) -> float | None:
    return score_logic.expected_point_from_text(value)


def coherent_snapshot_point(market_name: object, point: object) -> bool:
    expected = expected_point_from_text(market_name)
    if expected is None:
        return True
    try:
        actual = float(point)
    except (TypeError, ValueError):
        return False
    if pd.isna(actual):
        return False
    return abs(actual - expected) < 0.001


def display_odd(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/D"
    return f"{float(value):.2f}"


def display_score(value: object) -> str:
    if value is None or pd.isna(value) or value == "":
        return "N/D"
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def filter_non_empty_line(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "Linha" not in rows.columns:
        return rows
    clean = rows.copy()
    line = clean["Linha"].astype(str).str.strip().str.lower()
    return clean[~line.isin({"", "nan", "none", "n/d"})]


def filter_supported_score(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "Score" not in rows.columns:
        return rows
    score = rows["Score"].astype(str).str.strip().str.lower()
    return rows[~score.isin({"", "nan", "none", "n/d"})]


def filter_scored_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    filtered = filter_supported_score(rows)
    if filtered.empty or "Motivo" not in filtered.columns:
        return filtered
    reason = filtered["Motivo"].astype(str).str.strip().str.lower()
    return filtered[~reason.isin({"", "nan", "none", "n/d"})]


def clean_reason_column(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "Motivo" not in rows.columns:
        return rows
    cleaned = rows.copy()
    cleaned["Motivo"] = cleaned["Motivo"].map(clean_reason_for_display)
    return cleaned


def has_multiline_reason(rows: pd.DataFrame) -> bool:
    return "Motivo" in rows.columns and rows["Motivo"].astype(str).str.contains("\n", regex=False).any()


def table_row_height(rows: pd.DataFrame) -> int:
    return 68 if has_multiline_reason(rows) else 35


def render_table(rows: pd.DataFrame, height: int = TABLE_5_ROWS_HEIGHT) -> None:
    display = clean_reason_column(rows.copy())
    row_height = table_row_height(display)
    height = max(height, dataframe_content_height(display, min_height=height, max_height=2500, row_height=row_height))
    column_config = {}
    if "Score" in display.columns:
        display["Score"] = pd.to_numeric(display["Score"], errors="coerce")
        column_config["Score"] = st.column_config.NumberColumn("Score", format="%.1f")
    for odd_column in ("ODD", "Odd"):
        if odd_column in display.columns:
            display[odd_column] = pd.to_numeric(display[odd_column], errors="coerce")
            column_config[odd_column] = st.column_config.NumberColumn(odd_column, format="%.2f")
    if "Motivo" in display.columns:
        column_config["Motivo"] = st.column_config.TextColumn("Motivo", width="large")
    st.dataframe(
        display,
        width="stretch",
        height=height,
        hide_index=True,
        column_config=column_config,
        row_height=row_height,
    )


def dataframe_content_height(rows: pd.DataFrame, min_height: int = 110, max_height: int = 2500, row_height: int = 35) -> int:
    row_count = 0 if rows is None or rows.empty else len(rows)
    return min(max_height, max(min_height, 38 + (row_count + 1) * row_height))


def html_display_value(value: object, column: str) -> str:
    if value is None or pd.isna(value):
        return "N/D"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return "N/D"
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return text
    if column in {"ODD", "Odd"}:
        return f"{number:.2f}"
    if column in {"Score", "Linha"}:
        return f"{number:.1f}"
    return text


def prediction_table_html(
    rows: pd.DataFrame,
    columns: list[str],
    empty_text: str = "Sem mercados.",
    sortable: bool = False,
) -> str:
    if rows.empty:
        return f'<p class="predictions-empty">{escape(empty_text)}</p>'
    display = clean_reason_column(rows.copy())
    selected = [column for column in columns if column in display.columns]
    if not selected:
        return f'<p class="predictions-empty">{escape(empty_text)}</p>'
    display = display[selected].copy()
    for column in selected:
        display[column] = display[column].map(lambda value, col=column: html_display_value(value, col))
    header_cells = []
    for index, column in enumerate(selected):
        label = escape(str(column))
        if sortable:
            header_cells.append(
                "<th scope=\"col\">"
                f'<button type="button" class="predictions-sort-button" data-column-index="{index}" '
                f'aria-label="Ordenar {escape(str(column), quote=True)}">'
                f"{label}<span class=\"predictions-sort-indicator\"></span>"
                "</button>"
                "</th>"
            )
        else:
            header_cells.append(f'<th scope="col">{label}</th>')
    body_rows = []
    for _, row in display.iterrows():
        cells = []
        for column in selected:
            cell_class = ' class="predictions-cell-reason"' if column == "Motivo" else ""
            cells.append(f"<td{cell_class}>{escape(str(row.get(column, '')))}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    table = (
        f'<table class="predictions-table" data-sortable="{1 if sortable else 0}">'
        f"<thead><tr>{''.join(header_cells)}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )
    return f'<div class="predictions-table-wrap">{table}</div>'


def prediction_details_html(summary: str, body: str, open_section: bool = True, class_name: str = "predictions-section") -> str:
    open_attr = " open" if open_section else ""
    return (
        f'<details class="{class_name}"{open_attr}>'
        f"<summary>{escape(summary)}</summary>"
        f'<div class="predictions-body">{body}</div>'
        "</details>"
    )


def render_best_bets_table(rows: pd.DataFrame) -> None:
    display = clean_reason_column(rows.drop(columns=["_target_date", "_source_match_id", "market_key"], errors="ignore").copy())
    row_height = table_row_height(display)
    column_config = {}
    if "Linha" in display.columns:
        display["Linha"] = pd.to_numeric(display["Linha"], errors="coerce")
        column_config["Linha"] = st.column_config.NumberColumn("Linha", format="%.1f", width="small")
    for odd_column in ("ODD", "Odd"):
        if odd_column in display.columns:
            display[odd_column] = pd.to_numeric(display[odd_column], errors="coerce")
            column_config[odd_column] = st.column_config.NumberColumn(odd_column, format="%.2f", width="small")
    if "Score" in display.columns:
        display["Score"] = pd.to_numeric(display["Score"], errors="coerce")
        column_config["Score"] = st.column_config.NumberColumn("Score", format="%.1f", width="small")
    if "Motivo" in display.columns:
        column_config["Motivo"] = st.column_config.TextColumn("Motivo", width="large")
    st.dataframe(
        display,
        width="stretch",
        height=dataframe_content_height(display, min_height=160, max_height=2500, row_height=row_height),
        hide_index=True,
        column_config=column_config,
        row_height=row_height,
    )


def predictions_auto_resize_js() -> str:
    return """
      const resizeParentFrame = () => {
        let frame = null;
        try {
          frame = window.frameElement;
        } catch (_) {
          return;
        }
        if (!frame) return;

        const bodyHeight = Math.ceil(document.body.getBoundingClientRect().height) + 2;
        const height = Math.max(48, bodyHeight);
        frame.style.height = `${height}px`;
        frame.setAttribute("height", String(height));
      };

      const scheduleParentResize = () => {
        window.requestAnimationFrame(() => window.requestAnimationFrame(resizeParentFrame));
      };

      window.addEventListener("load", scheduleParentResize);
      document.querySelectorAll("details").forEach((details) => {
        details.addEventListener("toggle", scheduleParentResize);
      });
      if (window.ResizeObserver) {
        new ResizeObserver(scheduleParentResize).observe(document.body);
      }
      scheduleParentResize();
"""


def predictions_component_document(body: str, auto_resize: bool = False) -> str:
    auto_resize_js = predictions_auto_resize_js() if auto_resize else ""
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
{CARBON_IFRAME_CSS}
  </style>
</head>
<body>
  {body}
  <script>
    (() => {{
      const collator = new Intl.Collator("pt-BR", {{ numeric: true, sensitivity: "base" }});

      const numberValue = (text) => {{
        const normalized = text.trim().replace(",", ".");
        if (!/^-?\\d+(\\.\\d+)?$/.test(normalized)) {{
          return null;
        }}
        const value = Number(normalized);
        return Number.isFinite(value) ? value : null;
      }};

      const isEmptyValue = (text) => text === "" || text === "N/D" || text === "None";

      const compareText = (left, right) => {{
        const leftNumber = numberValue(left);
        const rightNumber = numberValue(right);
        if (leftNumber !== null && rightNumber !== null) {{
          return leftNumber - rightNumber;
        }}
        return collator.compare(left, right);
      }};

      document.addEventListener("click", (event) => {{
        const button = event.target.closest(".predictions-sort-button");
        if (!button) return;

        const table = button.closest("table");
        const tbody = table ? table.tBodies[0] : null;
        if (!tbody) return;

        const columnIndex = Number(button.dataset.columnIndex);
        const direction = button.dataset.sortDirection === "asc" ? "desc" : "asc";

        table.querySelectorAll(".predictions-sort-button").forEach((candidate) => {{
          candidate.dataset.sortDirection = "";
          const indicator = candidate.querySelector(".predictions-sort-indicator");
          if (indicator) indicator.textContent = "";
          const header = candidate.closest("th");
          if (header) header.removeAttribute("aria-sort");
        }});

        button.dataset.sortDirection = direction;
        const indicator = button.querySelector(".predictions-sort-indicator");
        if (indicator) indicator.textContent = direction === "asc" ? "^" : "v";
        const header = button.closest("th");
        if (header) header.setAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");

        const rows = Array.from(tbody.rows);
        rows.sort((leftRow, rightRow) => {{
          const left = (leftRow.cells[columnIndex]?.textContent || "").trim();
          const right = (rightRow.cells[columnIndex]?.textContent || "").trim();
          const leftEmpty = isEmptyValue(left);
          const rightEmpty = isEmptyValue(right);
          if (leftEmpty && rightEmpty) return 0;
          if (leftEmpty) return 1;
          if (rightEmpty) return -1;
          const result = compareText(left, right);
          return direction === "asc" ? result : -result;
        }});
        rows.forEach((row) => tbody.appendChild(row));
      }});
{auto_resize_js}
    }})();
  </script>
</body>
</html>
"""


def predictions_component_src(body: str, auto_resize: bool = False) -> str:
    document = predictions_component_document(body, auto_resize=auto_resize)
    encoded = b64encode(document.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{encoded}"


def predictions_component_height(rows: pd.DataFrame, open_all: bool = False) -> int:
    if rows.empty or "_match_group_key" not in rows.columns:
        return 120
    group_sizes = rows.groupby("_match_group_key", sort=False).size()
    if group_sizes.empty:
        return 120
    if open_all:
        total_rows = int(group_sizes.sum())
        total_groups = int(len(group_sizes))
        feed_gaps = max(0, total_groups - 1)
        table_header_height = 35
        table_row_height = 60
        section_chrome_height = 50
        feed_gap_height = 12
        height = (
            total_groups * (section_chrome_height + table_header_height)
            + total_rows * table_row_height
            + feed_gaps * feed_gap_height
            + 20
        )
        return min(4000, max(120, height))
    closed_height = 60 * len(group_sizes) + 40
    open_height = min(600, 70 + (int(group_sizes.max()) + 1) * 60)
    return min(1200, max(200, closed_height + open_height))


def best_bets_match_key(row: pd.Series) -> str:
    source_match_id = str(row.get("_source_match_id") or "").strip()
    if source_match_id:
        return source_match_id
    return "|".join(str(row.get(column) or "") for column in ["Data", "Liga", "Casa", "Fora"])


def best_bets_match_label(rows: pd.DataFrame) -> str:
    row = rows.iloc[0]
    data = str(row.get("Data") or "").strip()
    home = str(row.get("Casa") or "").strip()
    away = str(row.get("Fora") or "").strip()
    liga = str(row.get("Liga") or "").strip()
    title = f"{home} x {away}" if home and away else home or away or "Jogo"
    if liga:
        title = f"{title} ({liga})"
    return f"{data} | {title}" if data else title


def render_best_bets_by_match(rows: pd.DataFrame, columns: list[str]) -> None:
    if rows.empty:
        st.caption("Sem mercados.")
        return
    grouped = rows.copy()
    grouped["_match_group_key"] = grouped.apply(best_bets_match_key, axis=1)
    sections = []
    for _, match_rows in grouped.groupby("_match_group_key", sort=False):
        match_rows = match_rows.drop(columns=["_match_group_key"], errors="ignore")
        label = f"{best_bets_match_label(match_rows)} ({len(match_rows)})"
        body = prediction_table_html(match_rows, columns, "Sem mercados.", sortable=True)
        sections.append(prediction_details_html(label, body, True, "predictions-match"))
    components.html(
        predictions_component_document(f'<div class="predictions-feed">{"".join(sections)}</div>', auto_resize=True),
        height=predictions_component_height(grouped, open_all=True),
        scrolling=True,
    )


def x_drafts_signature(drafts: list[XPostDraft]) -> str:
    digest = hashlib.sha256()
    for draft in drafts:
        digest.update(draft.text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def publish_x_drafts_ui(
    drafts: list[XPostDraft],
    credentials: XCredentials,
    delay_seconds: int,
) -> None:
    if not ensure_x_publish_unlocked():
        return

    progress = st.progress(0)
    status = st.empty()

    def show_progress(done: int, total: int, result: object) -> None:
        progress.progress(done / total)
        post_id = getattr(result, "post_id", "")
        status.info(f"Publicado {done}/{total}: {post_id}")

    try:
        results = publish_x_posts(
            [draft.text for draft in drafts],
            credentials,
            api_base_url=settings.x_api_base_url,
            delay_seconds=delay_seconds,
            max_chars=settings.x_post_max_chars,
            progress_fn=show_progress,
        )
    except XPostError as exc:
        st.error(str(exc))
    else:
        st.success(f"X publicado: {len(results)} posts.")


def maybe_auto_publish_x(
    drafts: list[XPostDraft],
    credentials: XCredentials,
    missing: list[str],
    over_limit: list[XPostDraft],
    key_prefix: str,
) -> None:
    if not settings.x_auto_publish_enabled:
        return
    if missing:
        st.warning(f"Auto X nao iniciado. Configure no .env: {', '.join(missing)}")
        return
    if over_limit:
        st.warning("Auto X nao iniciado. Existe post acima do limite.")
        return

    signature = x_drafts_signature(drafts)
    auto_key = f"{key_prefix}_x_auto_publish_signature"
    if st.session_state.get(auto_key) == signature:
        return

    st.session_state[auto_key] = signature
    st.info("Auto X iniciado.")
    publish_x_drafts_ui(drafts, credentials, delay_seconds=settings.x_post_delay_seconds)


def render_x_single_publish_controls(
    drafts: list[XPostDraft],
    credentials: XCredentials,
    missing: list[str],
    key_prefix: str,
) -> None:
    with st.expander("Publicar aposta individual no X", expanded=False):
        for index, draft in enumerate(drafts, start=1):
            st.caption(f"{index}. {draft.match_label} | {draft.char_count} chars")
            st.code(draft.text)
            if st.button(
                "Publicar esta aposta",
                disabled=bool(missing or draft.char_count > settings.x_post_max_chars),
                key=f"{key_prefix}_publish_x_{index}",
            ):
                publish_x_drafts_ui([draft], credentials, delay_seconds=0)


def render_x_publish_controls(rows: pd.DataFrame, key_prefix: str = "best_bets") -> None:
    if not is_x_publish_unlocked():
        return

    drafts = build_best_bet_x_posts(rows, max_chars=settings.x_post_max_chars)
    if not drafts:
        return

    credentials = XCredentials.from_settings(settings)
    missing = credentials.missing_fields()
    over_limit = [draft for draft in drafts if draft.char_count > settings.x_post_max_chars]
    st.caption(
        f"X: {len(drafts)} publicacoes por aposta | auto "
        f"{'ativo' if settings.x_auto_publish_enabled else 'desativado'} | "
        f"delay geral {settings.x_post_delay_seconds}s | "
        f"limite {settings.x_post_max_chars} chars"
    )

    if missing:
        st.warning(f"Configure no .env: {', '.join(missing)}")
    if over_limit:
        labels = ", ".join(f"{draft.match_label} ({draft.char_count})" for draft in over_limit)
        st.error(f"Post X acima do limite: {labels}")

    maybe_auto_publish_x(drafts, credentials, missing, over_limit, key_prefix)

    if st.button(
        "Publicar todas no X",
        disabled=bool(missing or over_limit),
        type="primary",
        key=f"{key_prefix}_publish_x",
    ):
        publish_x_drafts_ui(drafts, credentials, delay_seconds=settings.x_post_delay_seconds)
    render_x_single_publish_controls(drafts, credentials, missing, key_prefix)


def render_best_bets_tab(rows: pd.DataFrame, key_prefix: str = "best_bets") -> None:
    render_x_publish_controls(rows, key_prefix=key_prefix)
    grouped_rows = {
        "Jogos": rows[rows["Tipo"].astype(str).eq("Jogo")].drop(columns=["Jogador"], errors="ignore").copy(),
        "Times": rows[rows["Tipo"].astype(str).eq("Time")].drop(columns=["Jogador"], errors="ignore").copy(),
        "Jogadores": rows[rows["Tipo"].astype(str).eq("Jogador")].copy(),
    }
    for group_name, group_rows in grouped_rows.items():
        with st.expander(f"{group_name} ({len(group_rows)})", expanded=True):
            if group_rows.empty:
                st.caption("Sem mercados.")
            else:
                exclude_cols = {"_target_date", "_source_match_id", "market_key"}
                if group_name == "Jogos":
                    exclude_cols.update({"Data", "Liga", "Casa", "Fora", "Tipo", "Time"})
                elif group_name == "Times":
                    exclude_cols.update({"Data", "Liga", "Casa", "Fora", "Tipo"})
                elif group_name == "Jogadores":
                    exclude_cols.update({"Data", "Liga", "Casa", "Fora", "Tipo", "Time"})

                display_columns = [
                    column
                    for column in BEST_BETS_COLUMNS
                    if column in group_rows.columns and column not in exclude_cols
                ]
                render_best_bets_by_match(group_rows, display_columns)


def numeric_filter_values(rows: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in rows.columns:
            return pd.to_numeric(rows[column].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return pd.Series(float("nan"), index=rows.index)


def best_bet_filter(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=BEST_BETS_COLUMNS)
    filtered = rows.copy()
    filtered["_odd"] = numeric_filter_values(filtered, "ODD", "Odd")
    filtered["_score"] = numeric_filter_values(filtered, "Score")
    filtered = filtered[(filtered["_odd"] >= 1.30) & (filtered["_score"] >= 75)]
    if filtered.empty:
        return pd.DataFrame(columns=BEST_BETS_COLUMNS)
    return (
        filtered.sort_values(["_score", "_odd"], ascending=[False, False])
        .drop(columns=["_odd", "_score"], errors="ignore")
        .reset_index(drop=True)
    )


def score_from_values(values: list[float], pick: object, line: object) -> str:
    return score_logic.score_from_values(values, pick, line)


def score_parts(values: list[float], pick: object, line: object) -> tuple[str, int, int, str]:
    return score_logic.score_parts(values, pick, line)


def hit_score(hits: int, total: int) -> str:
    return score_logic.hit_score(hits, total)


def line_hit(value: object, pick: object, line: object) -> bool | None:
    return score_logic.line_hit(value, pick, line)


def line_pick(value: object) -> object:
    return score_logic.line_pick(value)


def yes_no_pick(value: object) -> bool | None:
    text = plain_text(value)
    if text in {"sim", "yes"} or text.startswith(("sim ", "yes ")):
        return True
    if text in {"nao", "no"} or text.startswith(("nao ", "no ")):
        return False
    return None


def sum_values(*values: object) -> float | None:
    if any(value is None or pd.isna(value) for value in values):
        return None
    return sum(float(value) for value in values)


def diff_values(left: object, right: object) -> float | None:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return None
    return float(left) - float(right)


def min_values(left: object, right: object) -> float | None:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return None
    return min(float(left), float(right))


def side_filter_label(is_home: bool | None) -> str:
    if is_home is True:
        return "mandante"
    if is_home is False:
        return "visitante"
    return ""


def each_half_text(value: object) -> bool:
    text = plain_text(value)
    return "cada tempo" in text or "ambos os tempos" in text or "cada metade" in text


def unsupported_compound_market(value: object) -> bool:
    text = plain_text(value)
    return any(token in text for token in UNSUPPORTED_COMPOUND_MARKET_TOKENS)


def unsupported_player_period_market(value: object) -> bool:
    text = plain_text(value)
    return any(token in text for token in UNSUPPORTED_PLAYER_PERIOD_TOKENS)


def row_market_text(row: pd.Series) -> str:
    return " ".join(
        str(row.get(column) or "")
        for column in ("market_key", "market_name", "market_type_raw", "Mercado", "Pick", "runner_name")
    )


def scoreable_market_row(row: pd.Series) -> bool:
    text = row_market_text(row)
    if unsupported_compound_market(text):
        return False
    if str(row.get("market_type_raw") or "").upper() == "ODDSBOOST":
        return False
    if plain_text(row.get("market_key")).startswith("betfair-oddsboost"):
        return False
    return True


def period_from_text(value: object) -> str:
    text = plain_text(value)
    if "1t" in text or "1o tempo" in text or "1 tempo" in text or "primeiro tempo" in text or "first half" in text:
        return "1T"
    if "2t" in text or "2o tempo" in text or "2 tempo" in text or "segundo tempo" in text or "second half" in text:
        return "2T"
    return "FT"


def period_stat_attr(base_attr: str, row: pd.Series) -> str | None:
    period = period_from_text(row_market_text(row))
    if period == "FT":
        return base_attr
    if base_attr == "goals_total":
        return "first_half_goals_total" if period == "1T" else "second_half_goals_total"
    if base_attr == "corners_total":
        return "first_half_corners_total" if period == "1T" else "second_half_corners_total"
    return None


def team_stat_value(row: pd.Series, attr: str) -> float | None:
    if attr == "goals_total":
        return sum_values(row.get("goals_for"), row.get("goals_against"))
    if attr == "corners_total":
        return sum_values(row.get("corners_for"), row.get("corners_against"))
    if attr == "cards_total":
        return sum_values(row.get("cards_for"), row.get("cards_against"))
    if attr == "first_half_goals_total":
        return sum_values(row.get("first_half_goals_for"), row.get("first_half_goals_against"))
    if attr == "first_half_corners_total":
        return sum_values(row.get("first_half_corners_for"), row.get("first_half_corners_against"))
    if attr == "second_half_goals_for":
        return diff_values(row.get("goals_for"), row.get("first_half_goals_for"))
    if attr == "second_half_goals_against":
        return diff_values(row.get("goals_against"), row.get("first_half_goals_against"))
    if attr == "second_half_goals_total":
        first = team_stat_value(row, "first_half_goals_total")
        total = team_stat_value(row, "goals_total")
        return diff_values(total, first)
    if attr == "second_half_corners_for":
        return diff_values(row.get("corners_for"), row.get("first_half_corners_for"))
    if attr == "second_half_corners_against":
        return diff_values(row.get("corners_against"), row.get("first_half_corners_against"))
    if attr == "second_half_corners_total":
        first = team_stat_value(row, "first_half_corners_total")
        total = team_stat_value(row, "corners_total")
        return diff_values(total, first)
    if attr == "goalkeeper_saves":
        value = diff_values(row.get("shots_on_target_against"), row.get("goals_against"))
        return max(value, 0) if value is not None else None
    if attr == "corners_each_team":
        return min_values(row.get("corners_for"), row.get("corners_against"))
    if attr == "corners_each_team_each_half":
        first = min_values(row.get("first_half_corners_for"), row.get("first_half_corners_against"))
        second_for = diff_values(row.get("corners_for"), row.get("first_half_corners_for"))
        second_against = diff_values(row.get("corners_against"), row.get("first_half_corners_against"))
        second = min_values(second_for, second_against)
        if first is None or second is None:
            return None
        return min(first, second)
    if attr == "cards_each_team":
        return min_values(row.get("cards_for"), row.get("cards_against"))
    if attr == "shots_on_target_each_team":
        return min_values(row.get("shots_on_target_for"), row.get("shots_on_target_against"))
    if attr not in row.index:
        return None
    value = row.get(attr)
    if value is None or pd.isna(value):
        return None
    return float(value)


def team_result(row: pd.Series) -> str | None:
    goals_for = row.get("goals_for")
    goals_against = row.get("goals_against")
    if goals_for is None or goals_against is None or pd.isna(goals_for) or pd.isna(goals_against):
        return None
    if float(goals_for) > float(goals_against):
        return "win"
    if float(goals_for) < float(goals_against):
        return "loss"
    return "draw"


def more_corners_each_half(row: pd.Series) -> bool | None:
    first_for = row.get("first_half_corners_for")
    first_against = row.get("first_half_corners_against")
    second_for = diff_values(row.get("corners_for"), first_for)
    second_against = diff_values(row.get("corners_against"), first_against)
    if any(value is None or pd.isna(value) for value in [first_for, first_against, second_for, second_against]):
        return None
    return float(first_for) > float(first_against) and float(second_for) > float(second_against)


def side_result(row: pd.Series, side: str, first_half: bool = False) -> str | None:
    if first_half:
        goals_for = row.get("first_half_goals_for")
        goals_against = row.get("first_half_goals_against")
        if goals_for is None or goals_against is None or pd.isna(goals_for) or pd.isna(goals_against):
            return None
        result = "win" if float(goals_for) > float(goals_against) else "loss" if float(goals_for) < float(goals_against) else "draw"
    else:
        result = team_result(row)
    if result is None:
        return None
    if result == "draw":
        return "draw"
    if side == "home":
        return "home" if result == "win" else "away"
    return "away" if result == "win" else "home"


def result_outcomes_from_pick(match: pd.Series, pick: object) -> set[str]:
    text = plain_text(pick)
    outcomes: set[str] = set()
    if "empate" in text or text in {"draw", "x", "o empate"}:
        outcomes.add("draw")
    if teams_match(pick, match.get("home_team")) or plain_text(match.get("home_team")) in text:
        outcomes.add("home")
    if teams_match(pick, match.get("away_team")) or plain_text(match.get("away_team")) in text:
        outcomes.add("away")
    return outcomes


def score_pairs_from_text(value: object) -> list[tuple[int, int]]:
    text = plain_text(value).replace(" a ", "-")
    pairs = []
    for home, away in re.findall(r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})(?!\d)", text):
        pairs.append((int(home), int(away)))
    return pairs


def total_range_from_pick(value: object) -> tuple[int, int] | None:
    text = plain_text(value)
    match = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"\d{1,2}", text)
    if match:
        number = int(match.group(0))
        return number, number
    return None


def stat_pair_value(stat: pd.Series, left_attr: str, right_attr: str) -> str:
    left = format_sample_value(stat.get(left_attr))
    right = format_sample_value(stat.get(right_attr))
    return f"{left}-{right}" if left and right else ""


def side_scoreline(stat: pd.Series, side: str, first_half: bool = False) -> str:
    goals_for_attr = "first_half_goals_for" if first_half else "goals_for"
    goals_against_attr = "first_half_goals_against" if first_half else "goals_against"
    goals_for = stat.get(goals_for_attr)
    goals_against = stat.get(goals_against_attr)
    if side == "home":
        return stat_pair_value(pd.Series({"home": goals_for, "away": goals_against}), "home", "away")
    return stat_pair_value(pd.Series({"home": goals_against, "away": goals_for}), "home", "away")


def side_total_goals(stat: pd.Series, _side: str) -> object:
    return team_stat_value(stat, "goals_total")


def team_samples(
    team_stats_df: pd.DataFrame,
    match: pd.Series,
    limit: int = SCORE_SAMPLE_LIMIT,
) -> list[tuple[str, str, pd.DataFrame]]:
    return [
        (str(match.get("home_team")), "home", team_match_history(team_stats_df, match.get("home_team"), True, limit)),
        (str(match.get("away_team")), "away", team_match_history(team_stats_df, match.get("away_team"), False, limit)),
    ]


def game_predicate_score_reason(
    match: pd.Series,
    team_stats_df: pd.DataFrame,
    predicate,
    criterion: str,
    sample_value: Callable[[pd.Series, str], object] | None = None,
) -> tuple[str, str]:
    if team_stats_df.empty:
        return "N/D", ""
    hits_by_team: list[tuple[str, str, int, int, list[object]]] = []
    sources = set()
    hits = 0
    total = 0
    for team_name, side, rows in team_samples(team_stats_df, match):
        team_hits = 0
        team_total = 0
        team_values = []
        for _, stat in rows.iterrows():
            hit = predicate(stat, side)
            if hit is None:
                continue
            team_hits += int(hit)
            team_total += 1
            if sample_value is not None:
                team_values.append(sample_value(stat, side))
            if stat.get("source"):
                sources.add(str(stat.get("source")))
        hits += team_hits
        total += team_total
        hits_by_team.append((team_name, side, team_hits, team_total, team_values))
    if any(team_total < MIN_SCORE_SAMPLES for _, _, _, team_total, _ in hits_by_team):
        return "N/D", ""
    if total == 0:
        return "N/D", ""
    source_text = ", ".join(source_label(source) for source in sorted(sources, key=lambda item: SOURCE_PRIORITY.get(item, 99))) or "ESPN"
    parts = [f"Fonte: {source_text}", f"Criterio: {criterion}"]
    parts.extend(
        f"{team} ({'mandante' if side == 'home' else 'visitante'}) - {format_hits_with_samples(team_hits, team_total, team_values)}"
        for team, side, team_hits, team_total, team_values in hits_by_team
    )
    return hit_score(hits, total), " | ".join(parts)


def canonical_market_label(value: object) -> str:
    text = str(value or "")
    if text.endswith(" - FT"):
        return text[:-5]
    return text


def market_score_attr(mapping: dict[str, str], value: object) -> str | None:
    label = canonical_market_label(value)
    if label in mapping:
        return mapping[label]
    normalized = plain_text(label)
    for key, attr in mapping.items():
        if plain_text(key) == normalized:
            return attr
    return None


def stat_values(
    team_stats_df: pd.DataFrame,
    team_name: object,
    attr: str,
    limit: int = SCORE_SAMPLE_LIMIT,
    is_home: bool | None = None,
) -> list[float]:
    return [item[1] for item in stat_value_items(team_stats_df, team_name, attr, limit, is_home)]


def stat_value_items(
    team_stats_df: pd.DataFrame,
    team_name: object,
    attr: str,
    limit: int = SCORE_SAMPLE_LIMIT,
    is_home: bool | None = None,
) -> list[tuple[str, float, str]]:
    rows = team_stats_df[team_stats_df["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
    if rows.empty:
        return []
    if is_home is not None and "is_home" in rows.columns:
        rows = rows[rows["is_home"].notna()].copy()
        rows = rows[rows["is_home"].astype(bool) == is_home]
        if rows.empty:
            return []
    values = rows.apply(lambda row: team_stat_value(row, attr), axis=1)
    rows["_value"] = values
    rows = rows[rows["_value"].notna()].copy()
    if rows.empty:
        return []
    rows["_source_rank"] = rows["source"].map(SOURCE_PRIORITY).fillna(99) if "source" in rows.columns else 99
    rows = rows.sort_values(["match_date", "_source_rank"], ascending=[False, True])
    rows = rows.drop_duplicates(["match_date"], keep="first").head(limit)
    items = []
    for _, row in rows.iterrows():
        value = row.get("_value")
        if value is None or pd.isna(value):
            continue
        opponent = row.get("opponent_name") or "?"
        source = str(row.get("source") or "")
        label = f"{row.get('match_date')} vs {opponent}"
        items.append((label, float(value), source))
    return items


def source_label(source: object) -> str:
    return SOURCE_LABELS.get(str(source), str(source or "fonte N/D"))


def sources_label(items: list[tuple]) -> str:
    sources = sorted(
        {str(item[2]) for item in items if len(item) > 2 and item[2]},
        key=lambda item: SOURCE_PRIORITY.get(item, 99),
    )
    return ", ".join(source_label(source) for source in sources)


def evidence_from_items(
    source: str,
    items: list[tuple],
    pick: object,
    line: object,
    is_home: bool | None = None,
    criterion: object = "",
    subject: object = "",
) -> str:
    values = [item[1] for item in items]
    _, hits, total, _ = score_parts(values, pick, line)
    if total == 0:
        return ""
    source_text = sources_label(items) or source
    side = side_filter_label(is_home)
    parts = [f"Fonte: {source_text}"]
    if side:
        parts.append(f"Filtro: jogos como {side}")
    if criterion:
        parts.append(f"Criterio: {criterion}")
    if subject:
        parts.append(f"{subject} - {format_hits_with_samples(hits, total, values)}")
    else:
        parts.append(format_hits_with_samples(hits, total, values))
    return " | ".join(parts)


def bool_evidence(
    team_stats_df: pd.DataFrame,
    team_name: object,
    attr: str,
    is_home: bool | None = None,
) -> tuple[int, int, str, str, list[object]]:
    rows = team_stats_df[team_stats_df["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
    if rows.empty or attr not in rows.columns:
        return 0, 0, "", "", []
    if is_home is not None and "is_home" in rows.columns:
        rows = rows[rows["is_home"].notna()].copy()
        rows = rows[rows["is_home"].astype(bool) == is_home]
        if rows.empty:
            return 0, 0, "", "", []
    rows = rows[rows[attr].notna()].copy()
    if rows.empty:
        return 0, 0, "", "", []
    rows["_source_rank"] = rows["source"].map(SOURCE_PRIORITY).fillna(99) if "source" in rows.columns else 99
    rows = rows.sort_values(["match_date", "_source_rank"], ascending=[False, True])
    rows = rows.drop_duplicates(["match_date"], keep="first").head(SCORE_SAMPLE_LIMIT)
    details = []
    hits = 0
    total = 0
    samples = []
    sources = set()
    for _, row in rows.iterrows():
        value = row.get(attr)
        if value is None or pd.isna(value):
            continue
        hit = bool(value)
        hits += int(hit)
        total += 1
        if row.get("source"):
            sources.add(str(row.get("source")))
        goals_for = row.get("goals_for")
        goals_against = row.get("goals_against")
        score = f"{int(goals_for)}-{int(goals_against)}" if pd.notna(goals_for) and pd.notna(goals_against) else "placar N/D"
        if attr in {"over_15", "over_25"}:
            samples.append(team_stat_value(row, "goals_total"))
        elif attr == "btts":
            samples.append(side_scoreline(row, "home" if is_home else "away"))
        details.append(f"{row.get('match_date')} vs {row.get('opponent_name') or '?'} {score}={'sim' if hit else 'não'}")
    source_text = ", ".join(source_label(source) for source in sorted(sources, key=lambda item: SOURCE_PRIORITY.get(item, 99)))
    return hits, total, "; ".join(details), source_text, samples


def model_reason(match: pd.Series, market_key: object, team_stats_df: pd.DataFrame) -> str:
    market = str(market_key)
    if market not in {"over_15", "over_25", "btts"}:
        return ""
    home_hits, home_total, _, home_sources, home_samples = bool_evidence(team_stats_df, match.get("home_team"), market, True)
    away_hits, away_total, _, away_sources, away_samples = bool_evidence(team_stats_df, match.get("away_team"), market, False)
    if home_total < MIN_SCORE_SAMPLES or away_total < MIN_SCORE_SAMPLES:
        return ""
    source_text = ", ".join(dict.fromkeys([value for value in [home_sources, away_sources] if value]))
    criteria = {"over_15": "gols totais > 1.5", "over_25": "gols totais > 2.5", "btts": "ambas marcam"}
    return (
        f"Fonte: {source_text} | Criterio: {criteria.get(market, market)} | "
        f"{match.get('home_team')} (mandante) - {format_hits_with_samples(home_hits, home_total, home_samples)} | "
        f"{match.get('away_team')} (visitante) - {format_hits_with_samples(away_hits, away_total, away_samples)}"
    )


def model_score(match: pd.Series, market_key: object, team_stats_df: pd.DataFrame) -> str:
    market = str(market_key)
    if market not in {"over_15", "over_25", "btts"}:
        return "N/D"
    home_hits, home_total, _, _, _ = bool_evidence(team_stats_df, match.get("home_team"), market, True)
    away_hits, away_total, _, _, _ = bool_evidence(team_stats_df, match.get("away_team"), market, False)
    total = home_total + away_total
    if home_total < MIN_SCORE_SAMPLES or away_total < MIN_SCORE_SAMPLES or total == 0:
        return "N/D"
    return display_score(round(((home_hits + away_hits) / total) * 100, 1))


def team_predicate_score_reason(
    row: pd.Series,
    team_stats_df: pd.DataFrame,
    is_home: bool | None,
    predicate,
    criterion: str,
    sample_value: Callable[[pd.Series], object] | None = None,
) -> tuple[str, str]:
    if team_stats_df.empty:
        return "N/D", ""
    team_name = row.get("Time")
    if is_home is None:
        history = team_stats_df[team_stats_df["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
        if not history.empty:
            history["_source_rank"] = history["source"].map(SOURCE_PRIORITY).fillna(99) if "source" in history.columns else 99
            history = history.sort_values(["match_date", "_source_rank"], ascending=[False, True])
            history = history.drop_duplicates(["match_date"], keep="first").head(SCORE_SAMPLE_LIMIT)
    else:
        history = team_match_history(team_stats_df, team_name, is_home, SCORE_SAMPLE_LIMIT)
    if history.empty:
        return "N/D", ""
    hits = 0
    total = 0
    samples = []
    sources = set()
    for _, stat in history.iterrows():
        hit = predicate(stat)
        if hit is None:
            continue
        hits += int(hit)
        total += 1
        if sample_value is not None:
            samples.append(sample_value(stat))
        if stat.get("source"):
            sources.add(str(stat.get("source")))
    if total < MIN_SCORE_SAMPLES:
        return "N/D", ""
    source_text = ", ".join(source_label(source) for source in sorted(sources, key=lambda item: SOURCE_PRIORITY.get(item, 99))) or "ESPN"
    side = side_filter_label(is_home)
    side_part = f" | Filtro: jogos como {side}" if side else ""
    return hit_score(hits, total), f"Fonte: {source_text} | Criterio: {criterion}{side_part} | {team_name} - {format_hits_with_samples(hits, total, samples)}"


def predicate_sample_values(
    rows: pd.DataFrame,
    predicate,
    sample_value: Callable[[pd.Series], object] | None,
) -> list[object]:
    if sample_value is None:
        return []
    samples = []
    for _, stat in rows.iterrows():
        if predicate(stat) is not None:
            samples.append(sample_value(stat))
    return samples


def team_matchup_score_reason(
    row: pd.Series,
    match: pd.Series | None,
    team_stats_df: pd.DataFrame,
    is_home: bool | None,
    team_predicate: matchup_logic.Predicate,
    opponent_predicate: matchup_logic.Predicate,
    criterion: str,
    team_sample_value: Callable[[pd.Series], object] | None = None,
    opponent_sample_value: Callable[[pd.Series], object] | None = None,
) -> tuple[str, str]:
    if match is None or is_home is None:
        return team_predicate_score_reason(row, team_stats_df, is_home, team_predicate, criterion)
    team_name = row.get("Time")
    opponent_name = match.get("away_team") if is_home else match.get("home_team")
    if not team_name or not opponent_name or pd.isna(team_name) or pd.isna(opponent_name):
        return team_predicate_score_reason(row, team_stats_df, is_home, team_predicate, criterion)
    team_history = team_match_history(team_stats_df, team_name, is_home, SCORE_SAMPLE_LIMIT)
    opponent_history = team_match_history(team_stats_df, opponent_name, not is_home, SCORE_SAMPLE_LIMIT)
    result = matchup_logic.matchup_score(team_history, team_predicate, opponent_history, opponent_predicate, MIN_SCORE_SAMPLES)
    if result is None:
        return "N/D", ""
    source_text = ", ".join(
        source_label(source)
        for source in sorted(result.sources, key=lambda item: SOURCE_PRIORITY.get(item, 99))
    ) or "ESPN"
    team_side = side_filter_label(is_home)
    opponent_side = side_filter_label(not is_home)
    team_samples = predicate_sample_values(team_history, team_predicate, team_sample_value)
    opponent_samples = predicate_sample_values(opponent_history, opponent_predicate, opponent_sample_value)
    reason = (
        f"Fonte: {source_text} | Criterio: {criterion} | "
        f"{team_name} ({team_side}) - {format_hits_with_samples(result.team_hits, result.team_total, team_samples)} | "
        f"{opponent_name} ({opponent_side}) - {format_hits_with_samples(result.opponent_hits, result.opponent_total, opponent_samples)}"
    )
    return result.score, reason


def team_special_score_reason(
    row: pd.Series,
    team_stats_df: pd.DataFrame,
    is_home: bool | None = None,
    match: pd.Series | None = None,
) -> tuple[str, str]:
    text = plain_text(f"{row.get('market_key')} {row.get('Mercado')} {row.get('Pick')}")
    if "goleiro" in text or "defesa" in text:
        items = stat_value_items(team_stats_df, row.get("Time"), "goalkeeper_saves", SCORE_SAMPLE_LIMIT, is_home)
        if len(items) < MIN_SCORE_SAMPLES:
            return "N/D", ""
        score = score_from_values([item[1] for item in items], line_pick(row.get("Pick")), row.get("Linha"))
        criterion = f"{row.get('Mercado')} {line_pick(row.get('Pick'))} {row.get('Linha')}".strip()
        return score, evidence_from_items("ESPN", items, line_pick(row.get("Pick")), row.get("Linha"), is_home, criterion, row.get("Time"))
    if "handicap" in text and "gol" in text:
        handicap_match = re.search(r"([+-])\s*(\d+(?:[,.]\d+)?)", str(row.get("Pick") or ""))
        if handicap_match:
            handicap = float(handicap_match.group(2).replace(",", "."))
            if handicap_match.group(1) == "-":
                handicap = -handicap

            def predicate(stat: pd.Series) -> bool | None:
                margin = diff_values(stat.get("goals_for"), stat.get("goals_against"))
                return None if margin is None else margin + handicap > 0

            return team_matchup_score_reason(
                row,
                match,
                team_stats_df,
                is_home,
                predicate,
                lambda stat: matchup_logic.opponent_supports_goal_handicap(stat, handicap),
                f"saldo + handicap {handicap:g} > 0",
                lambda stat: stat_pair_value(stat, "goals_for", "goals_against"),
                lambda stat: stat_pair_value(stat, "goals_for", "goals_against"),
            )
    if "vence qualquer" in text:
        return team_matchup_score_reason(
            row,
            match,
            team_stats_df,
            is_home,
            matchup_logic.won_any_half,
            matchup_logic.lost_any_half,
            "venceu 1T ou 2T",
        )
    if "vence em ambos" in text:
        return team_matchup_score_reason(
            row,
            match,
            team_stats_df,
            is_home,
            matchup_logic.won_both_halves,
            matchup_logic.lost_both_halves,
            "venceu 1T e 2T",
        )
    if "marca em ambos" in text:
        def predicate(stat: pd.Series) -> bool | None:
            first = stat.get("first_half_goals_for")
            second = team_stat_value(stat, "second_half_goals_for")
            if first is None or second is None or pd.isna(first) or pd.isna(second):
                return None
            return float(first) > 0 and float(second) > 0

        return team_predicate_score_reason(row, team_stats_df, is_home, predicate, "marcou no 1T e 2T", lambda stat: team_stat_value(stat, "goals_for"))
    if "lidera no intervalo" in text:
        return team_matchup_score_reason(
            row,
            match,
            team_stats_df,
            is_home,
            matchup_logic.led_at_half_or_won_match,
            matchup_logic.trailed_at_half_or_lost_match,
            "liderou intervalo ou venceu FT",
        )
    if "escanteio" in text and ("aposta" in text or "mais escanteios" in text):
        if each_half_text(text):
            return team_matchup_score_reason(
                row,
                match,
                team_stats_df,
                is_home,
                matchup_logic.more_corners_each_half,
                matchup_logic.fewer_corners_each_half,
                "mais escanteios em cada tempo",
            )

        def predicate(stat: pd.Series) -> bool | None:
            if stat.get("corners_for") is None or stat.get("corners_against") is None or pd.isna(stat.get("corners_for")) or pd.isna(stat.get("corners_against")):
                return None
            return float(stat.get("corners_for")) > float(stat.get("corners_against"))

        return team_matchup_score_reason(
            row,
            match,
            team_stats_df,
            is_home,
            predicate,
            lambda stat: matchup_logic.less_than(stat, "corners_for", "corners_against"),
            "mais escanteios que adversario",
            lambda stat: stat_pair_value(stat, "corners_for", "corners_against"),
            lambda stat: stat_pair_value(stat, "corners_for", "corners_against"),
        )
    if "mais chutes no gol" in text:
        if each_half_text(text):
            return "N/D", ""

        def predicate(stat: pd.Series) -> bool | None:
            if stat.get("shots_on_target_for") is None or stat.get("shots_on_target_against") is None or pd.isna(stat.get("shots_on_target_for")) or pd.isna(stat.get("shots_on_target_against")):
                return None
            return float(stat.get("shots_on_target_for")) > float(stat.get("shots_on_target_against"))

        return team_matchup_score_reason(
            row,
            match,
            team_stats_df,
            is_home,
            predicate,
            lambda stat: matchup_logic.less_than(stat, "shots_on_target_for", "shots_on_target_against"),
            "mais chutes no gol",
            lambda stat: stat_pair_value(stat, "shots_on_target_for", "shots_on_target_against"),
            lambda stat: stat_pair_value(stat, "shots_on_target_for", "shots_on_target_against"),
        )
    return "N/D", ""


def team_score_reason(
    row: pd.Series,
    team_stats_df: pd.DataFrame,
    is_home: bool | None = None,
    match: pd.Series | None = None,
) -> tuple[str, str]:
    if team_stats_df.empty:
        return "N/D", ""
    if not scoreable_market_row(row):
        return "N/D", ""
    attr = market_score_attr(TEAM_SCORE_ATTRS, row.get("Mercado"))
    if attr:
        items = stat_value_items(team_stats_df, row.get("Time"), attr, SCORE_SAMPLE_LIMIT, is_home)
        if len(items) < MIN_SCORE_SAMPLES:
            return "N/D", ""
        score = score_from_values([item[1] for item in items], line_pick(row.get("Pick")), row.get("Linha"))
        criterion = f"{row.get('Mercado')} {line_pick(row.get('Pick'))} {row.get('Linha')}".strip()
        reason = evidence_from_items("ESPN", items, line_pick(row.get("Pick")), row.get("Linha"), is_home, criterion, row.get("Time"))
        if score != "N/D" and reason:
            return score, reason
    return team_special_score_reason(row, team_stats_df, is_home, match)


def team_score(row: pd.Series, team_stats_df: pd.DataFrame, is_home: bool | None = None, match: pd.Series | None = None) -> str:
    return team_score_reason(row, team_stats_df, is_home, match)[0]


def team_reason(row: pd.Series, team_stats_df: pd.DataFrame, is_home: bool | None = None, match: pd.Series | None = None) -> str:
    return team_score_reason(row, team_stats_df, is_home, match)[1]


def game_line_score_reason(
    row: pd.Series,
    match: pd.Series,
    team_stats_df: pd.DataFrame,
    attr: str,
    criterion: str,
) -> tuple[str, str]:
    attr = period_stat_attr(attr, row)
    if attr is None:
        return "N/D", ""
    pick = line_pick(row.get("Pick"))
    line = row.get("Linha")

    def predicate(stat: pd.Series, _side: str) -> bool | None:
        return line_hit(team_stat_value(stat, attr), pick, line)

    return game_predicate_score_reason(match, team_stats_df, predicate, criterion, lambda stat, _side: team_stat_value(stat, attr))


def game_score_reason(row: pd.Series, match: pd.Series, team_stats_df: pd.DataFrame) -> tuple[str, str]:
    if not scoreable_market_row(row):
        return "N/D", ""
    market_key = str(row.get("market_key") or "")
    text = plain_text(f"{market_key} {row.get('Mercado')} {row.get('Pick')}")
    if market_key == "totals":
        return game_line_score_reason(row, match, team_stats_df, "goals_total", "gols totais")
    if market_key == "totals-corners":
        return game_line_score_reason(row, match, team_stats_df, "corners_total", "escanteios totais")
    if market_key == "totals-bookings":
        return game_line_score_reason(row, match, team_stats_df, "cards_total", "cartoes totais")
    if "cada time" in text and "escanteio" in text and each_half_text(text):
        return game_line_score_reason(row, match, team_stats_df, "corners_each_team_each_half", "cada time com escanteios em cada tempo")
    if "cada time" in text and "escanteio" in text:
        return game_line_score_reason(row, match, team_stats_df, "corners_each_team", "cada time com escanteios")
    if "cada time" in text and "cart" in text:
        return game_line_score_reason(row, match, team_stats_df, "cards_each_team", "cada time com cartoes")
    if "cada time" in text and ("chute" in text or "finaliz" in text) and each_half_text(text):
        return "N/D", ""
    if "cada time" in text and ("chute" in text or "finaliz" in text):
        return game_line_score_reason(row, match, team_stats_df, "shots_on_target_each_team", "cada time com chutes no gol")

    desired = yes_no_pick(row.get("Pick"))
    if "ambos os times marcam dois" in text and desired is not None:
        def predicate(stat: pd.Series, _side: str) -> bool | None:
            if stat.get("goals_for") is None or stat.get("goals_against") is None or pd.isna(stat.get("goals_for")) or pd.isna(stat.get("goals_against")):
                return None
            value = float(stat.get("goals_for")) >= 2 and float(stat.get("goals_against")) >= 2
            return value is desired

        return game_predicate_score_reason(match, team_stats_df, predicate, "ambos 2+ gols", side_scoreline)
    if "ambos os times marcam no primeiro tempo" in text and desired is not None:
        def predicate(stat: pd.Series, _side: str) -> bool | None:
            first_for = stat.get("first_half_goals_for")
            first_against = stat.get("first_half_goals_against")
            if first_for is None or first_against is None or pd.isna(first_for) or pd.isna(first_against):
                return None
            value = float(first_for) > 0 and float(first_against) > 0
            return value is desired

        return game_predicate_score_reason(match, team_stats_df, predicate, "BTTS 1T", lambda stat, side: side_scoreline(stat, side, True))
    if "ambos os times marcam em ambos os tempos" in text and desired is not None:
        def predicate(stat: pd.Series, _side: str) -> bool | None:
            first_for = stat.get("first_half_goals_for")
            first_against = stat.get("first_half_goals_against")
            second_for = team_stat_value(stat, "second_half_goals_for")
            second_against = team_stat_value(stat, "second_half_goals_against")
            if any(value is None or pd.isna(value) for value in [first_for, first_against, second_for, second_against]):
                return None
            value = float(first_for) > 0 and float(first_against) > 0 and float(second_for) > 0 and float(second_against) > 0
            return value is desired

        return game_predicate_score_reason(match, team_stats_df, predicate, "BTTS 1T e 2T", side_scoreline)
    if ("ambos os times marcam" in text or market_key == "btts") and desired is not None:
        def predicate(stat: pd.Series, _side: str) -> bool | None:
            value = stat.get("btts")
            if value is None or pd.isna(value):
                return None
            return bool(value) is desired

        return game_predicate_score_reason(match, team_stats_df, predicate, "BTTS", side_scoreline)
    if "gol marcado em ambos os tempos" in text and desired is not None:
        def predicate(stat: pd.Series, _side: str) -> bool | None:
            first = team_stat_value(stat, "first_half_goals_total")
            second = team_stat_value(stat, "second_half_goals_total")
            if first is None or second is None:
                return None
            value = first > 0 and second > 0
            return value is desired

        return game_predicate_score_reason(match, team_stats_df, predicate, "gol no 1T e 2T", side_total_goals)

    total_range = total_range_from_pick(row.get("Pick"))
    if "faixa de gols" in text and total_range:
        low, high = total_range

        def predicate(stat: pd.Series, _side: str) -> bool | None:
            total = team_stat_value(stat, "goals_total")
            return None if total is None else low <= total <= high

        return game_predicate_score_reason(match, team_stats_df, predicate, f"gols totais entre {low}-{high}", side_total_goals)

    pairs = score_pairs_from_text(row.get("Pick"))
    if "qualquer outro empate" in text:
        def predicate(stat: pd.Series, side: str) -> bool | None:
            actual = side_result(stat, side)
            if actual is None:
                return None
            home_goals = stat.get("goals_for") if side == "home" else stat.get("goals_against")
            away_goals = stat.get("goals_against") if side == "home" else stat.get("goals_for")
            if home_goals is None or away_goals is None or pd.isna(home_goals) or pd.isna(away_goals):
                return None
            return actual == "draw" and (int(home_goals), int(away_goals)) not in {(0, 0), (1, 1)}

        return game_predicate_score_reason(match, team_stats_df, predicate, "empate exceto 0-0/1-1", side_scoreline)
    if "placar correto" in text and pairs:
        def predicate(stat: pd.Series, side: str) -> bool | None:
            home_goals = stat.get("goals_for") if side == "home" else stat.get("goals_against")
            away_goals = stat.get("goals_against") if side == "home" else stat.get("goals_for")
            if home_goals is None or away_goals is None or pd.isna(home_goals) or pd.isna(away_goals):
                return None
            return (int(home_goals), int(away_goals)) in pairs

        return game_predicate_score_reason(match, team_stats_df, predicate, "placar exato", side_scoreline)

    if "intervalo/fim" in text and "/" in str(row.get("Pick") or ""):
        parts = [part.strip() for part in str(row.get("Pick") or "").split("/", 1)]
        first_outcomes = result_outcomes_from_pick(match, parts[0])
        full_outcomes = result_outcomes_from_pick(match, parts[1])
        if first_outcomes and full_outcomes:
            def predicate(stat: pd.Series, side: str) -> bool | None:
                first = side_result(stat, side, True)
                full = side_result(stat, side)
                if first is None or full is None:
                    return None
                return first in first_outcomes and full in full_outcomes

            return game_predicate_score_reason(match, team_stats_df, predicate, "intervalo/fim")
    if "intervalo" in text and "intervalo/fim" not in text:
        outcomes = result_outcomes_from_pick(match, row.get("Pick"))
        if outcomes:
            def predicate(stat: pd.Series, side: str) -> bool | None:
                actual = side_result(stat, side, True)
                return None if actual is None else actual in outcomes

            return game_predicate_score_reason(match, team_stats_df, predicate, "resultado 1T", lambda stat, side: side_scoreline(stat, side, True))

    outcomes = result_outcomes_from_pick(match, row.get("Pick"))
    if outcomes and ("resultado" in text or "chance dupla" in text or "empate sem aposta" in text):
        def predicate(stat: pd.Series, side: str) -> bool | None:
            actual = side_result(stat, side)
            if actual is None:
                return None
            if "empate sem aposta" in text and actual == "draw":
                return None
            hit = actual in outcomes
            if "ambos os times marcam" in text:
                btts = stat.get("btts")
                if btts is None or pd.isna(btts):
                    return None
                hit = hit and bool(btts)
            if "mais/menos" in text or "mais de" in text or "menos de" in text:
                total_hit = line_hit(team_stat_value(stat, "goals_total"), line_pick(row.get("Pick")), row.get("Linha"))
                if total_hit is None:
                    return None
                hit = hit and total_hit
            return hit

        return game_predicate_score_reason(match, team_stats_df, predicate, "resultado historico", side_scoreline)
    return "N/D", ""


def game_total_score(row: pd.Series, team_stats_df: pd.DataFrame, match: pd.Series | None = None) -> str:
    if match is None:
        return "N/D"
    return game_score_reason(row, match, team_stats_df)[0]


def game_total_reason(row: pd.Series, team_stats_df: pd.DataFrame, match: pd.Series | None = None) -> str:
    if match is None:
        return ""
    return game_score_reason(row, match, team_stats_df)[1]


def player_stat_rows(
    row: pd.Series,
    player_stats_df: pd.DataFrame,
    attr: str,
    is_home: bool | None = None,
) -> pd.DataFrame:
    player_key = plain_text(row.get("Jogador"))
    if player_stats_df.empty or not player_key or attr not in player_stats_df.columns:
        return pd.DataFrame()
    rows = player_stats_df[
        player_stats_df["player_name"].apply(
            lambda value: plain_text(value) == player_key or player_key in plain_text(value) or plain_text(value) in player_key
        )
    ].copy()
    if not rows.empty and row.get("Time"):
        rows = rows[rows["team_name"].apply(lambda value: teams_match(value, row.get("Time")))]
    if rows.empty:
        return rows
    if is_home is not None and "is_home" in rows.columns:
        rows = rows[rows["is_home"].notna()].copy()
        rows = rows[rows["is_home"].astype(bool) == is_home]
        if rows.empty:
            return rows
    rows = rows[rows[attr].notna()].copy()
    if rows.empty:
        return rows
    rows["_source_rank"] = rows["source"].map(SOURCE_PRIORITY).fillna(99) if "source" in rows.columns else 99
    rows = rows.sort_values(["match_date", "_source_rank"], ascending=[False, True])
    return rows.drop_duplicates(["match_date"], keep="first").head(SCORE_SAMPLE_LIMIT)


def player_score(row: pd.Series, player_stats_df: pd.DataFrame, is_home: bool | None = None) -> str:
    if player_stats_df.empty:
        return "N/D"
    if not scoreable_market_row(row) or unsupported_player_period_market(row_market_text(row)):
        return "N/D"
    attr = market_score_attr(PLAYER_SCORE_ATTRS, row.get("Mercado"))
    if not attr:
        return "N/D"
    rows = player_stat_rows(row, player_stats_df, attr, is_home)
    if len(rows) < MIN_SCORE_SAMPLES:
        return "N/D"
    return score_from_values(list(rows[attr]), line_pick(row.get("Pick")), row.get("Linha"))


def player_reason(row: pd.Series, player_stats_df: pd.DataFrame, is_home: bool | None = None) -> str:
    if player_stats_df.empty:
        return ""
    if not scoreable_market_row(row) or unsupported_player_period_market(row_market_text(row)):
        return ""
    attr = market_score_attr(PLAYER_SCORE_ATTRS, row.get("Mercado"))
    if not attr:
        return ""
    rows = player_stat_rows(row, player_stats_df, attr, is_home)
    if len(rows) < MIN_SCORE_SAMPLES:
        return ""
    items = []
    for _, stat in rows.iterrows():
        value = stat.get(attr)
        if value is None or pd.isna(value):
            continue
        items.append((str(stat.get("match_date")), float(value), str(stat.get("source") or "")))
    criterion = f"{row.get('Mercado')} {line_pick(row.get('Pick'))} {row.get('Linha')}".strip()
    return evidence_from_items("ESPN", items, line_pick(row.get("Pick")), row.get("Linha"), is_home, criterion, row.get("Jogador"))


def player_score_reason(row: pd.Series, player_stats_df: pd.DataFrame, is_home: bool | None = None) -> tuple[str, str]:
    if player_stats_df.empty:
        return "N/D", ""
    if not scoreable_market_row(row) or unsupported_player_period_market(row_market_text(row)):
        return "N/D", ""
    attr = market_score_attr(PLAYER_SCORE_ATTRS, row.get("Mercado"))
    if not attr:
        return "N/D", ""
    rows = player_stat_rows(row, player_stats_df, attr, is_home)
    if len(rows) < MIN_SCORE_SAMPLES:
        return "N/D", ""
    score = score_from_values(list(rows[attr]), line_pick(row.get("Pick")), row.get("Linha"))
    items = []
    for _, stat in rows.iterrows():
        value = stat.get(attr)
        if value is None or pd.isna(value):
            continue
        items.append((str(stat.get("match_date")), float(value), str(stat.get("source") or "")))
    criterion = f"{row.get('Mercado')} {line_pick(row.get('Pick'))} {row.get('Linha')}".strip()
    reason = evidence_from_items("ESPN", items, line_pick(row.get("Pick")), row.get("Linha"), is_home, criterion, row.get("Jogador"))
    return score, reason


def source_reason(row: pd.Series) -> str:
    parts = ["Odd real", row.get("Fonte"), row.get("Casa")]
    team = row.get("Time")
    if team and str(team) != "Jogo":
        parts.append(team)
    return " | ".join(str(part) for part in parts if part and str(part).strip())


def market_label(value: object) -> str:
    labels = {
        "over_15": "Gols",
        "over_25": "Gols",
        "btts": "Ambas marcam",
    }
    return labels.get(str(value), str(value))


def period_label(value: object) -> str:
    text = plain_text(value)
    if "first half" in text or "1st half" in text or "primeiro tempo" in text:
        return "1T"
    if "second half" in text or "2nd half" in text or "segundo tempo" in text:
        return "2T"
    if "full time" in text or "tempo regulamentar" in text:
        return "FT"
    return ""


def game_market_label(market_type: object, market_name: object) -> str:
    if str(market_type) in {"betfair-result", "betfair-team-shots", "betfair-team-shots-on-target"} and market_name:
        return str(market_name)
    base = GAME_MARKETS.get(str(market_type)) or str(market_name or market_type)
    period = period_label(market_name)
    return f"{base} - {period}" if period else base


def game_section(row: pd.Series) -> str:
    text = plain_text(f"{row.get('Mercado')} {row.get('market_key')}")
    if "gol" in text or "ambas" in text:
        return "Gols"
    if "resultado" in text or "chance dupla" in text or "empate sem aposta" in text:
        return "Resultado"
    if "escanteio" in text or "corner" in text:
        return "Escanteios"
    if "cart" in text or "booking" in text:
        return "Cartões"
    return "Outros"


def game_team_name(match: pd.Series, raw: dict, market_type: object) -> str:
    team = raw.get("team_name")
    if team:
        return str(team)
    market = str(market_type or "")
    side = raw.get("team_side")
    if market.endswith("team1") or side == "home":
        return str(match.get("home_team"))
    if market.endswith("team2") or side == "away":
        return str(match.get("away_team"))
    return "Jogo"


def teamtotals_against_label(market_type: object) -> str | None:
    market = str(market_type or "")
    if "goals" in market:
        return "Gols sofridos"
    if "corners" in market:
        return "Escanteios contra"
    if "bookings" in market:
        return "Cartões contra"
    return None


def match_base(match: pd.Series) -> dict[str, object]:
    return {
        "Data": format_match_date(match),
        "Liga": match.get("league_name"),
        "Casa": match.get("home_team"),
        "Fora": match.get("away_team"),
    }


def popular_player_name(value: object) -> str:
    text = str(value or "").strip()
    normalized = plain_text(text)
    if not normalized or normalized in {"empate", "o empate", "nenhum", "sem gol", "sem marcador"}:
        return ""
    if any(token in normalized for token in ["qualquer outro", "cada time", " ou ", "cartoes no total"]):
        return ""
    if re.search(r"\be\b", normalized):
        return ""
    return text


def unsupported_snapshot_market(raw: dict, market_key: object, market_name: object) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            market_key,
            market_name,
            raw.get("market_type_raw"),
            raw.get("runner_name"),
            raw.get("outcome_name"),
        )
    )
    if unsupported_compound_market(text):
        return True
    if str(raw.get("market_type_raw") or "").upper() == "ODDSBOOST":
        return True
    if plain_text(market_key).startswith("betfair-oddsboost"):
        return True
    return False


def team_prop_market(raw: dict, market_name: object) -> bool:
    team_name = raw.get("team_name")
    if not team_name:
        return False
    text = plain_text(market_name)
    player_name = raw.get("player_name")
    return text.startswith("equipe ") or teams_match(player_name, team_name)


def team_prop_label(market_name: object) -> str:
    text = plain_text(market_name)
    if "falta" in text and ("sofr" in text or "receb" in text):
        return "Faltas sofridas"
    if "falta" in text:
        return "Faltas cometidas"
    return str(market_name or "")


def player_market_label(market_type: object, market_name: object) -> str | None:
    text = plain_text(market_name)
    if "envolvimento" in text and "falta" in text:
        return "Envolvimentos em faltas"
    return PLAYER_MARKETS.get(market_type)


def odds_rows_for_match(match: pd.Series, snapshots_df: pd.DataFrame) -> pd.DataFrame:
    if snapshots_df.empty:
        return pd.DataFrame()

    rows = []
    latest = snapshots_df.copy()
    if {"raw_home_team", "raw_away_team"}.issubset(latest.columns):
        latest = latest[
            latest.apply(
                lambda row: teams_pair_match(
                    row.get("raw_home_team"),
                    row.get("raw_away_team"),
                    match.get("home_team"),
                    match.get("away_team"),
                ),
                axis=1,
            )
        ]
        if latest.empty:
            return pd.DataFrame()
    latest["fetched_at"] = parse_datetime(latest["fetched_at"])
    latest = latest.sort_values("fetched_at")

    for _, snap in latest.iterrows():
        if not snapshot_matches_game(snap, match):
            continue
        raw = snapshot_raw(snap)
        market_type = raw.get("market_type") or snap.get("market_key")
        market_name = raw.get("market_name") or market_type
        team_goal_side = team_goal_market_side(raw, market_name, snap.get("market_type_raw"))
        team_goal_key = team_goal_market_key(team_goal_side)
        if team_goal_key:
            market_type = team_goal_key
            raw["team_side"] = team_goal_side
            raw["team_name"] = match.get("home_team") if team_goal_side == "home" else match.get("away_team")
        if unsupported_snapshot_market(raw, market_type, market_name):
            continue
        pick = raw.get("outcome_name") or snap.get("outcome_name")
        point = raw.get("point") if raw.get("point") is not None else snap.get("point")
        price = snap.get("price")
        if pd.isna(price):
            continue
        if snap.get("source") == "betfair-web":
            if plain_text(pick) == "linha":
                continue
            if not coherent_snapshot_point(market_name, point):
                continue

        market_type_text = str(market_type)
        popular_player = POPULAR_PLAYER_MARKETS.get(market_type)
        is_team_prop = team_prop_market(raw, market_name)
        is_player = (market_type in PLAYER_MARKETS or popular_player is not None) and not is_team_prop
        is_popular = market_type_text.startswith(("betfair-popular", "betfair-oddsboost"))
        is_game = ((market_type in GAME_MARKETS or is_popular) and not is_player) or is_team_prop
        if not is_player and not is_game:
            continue
        player_name = raw.get("player_name") or ""
        if is_player and unsupported_player_period_market(market_name):
            continue
        market_label = team_prop_label(market_name) if is_team_prop else player_market_label(market_type, market_name)
        pick_value = pick
        line_value = point
        if popular_player:
            market_label = popular_player[0]
            player_name = popular_player_name(pick)
            if not player_name:
                continue
            pick_value = "Over"
            line_value = 0.5
        team = game_team_name(match, raw, market_type) if is_game else (raw.get("team_name") or "")
        base_row = {
            "Tipo": "Jogador" if is_player else "Jogo",
            "Mercado": market_label or game_market_label(market_type, market_name),
            "Time": team,
            "Jogador": player_name,
            "Pick": pick_value,
            "Linha": format_point(line_value),
            "ODD": float(price),
            "Casa": snap.get("bookmaker"),
            "Fonte": snap.get("source"),
            "main_line": raw.get("main_line"),
            "market_key": market_type,
            "market_name": market_name,
            "market_type_raw": raw.get("market_type_raw") or snap.get("market_type_raw"),
            "runner_name": raw.get("runner_name") or snap.get("runner_name"),
        }
        rows.append(base_row)

        if is_game and team != "Jogo" and "teamtotals" in str(market_type):
            opponent = raw.get("away_team") if teams_match(team, raw.get("home_team")) else raw.get("home_team")
            contra_label = teamtotals_against_label(market_type)
            if contra_label:
                contra = dict(base_row)
                contra["Time"] = opponent or ""
                contra["Mercado"] = contra_label
                rows.append(contra)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    keys = ["Tipo", "Mercado", "Time", "Jogador", "Pick", "Linha"]
    idx = []
    for _, group in df.groupby(keys, dropna=False):
        if group["Fonte"].astype(str).eq("betfair-web").all():
            idx.append(group["ODD"].idxmin())
        else:
            idx.append(group["ODD"].idxmax())
    return df.loc[idx].sort_values(["Tipo", "Mercado", "Time", "Jogador", "Linha", "Pick"]).reset_index(drop=True)


def lineup_rows_for_match(match: pd.Series, lineups_df: pd.DataFrame, starter_only: bool = True) -> pd.DataFrame:
    if lineups_df.empty:
        return pd.DataFrame()
    source_match_id = str(match.get("source_match_id") or "")
    rows = lineups_df[lineups_df["source_match_id"].astype(str) == source_match_id].copy()
    if starter_only:
        rows = rows[rows["starter"].astype(bool)]
    return rows.sort_values(["team_name", "starter", "position", "player_name"], ascending=[True, False, True, True]).reset_index(drop=True)


def bool_from_db(value: object, default: bool = False) -> bool:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "sim"}
    return bool(value)


def roster_columns(rows: pd.DataFrame) -> pd.DataFrame:
    output = rows.copy()
    for column in ["source_match_id", "player_name", "team_name", "starter", "position", "jersey"]:
        if column not in output.columns:
            output[column] = None
    output["starter"] = output["starter"].apply(bool_from_db)
    return output[["source_match_id", "player_name", "team_name", "starter", "position", "jersey"]]


def dedupe_by_plain_name(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    temp_df = df.copy()
    temp_df["_plain_name"] = temp_df["player_name"].apply(plain_text)
    temp_df["_plain_team"] = temp_df["team_name"].apply(plain_text)
    return temp_df.drop_duplicates(["_plain_name", "_plain_team"], keep="first").drop(columns=["_plain_name", "_plain_team"])


def latest_lineup_rows_for_team(lineups_df: pd.DataFrame, team_name: object) -> pd.DataFrame:
    if lineups_df.empty:
        return pd.DataFrame()
    rows = lineups_df[lineups_df["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
    if rows.empty:
        return rows
    if "match_date" in rows.columns:
        rows = rows.sort_values(["match_date", "source_match_id"], ascending=[False, False])
        latest_date = rows["match_date"].dropna().max()
        if latest_date:
            rows = rows[rows["match_date"].eq(latest_date)]
    return dedupe_by_plain_name(
        roster_columns(rows).sort_values(
            ["starter", "position", "player_name"],
            ascending=[False, True, True],
        )
    ).reset_index(drop=True)


def latest_player_rows_from_stats(player_stats_df: pd.DataFrame, team_name: object) -> pd.DataFrame:
    if player_stats_df.empty:
        return pd.DataFrame()
    rows = player_stats_df[player_stats_df["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
    if rows.empty or "match_date" not in rows.columns:
        return pd.DataFrame()
    latest_date = rows["match_date"].dropna().max()
    if not latest_date:
        return pd.DataFrame()
    rows = rows[rows["match_date"].eq(latest_date)].copy()
    if rows.empty:
        return rows
    if "starter" not in rows.columns or not rows["starter"].notna().any():
        rows["starter"] = True
    return dedupe_by_plain_name(
        roster_columns(rows).sort_values(["starter", "position", "player_name"], ascending=[False, True, True])
    ).reset_index(drop=True)


def player_rows_for_match_team(
    match: pd.Series,
    lineups_df: pd.DataFrame,
    player_stats_df: pd.DataFrame,
    team_name: object,
) -> pd.DataFrame:
    rows = lineup_rows_for_match(match, lineups_df, starter_only=False)
    if not rows.empty:
        rows = rows[rows["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
    if not rows.empty:
        return dedupe_by_plain_name(roster_columns(rows))

    rows = latest_lineup_rows_for_team(lineups_df, team_name)
    if not rows.empty:
        return rows

    return latest_player_rows_from_stats(player_stats_df, team_name)


def player_team_index(match: pd.Series, lineups_df: pd.DataFrame) -> dict[str, str]:
    rows = lineup_rows_for_match(match, lineups_df)
    if rows.empty:
        return {}
    return {plain_text(row.get("player_name")): str(row.get("team_name")) for _, row in rows.iterrows()}


def player_history_team_index(match: pd.Series, player_stats_df: pd.DataFrame) -> dict[str, str]:
    if player_stats_df.empty:
        return {}
    rows = player_stats_df[
        player_stats_df["team_name"].apply(
            lambda value: teams_match(value, match.get("home_team")) or teams_match(value, match.get("away_team"))
        )
    ].copy()
    if rows.empty:
        return {}
    rows = rows.sort_values("match_date", ascending=False)
    return {
        plain_text(row.get("player_name")): str(row.get("team_name"))
        for _, row in rows.drop_duplicates("player_name", keep="first").iterrows()
    }


def lineup_placeholders(match: pd.Series, lineups_df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    rows = lineup_rows_for_match(match, lineups_df)
    if rows.empty:
        return pd.DataFrame()
    rows = rows[rows["team_name"].apply(lambda value: teams_match(value, team_name))]
    output = []
    for _, player in rows.iterrows():
        for market in PLAYER_REQUESTED_MARKETS:
            output.append(
                {
                    "Jogador": player.get("player_name"),
                    "Time": player.get("team_name"),
                    "Mercado": market,
                    "Pick": "Over",
                    "Linha": "",
                    "ODD": "N/D",
                    "Score": "N/D",
                    "Motivo": "Sem odd real | ESPN titular",
                }
            )
    return pd.DataFrame(output)


def model_rows_for_match(match: pd.Series, display_df: pd.DataFrame, team_stats_df: pd.DataFrame) -> pd.DataFrame:
    if display_df.empty:
        return pd.DataFrame()
    mask = display_df.apply(
        lambda row: teams_match(row.get("Casa"), match.get("home_team")) and teams_match(row.get("Fora"), match.get("away_team")),
        axis=1,
    )
    rows = display_df.loc[mask].copy()
    if rows.empty:
        return pd.DataFrame()
    base = match_base(match)
    output = pd.DataFrame(
        {
            "Data": base["Data"],
            "Liga": base["Liga"],
            "Casa": base["Casa"],
            "Fora": base["Fora"],
            "Time": "Jogo",
            "Mercado": rows["market_key"].map(market_label),
            "Pick": rows["Pick"],
            "Linha": rows["market_key"].map(MODEL_LINES).fillna(""),
            "ODD": rows["ODD"],
            "Score": rows.apply(lambda source_row: model_score(match, source_row.get("market_key"), team_stats_df), axis=1),
            "Motivo": rows["Motivo"],
            "market_key": rows["market_key"],
        }
    )
    output["Motivo"] = output.apply(
        lambda row: model_reason(match, rows.loc[row.name, "market_key"], team_stats_df) or row.get("Motivo"),
        axis=1,
    )
    return output


def game_market_rows(
    match: pd.Series,
    display_df: pd.DataFrame,
    odds_rows: pd.DataFrame,
    team_stats_df: pd.DataFrame,
) -> pd.DataFrame:
    game_rows = odds_rows[odds_rows["Tipo"] == "Jogo"].copy() if not odds_rows.empty else pd.DataFrame()
    if not game_rows.empty:
        game_rows = game_rows[game_rows["Time"].astype(str).eq("Jogo")]
        base = match_base(match)
        game_rows["Data"] = base["Data"]
        game_rows["Liga"] = base["Liga"]
        game_rows["Casa"] = base["Casa"]
        game_rows["Fora"] = base["Fora"]
        game_rows["ODD"] = game_rows["ODD"].map(display_odd)
        scored = game_rows.apply(lambda row: game_score_reason(row, match, team_stats_df), axis=1)
        game_rows["Score"] = scored.map(lambda value: value[0])
        game_rows["Motivo"] = scored.map(lambda value: value[1])
        game_rows = game_rows[GAME_COLUMNS + ["market_key"]]
    model = model_rows_for_match(match, display_df, team_stats_df)
    combined = pd.concat([model, game_rows], ignore_index=True)
    if not combined.empty:
        for column in combined.columns:
            combined[column] = combined[column].astype(str)
        combined = combined[combined["ODD"].ne("N/D")]
        combined = filter_scored_rows(combined)
    return combined


def team_market_rows(match: pd.Series, odds_rows: pd.DataFrame, team_stats_df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    if odds_rows.empty:
        return pd.DataFrame()

    rows = odds_rows[(odds_rows["Tipo"] == "Jogo") & (odds_rows["Time"].astype(str).ne("Jogo"))].copy()
    if rows.empty:
        return pd.DataFrame()

    rows = rows[rows["Time"].apply(lambda value: teams_match(value, team_name))]
    if rows.empty:
        return pd.DataFrame()

    is_home = teams_match(team_name, match.get("home_team"))
    scored = rows.apply(lambda row: team_score_reason(row, team_stats_df, is_home, match), axis=1)
    rows["Score"] = scored.map(lambda value: value[0])
    rows["Motivo"] = scored.map(lambda value: value[1])
    rows["Odd"] = rows["ODD"].map(display_odd)
    rows = rows[TEAM_COLUMNS]
    rows = rows[rows["Odd"].ne("N/D")]
    rows = filter_scored_rows(rows)
    rows = rows.drop_duplicates(["Time", "Mercado", "Pick", "Linha", "Odd"], keep="first")
    return rows.sort_values(["Mercado", "Linha", "Pick"]).reset_index(drop=True)


def safe_key(*parts: object) -> str:
    text = "-".join(plain_text(part) for part in parts)
    return "".join(char if char.isalnum() else "-" for char in text).strip("-")


def toggle_match(match_key: str) -> None:
    open_matches = st.session_state.setdefault("open_matches", [])
    if match_key in open_matches:
        open_matches.remove(match_key)
    else:
        open_matches.append(match_key)


def toggle_player_stats(player_key: str) -> None:
    open_players = st.session_state.setdefault("open_player_stats", [])
    if player_key in open_players:
        open_players.remove(player_key)
    else:
        open_players.append(player_key)


def toggle_player_group(group_key: str) -> None:
    open_groups = st.session_state.setdefault("open_player_groups", [])
    if group_key in open_groups:
        open_groups.remove(group_key)
    else:
        open_groups.append(group_key)


def render_game_market_sections(game_rows: pd.DataFrame, match_key: str) -> None:
    if game_rows.empty:
        render_table(pd.DataFrame(columns=GAME_MARKET_COLUMNS))
        return
    rows = game_rows.copy()
    rows["_section"] = rows.apply(game_section, axis=1)
    for section in ["Resultado", *GAME_SECTIONS]:
        section_rows = rows[rows["_section"] == section].drop(columns=["_section", "market_key"], errors="ignore")
        if section_rows.empty:
            continue
        with st.expander(section, expanded=True):
            render_table(section_rows[GAME_MARKET_COLUMNS])


def game_market_sections_html(game_rows: pd.DataFrame, sortable: bool = False) -> str:
    if game_rows.empty:
        return prediction_table_html(pd.DataFrame(columns=GAME_MARKET_COLUMNS), GAME_MARKET_COLUMNS, sortable=sortable)
    rows = game_rows.copy()
    rows["_section"] = rows.apply(game_section, axis=1)
    parts = []
    for section in ["Resultado", *GAME_SECTIONS]:
        section_rows = rows[rows["_section"] == section].drop(columns=["_section", "market_key"], errors="ignore")
        if section_rows.empty:
            continue
        body = prediction_table_html(section_rows, GAME_MARKET_COLUMNS, sortable=sortable)
        parts.append(prediction_details_html(f"{section} ({len(section_rows)})", body, True))
    return "".join(parts) or prediction_table_html(pd.DataFrame(columns=GAME_MARKET_COLUMNS), GAME_MARKET_COLUMNS, sortable=sortable)


def prediction_grid_html(*sections: str) -> str:
    return f'<div class="predictions-grid">{"".join(sections)}</div>'


def prediction_rows_for_match(prediction_rows: pd.DataFrame, match: pd.Series) -> pd.DataFrame:
    if prediction_rows.empty:
        return prediction_rows
    source_match_id = str(match.get("source_match_id") or "")
    if source_match_id and "_source_match_id" in prediction_rows.columns:
        rows = prediction_rows[prediction_rows["_source_match_id"].astype(str).eq(source_match_id)].copy()
        if not rows.empty:
            return rows
    return prediction_rows[
        prediction_rows["Casa"].apply(lambda value: teams_match(value, match.get("home_team")))
        & prediction_rows["Fora"].apply(lambda value: teams_match(value, match.get("away_team")))
    ].copy()


def render_predictions_tab(matches_df: pd.DataFrame, prediction_rows: pd.DataFrame) -> None:
    if matches_df.empty:
        st.info("Sem jogos para a data.")
        return
    if prediction_rows.empty:
        st.info("Sem mercados.")
        return

    match_sections = []
    prediction_rows = prediction_rows.copy()
    prediction_rows["_match_group_key"] = prediction_rows.apply(best_bets_match_key, axis=1)

    for _, match in matches_df.iterrows():
        title = f"{format_match_date(match)} | {match.get('home_team')} x {match.get('away_team')}"
        match_rows = prediction_rows_for_match(prediction_rows, match)
        game_rows = match_rows[match_rows["Tipo"].astype(str).eq("Jogo")].copy()
        team_rows = match_rows[match_rows["Tipo"].astype(str).eq("Time")].copy()
        player_rows = match_rows[match_rows["Tipo"].astype(str).eq("Jogador")].copy()
        home_team_markets = team_rows[team_rows["Time"].apply(lambda value: teams_match(value, match.get("home_team")))].copy()
        away_team_markets = team_rows[team_rows["Time"].apply(lambda value: teams_match(value, match.get("away_team")))].copy()
        home_players = player_rows[player_rows["Time"].apply(lambda value: teams_match(value, match.get("home_team")))].copy()
        away_players = player_rows[player_rows["Time"].apply(lambda value: teams_match(value, match.get("away_team")))].copy()

        game_html = prediction_details_html("Mercados do jogo", game_market_sections_html(game_rows, sortable=True), True)
        teams_html = prediction_grid_html(
            prediction_details_html(
                f"Mercados time {match.get('home_team')}",
                prediction_table_html(home_team_markets, TEAM_MARKET_COLUMNS, "Sem odds reais do time.", sortable=True),
                True,
            ),
            prediction_details_html(
                f"Mercados time {match.get('away_team')}",
                prediction_table_html(away_team_markets, TEAM_MARKET_COLUMNS, "Sem odds reais do time.", sortable=True),
                True,
            ),
        )
        players_html = prediction_grid_html(
            prediction_details_html(
                f"Mercado jogadores {match.get('home_team')}",
                prediction_table_html(home_players, PLAYER_MARKET_COLUMNS, "Sem odds reais de jogadores.", sortable=True),
                True,
            ),
            prediction_details_html(
                f"Mercado jogadores {match.get('away_team')}",
                prediction_table_html(away_players, PLAYER_MARKET_COLUMNS, "Sem odds reais de jogadores.", sortable=True),
                True,
            ),
        )
        body = "".join([game_html, teams_html, players_html])
        match_sections.append(prediction_details_html(title, body, False, "predictions-match"))

    components.html(
        predictions_component_document(f'<div class="predictions-feed">{"".join(match_sections)}</div>', auto_resize=True),
        height=predictions_component_height(prediction_rows, open_all=False),
        scrolling=True,
    )


def stat_display_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/D"
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def competition_display_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "N/D"
    normalized = plain_text(text)
    if "copa do brasil" in normalized:
        return "Copa BR"
    if "brazilian serie a" in normalized:
        return "Serie A"
    if "brazilian serie b" in normalized:
        return "Serie B"
    if "premier league" in normalized:
        return "Premier"
    if "libertadores" in normalized:
        return "Libertadores"
    if "sul americana" in normalized or "sudamericana" in normalized:
        return "Sul Americana"
    if "champions league" in normalized:
        return "Champions"
    if "europa league" in normalized:
        return "Europa"
    return text[:12]


def team_match_history(
    team_stats_df: pd.DataFrame,
    team_name: object,
    is_home: bool,
    limit: int = STATS_DISPLAY_GAMES,
) -> pd.DataFrame:
    if team_stats_df.empty or "is_home" not in team_stats_df.columns:
        return pd.DataFrame()
    rows = team_stats_df[team_stats_df["team_name"].apply(lambda value: teams_match(value, team_name))].copy()
    if rows.empty:
        return rows
    rows = rows[rows["is_home"].notna()].copy()
    if rows.empty:
        return rows
    rows = rows[rows["is_home"].astype(bool) == is_home]
    if rows.empty:
        return rows
    rows["_source_rank"] = rows["source"].map(SOURCE_PRIORITY).fillna(99) if "source" in rows.columns else 99
    rows = rows.sort_values(["match_date", "_source_rank"], ascending=[False, True])
    return rows.drop_duplicates(["match_date"], keep="first").head(limit)


def team_stats_row(label: str, values: list[object], average: object = "N/D") -> dict[str, object]:
    row = {"Estatística": label}
    for index in range(STATS_DISPLAY_GAMES):
        row[f"Jogo {index + 1}"] = values[index] if index < len(values) else "N/D"
    row["Média"] = average
    return row


def result_display_value(row: pd.Series) -> str:
    goals_for = row.get("goals_for")
    goals_against = row.get("goals_against")
    if goals_for is None or goals_against is None or pd.isna(goals_for) or pd.isna(goals_against):
        return "N/D"
    if float(goals_for) > float(goals_against):
        return "Vitória"
    if float(goals_for) < float(goals_against):
        return "Derrota"
    return "Empate"


def build_team_stats_table(team_stats_df: pd.DataFrame, team_name: object, is_home: bool) -> pd.DataFrame:
    output = []
    history = team_match_history(team_stats_df, team_name, is_home)
    result_values = [result_display_value(row) for _, row in history.iterrows()] if not history.empty else []
    result_row = team_stats_row("Resultado", result_values)
    for label, attr in TEAM_STAT_CATEGORIES:
        values = list(history[attr]) if not history.empty and attr in history.columns else []
        clean_values = [float(value) for value in values if value is not None and not pd.isna(value)]
        display_values = [stat_display_value(value) for value in values]
        average = stat_display_value(sum(clean_values) / len(clean_values)) if clean_values else "N/D"
        output.append(team_stats_row(label, display_values, average))
        if label == "Faltas sofridas":
            output.append(result_row)
    leagues = list(history["league_name"]) if not history.empty and "league_name" in history.columns else []
    opponents = list(history["opponent_name"]) if not history.empty and "opponent_name" in history.columns else []
    output.append(team_stats_row("Competição", [competition_display_value(value) for value in leagues]))
    output.append(team_stats_row("Adversário", [str(value) if value and not pd.isna(value) else "N/D" for value in opponents]))
    return pd.DataFrame(output)


def team_stats_key(match_key: str, team_name: object) -> str:
    return safe_key("team-stats", match_key, team_name)


def team_stats_html_table(table: pd.DataFrame) -> str:
    return table.to_html(index=False, escape=True, classes="team-stats-table", border=0)


def render_team_stats_group(team_stats_df: pd.DataFrame, team_name: object, title: str, is_home: bool) -> str:
    table = build_team_stats_table(team_stats_df, team_name, is_home)
    return (
        "<details>"
        f"<summary>{escape(title)}</summary>"
        '<div class="team-stats-body">'
        f"{team_stats_html_table(table)}"
        "</div>"
        "</details>"
    )


def render_team_stats_block(team_stats_df: pd.DataFrame, team_name: object, match_key: str) -> str:
    team_key = team_stats_key(match_key, team_name)
    home_html = render_team_stats_group(team_stats_df, team_name, "Jogos como mandante", True)
    away_html = render_team_stats_group(team_stats_df, team_name, "Jogos como visitante", False)
    return (
        f'<details class="team-stats-team" id="{team_key}">'
        f"<summary>{escape(str(team_name))}</summary>"
        '<div class="team-stats-body team-stats-split">'
        f"{home_html}"
        f"{away_html}"
        "</div>"
        "</details>"
    )


def render_team_statistics_tab(matches_df: pd.DataFrame, team_stats_df: pd.DataFrame) -> None:
    if matches_df.empty:
        st.info("Sem jogos para a data.")
        return
    for index, (_, match) in enumerate(matches_df.iterrows()):
        label = f"{format_match_date(match)} | {match.get('home_team')} x {match.get('away_team')}"
        with st.expander(label, expanded=index == 0):
            match_key = safe_key("team-match", match.get("match_id"), match.get("home_team"), match.get("away_team"))
            home_html = render_team_stats_block(team_stats_df, match.get("home_team"), match_key)
            away_html = render_team_stats_block(team_stats_df, match.get("away_team"), match_key)
            st.markdown(
                f'<div class="team-stats-match-grid">{home_html}{away_html}</div>',
                unsafe_allow_html=True,
            )


def player_stat_history(
    player_stats_df: pd.DataFrame,
    player_name: object,
    team_name: object,
    attr: str,
    is_home: bool,
    limit: int = STATS_DISPLAY_GAMES,
) -> pd.DataFrame:
    player_key = plain_text(player_name)
    if player_stats_df.empty or not player_key or attr not in player_stats_df.columns or "is_home" not in player_stats_df.columns:
        return pd.DataFrame()
    rows = player_stats_df[
        player_stats_df["player_name"].apply(
            lambda value: plain_text(value) == player_key or player_key in plain_text(value) or plain_text(value) in player_key
        )
    ].copy()
    if rows.empty:
        return rows
    rows = rows[rows["team_name"].apply(lambda value: teams_match(value, team_name))]
    rows = rows[rows["is_home"].notna()].copy()
    if rows.empty:
        return rows
    rows = rows[rows["is_home"].astype(bool) == is_home]
    rows = rows[rows[attr].notna()].copy()
    if rows.empty:
        return rows
    rows["_source_rank"] = rows["source"].map(SOURCE_PRIORITY).fillna(99) if "source" in rows.columns else 99
    rows = rows.sort_values(["match_date", "_source_rank"], ascending=[False, True])
    return rows.drop_duplicates(["match_date"], keep="first").head(limit)


def build_player_stats_table(player_stats_df: pd.DataFrame, player: pd.Series, is_home: bool) -> pd.DataFrame:
    output = []
    league_row = {"Estatística": "Competição"}
    opponent_row = {"Estatística": "Adversário"}
    for label, attr in PLAYER_STAT_CATEGORIES:
        history = player_stat_history(player_stats_df, player.get("player_name"), player.get("team_name"), attr, is_home)
        values = list(history[attr]) if not history.empty else []
        if label == "Finalizações":
            opponents = list(history["opponent_name"]) if not history.empty and "opponent_name" in history.columns else []
            leagues = list(history["league_name"]) if not history.empty and "league_name" in history.columns else []
            for index in range(STATS_DISPLAY_GAMES):
                if index >= len(opponents) or not opponents[index] or pd.isna(opponents[index]):
                    opponent_row[f"Jogo {index + 1}"] = "N/D"
                    league_row[f"Jogo {index + 1}"] = "N/D"
                    continue
                opponent_row[f"Jogo {index + 1}"] = str(opponents[index])
                league_row[f"Jogo {index + 1}"] = competition_display_value(leagues[index] if index < len(leagues) else "")
        clean_values = [float(value) for value in values if value is not None and not pd.isna(value)]
        if not clean_values:
            continue
        row = {"Estatística": label}
        for index in range(STATS_DISPLAY_GAMES):
            row[f"Jogo {index + 1}"] = stat_display_value(values[index]) if index < len(values) else "N/D"
        row["Média"] = stat_display_value(sum(clean_values) / len(clean_values)) if clean_values else "N/D"
        output.append(row)
    if not output:
        return pd.DataFrame()
    league_row["Média"] = ""
    opponent_row["Média"] = ""
    output.append(league_row)
    output.append(opponent_row)
    return pd.DataFrame(output)


def player_display_name(player: pd.Series) -> str:
    parts = []
    jersey = str(player.get("jersey") or "").strip()
    position = str(player.get("position") or "").strip()
    if jersey:
        parts.append(f"#{jersey}")
    if position:
        parts.append(position)
    parts.append(str(player.get("player_name") or "Jogador N/D"))
    return " | ".join(parts)


def player_stats_key(match_key: str, player: pd.Series) -> str:
    return safe_key("player-stats", match_key, player.get("team_name"), player.get("player_name"))


def render_player_stats_cards(player_stats_df: pd.DataFrame, players_df: pd.DataFrame, match_key: str, empty_label: str) -> None:
    if players_df.empty:
        st.caption(empty_label)
        return
    for _, player in players_df.iterrows():
        player_key = player_stats_key(match_key, player)
        is_open = player_key in st.session_state.setdefault("open_player_stats", [])
        arrow = "[-]" if is_open else "[+]"
        st.button(
            f"{arrow}  {player_display_name(player)}",
            key=f"player_stats_button_{player_key}",
            use_container_width=True,
            on_click=toggle_player_stats,
            args=(player_key,),
        )
        if not is_open:
            continue

        home_table = build_player_stats_table(player_stats_df, player, True)
        away_table = build_player_stats_table(player_stats_df, player, False)
        if home_table.empty and away_table.empty:
            st.caption("Sem histórico preenchido para jogador.")
            continue
        home_col, away_col = st.columns(2)
        with home_col:
            st.markdown("**Jogos como mandante**")
            if home_table.empty:
                st.caption("Sem dados.")
            else:
                st.dataframe(home_table, width="stretch", hide_index=True, height=dataframe_content_height(home_table, 110, 2500))
        with away_col:
            st.markdown("**Jogos como Visitante**")
            if away_table.empty:
                st.caption("Sem dados.")
            else:
                st.dataframe(away_table, width="stretch", hide_index=True, height=dataframe_content_height(away_table, 110, 2500))


def render_player_stats_group(
    player_stats_df: pd.DataFrame,
    players_df: pd.DataFrame,
    match_key: str,
    title: str,
    default_open: bool,
) -> None:
    group_key = safe_key("player-group", match_key, title)
    open_groups = st.session_state.setdefault("open_player_groups", [])
    if group_key not in open_groups and f"{group_key}_initialized" not in st.session_state:
        if default_open:
            open_groups.append(group_key)
        st.session_state[f"{group_key}_initialized"] = True

    is_open = group_key in open_groups
    arrow = "[-]" if is_open else "[+]"
    count = len(players_df) if not players_df.empty else 0
    st.button(
        f"{arrow}  {title} ({count})",
        key=f"player_group_button_{group_key}",
        use_container_width=True,
        on_click=toggle_player_group,
        args=(group_key,),
    )
    if is_open:
        render_player_stats_cards(player_stats_df, players_df, match_key, f"Sem {title.lower()}.")


def render_player_stats_team_block(
    match: pd.Series,
    lineups_df: pd.DataFrame,
    player_stats_df: pd.DataFrame,
    team_name: object,
) -> None:
    st.markdown(f"**{team_name}**")
    rows = player_rows_for_match_team(match, lineups_df, player_stats_df, team_name)
    match_key = safe_key(match.get("source_match_id"), team_name)
    starters = rows[rows["starter"].astype(bool)].copy() if not rows.empty else pd.DataFrame()
    bench = rows[~rows["starter"].astype(bool)].copy() if not rows.empty else pd.DataFrame()
    render_player_stats_group(player_stats_df, starters, safe_key(match_key, "starters"), "Titulares", True)
    render_player_stats_group(player_stats_df, bench, safe_key(match_key, "bench"), "Reservas", False)


def render_player_statistics_tab(matches_df: pd.DataFrame, lineups_df: pd.DataFrame, player_stats_df: pd.DataFrame) -> None:
    if matches_df.empty:
        st.info("Sem jogos para a data.")
        return
    for index, (_, match) in enumerate(matches_df.iterrows()):
        label = f"{format_match_date(match)} | {match.get('home_team')} x {match.get('away_team')}"
        with st.expander(label, expanded=index == 0):
            home_col, away_col = st.columns(2)
            with home_col:
                render_player_stats_team_block(match, lineups_df, player_stats_df, match.get("home_team"))
            with away_col:
                render_player_stats_team_block(match, lineups_df, player_stats_df, match.get("away_team"))


def player_market_rows(
    match: pd.Series,
    odds_rows: pd.DataFrame,
    lineups_df: pd.DataFrame,
    player_stats_df: pd.DataFrame,
    team_name: str,
) -> pd.DataFrame:
    mapped_teams = player_team_index(match, lineups_df)
    mapped_teams.update({key: value for key, value in player_history_team_index(match, player_stats_df).items() if key not in mapped_teams})
    rows = odds_rows[odds_rows["Tipo"] == "Jogador"].copy() if not odds_rows.empty else pd.DataFrame()
    if not rows.empty:
        rows["Time"] = rows.apply(
            lambda row: row.get("Time") or mapped_teams.get(plain_text(row.get("Jogador"))) or "",
            axis=1,
        )
        rows = rows[rows["Time"].apply(lambda value: teams_match(value, team_name))]
        rows["ODD"] = rows["ODD"].map(display_odd)
        is_home = teams_match(team_name, match.get("home_team"))
        scored = rows.apply(lambda row: player_score_reason(row, player_stats_df, is_home), axis=1)
        rows["Score"] = scored.map(lambda value: value[0])
        rows["Motivo"] = scored.map(lambda value: value[1])
        rows = rows[PLAYER_COLUMNS]

    combined = rows.copy()
    if combined.empty:
        return pd.DataFrame()
    combined = combined[combined["ODD"].ne("N/D")]
    combined = filter_non_empty_line(combined)
    combined = filter_scored_rows(combined)
    if combined.empty:
        return pd.DataFrame()
    combined = combined.drop_duplicates(["Jogador", "Time", "Mercado", "Pick", "Linha", "ODD"], keep="first")
    return combined.sort_values(["Jogador", "Mercado", "Linha", "Pick"]).reset_index(drop=True)


def append_match_context(rows: pd.DataFrame, match: pd.Series, row_type: str) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=BEST_BETS_COLUMNS)
    base = match_base(match)
    output = rows.copy()
    output["_source_match_id"] = str(match.get("source_match_id") or "")
    output["_target_date"] = str(match.get("target_date") or "")
    output["Data"] = base["Data"]
    output["Liga"] = base["Liga"]
    output["Casa"] = base["Casa"]
    output["Fora"] = base["Fora"]
    output["Tipo"] = row_type
    if "Odd" in output.columns and "ODD" not in output.columns:
        output = output.rename(columns={"Odd": "ODD"})
    for column in BEST_BETS_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    extra_columns = [column for column in ["market_key", "_source_match_id", "_target_date"] if column in output.columns]
    return output[BEST_BETS_COLUMNS + extra_columns]


@st.cache_data(ttl=60, show_spinner=False)
def all_bet_rows(
    matches_df: pd.DataFrame,
    display_df: pd.DataFrame,
    snapshots_df: pd.DataFrame,
    team_stats_df: pd.DataFrame,
    lineups_df: pd.DataFrame,
    player_stats_df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    high_snapshots = snapshots_df.copy()
    if not high_snapshots.empty and "price" in high_snapshots.columns:
        high_snapshots["_odd"] = pd.to_numeric(high_snapshots["price"], errors="coerce")
        high_snapshots = high_snapshots[high_snapshots["_odd"] >= 1.30].drop(columns=["_odd"], errors="ignore")
    snapshot_groups: dict[tuple[str, str], pd.DataFrame] = {}
    if {"raw_home_team", "raw_away_team"}.issubset(high_snapshots.columns):
        grouped = high_snapshots.copy()
        grouped["_home_key"] = grouped["raw_home_team"].map(plain_text)
        grouped["_away_key"] = grouped["raw_away_team"].map(plain_text)
        for key, group in grouped.groupby(["_home_key", "_away_key"], dropna=False):
            snapshot_groups[(str(key[0]), str(key[1]))] = group.drop(columns=["_home_key", "_away_key"], errors="ignore")

    for _, match in matches_df.iterrows():
        match_key = (plain_text(match.get("home_team")), plain_text(match.get("away_team")))
        match_snapshots = snapshot_groups.get(match_key, pd.DataFrame())
        match_odds = odds_rows_for_match(match, match_snapshots if not match_snapshots.empty else high_snapshots)
        rows.append(append_match_context(game_market_rows(match, display_df, match_odds, team_stats_df), match, "Jogo"))
        rows.append(
            append_match_context(
                team_market_rows(match, match_odds, team_stats_df, str(match.get("home_team"))),
                match,
                "Time",
            )
        )
        rows.append(
            append_match_context(
                team_market_rows(match, match_odds, team_stats_df, str(match.get("away_team"))),
                match,
                "Time",
            )
        )
        rows.append(
            append_match_context(
                player_market_rows(match, match_odds, lineups_df, player_stats_df, str(match.get("home_team"))),
                match,
                "Jogador",
            )
        )
        rows.append(
            append_match_context(
                player_market_rows(match, match_odds, lineups_df, player_stats_df, str(match.get("away_team"))),
                match,
                "Jogador",
            )
        )

    combined = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=BEST_BETS_COLUMNS)
    if combined.empty:
        return combined
    return combined.drop_duplicates(
        ["Data", "Liga", "Casa", "Fora", "Tipo", "Time", "Jogador", "Mercado", "Pick", "Linha", "ODD"],
        keep="first",
    ).reset_index(drop=True)


def best_bets_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=BEST_BETS_COLUMNS)
    combined = rows.copy()
    combined = best_bet_filter(combined)
    if combined.empty:
        return combined
    return combined.drop_duplicates(
        ["Data", "Liga", "Casa", "Fora", "Tipo", "Time", "Jogador", "Mercado", "Pick", "Linha", "ODD"],
        keep="first",
    ).drop(columns=["market_key"], errors="ignore").reset_index(drop=True)


TARGET_DATE_PARAMS = {
    "today_date": TODAY_DATE,
    "tomorrow_date": TOMORROW_DATE,
    "stale_offset": f"-{settings.odds_stale_after_hours} hours",
}

DASHBOARD_COUNTS_SQL = """
with target_matches as (
  select source_match_id, target_date
  from matches
  where target_date in (:today_date, :tomorrow_date)
),
latest_betfair_odds as (
  select
    fetched_at,
    coalesce(
      (select target_date from target_matches tm where tm.source_match_id = odds_snapshots.source_match_id limit 1),
      date(commence_time)
    ) as target_date,
    row_number() over (
      partition by
        source,
        bookmaker,
        coalesce(
          (select target_date from target_matches tm where tm.source_match_id = odds_snapshots.source_match_id limit 1),
          date(commence_time)
        ),
        market_key,
        outcome_name,
        coalesce(point, -9999),
        market_name,
        market_type_raw,
        raw_home_team,
        raw_away_team,
        team_name,
        player_name
      order by fetched_at desc
    ) as rn
  from odds_snapshots
  where source = 'betfair-web'
    and (
      source_match_id in (select source_match_id from target_matches)
      or date(commence_time) in (:today_date, :tomorrow_date)
    )
)
select
  (select count(*) from analysis_results where target_date in (:today_date, :tomorrow_date)) as palpites,
  (select count(*) from target_matches) as jogos,
  (select count(*) from latest_betfair_odds where rn = 1) as odds_snapshots,
  (select count(*) from latest_betfair_odds where rn = 1 and fetched_at < datetime('now', :stale_offset)) as odds_stale
"""

RESULTS_SQL = """
select
  ar.target_date,
  m.kickoff_at,
  ar.league_name,
  ar.home_team,
  ar.away_team,
  ar.market_key,
  ar.pick,
  ar.score,
  ar.home_hit_rate,
  ar.away_hit_rate,
  ar.sample_size,
  ar.reason,
  ar.created_at
from analysis_results ar
left join matches m on m.source_match_id = ar.source_match_id
where ar.target_date in (:today_date, :tomorrow_date)
order by ar.target_date desc, score desc
"""

MATCHES_SQL = """
select source_match_id, target_date, league_name, home_team, away_team, status, kickoff_at
from matches
where target_date in (:today_date, :tomorrow_date)
order by target_date, kickoff_at
"""

SNAPSHOTS_SQL = """
select
  target_date,
  source,
  fetched_at,
  bookmaker,
  market_key,
  outcome_name,
  price,
  point,
  raw_json,
  raw_home_team,
  raw_away_team,
  commence_time,
  market_name,
  market_type,
  market_type_raw,
  market_category,
  team_name,
  player_name,
  case
    when fetched_at < datetime('now', :stale_offset) then 1
    else 0
  end as odds_stale
from (
  select
    coalesce(
      (select m.target_date from matches m where m.source_match_id = odds_snapshots.source_match_id limit 1),
      date(commence_time)
    ) as target_date,
    source,
    fetched_at,
    bookmaker,
    market_key,
    outcome_name,
    price,
    point,
    raw_json,
    raw_home_team,
    raw_away_team,
    commence_time,
    market_name,
    market_type,
    market_type_raw,
    market_category,
    team_name,
    player_name,
    row_number() over (
      partition by
        source,
        bookmaker,
        coalesce(
          (select m.target_date from matches m where m.source_match_id = odds_snapshots.source_match_id limit 1),
          date(commence_time)
        ),
        market_key,
        outcome_name,
        coalesce(point, -9999),
        market_name,
        market_type_raw,
        raw_home_team,
        raw_away_team,
        team_name,
        player_name
      order by fetched_at desc
    ) as rn
  from odds_snapshots
  where source = 'betfair-web'
    and (
      source_match_id in (
        select source_match_id from matches where target_date in (:today_date, :tomorrow_date)
      )
      or date(commence_time) in (:today_date, :tomorrow_date)
    )
)
where rn = 1
order by fetched_at desc
"""

LINEUPS_SQL = """
select
  l.source_match_id,
  l.player_name,
  l.team_name,
  l.starter,
  l.position,
  l.jersey,
  coalesce(m.target_date, '') as match_date
from player_lineups l
left join matches m
  on m.source = l.source
 and m.source_match_id = l.source_match_id
where l.source_match_id in (
  select source_match_id from matches where target_date in (:today_date, :tomorrow_date)
)
order by l.team_name, l.starter desc, l.player_name
"""

TEAM_STATS_SQL = """
with target_teams as (
  select home_team as team_name from matches where target_date in (:today_date, :tomorrow_date)
  union
  select away_team as team_name from matches where target_date in (:today_date, :tomorrow_date)
)
select
  source,
  team_name,
  opponent_name,
  coalesce(json_extract(raw_json, '$.league.name'), '') as league_name,
  match_date,
  goals_for,
  goals_against,
  btts,
  over_15,
  over_25,
  corners_for,
  corners_against,
  cards_for,
  cards_against,
  shots_total_for,
  shots_total_against,
  shots_on_target_for,
  shots_on_target_against,
  offsides_for,
  offsides_against,
  throw_ins_for,
  first_half_goals_for,
  first_half_goals_against,
  first_half_corners_for,
  first_half_corners_against,
  xg_for,
  xg_against,
  fouls_committed,
  fouls_suffered,
  is_home
from team_stats
where source = 'espn'
  and team_name in (select team_name from target_teams)
order by match_date desc
"""

PLAYER_STATS_SQL = """
with target_teams as (
  select home_team as team_name from matches where target_date in (:today_date, :tomorrow_date)
  union
  select away_team as team_name from matches where target_date in (:today_date, :tomorrow_date)
)
select
  p.source,
  p.source_match_id,
  p.player_name,
  p.team_name,
  p.match_date,
  p.minutes,
  p.goals,
  p.assists,
  coalesce(p.goals, 0) + coalesce(p.assists, 0) as goals_or_assists,
  p.shots,
  p.shots_on_target,
  p.fouls,
  p.fouls_suffered,
  case
    when p.fouls is null and p.fouls_suffered is null then null
    else coalesce(p.fouls, 0) + coalesce(p.fouls_suffered, 0)
  end as foul_involvements,
  p.yellow_cards,
  p.red_cards,
  p.cards,
  json_extract(p.raw_json, '$.starter') as starter,
  coalesce(
    json_extract(p.raw_json, '$.position.abbreviation'),
    json_extract(p.raw_json, '$.position.displayName'),
    json_extract(p.raw_json, '$.position.name')
  ) as position,
  json_extract(p.raw_json, '$.jersey') as jersey,
  ts.opponent_name,
  coalesce(json_extract(ts.raw_json, '$.league.name'), '') as league_name,
  ts.is_home
from player_stats p
left join team_stats ts
  on ts.source = p.source
 and ts.source_match_id = p.source_match_id
    and ts.team_name = p.team_name
where p.source = 'espn'
  and p.team_name in (select team_name from target_teams)
order by p.match_date desc
"""


def rows_for_day(rows: pd.DataFrame, date_value: str, column: str = "target_date") -> pd.DataFrame:
    if rows.empty or column not in rows.columns:
        return pd.DataFrame(columns=rows.columns)
    return rows[rows[column].astype(str).eq(date_value)].copy()


def render_day_expanders(
    title_count_rows: pd.DataFrame,
    render_day,
    column: str = "target_date",
    empty_text: str = "Sem dados.",
    days: tuple[tuple[str, str], ...] = DASHBOARD_DAYS,
) -> None:
    day_groups = [
        (date_value, label, rows_for_day(title_count_rows, date_value, column))
        for date_value, label in days
    ]
    first_open_index = next((index for index, (_, _, day_rows) in enumerate(day_groups) if not day_rows.empty), 0)
    for index, (date_value, label, day_rows) in enumerate(day_groups):
        with st.expander(f"{label} ({len(day_rows)})", expanded=index == first_open_index):
            if day_rows.empty:
                st.info(empty_text)
            else:
                render_day(date_value, day_rows)


def load_dashboard_counts() -> tuple[int, int, int, int]:
    counts = read_sql(DASHBOARD_COUNTS_SQL, TARGET_DATE_PARAMS)
    if counts.empty:
        return 0, 0, 0, 0

    def count_value(column: str) -> int:
        value = counts.iloc[0].get(column, 0)
        return 0 if pd.isna(value) else int(value)

    return (
        count_value("palpites"),
        count_value("jogos"),
        count_value("odds_snapshots"),
        count_value("odds_stale"),
    )


def load_results() -> pd.DataFrame:
    return read_sql(RESULTS_SQL, TARGET_DATE_PARAMS)


def load_matches() -> pd.DataFrame:
    return read_sql(MATCHES_SQL, TARGET_DATE_PARAMS)


def load_snapshots() -> pd.DataFrame:
    return read_sql(SNAPSHOTS_SQL, TARGET_DATE_PARAMS)


def load_lineups() -> pd.DataFrame:
    return read_sql(LINEUPS_SQL, TARGET_DATE_PARAMS)


def load_team_stats() -> pd.DataFrame:
    return read_sql(TEAM_STATS_SQL, TARGET_DATE_PARAMS)


def load_player_stats() -> pd.DataFrame:
    return read_sql(PLAYER_STATS_SQL, TARGET_DATE_PARAMS)


def load_display_results() -> tuple[pd.DataFrame, pd.DataFrame]:
    results = load_results()
    snapshots = load_snapshots()
    return add_display_columns(results, snapshots), snapshots


def load_prediction_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    matches = load_matches()
    display_results, snapshots = load_display_results()
    team_stats = load_team_stats()
    lineups = load_lineups()
    player_stats = load_player_stats()
    return matches, display_results, snapshots, team_stats, lineups, player_stats


DATE_FILTER_ALL = "Hoje + Amanhã"
DATE_FILTER_OPTIONS = [DATE_FILTER_ALL, "Hoje", "Amanhã"]
DATE_FILTER_VALUES = {DATE_FILTER_ALL: "", "Hoje": TODAY_DATE, "Amanhã": TOMORROW_DATE}


def days_for_filter(day_label: str) -> tuple[tuple[str, str], ...]:
    date_value = DATE_FILTER_VALUES.get(day_label, "")
    if not date_value:
        return DASHBOARD_DAYS
    label = next((label for value, label in DASHBOARD_DAYS if value == date_value), day_label)
    return ((date_value, label),)


def carbon_key(active_tab: str, name: str) -> str:
    return safe_key("carbon", active_tab, name)


def unique_string_values(rows: pd.DataFrame, *columns: str, limit: int = 140) -> list[str]:
    values: dict[str, str] = {}
    for column in columns:
        if rows.empty or column not in rows.columns:
            continue
        for value in rows[column].dropna().astype(str):
            text = value.strip()
            if not text or plain_text(text) in {"n d", "nan", "none"}:
                continue
            values.setdefault(plain_text(text), text)
    return [values[key] for key in sorted(values)[:limit]]


def filter_rows_by_day(rows: pd.DataFrame, day_label: str, column: str) -> pd.DataFrame:
    if rows.empty or column not in rows.columns:
        return rows.copy()
    date_value = DATE_FILTER_VALUES.get(day_label, "")
    if not date_value:
        return rows.copy()
    return rows[rows[column].astype(str).eq(date_value)].copy()


def filter_matches_by_team(matches: pd.DataFrame, team_name: str) -> pd.DataFrame:
    if matches.empty or team_name == "Todos":
        return matches.copy()
    return matches[
        matches["home_team"].apply(lambda value: teams_match(value, team_name))
        | matches["away_team"].apply(lambda value: teams_match(value, team_name))
    ].copy()


def filter_matches_by_prediction_rows(matches: pd.DataFrame, prediction_rows: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return matches.copy()
    if prediction_rows.empty:
        return matches.iloc[0:0].copy()
    if "_source_match_id" in prediction_rows.columns and "source_match_id" in matches.columns:
        match_ids = set(prediction_rows["_source_match_id"].dropna().astype(str))
        if match_ids:
            return matches[matches["source_match_id"].astype(str).isin(match_ids)].copy()
    return matches.copy()


def filter_text_contains(rows: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    search = plain_text(query).strip()
    if rows.empty or not search:
        return rows.copy()
    available_columns = [column for column in columns if column in rows.columns]
    if not available_columns:
        return rows.copy()
    mask = rows[available_columns].fillna("").astype(str).agg(" ".join, axis=1).apply(lambda value: search in plain_text(value))
    return rows[mask].copy()


def filter_team_columns(rows: pd.DataFrame, team_name: str, columns: list[str]) -> pd.DataFrame:
    if rows.empty or team_name == "Todos":
        return rows.copy()
    available_columns = [column for column in columns if column in rows.columns]
    if not available_columns:
        return rows.copy()
    mask = pd.Series(False, index=rows.index)
    for column in available_columns:
        mask = mask | rows[column].apply(lambda value: teams_match(value, team_name))
    return rows[mask].copy()


def filter_numeric_min(rows: pd.DataFrame, min_value: float, *columns: str) -> pd.DataFrame:
    if rows.empty or min_value <= 0:
        return rows.copy()
    values = numeric_filter_values(rows, *columns)
    return rows[values >= min_value].copy()


def prediction_team_options(matches: pd.DataFrame, rows: pd.DataFrame) -> list[str]:
    values: dict[str, str] = {}
    for source_rows, columns in (
        (matches, ("home_team", "away_team")),
        (rows, ("Casa", "Fora", "Time")),
    ):
        for value in unique_string_values(source_rows, *columns):
            values.setdefault(plain_text(value), value)
    return ["Todos", *[values[key] for key in sorted(values)]]


def render_prediction_filter_controls(
    active_tab: str,
    rows: pd.DataFrame,
    matches: pd.DataFrame,
    *,
    score_default: int,
    odd_default: float,
) -> dict[str, object]:
    type_options = ["Todos", *unique_string_values(rows, "Tipo")]
    if len(type_options) == 1:
        type_options.extend(["Jogo", "Time", "Jogador"])
    market_options = ["Todos", *unique_string_values(rows, "Mercado")]
    team_options = prediction_team_options(matches, rows)

    with st.container(key="carbon_filter_panel"):
        st.markdown(
            '<div class="carbon-panel-kicker">Filtros operacionais</div>'
            '<div class="carbon-panel-copy">Todos os filtros abaixo atuam sobre os mesmos DataFrames usados pelas tabelas atuais.</div>',
            unsafe_allow_html=True,
        )
        first_row = st.columns([1.0, 1.0, 1.2, 1.2], gap="small")
        with first_row[0]:
            day = st.selectbox("Data", DATE_FILTER_OPTIONS, key=carbon_key(active_tab, "day"))
        with first_row[1]:
            bet_type = st.selectbox("Tipo", type_options, key=carbon_key(active_tab, "type"))
        with first_row[2]:
            team = st.selectbox("Time", team_options, key=carbon_key(active_tab, "team"))
        with first_row[3]:
            market = st.selectbox("Mercado", market_options, key=carbon_key(active_tab, "market"))

        second_row = st.columns([0.9, 0.9, 2.2], gap="small")
        with second_row[0]:
            score_min = st.slider("Score mínimo", 0, 100, score_default, 1, key=carbon_key(active_tab, "score"))
        with second_row[1]:
            odd_min = st.number_input(
                "Odd mínima",
                min_value=0.0,
                max_value=1000.0,
                value=odd_default,
                step=0.05,
                format="%.2f",
                key=carbon_key(active_tab, "odd"),
            )
        with second_row[2]:
            query = st.text_input(
                "Busca livre",
                placeholder="Time, jogador, mercado, pick, motivo ou liga",
                key=carbon_key(active_tab, "query"),
            )
    return {
        "day": str(day),
        "type": str(bet_type),
        "team": str(team),
        "market": str(market),
        "score_min": int(score_min),
        "odd_min": float(odd_min),
        "query": str(query or "").strip(),
    }


def apply_prediction_filters(rows: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    filtered = filter_rows_by_day(rows, str(filters["day"]), "_target_date")
    bet_type = str(filters["type"])
    if bet_type != "Todos" and "Tipo" in filtered.columns:
        filtered = filtered[filtered["Tipo"].astype(str).eq(bet_type)].copy()
    market = str(filters["market"])
    if market != "Todos" and "Mercado" in filtered.columns:
        filtered = filtered[filtered["Mercado"].astype(str).eq(market)].copy()
    filtered = filter_team_columns(filtered, str(filters["team"]), ["Casa", "Fora", "Time"])
    filtered = filter_numeric_min(filtered, float(filters["score_min"]), "Score")
    filtered = filter_numeric_min(filtered, float(filters["odd_min"]), "ODD", "Odd")
    return filter_text_contains(
        filtered,
        str(filters["query"]),
        ["Data", "Liga", "Casa", "Fora", "Tipo", "Time", "Jogador", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"],
    ).reset_index(drop=True)


def prediction_filter_status(filters: dict[str, object], shown: int, total: int) -> list[tuple[str, str]]:
    team = str(filters["team"])
    market = str(filters["market"])
    query = str(filters["query"]) or "sem busca"
    scope = []
    if str(filters["type"]) != "Todos":
        scope.append(str(filters["type"]))
    if team != "Todos":
        scope.append(team)
    if market != "Todos":
        scope.append(market)
    return [
        ("Data", str(filters["day"])),
        ("Linhas", f"{shown:,}".replace(",", ".") + f" de {total:,}".replace(",", ".")),
        ("Recorte", " | ".join(scope) if scope else "todos os tipos e mercados"),
        ("Score/Odd", f">= {filters['score_min']} / >= {float(filters['odd_min']):.2f}"),
        ("Busca", query),
    ]


def render_team_filter_controls(active_tab: str, matches: pd.DataFrame, team_stats: pd.DataFrame) -> dict[str, object]:
    team_options = ["Todos", *unique_string_values(matches, "home_team", "away_team")]
    source_options = ["Todas", *unique_string_values(team_stats, "source")]
    with st.container(key="carbon_filter_panel"):
        st.markdown(
            '<div class="carbon-panel-kicker">Filtros operacionais</div>'
            '<div class="carbon-panel-copy">O recorte altera partidas exibidas e o histórico usado nas tabelas ESPN.</div>',
            unsafe_allow_html=True,
        )
        columns = st.columns([1.0, 1.3, 1.0, 1.0, 1.8], gap="small")
        with columns[0]:
            day = st.selectbox("Data", DATE_FILTER_OPTIONS, key=carbon_key(active_tab, "day"))
        with columns[1]:
            team = st.selectbox("Time", team_options, key=carbon_key(active_tab, "team"))
        with columns[2]:
            source = st.selectbox("Fonte", source_options, key=carbon_key(active_tab, "source"))
        with columns[3]:
            side = st.selectbox("Histórico", ["Mandante + visitante", "Mandante", "Visitante"], key=carbon_key(active_tab, "side"))
        with columns[4]:
            query = st.text_input("Busca", placeholder="Time, liga ou adversário", key=carbon_key(active_tab, "query"))
    return {"day": str(day), "team": str(team), "source": str(source), "side": str(side), "query": str(query or "").strip()}


def apply_team_filters(
    matches: pd.DataFrame,
    team_stats: pd.DataFrame,
    filters: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    filtered_matches = filter_rows_by_day(matches, str(filters["day"]), "target_date")
    filtered_matches = filter_matches_by_team(filtered_matches, str(filters["team"]))
    filtered_matches = filter_text_contains(filtered_matches, str(filters["query"]), ["league_name", "home_team", "away_team"])

    filtered_stats = team_stats.copy()
    if str(filters["team"]) != "Todos" and "team_name" in filtered_stats.columns:
        filtered_stats = filtered_stats[filtered_stats["team_name"].apply(lambda value: teams_match(value, str(filters["team"])))].copy()
    if str(filters["source"]) != "Todas" and "source" in filtered_stats.columns:
        filtered_stats = filtered_stats[filtered_stats["source"].astype(str).eq(str(filters["source"]))].copy()
    if "is_home" in filtered_stats.columns:
        if str(filters["side"]) == "Mandante":
            filtered_stats = filtered_stats[filtered_stats["is_home"].astype(bool)].copy()
        elif str(filters["side"]) == "Visitante":
            filtered_stats = filtered_stats[~filtered_stats["is_home"].astype(bool)].copy()
    return filtered_matches.reset_index(drop=True), filtered_stats.reset_index(drop=True)


def render_player_filter_controls(
    active_tab: str,
    matches: pd.DataFrame,
    lineups: pd.DataFrame,
    player_stats: pd.DataFrame,
) -> dict[str, object]:
    team_options = ["Todos", *unique_string_values(matches, "home_team", "away_team", limit=120)]
    source_options = ["Todas", *unique_string_values(player_stats, "source")]
    position_options = ["Todas", *unique_string_values(lineups, "position")]
    with st.container(key="carbon_filter_panel"):
        st.markdown(
            '<div class="carbon-panel-kicker">Filtros operacionais</div>'
            '<div class="carbon-panel-copy">O painel filtra partidas, lineups e histórico individual sem alterar a coleta nem o scoring.</div>',
            unsafe_allow_html=True,
        )
        first_row = st.columns([1.0, 1.25, 1.0, 1.0], gap="small")
        with first_row[0]:
            day = st.selectbox("Data", DATE_FILTER_OPTIONS, key=carbon_key(active_tab, "day"))
        with first_row[1]:
            team = st.selectbox("Time", team_options, key=carbon_key(active_tab, "team"))
        with first_row[2]:
            status = st.selectbox("Lineup", ["Todos", "Titulares", "Reservas"], key=carbon_key(active_tab, "status"))
        with first_row[3]:
            position = st.selectbox("Posição", position_options, key=carbon_key(active_tab, "position"))
        second_row = st.columns([1.0, 2.6], gap="small")
        with second_row[0]:
            source = st.selectbox("Fonte", source_options, key=carbon_key(active_tab, "source"))
        with second_row[1]:
            query = st.text_input("Busca", placeholder="Jogador, time ou posição", key=carbon_key(active_tab, "query"))
    return {
        "day": str(day),
        "team": str(team),
        "status": str(status),
        "position": str(position),
        "source": str(source),
        "query": str(query or "").strip(),
    }


def filter_player_stats_teams(matches: pd.DataFrame, team_names: set[str]) -> pd.DataFrame:
    if matches.empty or not team_names:
        return matches.copy()
    normalized = {plain_text(team) for team in team_names if plain_text(team)}
    return matches[
        matches["home_team"].apply(lambda value: plain_text(value) in normalized)
        | matches["away_team"].apply(lambda value: plain_text(value) in normalized)
    ].copy()


def apply_player_filters(
    matches: pd.DataFrame,
    lineups: pd.DataFrame,
    player_stats: pd.DataFrame,
    filters: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    filtered_matches = filter_rows_by_day(matches, str(filters["day"]), "target_date")
    filtered_matches = filter_matches_by_team(filtered_matches, str(filters["team"]))

    filtered_lineups = filter_team_columns(lineups, str(filters["team"]), ["team_name"])
    filtered_stats = filter_team_columns(player_stats, str(filters["team"]), ["team_name"])

    if str(filters["status"]) != "Todos" and "starter" in filtered_lineups.columns:
        starter_value = str(filters["status"]) == "Titulares"
        filtered_lineups = filtered_lineups[filtered_lineups["starter"].apply(bool_from_db).eq(starter_value)].copy()
    if str(filters["position"]) != "Todas" and "position" in filtered_lineups.columns:
        filtered_lineups = filtered_lineups[filtered_lineups["position"].astype(str).eq(str(filters["position"]))].copy()
    if str(filters["source"]) != "Todas" and "source" in filtered_stats.columns:
        filtered_stats = filtered_stats[filtered_stats["source"].astype(str).eq(str(filters["source"]))].copy()

    filtered_lineups = filter_text_contains(filtered_lineups, str(filters["query"]), ["player_name", "team_name", "position", "jersey"])
    filtered_stats = filter_text_contains(filtered_stats, str(filters["query"]), ["player_name", "team_name", "position", "league_name", "opponent_name"])
    if str(filters["query"]).strip():
        teams_with_players = set()
        for frame in (filtered_lineups, filtered_stats):
            if "team_name" in frame.columns:
                teams_with_players.update(frame["team_name"].dropna().astype(str))
        filtered_matches = filter_player_stats_teams(filtered_matches, teams_with_players)

    return filtered_matches.reset_index(drop=True), filtered_lineups.reset_index(drop=True), filtered_stats.reset_index(drop=True)


def generic_filter_status(filters: dict[str, object], shown: int, total: int) -> list[tuple[str, str]]:
    visible = f"{shown:,}".replace(",", ".") + f" de {total:,}".replace(",", ".")
    items = [("Data", str(filters.get("day", DATE_FILTER_ALL))), ("Registros", visible)]
    for label, key in (("Time", "team"), ("Fonte", "source"), ("Estado", "status"), ("Posicao", "position")):
        value = str(filters.get(key, ""))
        if value and value not in {"Todos", "Todas"}:
            items.append((label, value))
    query = str(filters.get("query", "")).strip()
    items.append(("Busca", query if query else "sem busca"))
    return items


tab_options = ["Barbadas do Dia", "Palpites", "Estatísticas dos Times", "Estatísticas jogadores"]
palpites_count, jogos_count, odds_snapshots_count, odds_stale_count = load_dashboard_counts()

default_tab = tab_options[0]
active_tab = st.session_state.get("carbon_active_tab", default_tab)
if active_tab not in tab_options:
    active_tab = default_tab

render_header(
    active_tab=active_tab,
    palpites=palpites_count,
    jogos=jogos_count,
    odds_snapshots=odds_snapshots_count,
    odds_stale=odds_stale_count,
)

with st.container(key="carbon_nav_panel"):
    selected_tab = st.segmented_control(
        "Aba",
        tab_options,
        default=active_tab,
        key="carbon_active_tab",
        label_visibility="collapsed",
    )
active_tab = selected_tab or active_tab


def render_carbon_columns(
    legend_items: list[tuple[str, str, str]],
    heading: str,
    render_main: Callable[[], None],
) -> None:
    render_legend(legend_items)
    with st.container(key="carbon_main_panel"):
        render_main_heading(active_tab, heading)
        render_main()

if active_tab == "Barbadas do Dia":
    matches, display_results, snapshots, team_stats, lineups, player_stats = load_prediction_data()
    prediction_rows = all_bet_rows(matches, display_results, snapshots, team_stats, lineups, player_stats)
    best_bets_all = best_bets_rows(prediction_rows)
    filters = render_prediction_filter_controls(active_tab, best_bets_all, matches, score_default=75, odd_default=1.30)
    best_bets = apply_prediction_filters(best_bets_all, filters)
    status_items = prediction_filter_status(filters, len(best_bets), len(best_bets_all))
    render_filterbar(active_tab, status_items[:4])
    today_count = len(rows_for_day(best_bets, TODAY_DATE, "_target_date"))
    tomorrow_count = len(rows_for_day(best_bets, TOMORROW_DATE, "_target_date"))
    type_counts = best_bets["Tipo"].astype(str).value_counts().to_dict() if not best_bets.empty else {}
    legend_items = [
        ("Hoje", f"{today_count} linhas", "best bets"),
        ("Amanhã", f"{tomorrow_count} linhas", "best bets"),
        ("Jogos", str(type_counts.get("Jogo", 0)), "grupo preservado"),
        ("Times", str(type_counts.get("Time", 0)), "grupo preservado"),
        ("Jogadores", str(type_counts.get("Jogador", 0)), "grupo preservado"),
    ]
    render_carbon_columns(
        legend_items,
        "Tabela completa de recomendações: Data, Liga, Casa, Fora, Tipo, Time, Jogador, Mercado, Pick, Linha, ODD, Score e Motivo.",
        lambda: render_day_expanders(
            best_bets,
            lambda date_value, day_rows: render_best_bets_tab(day_rows, key_prefix=f"best_bets_{date_value}"),
            "_target_date",
            "Sem mercados.",
            days_for_filter(str(filters["day"])),
        ),
    )

elif active_tab == "Palpites":
    matches, display_results, snapshots, team_stats, lineups, player_stats = load_prediction_data()
    prediction_rows_all = all_bet_rows(matches, display_results, snapshots, team_stats, lineups, player_stats)
    filters = render_prediction_filter_controls(active_tab, prediction_rows_all, matches, score_default=0, odd_default=0.0)
    prediction_rows = apply_prediction_filters(prediction_rows_all, filters)
    filtered_matches = filter_rows_by_day(matches, str(filters["day"]), "target_date")
    filtered_matches = filter_matches_by_team(filtered_matches, str(filters["team"]))
    filtered_matches = filter_matches_by_prediction_rows(filtered_matches, prediction_rows)
    status_items = prediction_filter_status(filters, len(prediction_rows), len(prediction_rows_all))
    render_filterbar(active_tab, status_items[:4])
    type_counts = prediction_rows["Tipo"].astype(str).value_counts().to_dict() if not prediction_rows.empty else {}
    legend_items = [
        ("Partidas", str(len(filtered_matches)), str(filters["day"])),
        ("Jogo", str(type_counts.get("Jogo", 0)), "mercados gerais"),
        ("Times", str(type_counts.get("Time", 0)), "mandante/visitante"),
        ("Jogadores", str(type_counts.get("Jogador", 0)), "props e histórico"),
        ("Motivos", "100%", "preservados"),
    ]
    render_carbon_columns(
        legend_items,
        "Todos os mercados por partida continuam agrupados em jogo, times e jogadores, com ODD, Score e Motivo ordenáveis.",
        lambda: render_day_expanders(
            filtered_matches,
            lambda date_value, day_matches: render_predictions_tab(
                day_matches,
                rows_for_day(prediction_rows, date_value, "_target_date"),
            ),
            "target_date",
            "Sem jogos para a data.",
            days_for_filter(str(filters["day"])),
        ),
    )

elif active_tab == "Estatísticas dos Times":
    matches = load_matches()
    team_stats = load_team_stats()
    filters = render_team_filter_controls(active_tab, matches, team_stats)
    filtered_matches, filtered_team_stats = apply_team_filters(matches, team_stats, filters)
    status_items = generic_filter_status(filters, len(filtered_team_stats), len(team_stats))
    render_filterbar(active_tab, status_items[:4])
    target_teams = pd.concat(
        [filtered_matches.get("home_team", pd.Series(dtype=str)), filtered_matches.get("away_team", pd.Series(dtype=str))],
        ignore_index=True,
    ).dropna()
    legend_items = [
        ("Partidas", str(len(filtered_matches)), str(filters["day"])),
        ("Times", str(target_teams.nunique()), "mandante/visitante"),
        ("Histórico", str(STATS_DISPLAY_GAMES), "jogos por lado"),
        ("Métricas", str(len(TEAM_STAT_CATEGORIES)), "gols, xG, faltas"),
        ("Fonte", str(filters["source"]), "histórico filtrável"),
    ]
    render_carbon_columns(
        legend_items,
        "Histórico mandante/visitante com Jogo 1 a Jogo 10, Média, Resultado, Competição, Adversário e todas as métricas atuais.",
        lambda: render_day_expanders(
            filtered_matches,
            lambda _date, day_matches: render_team_statistics_tab(day_matches, filtered_team_stats),
            "target_date",
            "Sem jogos para a data.",
            days_for_filter(str(filters["day"])),
        ),
    )

elif active_tab == "Estatísticas jogadores":
    matches = load_matches()
    lineups = load_lineups()
    player_stats = load_player_stats()
    filters = render_player_filter_controls(active_tab, matches, lineups, player_stats)
    filtered_matches, filtered_lineups, filtered_player_stats = apply_player_filters(matches, lineups, player_stats, filters)
    status_items = generic_filter_status(filters, len(filtered_lineups), len(lineups))
    render_filterbar(active_tab, status_items[:4])
    from src.db.models import bool_from_db
    starters = int(filtered_lineups["starter"].apply(bool_from_db).sum()) if not filtered_lineups.empty and "starter" in filtered_lineups.columns else 0
    bench = max(0, len(filtered_lineups) - starters)
    legend_items = [
        ("Jogadores", str(len(filtered_lineups)), "lineups filtradas"),
        ("Stats", str(len(filtered_player_stats)), "linhas jogador"),
        ("Titulares", str(starters), "estado filtrável"),
        ("Reservas", str(bench), "estado filtrável"),
        ("Mercados", str(len(PLAYER_STAT_CATEGORIES)), "histórico"),
    ]
    render_carbon_columns(
        legend_items,
        "Lineup, titulares, reservas, camisa, posição, mercados, histórico individual, jogos e Média no mesmo fluxo denso.",
        lambda: render_day_expanders(
            filtered_matches,
            lambda _date, day_matches: render_player_statistics_tab(day_matches, filtered_lineups, filtered_player_stats),
            "target_date",
            "Sem jogos para a data.",
            days_for_filter(str(filters["day"])),
        ),
    )
