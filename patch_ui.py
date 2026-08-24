import re
import os

html_path = "C:/Users/52664/.gemini/antigravity/scratch/sfa-ifa-pro/static/index.html"
js_path = "C:/Users/52664/.gemini/antigravity/scratch/sfa-ifa-pro/static/app.js"

# 1. Update HTML
with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()

# Remove legend items
html_content = re.sub(r'<span class="legend-item"><span class="legend-color ema9"></span>EMA 9</span>', "", html_content)
html_content = re.sub(r'<span class="legend-item"><span class="legend-color ema21"></span>EMA 21</span>', "", html_content)

# Remove buttons
html_content = re.sub(r'<button class="btn btn-mini active" id="btn-toggle-ema9">EMA 9</button>', "", html_content)
html_content = re.sub(r'<button class="btn btn-mini active" id="btn-toggle-ema21">EMA 21</button>', "", html_content)

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

# 2. Update JS
with open(js_path, "r", encoding="utf-8") as f:
    js_content = f.read()

# Remove series variables
js_content = re.sub(r'let ema9Series;\nlet ema21Series;\n', "", js_content)
js_content = re.sub(r'let showEma9 = true;\nlet showEma21 = true;\n', "", js_content)

# Remove series initialization
js_content = re.sub(r'// 3\. EMA 9 Series.*?title: \'EMA 9\'.*?}\);', "", js_content, flags=re.DOTALL)
js_content = re.sub(r'// 4\. EMA 21 Series.*?title: \'EMA 21\'.*?}\);', "", js_content, flags=re.DOTALL)

# Remove array declarations
js_content = re.sub(r'const ema9s = \[\];\n\s+const ema21s = \[\];\n', "", js_content)

# Remove data pushing
js_content = re.sub(r'if \(t\.ema_9 !== null.*?ema9s\.push.*?;\n', "", js_content)
js_content = re.sub(r'if \(t\.ema_21 !== null.*?ema21s\.push.*?;\n', "", js_content)

# Remove setData
js_content = re.sub(r'if \(showEma9\) ema9Series\.setData\(deduplicateSeriesData\(ema9s\)\);\n', "", js_content)
js_content = re.sub(r'if \(showEma21\) ema21Series\.setData\(deduplicateSeriesData\(ema21s\)\);\n', "", js_content)

# Remove update ticks
js_content = re.sub(r'if \(tick\.ema_9 !== null && tick\.ema_9 !== undefined && showEma9\) \{.*?\}', "", js_content, flags=re.DOTALL)
js_content = re.sub(r'if \(tick\.ema_21 !== null && tick\.ema_21 !== undefined && showEma21\) \{.*?\}', "", js_content, flags=re.DOTALL)

# Remove button listeners
js_content = re.sub(r'document\.getElementById\("btn-toggle-ema9"\)\.addEventListener.*?\}\);', "", js_content, flags=re.DOTALL)
js_content = re.sub(r'document\.getElementById\("btn-toggle-ema21"\)\.addEventListener.*?\}\);', "", js_content, flags=re.DOTALL)


with open(js_path, "w", encoding="utf-8") as f:
    f.write(js_content)

print("UI patched successfully")
