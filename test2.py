import re
html = open('test_betfair.html', 'r', encoding='utf-8').read()
names = re.findall(r'"eventId"\s*:\s*\d+\s*,\s*"name"\s*:\s*"([^"]+?)"', html)
for name in names:
    print(name)
