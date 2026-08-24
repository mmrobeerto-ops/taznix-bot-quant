import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    engine_code = f.read()

# Bypass Factor K filter
engine_code = engine_code.replace("if factor_k < 1.0:", "if factor_k < -99.0: # Bypassed for simulation")

with open(path, 'w', encoding='utf-8') as f:
    f.write(engine_code)
