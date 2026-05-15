from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
PUBLIC_DB = ROOT_DIR / "public_data" / "betsniper_public.db"

os.environ["PUBLIC_VIEWER_MODE"] = "true"
os.environ["BETFAIR_WEB_ENABLED"] = "false"
os.environ["X_AUTO_PUBLISH_ENABLED"] = "false"

if PUBLIC_DB.exists():
    os.environ.setdefault("APP_DB_URL", "sqlite:///public_data/betsniper_public.db")

import app  # noqa: E402,F401
