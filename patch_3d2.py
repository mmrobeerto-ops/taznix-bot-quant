import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Make filament thicker
js = re.sub(r'const filamentGeo = new THREE\.CylinderGeometry\(0\.05, 0\.05, 20, 8\);', 
            r'const filamentGeo = new THREE.CylinderGeometry(0.15, 0.15, 30, 12);', js)

# Increase filament scaling logic
js = re.sub(r'centralFilament\.scale\.y = 1 \+ Math\.abs\(currentZScore\) \* 0\.5;', 
            r'centralFilament.scale.y = 1 + Math.abs(currentZScore) * 1.5; centralFilament.scale.x = 1 + Math.abs(currentZScore) * 0.3; centralFilament.scale.z = 1 + Math.abs(currentZScore) * 0.3;', js)

# Make pulse thicker
js = re.sub(r'const ringGeo = new THREE\.TorusGeometry\(1, 0\.1, 16, 100\);',
            r'const ringGeo = new THREE.TorusGeometry(1.5, 0.3, 32, 100);', js)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
