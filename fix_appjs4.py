import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Completely remove the broken indicator listeners for vwap-bands and ofi
js = re.sub(r'// document\.getElementById\("btn-toggle-vwap-bands"\)\.addEventListener.*?\}\);', '', js, flags=re.DOTALL)
js = re.sub(r'// document\.getElementById\("btn-toggle-ofi"\)\.addEventListener.*?\}\);', '', js, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
