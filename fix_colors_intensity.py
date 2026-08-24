import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# 1. Reduce Bloom Strength
js_code = js_code.replace('bloomPass.strength = 2.5;', 'bloomPass.strength = 1.0; // Lower intensity')
js_code = js_code.replace('bloomPass.strength = 2.0;', 'bloomPass.strength = 0.8; // Lower intensity')
js_code = js_code.replace('bloomPass.strength = 1.5;', 'bloomPass.strength = 0.5; // Lower intensity')
js_code = js_code.replace('1.5, 0.5, 0.4', '0.6, 0.5, 0.5') # Base bloom parameters

# 2. Change Data colors to Red and Green (and a dim neutral)
old_colors = """    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.0, 0.05); // Red
        bloomPass.strength = 2.5; 
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(1.0, 0.84, 0.0); // Bright Gold
        bloomPass.strength = 2.0;
    } else {
        targetDataColor.set(1.0, 0.75, 0.0); // Amber
        bloomPass.strength = 1.5;
    }"""

new_colors = """    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.2, 0.2); // Soft Red for data
        bloomPass.strength = 1.0; 
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(0.2, 1.0, 0.3); // Green for data
        bloomPass.strength = 1.0;
    } else {
        targetDataColor.set(0.2, 0.4, 0.4); // Dim neutral cyan for standby
        bloomPass.strength = 0.5;
    }"""
js_code = js_code.replace(old_colors, new_colors)

# Also update the initialization colors
js_code = js_code.replace('let targetDataColor = new THREE.Vector3(1.0, 0.75, 0.0); // Amber base for rings', 'let targetDataColor = new THREE.Vector3(0.2, 0.4, 0.4); // Dim neutral base')
js_code = js_code.replace('let currentDataColor = new THREE.Vector3(1.0, 0.75, 0.0);', 'let currentDataColor = new THREE.Vector3(0.2, 0.4, 0.4);')


with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
