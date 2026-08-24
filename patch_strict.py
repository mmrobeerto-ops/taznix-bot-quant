import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Comment out strict ADX blocks
code = re.sub(r'if adx_15m < 25\.0:\s*self\._record_rejected_order.*?\n\s*elif', r'if', code)
code = re.sub(r'elif adx_15m < 25\.0:\s*self\._record_rejected_order.*?\n', r'', code)
code = re.sub(r'elif not adx_15m_rising:\s*self\._record_rejected_order.*?\n', r'', code)

# Relax volume
code = re.sub(r'volume_institutional = candles_1m\[-1\]\["volume"\] > avg_vol_20 \* 0\.75', r'volume_institutional = candles_1m[-1]["volume"] > avg_vol_20 * 0.50', code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)

