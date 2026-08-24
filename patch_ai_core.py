import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Replace Grids with Particle Fields
old_grids = """    // 3. Asks Grid (Top - Red)
    const gridGeo = new THREE.PlaneGeometry(30, 20, 40, 30);
    gridGeo.rotateX(-Math.PI / 2);
    const asksMat = new THREE.MeshBasicMaterial({ color: 0xFF2E63, wireframe: true, transparent: true, opacity: 0.35 });
    asksMesh = new THREE.Mesh(gridGeo, asksMat);
    asksMesh.position.y = 4;
    scene.add(asksMesh);

    // 4. Bids Grid (Bottom - Green)
    const bidsMat = new THREE.MeshBasicMaterial({ color: 0x00FF9D, wireframe: true, transparent: true, opacity: 0.35 });
    bidsMesh = new THREE.Mesh(gridGeo.clone(), bidsMat);
    bidsMesh.position.y = -4;
    scene.add(bidsMesh);"""

new_grids = """    // 3. Asks Entropy Field (Top - Red Particles)
    const gridGeo = new THREE.PlaneGeometry(35, 25, 60, 45);
    gridGeo.rotateX(-Math.PI / 2);
    const asksMat = new THREE.PointsMaterial({ color: 0xFF2E63, size: 0.07, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending });
    asksMesh = new THREE.Points(gridGeo, asksMat);
    asksMesh.position.y = 5;
    scene.add(asksMesh);

    // 4. Bids Entropy Field (Bottom - Green Particles)
    const bidsMat = new THREE.PointsMaterial({ color: 0x00FF9D, size: 0.07, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending });
    bidsMesh = new THREE.Points(gridGeo.clone(), bidsMat);
    bidsMesh.position.y = -5;
    scene.add(bidsMesh);"""

js = js.replace(old_grids, new_grids)

# Replace Core with Singularity
old_core = """    // 5. Holographic Quantum Core (Gyroscope Bot - Cyan)
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
    const holoRingGeo = new THREE.TorusGeometry(1.4, 0.05, 16, 64);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending });
    
    const ring1 = new THREE.Mesh(holoRingGeo, ringMat);
    ring1.rotation.x = Math.PI / 2;
    centralFilament.add(ring1);

    const ring2 = new THREE.Mesh(holoRingGeo, ringMat);
    ring2.rotation.y = Math.PI / 2;
    centralFilament.add(ring2);
    
    const ring3 = new THREE.Mesh(holoRingGeo, ringMat);
    ring3.rotation.x = Math.PI / 4;
    ring3.rotation.y = Math.PI / 4;
    centralFilament.add(ring3);"""

new_core = """    // 5. Quantum Singularity Core (Torus Knot + Particle Cloud)
    centralFilament = new THREE.Group();
    scene.add(centralFilament);

    // Mathematical Torus Knot (The Brain/Logic)
    const knotGeo = new THREE.TorusKnotGeometry(0.6, 0.15, 100, 16);
    const knotMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending });
    const botBrain = new THREE.Mesh(knotGeo, knotMat);
    centralFilament.add(botBrain);

    // Outer Particle Cloud (The Quantum State)
    const cloudGeo = new THREE.IcosahedronGeometry(1.2, 3);
    const cloudMat = new THREE.PointsMaterial({ color: 0xFFFFFF, size: 0.04, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending });
    const botCloud = new THREE.Points(cloudGeo, cloudMat);
    centralFilament.add(botCloud);

    // Data Extraction Beams (Connecting to the Order Book fields)
    const beamGeo = new THREE.CylinderGeometry(0.02, 0.02, 10, 8);
    const beamMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending });
    const dataBeam = new THREE.Mesh(beamGeo, beamMat);
    centralFilament.add(dataBeam);"""

js = js.replace(old_core, new_core)

# Update animate function to handle Group (centralFilament.material doesn't exist for Group)
old_animate_color = """    // Filament pulse
    if (Math.abs(currentZScore) > 2.0) {
        centralFilament.material.color.setHex(currentZScore > 0 ? 0xFF2E63 : 0x00FF9D);
        const s = 1 + Math.abs(currentZScore) * 0.5;
        centralFilament.scale.set(s, s, s);
    } else {
        centralFilament.material.color.setHex(0x00F0FF);
        centralFilament.scale.set(1,1,1);
    }"""

new_animate_color = """    // Core Pulse (Singularity)
    let coreColor = 0x00F0FF;
    let s = 1;
    if (Math.abs(currentZScore) > 2.0) {
        coreColor = currentZScore > 0 ? 0xFF2E63 : 0x00FF9D;
        s = 1 + Math.abs(currentZScore) * 0.3;
    }
    
    // Apply to children
    centralFilament.scale.set(s, s, s);
    centralFilament.children.forEach(child => {
        if (child.material && child.geometry.type === 'TorusKnotGeometry') {
            child.material.color.setHex(coreColor);
            child.rotation.y += 0.05 * speedMult;
            child.rotation.x += 0.02 * speedMult;
        }
        if (child.material && child.geometry.type === 'IcosahedronGeometry') {
            child.rotation.y -= 0.01 * speedMult; // Cloud spins oppositely
            child.material.color.setHex(coreColor);
        }
    });
"""
js = js.replace(old_animate_color, new_animate_color)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
