from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from config import ROOT_DIR, settings
from src.collectors.betfair_auth import (
    betfair_context_options,
    ensure_betfair_login,
    grant_betfair_geolocation,
    is_betfair_login_page,
)


def rooted(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


def main() -> None:
    storage_state = rooted(settings.betfair_storage_state)
    storage_state.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(**betfair_context_options(storage_state))
        grant_betfair_geolocation(context)
        page = context.new_page()
        page.goto(settings.betfair_base_url, wait_until="domcontentloaded", timeout=60_000)
        logged_in = ensure_betfair_login(page, storage_state, settings.betfair_base_url)
        if not logged_in or is_betfair_login_page(page):
            input("Login Betfair no navegador aberto. Depois ENTER aqui: ")
        context.storage_state(path=str(storage_state))
        context.close()
        browser.close()
    print(f"OK: {storage_state}")


if __name__ == "__main__":
    main()
