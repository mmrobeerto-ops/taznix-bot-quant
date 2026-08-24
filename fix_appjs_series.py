import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Comment out all usages of the missing series objects
js = re.sub(r'(if \(showSma200\) sma200Series)', r'// \1', js)
js = re.sub(r'(if \(showVwap\) vwapSeries)', r'// \1', js)
js = re.sub(r'(if \(showVwapBands\))', r'if (false)', js)
js = re.sub(r'(if \(tick\.vwap .*? showVwap\))', r'if (false)', js)
js = re.sub(r'(if \(tick\.vwap_upper .*? showVwapBands\))', r'if (false)', js)
js = re.sub(r'(if \(tick\.vwap_lower .*? showVwapBands\))', r'if (false)', js)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
