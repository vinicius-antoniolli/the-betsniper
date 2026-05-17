import re

from _paths import BETFAIR_COMPETITION_PAGE

html = BETFAIR_COMPETITION_PAGE.read_text(encoding='utf-8')
names = re.findall(r'"eventId"\s*:\s*\d+\s*,\s*"name"\s*:\s*"([^"]+?)"', html)
for name in names:
    print(name)
