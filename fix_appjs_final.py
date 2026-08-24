import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

js = re.sub(r'priceSeries\.setData\(candles\);', '', js)
js = re.sub(r'chart\.timeScale\(\)\.fitContent\(\);', '', js)
js = re.sub(r'priceSeries\.setMarkers\(chartMarkers\);', '', js)
js = re.sub(r'if \(priceSeries\) priceSeries\.update\(currentCandle\);', '', js)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
