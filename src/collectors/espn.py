from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

import httpx
from sqlmodel import Session

from config import settings
from src.db.cache import get_cached, put_cached


log = logging.getLogger(__name__)


class EspnClient:
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    SOURCE = "espn"

    def __init__(self, session: Session, league_slug: str | None = None, season: int | None = None) -> None:
        self.session = session
        self.league_slug = league_slug or settings.espn_league_slug
        self.season = season or settings.espn_season
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

    def _get(self, endpoint: str, params: dict[str, Any], ttl: timedelta) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{self.league_slug}/{endpoint}"
        cached = get_cached(self.session, self.SOURCE, url, params)
        if cached:
            return json.loads(cached)

        response = httpx.get(url, params=params, headers=self.headers, timeout=30)
        response.raise_for_status()
        body = response.text
        put_cached(self.session, self.SOURCE, url, params, body, ttl, response.status_code)
        return response.json()

    def scoreboard_by_date(self, target_date: str) -> list[dict[str, Any]]:
        date_param = target_date.replace("-", "")
        payload = self._get(
            "scoreboard",
            {"dates": date_param, "limit": 100},
            ttl=timedelta(minutes=30),
        )
        return list(payload.get("events", []))

    def team_schedule(self, team_id: str) -> list[dict[str, Any]]:
        payload = self._get(
            f"teams/{team_id}/schedule",
            {"season": self.season},
            ttl=timedelta(hours=12),
        )
        return list(payload.get("events", []))

    def summary(self, event_id: str) -> dict[str, Any]:
        return self._get(
            "summary",
            {"event": event_id},
            ttl=timedelta(minutes=15),
        )


def competitor_by_home_away(event: dict[str, Any], home_away: str) -> dict[str, Any] | None:
    competition = (event.get("competitions") or [{}])[0]
    for competitor in competition.get("competitors", []):
        if competitor.get("homeAway") == home_away:
            return competitor
    return None


def team_id(competitor: dict[str, Any] | None) -> str | None:
    if not competitor:
        return None
    team = competitor.get("team") or {}
    value = team.get("id") or competitor.get("id")
    return str(value) if value else None


def team_name(competitor: dict[str, Any] | None) -> str:
    if not competitor:
        return "Unknown"
    team = competitor.get("team") or {}
    return team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "Unknown"


def score_value(competitor: dict[str, Any] | None) -> int | None:
    if not competitor:
        return None
    raw = competitor.get("score")
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("displayValue")
    if raw in (None, ""):
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def is_completed(event: dict[str, Any]) -> bool:
    competition = (event.get("competitions") or [{}])[0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    return bool(status_type.get("completed"))
