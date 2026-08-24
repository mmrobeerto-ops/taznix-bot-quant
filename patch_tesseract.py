import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Replace the Icosahedron with a Tesseract (Cube within a cube)
old_drone = """    // 5. Central Filament (VWAP/Price - Cyan)
    const droneGeo = new THREE.IcosahedronGeometry(0.5, 1);
    const droneMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
    centralFilament = new THREE.Mesh(droneGeo, droneMat); // Reusing variable name for compatibility
    scene.add(centralFilament);

    // Inner solid core for the drone
    const coreGeo = new THREE.IcosahedronGeometry(0.3, 0);
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF, transparent: true, opacity: 0.5 });
    const droneCore = new THREE.Mesh(coreGeo, coreMat);
    centralFilament.add(droneCore);"""

new_tesseract = """    // 5. Central Tesseract (Quantum Motor - Cyan)
    const outerCube = new THREE.BoxGeometry(1.8, 1.8, 1.8);
    const tesseractMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
    centralFilament = new THREE.Mesh(outerCube, tesseractMat); 
    scene.add(centralFilament);

    // Inner solid core for the tesseract
    const innerCube = new THREE.BoxGeometry(0.8, 0.8, 0.8);
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF, transparent: true, opacity: 0.5, wireframe: true });
    const droneCore = new THREE.Mesh(innerCube, coreMat);
    centralFilament.add(droneCore);"""

js = js.replace(old_drone, new_tesseract)

# Fix potential NaN in updateQuantumMesh
old_api = """window.updateQuantumMesh = function(zScore, ofi, isActive) {"""
new_api = """window.updateQuantumMesh = function(zScore, ofi, isActive) {
    zScore = Number(zScore) || 0;
    ofi = Number(ofi) || 0;
    if (isNaN(zScore)) zScore = 0;
    if (isNaN(ofi)) ofi = 0;"""

js = js.replace(old_api, new_api)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
