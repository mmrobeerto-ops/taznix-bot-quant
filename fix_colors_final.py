import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# Let's replace the whole color logic block
old_block = """    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.0, 0.05); // Red
        bloomPass.strength = 1.0; // Lower intensity 
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(1.0, 0.84, 0.0); // Bright Gold
        bloomPass.strength = 0.8; // Lower intensity
    } else {
        targetDataColor.set(1.0, 0.75, 0.0); // Amber
        bloomPass.strength = 0.5; // Lower intensity
    }"""

new_block = """    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.1, 0.2); // Red (Venta)
        bloomPass.strength = 1.0; 
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(0.2, 1.0, 0.3); // Green (Compra)
        bloomPass.strength = 1.0;
    } else {
        targetDataColor.set(0.0, 0.94, 1.0); // Cyan (Espera)
        bloomPass.strength = 0.5;
    }"""

js_code = js_code.replace(old_block, new_block)

# Also fix the initial color
js_code = js_code.replace("let currentDataColor = new THREE.Vector3(0.2, 0.4, 0.4);", "let currentDataColor = new THREE.Vector3(0.0, 0.94, 1.0);")
js_code = js_code.replace("let targetDataColor = new THREE.Vector3(0.2, 0.4, 0.4); // Dim neutral base", "let targetDataColor = new THREE.Vector3(0.0, 0.94, 1.0); // Cyan standby")


with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
