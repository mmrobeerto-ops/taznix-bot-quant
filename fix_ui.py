import re

# 1. Fix index.html
path_html = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path_html, 'r', encoding='utf-8') as f:
    html = f.read()

# I will find the chart-viewport-wrapper block
wrapper_str = '''<div class="chart-viewport-wrapper">
                    <div id="threejs-canvas-container" style="width:100%; height:100%; position:relative; overflow:hidden;"></div>
                </div>'''

# The rest of the section until "Right Workspace"
start_idx = html.find('<div class="chart-viewport-wrapper">')
end_idx = html.find('<!-- Right Workspace:')
if start_idx != -1 and end_idx != -1:
    before = html[:start_idx]
    after = html[end_idx:]
    # insert the wrapper and close the section properly
    new_html = before + wrapper_str + "\n            </div>\n\n            " + after
    with open(path_html, 'w', encoding='utf-8') as f:
        f.write(new_html)

# 2. Fix app.js
path_js = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path_js, 'r', encoding='utf-8') as f:
    js = f.read()

# Comment out event listeners for the deleted buttons
js = re.sub(r'(document\.getElementById\("btn-tf-[^"]+"\)\.addEventListener)', r'// \1', js)
js = re.sub(r'(document\.getElementById\("btn-toggle-[^"]+"\)\.addEventListener)', r'// \1', js)
js = re.sub(r'(document\.getElementById\("btn-sim-spike-[^"]+"\)\.addEventListener)', r'// \1', js)
js = re.sub(r'(document\.getElementById\("btn-force-[^"]+"\)\.addEventListener)', r'// \1', js)

with open(path_js, 'w', encoding='utf-8') as f:
    f.write(js)

