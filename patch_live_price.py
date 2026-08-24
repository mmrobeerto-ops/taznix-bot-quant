import re

# Update index.html
path_html = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path_html, 'r', encoding='utf-8') as f:
    html = f.read()

target_div = '<div class="chart-viewport-wrapper">'
new_div = '''<div class="chart-viewport-wrapper" style="position: relative;">
                    <div id="live-btc-price" style="position: absolute; top: 15px; right: 20px; font-size: 2.8rem; font-family: 'JetBrains Mono', monospace; font-weight: 800; color: #00F0FF; text-shadow: 0 0 20px #00F0FF, 0 0 40px #00F0FF; z-index: 10; pointer-events: none; opacity: 0.9;">
                        BTC/USDT <br/><span style="font-size: 3.5rem;">.00</span>
                    </div>'''
html = html.replace(target_div, new_div)

# Cache buster for app.js
html = re.sub(r'app\.js\??[^"]*"', r'app.js?v=liveprice1"', html)

with open(path_html, 'w', encoding='utf-8') as f:
    f.write(html)

# Update app.js
path_js = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path_js, 'r', encoding='utf-8') as f:
    js = f.read()

old_zscore_update = '''document.getElementById("lbl-zscore").textContent = tick.z_score ? tick.z_score.toFixed(2) : "0.00";'''
new_zscore_update = '''document.getElementById("lbl-zscore").textContent = tick.z_score ? tick.z_score.toFixed(2) : "0.00";
        
        const btcEl = document.getElementById("live-btc-price");
        if (btcEl && tick.price) {
            btcEl.innerHTML = BTC/USDT <br/><span style="font-size: 3.5rem;">{parseFloat(tick.price).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>;
        }'''

js = js.replace(old_zscore_update, new_zscore_update)

with open(path_js, 'w', encoding='utf-8') as f:
    f.write(js)
