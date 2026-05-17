import os

from _paths import ensure_project_imports

ensure_project_imports()

from src.collectors.betfair_web import BetfairMatch, BetfairWebClient

os.environ["PUBLIC_VIEWER_MODE"] = "true"

client = BetfairWebClient(None, "2026-05-15")
matches = [BetfairMatch("123", "Internacional", "Vasco da Gama", None)]
urls = client._discover_event_urls_from_html(matches)
print("Found:", urls)
