import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Fix the broken replacement at the bottom
js = js.replace("       let isAutoPilotActive = true;\nlet prevBtcPrice = 0;", "        isActive = true;")

# Update the BTC logic to use window.prevBtcPrice
old_btc = """            if (prevBtcPrice > 0) {
                if (currentPrice < prevBtcPrice) {
                    colorStr = "#FF2E63"; // Red for drop
                    glowStr = "#FF2E63";
                } else if (currentPrice > prevBtcPrice) {
                    colorStr = "#00FF9D"; // Green for rise
                    glowStr = "#00FF9D";
                }
            }
            prevBtcPrice = currentPrice;"""

new_btc = """            window.prevBtcPrice = window.prevBtcPrice || currentPrice;
            if (currentPrice < window.prevBtcPrice) {
                colorStr = "#FF2E63"; // Red for drop
                glowStr = "#FF2E63";
            } else if (currentPrice > window.prevBtcPrice) {
                colorStr = "#00FF9D"; // Green for rise
                glowStr = "#00FF9D";
            }
            window.prevBtcPrice = currentPrice;"""

js = js.replace(old_btc, new_btc)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
