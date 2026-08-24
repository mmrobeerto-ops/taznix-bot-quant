import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Fix the broken indents
code = re.sub(r'                        elif not volume_institutional:', r'            elif not volume_institutional:', code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)

