from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from config import settings
from src.db.models import AnalysisResult, Match, OddsSnapshot, PlayerLineup, PlayerStat, TeamStat
from src.time_utils import utc_now


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(ZoneInfo(settings.app_timezone))
    return parsed.replace(tzinfo=None)


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upsert_match_from_espn(session: Session, item: dict[str, Any], target_date: str) -> Match:
    competition = (item.get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    home = next((row for row in competitors if row.get("homeAway") == "home"), None)
    away = next((row for row in competitors if row.get("homeAway") == "away"), None)
    league = item.get("league") or {}
    season = item.get("season") or {}
    fixture_id = str(item.get("id") or competition.get("id"))

    def name(competitor: dict[str, Any] | None) -> str:
        team = (competitor or {}).get("team") or {}
        return team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "Unknown"

    def score(competitor: dict[str, Any] | None) -> int | None:
        raw = (competitor or {}).get("score")
        if isinstance(raw, dict):
            raw = raw.get("value") or raw.get("displayValue")
        if raw in (None, ""):
            return None
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None

    row = session.exec(select(Match).where(Match.source == "espn", Match.source_match_id == fixture_id)).first()
    if not row:
        row = Match(
            source="espn",
            source_match_id=fixture_id,
            league_id=int(league.get("id") or 630),
            league_name=league.get("name") or "Brazilian Serie A",
            season=int(season.get("year") or 0),
            target_date=target_date,
            home_team=name(home),
            away_team=name(away),
        )
        session.add(row)

    status = (competition.get("status") or item.get("status") or {}).get("type") or {}
    row.kickoff_at = parse_iso_datetime(item.get("date") or competition.get("date"))
    row.status = status.get("shortDetail") or status.get("description")
    row.home_score = score(home)
    row.away_score = score(away)
    row.raw_json = json.dumps(item, ensure_ascii=False)
    row.updated_at = utc_now()
    session.commit()
    session.refresh(row)
    return row


def upsert_team_stat(
    session: Session,
    source_match_id: str,
    team_name: str,
    opponent_name: str | None,
    match_date: str,
    is_home: bool,
    goals_for: int | None,
    goals_against: int | None,
    raw: dict[str, Any],
    source: str = "espn",
    corners_for: int | None = None,
    corners_against: int | None = None,
    cards_for: int | None = None,
    cards_against: int | None = None,
    shots_total_for: int | None = None,
    shots_total_against: int | None = None,
    shots_on_target_for: int | None = None,
    shots_on_target_against: int | None = None,
    offsides_for: int | None = None,
    offsides_against: int | None = None,
    throw_ins_for: int | None = None,
    first_half_goals_for: int | None = None,
    first_half_goals_against: int | None = None,
    first_half_corners_for: int | None = None,
    first_half_corners_against: int | None = None,
    xg_for: float | None = None,
    xg_against: float | None = None,
    fouls_committed: int | None = None,
    fouls_suffered: int | None = None,
    commit: bool = True,
) -> TeamStat:
    row = session.exec(
        select(TeamStat).where(
            TeamStat.source == source,
            TeamStat.source_match_id == source_match_id,
            TeamStat.team_name == team_name,
        )
    ).first()
    total_goals = None if goals_for is None or goals_against is None else goals_for + goals_against
    if not row:
        row = TeamStat(
            source=source,
            source_match_id=source_match_id,
            team_name=team_name,
            opponent_name=opponent_name,
            match_date=match_date,
            is_home=is_home,
        )
        session.add(row)

    row.opponent_name = opponent_name
    row.match_date = match_date
    row.is_home = is_home
    row.goals_for = goals_for
    row.goals_against = goals_against
    row.btts = None if goals_for is None or goals_against is None else goals_for > 0 and goals_against > 0
    row.over_15 = None if total_goals is None else total_goals > 1.5
    row.over_25 = None if total_goals is None else total_goals > 2.5
    row.corners_for = corners_for
    row.corners_against = corners_against
    row.cards_for = cards_for
    row.cards_against = cards_against
    row.shots_total_for = shots_total_for
    row.shots_total_against = shots_total_against
    row.shots_on_target_for = shots_on_target_for
    row.shots_on_target_against = shots_on_target_against
    row.offsides_for = offsides_for
    row.offsides_against = offsides_against
    row.throw_ins_for = throw_ins_for
    row.first_half_goals_for = first_half_goals_for
    row.first_half_goals_against = first_half_goals_against
    row.first_half_corners_for = first_half_corners_for
    row.first_half_corners_against = first_half_corners_against
    row.xg_for = xg_for
    row.xg_against = xg_against
    row.fouls_committed = fouls_committed
    row.fouls_suffered = fouls_suffered
    row.raw_json = json.dumps(raw, ensure_ascii=False)
    if commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()
    return row


def upsert_player_stat(
    session: Session,
    source_match_id: str,
    player_name: str,
    team_name: str | None,
    match_date: str,
    minutes: int | None,
    shots: int | None,
    shots_on_target: int | None,
    fouls: int | None,
    fouls_suffered: int | None,
    cards: int | None,
    raw: dict[str, Any],
    source: str = "espn",
    yellow_cards: int | None = None,
    red_cards: int | None = None,
    goals: int | None = None,
    assists: int | None = None,
    commit: bool = True,
) -> PlayerStat:
    row = session.exec(
        select(PlayerStat).where(
            PlayerStat.source == source,
            PlayerStat.source_match_id == source_match_id,
            PlayerStat.player_name == player_name,
        )
    ).first()
    if not row:
        row = PlayerStat(
            source=source,
            source_match_id=source_match_id,
            player_name=player_name,
            match_date=match_date,
        )
        session.add(row)
    row.team_name = team_name
    row.match_date = match_date
    row.minutes = minutes
    row.goals = goals
    row.assists = assists
    row.shots = shots
    row.shots_on_target = shots_on_target
    row.fouls = fouls
    row.fouls_suffered = fouls_suffered
    row.cards = cards
    row.yellow_cards = yellow_cards
    row.red_cards = red_cards
    row.raw_json = json.dumps(raw, ensure_ascii=False)
    if commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()
    return row


def insert_odds_snapshot(
    session: Session,
    source_match_id: str | None,
    bookmaker: str,
    market: dict[str, Any],
    raw: dict[str, Any],
    source: str = "betfair-web",
    commit: bool = True,
) -> None:
    for outcome in market.get("outcomes", []):
        compact_raw = {
            "source": source,
            "home_team": raw.get("home_team"),
            "away_team": raw.get("away_team"),
            "commence_time": raw.get("commence_time"),
            "bookmaker": bookmaker,
            "market_key": market.get("key") or "unknown",
            "market_name": market.get("name"),
            "market_type": market.get("market_type") or market.get("key"),
            "market_category": "player" if market.get("player_prop") else "game",
            "team_side": outcome.get("team_side") or market.get("team_side"),
            "team_name": outcome.get("team_name"),
            "player_name": outcome.get("player_name"),
            "player_id": outcome.get("player_id"),
            "outcome_name": outcome.get("name") or "unknown",
            "point": outcome.get("point") if outcome.get("point") is not None else market.get("handicap"),
            "price": outcome.get("price"),
            "main_line": outcome.get("main_line"),
            "market_id": outcome.get("market_id") or market.get("market_id"),
            "market_type_raw": outcome.get("market_type_raw") or market.get("market_type_raw"),
            "selection_id": outcome.get("selection_id"),
            "runner_name": outcome.get("runner_name"),
            "runner_handicap": outcome.get("runner_handicap"),
        }
        session.add(
            OddsSnapshot(
                source=source,
                source_match_id=source_match_id,
                bookmaker=bookmaker,
                market_key=market.get("key") or "unknown",
                outcome_name=outcome.get("name") or "unknown",
                price=outcome.get("price"),
                point=compact_raw["point"],
                raw_json=json.dumps(compact_raw, ensure_ascii=False),
                raw_home_team=compact_raw["home_team"],
                raw_away_team=compact_raw["away_team"],
                commence_time=compact_raw["commence_time"],
                market_name=compact_raw["market_name"],
                market_type=compact_raw["market_type"],
                market_category=compact_raw["market_category"],
                team_side=compact_raw["team_side"],
                team_name=compact_raw["team_name"],
                player_name=compact_raw["player_name"],
                player_id=compact_raw["player_id"],
                main_line=compact_raw["main_line"],
                market_id=compact_raw["market_id"],
                market_type_raw=compact_raw["market_type_raw"],
                selection_id=compact_raw["selection_id"],
                runner_name=compact_raw["runner_name"],
                runner_handicap=_float_or_none(compact_raw["runner_handicap"]),
            )
        )
    if commit:
        session.commit()


def upsert_player_lineup(
    session: Session,
    source_match_id: str,
    player_id: str | None,
    player_name: str,
    team_name: str,
    starter: bool,
    position: str | None,
    jersey: str | None,
    raw: dict[str, Any],
    source: str = "espn",
    commit: bool = True,
) -> PlayerLineup:
    row = session.exec(
        select(PlayerLineup).where(
            PlayerLineup.source == source,
            PlayerLineup.source_match_id == source_match_id,
            PlayerLineup.player_name == player_name,
            PlayerLineup.team_name == team_name,
        )
    ).first()
    if not row:
        row = PlayerLineup(
            source=source,
            source_match_id=source_match_id,
            player_id=player_id,
            player_name=player_name,
            team_name=team_name,
        )
        session.add(row)
    row.player_id = player_id
    row.starter = starter
    row.position = position
    row.jersey = jersey
    row.raw_json = json.dumps(raw, ensure_ascii=False)
    if commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()
    return row


def upsert_analysis_result(session: Session, result: AnalysisResult, commit: bool = True) -> None:
    row = session.exec(
        select(AnalysisResult).where(
            AnalysisResult.target_date == result.target_date,
            AnalysisResult.source_match_id == result.source_match_id,
            AnalysisResult.market_key == result.market_key,
            AnalysisResult.pick == result.pick,
        )
    ).first()
    if row:
        row.score = result.score
        row.home_hit_rate = result.home_hit_rate
        row.away_hit_rate = result.away_hit_rate
        row.sample_size = result.sample_size
        row.reason = result.reason
        row.created_at = utc_now()
    else:
        session.add(result)
    if commit:
        session.commit()
    else:
        session.flush()
