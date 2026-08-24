import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Fix the broken btn-toggle-autopilot listener
js = js.replace('// document.getElementById("btn-toggle-autopilot").addEventListener("click", async () => {', 'document.getElementById("btn-toggle-autopilot").addEventListener("click", async () => {')

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
