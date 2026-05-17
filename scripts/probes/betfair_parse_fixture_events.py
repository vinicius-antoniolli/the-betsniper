from _paths import BETFAIR_COMPETITION_PAGE, ensure_project_imports

ensure_project_imports()

from src.collectors.betfair_web import BetfairWebClient

html = BETFAIR_COMPETITION_PAGE.read_text(encoding='utf-8')
client = BetfairWebClient(None, '2026-05-15')
events = client._sports_events_from_html(html, 'https://www.betfair.bet.br/apostas/futebol/brasileir%C3%A3o-s%C3%A9rie-a/c-13')
print("Events returned:", events)
