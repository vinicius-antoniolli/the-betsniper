from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from config import settings


MATCH_EXPIRATION_GRACE_PERIOD = timedelta(hours=2)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def app_now() -> datetime:
    return datetime.now(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)


def app_local_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)
    return value


def expired_match_cutoff(now: datetime | None = None) -> datetime:
    current = app_local_datetime(now) if now else app_now()
    return current - MATCH_EXPIRATION_GRACE_PERIOD


def match_kickoff_is_expired(kickoff_at: datetime | None, now: datetime | None = None) -> bool:
    if kickoff_at is None:
        return False
    return app_local_datetime(kickoff_at) <= expired_match_cutoff(now)
