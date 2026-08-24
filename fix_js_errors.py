import re

# Fix tzanix_quantum-core.js ringGeo redeclaration
path_core = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path_core, 'r', encoding='utf-8') as f:
    core_js = f.read()

# Replace the first ringGeo with holoRingGeo
old_ring = "const ringGeo = new THREE.TorusGeometry(1.4, 0.05, 16, 64);"
new_ring = "const holoRingGeo = new THREE.TorusGeometry(1.4, 0.05, 16, 64);"
core_js = core_js.replace(old_ring, new_ring)
core_js = core_js.replace("new THREE.Mesh(ringGeo, ringMat);", "new THREE.Mesh(holoRingGeo, ringMat);")

with open(path_core, 'w', encoding='utf-8') as f:
    f.write(core_js)


# Fix app.js missing backticks
path_app = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\app.js"
with open(path_app, 'r', encoding='utf-8') as f:
    app_js = f.read()

bad_line = """btcEl.innerHTML = BTC/USDT <br/><span style="font-size: 3.5rem;">{parseFloat(tick.price).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>;"""
good_line = """btcEl.innerHTML = BTC/USDT <br/><span style="font-size: 3.5rem;">{parseFloat(tick.price).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>;"""
app_js = app_js.replace(bad_line, good_line)

with open(path_app, 'w', encoding='utf-8') as f:
    f.write(app_js)

