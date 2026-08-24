import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace quantitativo with Quant-X (case insensitive)
html = re.sub(r'(?i)quantitativo', 'Quant-X', html)
# Let's also bump the cache buster for the core script
html = re.sub(r'tzanix_quantum-core\.js\??[^"]*"', r'tzanix_quantum-core.js?v=glsl_fbo"', html)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
