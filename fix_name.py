import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace any case variation of Cuantitativo
html = re.sub(r'(?i)cuantitativo', 'QUANT-X', html)
html = re.sub(r'(?i)quantitativo', 'QUANT-X', html)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
