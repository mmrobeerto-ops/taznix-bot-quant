import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Add event listeners for the new floating buttons
new_listeners = '''
    const btnSimVol = document.getElementById("btn-sim-volatility");
    if (btnSimVol) {
        btnSimVol.addEventListener("click", () => {
            fetch("/api/simulate/spike?direction=UP", {method: "POST"}).catch(e => console.error(e));
        });
    }

    const btnStartBot = document.getElementById("btn-start-bot");
    if (btnStartBot) {
        btnStartBot.addEventListener("click", () => {
            document.getElementById("btn-toggle-autopilot").click(); // Trigger the real autopilot button logic
        });
    }
'''

# Find the end of DOMContentLoaded or add to setupEventListeners
js = js.replace('function setupEventListeners() {', 'function setupEventListeners() {\n' + new_listeners)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)

