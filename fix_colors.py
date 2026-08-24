import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# Change base colors to Amber/Gold
js_code = js_code.replace('let targetColor = new THREE.Vector3(0.0, 0.94, 1.0); // Cyan base', 'let targetColor = new THREE.Vector3(1.0, 0.75, 0.0); // Amber/Gold base')
js_code = js_code.replace('let currentColor = new THREE.Vector3(0.0, 0.94, 1.0);', 'let currentColor = new THREE.Vector3(1.0, 0.75, 0.0);')

# Change market state fallback color
old_fallback = """    } else {
        targetColor.set(0.0, 0.94, 1.0); // Cyan
        bloomPass.strength = 3.0;
    }"""
new_fallback = """    } else {
        targetColor.set(1.0, 0.75, 0.0); // Amber/Gold
        bloomPass.strength = 3.5;
    }"""
js_code = js_code.replace(old_fallback, new_fallback)

# Change the Green (BUY) to a brighter Gold/Yellow to match the theme
old_green = """    } else if (window.globalMarketState === 1) {
        targetColor.set(0.0, 1.0, 0.61); // Green
        bloomPass.strength = 4.0;
    }"""
new_green = """    } else if (window.globalMarketState === 1) {
        targetColor.set(1.0, 0.84, 0.0); // Bright Gold
        bloomPass.strength = 5.0;
    }"""
js_code = js_code.replace(old_green, new_green)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
