import httpx
import os

from _paths import ensure_project_imports

ensure_project_imports()

from src.collectors.betfair_web import BetfairMatch, BetfairWebClient

os.environ["PUBLIC_VIEWER_MODE"] = "true"

class MockClient(BetfairWebClient):
    def _discover_event_urls_from_html(self, matches):
        url = self.competition_url or 'https://www.betfair.bet.br/apostas/futebol/brasileir%C3%A3o-s%C3%A9rie-a/c-13'
        try:
            response = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True)
            response.raise_for_status()
            print("Status:", response.status_code)
            print("Response len:", len(response.text))
        except Exception as exc:
            print("Error:", exc)
            return {}
        
        events = []
        for item in self._sports_events_from_html(response.text, url):
            event_url = item.get("url") or self._event_url(item["name"], item["event_id"])
            events.append((item["name"], event_url))
        
        print("Parsed events:", events)
        
        found = {}
        for match in matches:
            key = self._norm(match.label)
            for event_name, event_url in events:
                if self._event_text_matches(event_name, match):
                    found[key] = event_url
                    break
        return found

client = MockClient(None, "2026-05-15")
matches = [BetfairMatch("123", "Internacional", "Vasco da Gama", None)]
urls = client._discover_event_urls_from_html(matches)
print("Found:", urls)
