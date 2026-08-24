import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

js = js.replace('// document.getElementById("btn-toggle-sma200").addEventListener("click", (e) => {', 'document.getElementById("btn-toggle-sma200").addEventListener("click", (e) => {')
js = js.replace('// document.getElementById("btn-toggle-vwap").addEventListener("click", (e) => {', 'document.getElementById("btn-toggle-vwap").addEventListener("click", (e) => {')

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
