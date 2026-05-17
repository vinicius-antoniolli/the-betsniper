from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PROBES_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = PROBES_DIR / "fixtures"
BETFAIR_COMPETITION_PAGE = FIXTURES_DIR / "betfair_competition_page.html"
PUBLIC_DB = ROOT_DIR / "public_data" / "betsniper_public.db"


def ensure_project_imports() -> None:
    root = str(ROOT_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
