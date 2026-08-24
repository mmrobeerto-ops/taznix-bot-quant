import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Completely remove anything after threejs-canvas-container wrapper up to </section>
html = re.sub(r'(<div class="chart-viewport-wrapper">.*?</div>)\s*<div class="chart-actions-toolbar">.*?</section>', r'\1\n            </section>', html, flags=re.DOTALL)

with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
