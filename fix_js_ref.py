import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Fix ReferenceError: move speedMult declaration to the top of animate()
js = js.replace('const targetBend = currentZScore;', 
'''// OFI determines speed of rotation and scrolling
    let speedMult = 1 + Math.abs(currentOFI) / 200;
    speedMult = Math.min(speedMult, 5.0); // Cap speed
    
    // Z-Score logic
    const targetBend = currentZScore;''')

# Remove the old speedMult declaration
js = js.replace('''// OFI determines speed of rotation and scrolling
    let speedMult = 1 + Math.abs(currentOFI) / 200;
    speedMult = Math.min(speedMult, 5.0); // Cap speed''', '', 1) # only replace the second occurrence

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
