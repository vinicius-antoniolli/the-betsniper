from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import ROOT_DIR, settings


log = logging.getLogger(__name__)


def rooted_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def public_snapshot_base_date() -> str | None:
    if not settings.public_viewer_mode:
        return None
    metadata_path = rooted_path(settings.public_snapshot_metadata)
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
    public_base_date = public_snapshot_base_date()
    if public_base_date:
        return datetime.fromisoformat(public_base_date).date()
    return datetime.now(ZoneInfo(settings.app_timezone)).date()
