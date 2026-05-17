from __future__ import annotations

import re
from functools import lru_cache
from unicodedata import normalize

import pandas as pd


TEAM_TOKEN_ALIASES = {
    "mg": "mineiro",
    "pr": "paranaense",
}
TEAM_TOKEN_STOPWORDS = {"ac", "club", "clube", "ec", "fc", "sc", "da", "de", "do", "das", "dos"}


@lru_cache(maxsize=20000)
def _plain_text_cached(text: str) -> str:
    text = normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def plain_text(value: object) -> str:
    return _plain_text_cached("" if value is None else str(value))


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
