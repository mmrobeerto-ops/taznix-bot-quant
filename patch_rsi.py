import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Comment out RSI rejections
code = re.sub(r'elif not macro_rsi_buy_aligned:', r'# elif not macro_rsi_buy_aligned:', code)
code = re.sub(r'self\._record_rejected_order\("BUY", price, f"\{reason\} \[REJECTED: Multilevel RSI not aligned.*?\]"\)', r'# pass', code)

code = re.sub(r'elif not macro_rsi_sell_aligned:', r'# elif not macro_rsi_sell_aligned:', code)
code = re.sub(r'self\._record_rejected_order\("SELL", price, f"\{reason\} \[REJECTED: Multilevel RSI not aligned.*?\]"\)', r'# pass', code)

code = re.sub(r'elif current_rsi is not None and current_rsi > 65\.0:', r'# elif current_rsi is not None and current_rsi > 65.0:', code)
code = re.sub(r'self\._record_rejected_order\("BUY", price, f"\{reason\} \[REJECTED: RSI 1m is overbought.*?\]"\)', r'# pass', code)

code = re.sub(r'elif current_rsi is not None and current_rsi < 35\.0:', r'# elif current_rsi is not None and current_rsi < 35.0:', code)
code = re.sub(r'self\._record_rejected_order\("SELL", price, f"\{reason\} \[REJECTED: RSI 1m is oversold.*?\]"\)', r'# pass', code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)

