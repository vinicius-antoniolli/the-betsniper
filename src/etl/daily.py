from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, delete, select

from config import FootballLeagueConfig, football_leagues, settings
from src.collectors.espn import (
    EspnClient,
    competitor_by_home_away,
    is_completed,
    score_value,
    team_id,
    team_name,
)
from src.collectors.betfair_web import BetfairWebClient
from src.db.models import AnalysisResult, Match, OddsSnapshot, PlayerLineup
from src.db.session import get_session
from src.etl.analysis import analyze_match
from src.etl.helpers import (
    insert_odds_snapshot,
    parse_iso_datetime,
    upsert_match_from_espn,
    upsert_player_lineup,
    upsert_player_stat,
    upsert_team_stat,
)
from src.time_utils import match_kickoff_is_expired


log = logging.getLogger(__name__)
HISTORY_SIDE_LIMIT = 10


def _today() -> str:
    return datetime.now(ZoneInfo(settings.app_timezone)).date().isoformat()


def target_date_window(target_date: str | None = None, days: int = 2) -> list[str]:
    base = datetime.fromisoformat(target_date).date() if target_date else datetime.now(ZoneInfo(settings.app_timezone)).date()
    return [(base + timedelta(days=offset)).isoformat() for offset in range(max(days, 1))]


def _extract_team_ids(event: dict) -> tuple[str | None, str | None]:
    home = competitor_by_home_away(event, "home")
    away = competitor_by_home_away(event, "away")
    return team_id(home), team_id(away)


def _event_team_is_home(event: dict, target_team_id: str) -> bool | None:
    competition = (event.get("competitions") or [{}])[0]
    for competitor in competition.get("competitors", []):
        if team_id(competitor) == target_team_id:
            return competitor.get("homeAway") == "home"
    return None


def _espn_all_competition_history(
    session: Session,
    team_id_value: str,
    target_date: str,
    limit: int = HISTORY_SIDE_LIMIT,
) -> list[tuple[dict, EspnClient]]:
    events: list[tuple[dict, EspnClient]] = []
    seen_ids: set[str] = set()
    for history_league in football_leagues():
        client = EspnClient(session, history_league.espn_slug, history_league.espn_season)
        try:
            schedule = client.team_schedule(team_id_value)
        except Exception as exc:
            log.warning("Histórico ESPN falhou: %s | %s | %s", history_league.name, team_id_value, exc)
            continue
        for event in schedule:
            event_id = str(event.get("id") or "")
            if not event_id or event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            events.append((event, client))

    history = [
        (event, client)
        for event, client in events
        if is_completed(event)
        and _event_local_date(event) < target_date
        and _event_team_is_home(event, team_id_value) is not None
    ]
    history.sort(key=lambda item: item[0].get("date") or "", reverse=True)

    selected: list[tuple[dict, EspnClient]] = []
    counts = {True: 0, False: 0}
    for event, client in history:
        is_home = _event_team_is_home(event, team_id_value)
        if is_home is None or counts[is_home] >= limit:
            continue
        counts[is_home] += 1
        selected.append((event, client))
        if counts[True] >= limit and counts[False] >= limit:
            break
    return selected


def _event_local_date(event: dict) -> str:
    parsed_date = parse_iso_datetime(event.get("date"))
    return parsed_date.date().isoformat() if parsed_date else (event.get("date") or "")[:10]


def _espn_source_match_id(event: dict) -> str:
    competition = (event.get("competitions") or [{}])[0]
    value = event.get("id") or competition.get("id")
    return str(value) if value else ""


def _espn_kickoff_at(event: dict) -> datetime | None:
    competition = (event.get("competitions") or [{}])[0]
    return parse_iso_datetime(event.get("date") or competition.get("date"))


def _discard_expired_espn_match(session: Session, source_match_id: str) -> None:
    if not source_match_id:
        return
    session.exec(delete(AnalysisResult).where(AnalysisResult.source_match_id == source_match_id))
    session.exec(delete(PlayerLineup).where(PlayerLineup.source == "espn", PlayerLineup.source_match_id == source_match_id))
    session.exec(delete(OddsSnapshot).where(OddsSnapshot.source_match_id == source_match_id))
    session.exec(delete(Match).where(Match.source == "espn", Match.source_match_id == source_match_id))
    session.commit()


