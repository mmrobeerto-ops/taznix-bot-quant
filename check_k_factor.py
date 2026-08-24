import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    engine_code = f.read()

# The bot is rejecting trades due to K-Factor: "Filtro Masa Critica - Factor K Subcritico"
# We need to find this filter and bypass it by changing the condition or replacing the string.
# We will just replace the condition if factor_k < 1.0: or similar with if False:

# Since I don't know the exact variable name, I'll use regex to find the string and comment out the block.
# Let's just find "Factor K Subcr" and see how it's structured.
lines = engine_code.split('\n')
for i, line in enumerate(lines):
    if "Factor K Subcr" in line:
        print(f"Line {i}: {line}")
        if i-1 >= 0: print(f"Line {i-1}: {lines[i-1]}")
        if i-2 >= 0: print(f"Line {i-2}: {lines[i-2]}")

