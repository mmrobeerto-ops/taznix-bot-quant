import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update Title and Subtitle
html = html.replace('TZANiX Cuantitativo', 'TZANiX Quant-X')
html = html.replace('MOTOR ALGORITMICO CUANTITATIVO INSTITUCIONAL', 'MOTOR ALGORÍTMICO CUANTITATIVO HFT')

# 2. Add Floating Toolbar inside the canvas container
floating_toolbar = '''<div id="threejs-canvas-container" style="width:100%; height:100%; position:relative; overflow:hidden;">
                        <div id="floating-sim-toolbar" style="position:absolute; bottom:20px; left:50%; transform:translateX(-50%); display:flex; gap:15px; z-index:10; background:rgba(8,12,20,0.65); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); padding:10px 20px; border:1px solid rgba(0,240,255,0.15); border-radius:8px; box-shadow:0 10px 30px rgba(0,0,0,0.6);">
                            <button id="btn-start-bot" class="btn btn-primary" style="background:transparent; border:1px solid rgba(0,240,255,0.3); color:#00F0FF; font-family:'JetBrains Mono',monospace; letter-spacing:1px; font-size:11px; padding:6px 12px; cursor:pointer;">[ INICIAR BOT ]</button>
                            <button id="btn-sim-volatility" class="btn btn-danger" style="background:transparent; border:1px solid rgba(255,46,99,0.3); color:#FF2E63; font-family:'JetBrains Mono',monospace; letter-spacing:1px; font-size:11px; padding:6px 12px; cursor:pointer;">[ SIMULAR VOLATILIDAD / ATAQUE ]</button>
                        </div>
                    </div>'''

html = re.sub(r'<div id="threejs-canvas-container"[^>]*>.*?</div>', floating_toolbar, html, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

