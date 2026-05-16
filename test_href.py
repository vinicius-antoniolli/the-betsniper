import re
html = open('test_betfair.html', 'r', encoding='utf-8').read()
matches = re.findall(r'href=["\'][^"\']*35570147[^"\']*["\']', html)
print(matches[:5])
