from src.collectors.betfair_web import BetfairWebClient, BetfairMatch
import os
os.environ["PUBLIC_VIEWER_MODE"] = "true"

client = BetfairWebClient(None, "2026-05-15")
url = client.competition_url or 'https://www.betfair.bet.br/apostas/futebol/brasil-s%C3%A9rie-a/c-13'
print("Using URL:", url)
import httpx
resp = httpx.get(url, headers={'User-Agent': 'Mozilla/5.0'})
events = client._sports_events_from_html(resp.text, url)
print("Events:", events)
