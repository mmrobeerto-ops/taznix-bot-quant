import re

# 1. Update HTML
path_html = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path_html, 'r', encoding='utf-8') as f:
    html = f.read()

# Remove the floating toolbar completely
html = re.sub(r'<div id="floating-sim-toolbar".*?</div>\s*</div>', '</div>', html, flags=re.DOTALL)

with open(path_html, 'w', encoding='utf-8') as f:
    f.write(html)

# 2. Update 3D Engine to use the Avatar (Icosahedron)
path_js = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path_js, 'r', encoding='utf-8') as f:
    js = f.read()

# Replace Filament with Drone
js = re.sub(r'const filamentGeo = new THREE\.CylinderGeometry.*?scene\.add\(centralFilament\);',
'''const droneGeo = new THREE.IcosahedronGeometry(0.5, 1);
    const droneMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
    centralFilament = new THREE.Mesh(droneGeo, droneMat); // Reusing variable name for compatibility
    scene.add(centralFilament);

    // Inner solid core for the drone
    const coreGeo = new THREE.IcosahedronGeometry(0.3, 0);
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF, transparent: true, opacity: 0.5 });
    const droneCore = new THREE.Mesh(coreGeo, coreMat);
    centralFilament.add(droneCore);''', js, flags=re.DOTALL)

# Add rotation logic in animate()
js = js.replace('const targetBend = currentZScore;', 
'''const targetBend = currentZScore;
    centralFilament.rotation.x += 0.02 * speedMult;
    centralFilament.rotation.y += 0.03 * speedMult;
    centralFilament.rotation.z += 0.01 * speedMult;''')

# Scale the drone properly instead of just Y
js = re.sub(r'centralFilament\.scale\.y = 1 \+ Math\.abs\(currentZScore\) \* 1\.5;.*?centralFilament\.scale\.z = 1 \+ Math\.abs\(currentZScore\) \* 0\.5;',
'''const s = 1 + Math.abs(currentZScore) * 0.5;
        centralFilament.scale.set(s, s, s);''', js, flags=re.DOTALL)

with open(path_js, 'w', encoding='utf-8') as f:
    f.write(js)
