import re

path_html = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path_html, 'r', encoding='utf-8') as f:
    html = f.read()

# Add cache buster to all custom script tags
html = re.sub(r'src="app\.js\??[^"]*"', r'src="app.js?v=999"', html)
html = re.sub(r'src="tzanix_quantum-core\.js\??[^"]*"', r'src="tzanix_quantum-core.js?v=999"', html)

with open(path_html, 'w', encoding='utf-8') as f:
    f.write(html)