def _number_from_value(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", ""))
    except (TypeError, ValueError):
        return None


def _stat_float_value(stats: list[dict], *names: str) -> float | None:
    targets = set(names)
    for item in stats:
        if item.get("name") not in targets:
            continue
        value = item.get("value")
        if value is None:
            value = item.get("displayValue")
        return _number_from_value(value)
    return None


def _stat_value(stats: list[dict], *names: str) -> int | None:
    value = _stat_float_value(stats, *names)
    return int(value) if value is not None else None


def _competitor_first_period_score(competitor: dict | None) -> int | None:
    if not competitor:
        return None
    linescores = competitor.get("linescores") or []
    if not linescores:
        return None
    first = linescores[0] or {}
    value = first.get("value")
    if value is None:
        value = first.get("displayValue")
    return _stat_value([{"name": "score", "value": value}], "score")


def _summary_first_period_score(summary: dict, team_display_name: str) -> int | None:
    competitors = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or []
    for competitor in competitors:
        team = competitor.get("team") or {}
        names = {
            team.get("displayName"),
            team.get("shortDisplayName"),
            team.get("name"),
            team.get("location"),
        }
        if team_display_name in names:
            return _competitor_first_period_score(competitor)
    return None


def _sum_known(*values: int | None) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _summary_team_stats(summary: dict, team_display_name: str) -> dict[str, int | float | None]:
    for item in (summary.get("boxscore") or {}).get("teams") or []:
        team = item.get("team") or {}
        names = {
            team.get("displayName"),
            team.get("shortDisplayName"),
            team.get("name"),
            team.get("location"),
        }
        if team_display_name not in names:
            continue
        stats = item.get("statistics") or []
        yellow = _stat_value(stats, "yellowCards")
        red = _stat_value(stats, "redCards")
        return {
            "corners": _stat_value(stats, "wonCorners"),
            "cards": _sum_known(yellow, red),
            "shots_total": _stat_value(stats, "totalShots"),
            "shots_on_target": _stat_value(stats, "shotsOnTarget"),
            "offsides": _stat_value(stats, "offsides"),
            "throw_ins": _stat_value(stats, "throwIns"),
            "first_half_corners": _stat_value(stats, "firstHalfCorners"),
            "xg": _stat_float_value(stats, "expectedGoals", "xG"),
            "fouls_committed": _stat_value(stats, "foulsCommitted"),
        }
    return {
        "corners": None,
        "cards": None,
        "shots_total": None,
        "shots_on_target": None,
        "offsides": None,
        "throw_ins": None,
        "first_half_corners": None,
        "xg": None,
        "fouls_committed": None,
    }


def _store_espn_player_stats(session: Session, summary: dict, source_match_id: str, match_date: str) -> None:
    for group in summary.get("rosters") or []:
        team = group.get("team") or {}
        team_display = team.get("displayName") or team.get("shortDisplayName") or team.get("name")
        for item in group.get("roster") or []:
            athlete = item.get("athlete") or {}
            name = (athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName") or "").strip()
            if not name:
                continue
            stats = item.get("stats") or []
            yellow = _stat_value(stats, "yellowCards")
            red = _stat_value(stats, "redCards")
            upsert_player_stat(
                session=session,
                source_match_id=source_match_id,
                player_name=name,
                team_name=team_display,
                match_date=match_date,
                minutes=_stat_value(stats, "minutes"),
                goals=_stat_value(stats, "totalGoals"),
                assists=_stat_value(stats, "goalAssists"),
                shots=_stat_value(stats, "totalShots"),
                shots_on_target=_stat_value(stats, "shotsOnTarget"),
                fouls=_stat_value(stats, "foulsCommitted"),
                fouls_suffered=_stat_value(stats, "foulsSuffered"),
                cards=_sum_known(yellow, red),
                raw=item,
                source="espn",
                yellow_cards=yellow,
                red_cards=red,
                commit=False,
            )


def _store_espn_event_as_team_stats(session: Session, client: EspnClient, event: dict) -> None:
    home = competitor_by_home_away(event, "home")
    away = competitor_by_home_away(event, "away")
    fixture_id = str(event.get("id"))
    match_date = _event_local_date(event)

    home_name = team_name(home)
    away_name = team_name(away)
    home_goals = score_value(home)
    away_goals = score_value(away)

    if home_goals is None or away_goals is None:
        return

    try:
        summary = client.summary(fixture_id)
    except Exception as exc:
        log.warning("Summary ESPN falhou: %s | %s", fixture_id, exc)
        summary = {}

    home_first_half_goals = _summary_first_period_score(summary, home_name)
    if home_first_half_goals is None:
        home_first_half_goals = _competitor_first_period_score(home)
    away_first_half_goals = _summary_first_period_score(summary, away_name)
    if away_first_half_goals is None:
        away_first_half_goals = _competitor_first_period_score(away)
    home_extra = _summary_team_stats(summary, home_name)
    away_extra = _summary_team_stats(summary, away_name)
    _store_espn_player_stats(session, summary, fixture_id, match_date)

    upsert_team_stat(
        session=session,
        source_match_id=fixture_id,
        team_name=home_name,
        opponent_name=away_name,
        match_date=match_date,
        is_home=True,
        goals_for=home_goals,
        goals_against=away_goals,
        raw=event,
        source="espn",
        corners_for=home_extra["corners"],
        corners_against=away_extra["corners"],
        cards_for=home_extra["cards"],
        cards_against=away_extra["cards"],
        shots_total_for=home_extra["shots_total"],
        shots_total_against=away_extra["shots_total"],
        shots_on_target_for=home_extra["shots_on_target"],
        shots_on_target_against=away_extra["shots_on_target"],
        offsides_for=home_extra["offsides"],
        offsides_against=away_extra["offsides"],
        throw_ins_for=home_extra["throw_ins"],
        first_half_goals_for=home_first_half_goals,
        first_half_goals_against=away_first_half_goals,
        first_half_corners_for=home_extra["first_half_corners"],
        first_half_corners_against=away_extra["first_half_corners"],
        xg_for=home_extra["xg"],
        xg_against=away_extra["xg"],
        fouls_committed=home_extra["fouls_committed"],
        fouls_suffered=away_extra["fouls_committed"],
        commit=False,
    )
    upsert_team_stat(
        session=session,
        source_match_id=fixture_id,
        team_name=away_name,
        opponent_name=home_name,
        match_date=match_date,
        is_home=False,
        goals_for=away_goals,
        goals_against=home_goals,
        raw=event,
        source="espn",
        corners_for=away_extra["corners"],
        corners_against=home_extra["corners"],
        cards_for=away_extra["cards"],
        cards_against=home_extra["cards"],
        shots_total_for=away_extra["shots_total"],
        shots_total_against=home_extra["shots_total"],
        shots_on_target_for=away_extra["shots_on_target"],
        shots_on_target_against=home_extra["shots_on_target"],
        offsides_for=away_extra["offsides"],
        offsides_against=home_extra["offsides"],
        throw_ins_for=away_extra["throw_ins"],
        first_half_goals_for=away_first_half_goals,
        first_half_goals_against=home_first_half_goals,
        first_half_corners_for=away_extra["first_half_corners"],
        first_half_corners_against=home_extra["first_half_corners"],
        xg_for=away_extra["xg"],
        xg_against=home_extra["xg"],
        fouls_committed=away_extra["fouls_committed"],
        fouls_suffered=home_extra["fouls_committed"],
        commit=False,
    )
    session.commit()


def _store_espn_lineups(session: Session, client: EspnClient, source_match_id: str) -> None:
    try:
        summary = client.summary(source_match_id)
    except Exception as exc:
        log.warning("Escalação ESPN falhou: %s | %s", source_match_id, exc)
        return

    for group in summary.get("rosters") or []:
        team = group.get("team") or {}
        team_display = team.get("displayName") or team.get("shortDisplayName") or team.get("name")
        if not team_display:
            continue
        for item in group.get("roster") or []:
            athlete = item.get("athlete") or {}
            name = (athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName") or "").strip()
            if not name:
                continue
            position = item.get("position") or athlete.get("position") or {}
            upsert_player_lineup(
                session=session,
                source_match_id=source_match_id,
                player_id=str(athlete.get("id")) if athlete.get("id") else None,
                player_name=name,
                team_name=team_display,
                starter=bool(item.get("starter")),
                position=position.get("abbreviation") or position.get("displayName") or position.get("name"),
                jersey=str(item.get("jersey") or athlete.get("jersey") or "") or None,
                raw=item,
                source="espn",
                commit=False,
            )
    session.commit()


def _apply_league_label(session: Session, match: Match, league: FootballLeagueConfig) -> Match:
    if match.league_name == league.name:
        return match
    match.league_name = league.name
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def collect_fixtures_and_history(session: Session, target_date: str) -> list[Match]:
    all_matches: list[Match] = []
    for league in football_leagues():
        client = EspnClient(session, league.espn_slug, league.espn_season)
        fixtures = client.scoreboard_by_date(target_date)
        matches: list[Match] = []

        log.info("Jogos ESPN %s encontrados: %s", league.name, len(fixtures))
        for item in fixtures:
            kickoff_at = _espn_kickoff_at(item)
            if match_kickoff_is_expired(kickoff_at):
                source_match_id = _espn_source_match_id(item)
                home = team_name(competitor_by_home_away(item, "home"))
                away = team_name(competitor_by_home_away(item, "away"))
                log.info(
                    "Jogo ESPN descartado por inicio ha mais de 2h: %s | %s x %s | %s",
                    source_match_id,
                    home,
                    away,
                    kickoff_at,
                )
                _discard_expired_espn_match(session, source_match_id)
                continue
            match = _apply_league_label(session, upsert_match_from_espn(session, item, target_date), league)
            matches.append(match)
            all_matches.append(match)
            _store_espn_lineups(session, client, match.source_match_id)

            for team_id_value in _extract_team_ids(item):
                if not team_id_value:
                    continue
                for past, history_client in _espn_all_competition_history(session, team_id_value, target_date):
                    _store_espn_event_as_team_stats(session, history_client, past)
    return all_matches


def collect_odds(session: Session, target_date: str) -> None:
    total_events = 0

    if not settings.betfair_web_enabled:
        log.info("BETFAIR_WEB_ENABLED=false. Pulando odds.")
        return

    clients = [
        BetfairWebClient(session, target_date, league.name, league.betfair_competition_url)
        for league in football_leagues()
    ]

    for client in clients:
        source_match_ids = []
        query = select(Match.source_match_id).where(Match.target_date == target_date)
        league_name = getattr(client, "league_name", None)
        if league_name:
            query = query.where(Match.league_name == league_name)
        source_match_ids = session.exec(query).all()
        try:
            events = client.odds()
        except Exception as exc:
            log.warning("Eventos odds %s falharam: %s", client.source, exc)
            events = []
        total_events += len(events)
        log.info("Eventos odds %s encontrados: %s", client.source, len(events))

        if events and source_match_ids:
            session.exec(
                delete(OddsSnapshot).where(
                    OddsSnapshot.source == client.source,
                    OddsSnapshot.source_match_id.in_(source_match_ids),
                )
            )
            session.commit()

        for event in events:
            source_match_id = event.get("id") or event.get("canonical_event_id")
            for bookmaker in event.get("bookmakers", []):
                title = bookmaker.get("title") or bookmaker.get("key") or "unknown"
                for market in bookmaker.get("markets", []):
                    insert_odds_snapshot(session, source_match_id, title, market, event, source=client.source, commit=False)
        session.commit()

    log.info("Eventos odds total encontrados: %s", total_events)


def run_daily_etl(target_date: str | None = None, include_odds: bool = True) -> None:
    date_value = target_date or _today()
    log.info("ETL início: %s", date_value)

    with get_session() as session:
        matches = collect_fixtures_and_history(session, date_value)
        if include_odds:
            collect_odds(session, date_value)
        for match in matches:
            analyze_match(session, match)

    log.info("ETL fim: %s", date_value)


def run_etl_window(target_date: str | None = None, include_odds: bool = True, days: int = 2) -> None:
    for date_value in target_date_window(target_date, days):
        run_daily_etl(target_date=date_value, include_odds=include_odds)
