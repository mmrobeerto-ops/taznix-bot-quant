import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

html = re.sub(r'tzanix_quantum-core\.js\??[^"]*"', r'tzanix_quantum-core.js?v=hologram_rings"', html)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
