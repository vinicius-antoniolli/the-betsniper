import re

from _paths import BETFAIR_COMPETITION_PAGE

html = BETFAIR_COMPETITION_PAGE.read_text(encoding='utf-8')
matches = re.findall(r'href=["\'][^"\']*35570147[^"\']*["\']', html)
print(matches[:5])
