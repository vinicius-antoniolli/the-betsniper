import re
import urllib.request

from _paths import BETFAIR_COMPETITION_PAGE

url = 'https://www.betfair.bet.br/apostas/futebol/brasileir%C3%A3o-s%C3%A9rie-a/c-13'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    print('Length:', len(html))
    print('eventId matches:', len(re.findall(r'eventId', html)))
    print('eventId pattern matches:', len(re.findall(r'"eventId"\s*:\s*\d+\s*,\s*"name"\s*:\s*"[^"]+?"', html)))
    print('href pattern matches:', len(re.findall(r'href=["\'][^"\']*/e-\d+[^"\']*["\']', html)))
    BETFAIR_COMPETITION_PAGE.parent.mkdir(parents=True, exist_ok=True)
    BETFAIR_COMPETITION_PAGE.write_text(html, encoding='utf-8')
except Exception as e:
    print(e)
