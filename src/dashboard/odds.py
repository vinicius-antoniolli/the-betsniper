from __future__ import annotations

import json

import pandas as pd

from src.dashboard.text_utils import format_match_date, parse_datetime, plain_text, teams_pair_match


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
