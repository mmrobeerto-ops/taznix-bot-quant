import re

css_path = 'static/style.css'
with open(css_path, 'r', encoding='utf-8') as f:
    css = f.read()

# Update Body Background
css = re.sub(r'body\s*\{[^}]*line-height:\s*1\.5;\n\}', '''body {
    background: radial-gradient(circle at 50% 50%, #0a111e 0%, #030508 100%),
                linear-gradient(rgba(0, 240, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 240, 255, 0.03) 1px, transparent 1px);
    background-size: 100% 100%, 40px 40px, 40px 40px;
    background-color: #030508;
    background-attachment: fixed;
    color: var(--text-primary);
    font-family: var(--font-body);
    min-height: 100vh;
    overflow-x: hidden;
    line-height: 1.5;
}''', css)

# Update Glass Panel
css = re.sub(r'\.glass-panel\s*\{[^}]*\}', '''.glass-panel {
    background: rgba(8, 12, 20, 0.70);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(0, 240, 255, 0.15);
    border-radius: 6px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
    transition: all 0.3s ease;
    position: relative;
}''', css)

# Update Glass Panel Hover
css = re.sub(r'\.glass-panel:hover\s*\{[^}]*\}', '''.glass-panel:hover {
    border-color: rgba(0, 240, 255, 0.35);
    box-shadow: 0 10px 30px rgba(0, 240, 255, 0.05);
}''', css)

# Update L-Brackets
css = re.sub(r'\.glass-panel::before,\s*\.glass-panel::after\s*\{[^}]*\}', '''.glass-panel::before, .glass-panel::after {
  content: "";
  position: absolute;
  width: 15px;
  height: 15px;
  border: 2px solid rgba(0, 240, 255, 0.5);
  pointer-events: none;
}''', css)

# Update Card Titles / Section Headers
css = re.sub(r'\.card-title\s*\{[^}]*\}', '''.card-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    color: #7D8590;
    text-transform: uppercase;
}''', css)

css = re.sub(r'\.section-header-title\s*\{[^}]*\}', '''.section-header-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    color: #7D8590;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}''', css)

# Update Section Header padding/border
css = re.sub(r'\.section-header\s*\{[^}]*\}', '''.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding-bottom: 10px;
    margin-bottom: 10px;
}''', css)

with open(css_path, 'w', encoding='utf-8') as f:
    f.write(css)

