from __future__ import annotations

import re
from unicodedata import normalize

from sqlmodel import Session, select

from src.db.models import AnalysisResult, Match, TeamStat
from src.domain.reasons import format_hits_with_samples
from src.etl.helpers import upsert_analysis_result

SOURCE_PRIORITY = {"espn": 0}
SOURCE_LABELS = {"espn": "ESPN"}


def _plain(value: object) -> str:
    return normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower().strip()


_TEAM_TOKEN_ALIASES = {
    "mg": "mineiro",
    "pr": "paranaense",
}
_TEAM_TOKEN_STOPWORDS = {"ac", "club", "clube", "ec", "fc", "sc", "da", "de", "do", "das", "dos"}


def _team_tokens(value: object) -> set[str]:
    text = re.sub(r"[^a-z0-9]+", " ", _plain(value))
    return {
        _TEAM_TOKEN_ALIASES.get(token, token)
        for token in text.split()
        if token and token not in _TEAM_TOKEN_STOPWORDS
    }


def _teams_match(left: object, right: object) -> bool:
    a = _plain(left)
    b = _plain(right)
    if not a or not b:
        return False
    if a == b:
        return True
    left_tokens = _team_tokens(left)
    right_tokens = _team_tokens(right)
    return bool(left_tokens and right_tokens and (left_tokens <= right_tokens or right_tokens <= left_tokens))


def _source_label(source: object) -> str:
    return SOURCE_LABELS.get(str(source), str(source or "fonte N/D"))


def _sources_label(*groups: list[TeamStat]) -> str:
    sources = {
        row.source
        for group in groups
        for row in group
        if row.source
    }
    return ", ".join(_source_label(source) for source in sorted(sources, key=lambda item: SOURCE_PRIORITY.get(item, 99)))


def _dedupe_stats(stats: list[TeamStat], attr: str, limit: int = 10) -> list[TeamStat]:
    rows = [row for row in stats if getattr(row, attr) is not None]
    rows.sort(key=lambda row: (row.match_date, -SOURCE_PRIORITY.get(row.source, 99)), reverse=True)
    seen = set()
    output = []
    for row in rows:
        if row.match_date in seen:
            continue
        seen.add(row.match_date)
        output.append(row)
        if len(output) >= limit:
            break
    return output


def _hit_rate(stats: list[TeamStat], attr: str) -> float | None:
    values = [getattr(row, attr) for row in _dedupe_stats(stats, attr)]
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 3)


def _hit_count(stats: list[TeamStat], attr: str) -> tuple[int, int]:
    values = [getattr(row, attr) for row in _dedupe_stats(stats, attr)]
    return sum(1 for value in values if value), len(values)


def _sample_values(stats: list[TeamStat], attr: str) -> list[object]:
    samples = []
    for row in _dedupe_stats(stats, attr):
        value = getattr(row, attr)
        if value is None:
            continue
        if attr in {"over_15", "over_25"} and row.goals_for is not None and row.goals_against is not None:
            samples.append(row.goals_for + row.goals_against)
        elif attr == "btts" and row.goals_for is not None and row.goals_against is not None:
            samples.append(f"{row.goals_for}-{row.goals_against}")
        else:
            samples.append(value)
    return samples


def _stat_detail(stats: list[TeamStat], attr: str) -> str:
    details = []
    for row in _dedupe_stats(stats, attr):
        value = getattr(row, attr)
        if value is None:
            continue
        score = (
            f"{row.goals_for}-{row.goals_against}"
            if row.goals_for is not None and row.goals_against is not None
            else "placar N/D"
        )
        details.append(
            f"{row.match_date} vs {row.opponent_name or '?'} {score}={'sim' if value else 'não'}"
        )
    return "; ".join(details)


def _last_team_stats(session: Session, team_name: str, limit: int = 10) -> list[TeamStat]:
    rows = list(
        session.exec(select(TeamStat).where(TeamStat.source == "espn").order_by(TeamStat.match_date.desc()).limit(500))
    )
    return [row for row in rows if _teams_match(row.team_name, team_name)][: limit * 3]


def analyze_match(session: Session, match: Match) -> None:
    home_stats = _last_team_stats(session, match.home_team)
    away_stats = _last_team_stats(session, match.away_team)
    sample_size = min(len(home_stats), len(away_stats), 10)
    if sample_size == 0:
        return

    markets = [
        ("btts", "Sim", "btts", "Ambas marcam"),
        ("over_15", "Over 1.5", "over_15", "Mais de 1.5 gols"),
        ("over_25", "Over 2.5", "over_25", "Mais de 2.5 gols"),
    ]

    for market_key, pick, attr, label in markets:
        home_rate = _hit_rate(home_stats, attr)
        away_rate = _hit_rate(away_stats, attr)
        if home_rate is None or away_rate is None:
            continue
        home_hits, home_total = _hit_count(home_stats, attr)
        away_hits, away_total = _hit_count(away_stats, attr)
        home_sample = _dedupe_stats(home_stats, attr)
        away_sample = _dedupe_stats(away_stats, attr)
        home_values = _sample_values(home_stats, attr)
        away_values = _sample_values(away_stats, attr)
        total = home_total + away_total
        if total == 0:
            continue
        score = round(((home_hits + away_hits) / total) * 100, 1)
        reason = (
            f"Fonte: {_sources_label(home_sample, away_sample)} | "
            f"{match.home_team} - {format_hits_with_samples(home_hits, home_total, home_values)} | "
            f"{match.away_team} - {format_hits_with_samples(away_hits, away_total, away_values)}"
        )
        upsert_analysis_result(
            session,
            AnalysisResult(
                target_date=match.target_date,
                source_match_id=match.source_match_id,
                league_name=match.league_name,
                home_team=match.home_team,
                away_team=match.away_team,
                market_key=market_key,
                pick=pick,
                score=score,
                home_hit_rate=home_rate,
                away_hit_rate=away_rate,
                sample_size=sample_size,
                reason=reason,
            ),
            commit=False,
        )
    session.commit()
