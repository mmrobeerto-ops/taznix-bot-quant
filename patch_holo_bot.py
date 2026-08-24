import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

old_code = """    // 5. Central Tesseract (Quantum Motor - Cyan)
    const outerCube = new THREE.BoxGeometry(1.8, 1.8, 1.8);
    const tesseractMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
    centralFilament = new THREE.Mesh(outerCube, tesseractMat); 
    scene.add(centralFilament);

    // Inner solid core for the tesseract
    const innerCube = new THREE.BoxGeometry(0.8, 0.8, 0.8);
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF, transparent: true, opacity: 0.5, wireframe: true });
    const droneCore = new THREE.Mesh(innerCube, coreMat);
    centralFilament.add(droneCore);"""

new_code = """    // 5. Holographic Quantum Core (Gyroscope Bot - Cyan)
    const coreGeo = new THREE.IcosahedronGeometry(0.8, 2); // Sphere-like with triangles
    const holoMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending });
    centralFilament = new THREE.Mesh(coreGeo, holoMat); 
    scene.add(centralFilament);

    // Inner energy node
    const innerNodeGeo = new THREE.IcosahedronGeometry(0.4, 1);
    const nodeMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF, wireframe: false, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending });
    const energyNode = new THREE.Mesh(innerNodeGeo, nodeMat);
    centralFilament.add(energyNode);

    // Orbital Rings (Gyroscope)
    const ringGeo = new THREE.TorusGeometry(1.4, 0.05, 16, 64);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending });
    
    const ring1 = new THREE.Mesh(ringGeo, ringMat);
    ring1.rotation.x = Math.PI / 2;
    centralFilament.add(ring1);

    const ring2 = new THREE.Mesh(ringGeo, ringMat);
    ring2.rotation.y = Math.PI / 2;
    centralFilament.add(ring2);
    
    const ring3 = new THREE.Mesh(ringGeo, ringMat);
    ring3.rotation.x = Math.PI / 4;
    ring3.rotation.y = Math.PI / 4;
    centralFilament.add(ring3);"""

js = js.replace(old_code, new_code)
with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
