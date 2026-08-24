import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Make BTC text smaller
html = html.replace('font-size: 2.8rem;', 'font-size: 1.2rem; text-align: right;')
html = html.replace('font-size: 3.5rem;', 'font-size: 1.6rem;')

# Tone down the text shadow glow
html = html.replace('text-shadow: 0 0 20px #00F0FF, 0 0 40px #00F0FF;', 'text-shadow: 0 0 10px #00F0FF, 0 0 20px #00F0FF;')

# Bump cache buster for JS
html = re.sub(r'tzanix_quantum-core\.js\??[^"]*"', r'tzanix_quantum-core.js?v=hologram_rings_fixed"', html)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
