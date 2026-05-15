from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from src.domain.scoring import hit_score


Predicate = Callable[[pd.Series], bool | None]


@dataclass(frozen=True)
class MatchupScore:
    score: str
    team_hits: int
    team_total: int
    opponent_hits: int
    opponent_total: int
    sources: frozenset[str]


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _diff(left: object, right: object) -> float | None:
    if _missing(left) or _missing(right):
        return None
    return float(left) - float(right)


def greater_than(row: pd.Series, left: str, right: str) -> bool | None:
    if _missing(row.get(left)) or _missing(row.get(right)):
        return None
    return float(row.get(left)) > float(row.get(right))


def less_than(row: pd.Series, left: str, right: str) -> bool | None:
    if _missing(row.get(left)) or _missing(row.get(right)):
        return None
    return float(row.get(left)) < float(row.get(right))


def won_any_half(row: pd.Series) -> bool | None:
    first = greater_than(row, "first_half_goals_for", "first_half_goals_against")
    second_for = _diff(row.get("goals_for"), row.get("first_half_goals_for"))
    second_against = _diff(row.get("goals_against"), row.get("first_half_goals_against"))
    if first is None or second_for is None or second_against is None:
        return None
    return first or second_for > second_against


def lost_any_half(row: pd.Series) -> bool | None:
    first = less_than(row, "first_half_goals_for", "first_half_goals_against")
    second_for = _diff(row.get("goals_for"), row.get("first_half_goals_for"))
    second_against = _diff(row.get("goals_against"), row.get("first_half_goals_against"))
    if first is None or second_for is None or second_against is None:
        return None
    return first or second_for < second_against


def won_both_halves(row: pd.Series) -> bool | None:
    first = greater_than(row, "first_half_goals_for", "first_half_goals_against")
    second_for = _diff(row.get("goals_for"), row.get("first_half_goals_for"))
    second_against = _diff(row.get("goals_against"), row.get("first_half_goals_against"))
    if first is None or second_for is None or second_against is None:
        return None
    return first and second_for > second_against


def lost_both_halves(row: pd.Series) -> bool | None:
    first = less_than(row, "first_half_goals_for", "first_half_goals_against")
    second_for = _diff(row.get("goals_for"), row.get("first_half_goals_for"))
    second_against = _diff(row.get("goals_against"), row.get("first_half_goals_against"))
    if first is None or second_for is None or second_against is None:
        return None
    return first and second_for < second_against


def led_at_half_or_won_match(row: pd.Series) -> bool | None:
    first = greater_than(row, "first_half_goals_for", "first_half_goals_against")
    result_margin = _diff(row.get("goals_for"), row.get("goals_against"))
    if first is None or result_margin is None:
        return None
    return first or result_margin > 0


def trailed_at_half_or_lost_match(row: pd.Series) -> bool | None:
    first = less_than(row, "first_half_goals_for", "first_half_goals_against")
    result_margin = _diff(row.get("goals_for"), row.get("goals_against"))
    if first is None or result_margin is None:
        return None
    return first or result_margin < 0


def more_corners_each_half(row: pd.Series) -> bool | None:
    first = greater_than(row, "first_half_corners_for", "first_half_corners_against")
    second_for = _diff(row.get("corners_for"), row.get("first_half_corners_for"))
    second_against = _diff(row.get("corners_against"), row.get("first_half_corners_against"))
    if first is None or second_for is None or second_against is None:
        return None
    return first and second_for > second_against


def fewer_corners_each_half(row: pd.Series) -> bool | None:
    first = less_than(row, "first_half_corners_for", "first_half_corners_against")
    second_for = _diff(row.get("corners_for"), row.get("first_half_corners_for"))
    second_against = _diff(row.get("corners_against"), row.get("first_half_corners_against"))
    if first is None or second_for is None or second_against is None:
        return None
    return first and second_for < second_against


def covers_goal_handicap(row: pd.Series, handicap: float) -> bool | None:
    margin = _diff(row.get("goals_for"), row.get("goals_against"))
    return None if margin is None else margin + handicap > 0


def opponent_supports_goal_handicap(row: pd.Series, handicap: float) -> bool | None:
    margin = _diff(row.get("goals_for"), row.get("goals_against"))
    return None if margin is None else margin < handicap


def predicate_counts(rows: pd.DataFrame, predicate: Predicate) -> tuple[int, int, frozenset[str]]:
    hits = 0
    total = 0
    sources: set[str] = set()
    for _, stat in rows.iterrows():
        hit = predicate(stat)
        if hit is None:
            continue
        hits += int(hit)
        total += 1
        source = stat.get("source")
        if source:
            sources.add(str(source))
    return hits, total, frozenset(sources)


def matchup_score(
    team_rows: pd.DataFrame,
    team_predicate: Predicate,
    opponent_rows: pd.DataFrame,
    opponent_predicate: Predicate,
    min_samples: int,
) -> MatchupScore | None:
    team_hits, team_total, team_sources = predicate_counts(team_rows, team_predicate)
    opponent_hits, opponent_total, opponent_sources = predicate_counts(opponent_rows, opponent_predicate)
    if team_total < min_samples or opponent_total < min_samples:
        return None
    total = team_total + opponent_total
    return MatchupScore(
        score=hit_score(team_hits + opponent_hits, total),
        team_hits=team_hits,
        team_total=team_total,
        opponent_hits=opponent_hits,
        opponent_total=opponent_total,
        sources=team_sources | opponent_sources,
    )
