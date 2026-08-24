import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# Make red much stronger and bloom more intense
old_red = """targetColor.set(1.0, 0.18, 0.39); // Red
        bloomPass.strength = 4.0;"""
new_red = """targetColor.set(1.0, 0.0, 0.05); // Pure Intense Red
        bloomPass.strength = 7.0; // Extreme Bloom for Red"""

js_code = js_code.replace(old_red, new_red)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
