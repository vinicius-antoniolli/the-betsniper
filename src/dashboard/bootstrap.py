from __future__ import annotations

import os
from pathlib import Path


TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def configure_public_viewer_database() -> None:
    public_db = project_root() / "public_data" / "betsniper_public.db"
    public_mode = os.environ.get("PUBLIC_VIEWER_MODE", "").strip().lower() in TRUE_ENV_VALUES
    if public_mode and public_db.exists():
        os.environ.setdefault("APP_DB_URL", "sqlite:///public_data/betsniper_public.db")
