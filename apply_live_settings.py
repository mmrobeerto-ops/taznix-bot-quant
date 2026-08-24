import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update K-Factor
code = code.replace("if factor_k < -99.0: # Bypassed for simulation", "if factor_k < 0.5:")
code = code.replace("Factor K Subcrítico ({factor_k:.4f} < 1.0)", "Factor K Subcrítico ({factor_k:.4f} < 0.5)")

# 2. Update Z-Score thresholds
code = code.replace("z_score < -2.5", "z_score < -1.8")
code = code.replace("Z: {z_score:.2f} < -2.5", "Z: {z_score:.2f} < -1.8")
code = code.replace("z_score > 2.5", "z_score > 1.8")
code = code.replace("Z: {z_score:.2f} > 2.5", "Z: {z_score:.2f} > 1.8")

# 3. Disable candlestick confirmation (set them to True by default, ignore the actual _is_bullish_engulfing return value)
code = code.replace("confirm_buy_candle = self._is_bullish_engulfing(v1, v0)", "confirm_buy_candle = True # self._is_bullish_engulfing(v1, v0)")
code = code.replace("confirm_sell_candle = self._is_bearish_engulfing(v1, v0) or self._is_three_black_crows(v2, v1, v0)", "confirm_sell_candle = True # self._is_bearish_engulfing(v1, v0) or self._is_three_black_crows(v2, v1, v0)")

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
