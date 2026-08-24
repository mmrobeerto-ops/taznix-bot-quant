import re
path_html = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path_html, 'r', encoding='utf-8') as f:
    html = f.read()
html = re.sub(r'tzanix_quantum-core\.js\??[^"]*"', r'tzanix_quantum-core.js?v=creation1"', html)
with open(path_html, 'w', encoding='utf-8') as f:
    f.write(html)
