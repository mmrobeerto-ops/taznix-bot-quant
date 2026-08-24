import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# Add geometry declaration
old_decl = "let coreMesh, ringsGroup, absorptionMesh;"
new_decl = "let coreMesh, ringsGroup, absorptionMesh, triggerGeometryMesh;"
js_code = js_code.replace(old_decl, new_decl)

# Initialize the geometry
old_init = "    // 3. ABSORPTION STREAMS GEOMETRY"
new_init = """    // NEW: TRIGGER GEOMETRY (Icosahedron that forms on decisions)
    const triggerGeo = new THREE.IcosahedronGeometry(4.0, 1);
    triggerGeometryMesh = new THREE.Mesh(triggerGeo, new THREE.MeshBasicMaterial({
        color: 0x00FF9D, wireframe: true, transparent: true, opacity: 0.0, blending: THREE.AdditiveBlending, depthWrite: false
    }));
    scene.add(triggerGeometryMesh);
    
    // 3. ABSORPTION STREAMS GEOMETRY"""
js_code = js_code.replace(old_init, new_init)

# Animate the geometry
old_anim = "    // The core is ALWAYS Cyan. The DATA (Rings & Absorption) changes color based on market."
new_anim = """    // The core is ALWAYS Cyan. The DATA (Rings & Absorption) changes color based on market.
    let targetTriggerScale = 0.5;
    let targetTriggerOpacity = 0.0;"""
js_code = js_code.replace(old_anim, new_anim)

old_logic = """    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.1, 0.2); // Red (Venta)
        bloomPass.strength = 1.0; 
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(0.2, 1.0, 0.3); // Green (Compra)
        bloomPass.strength = 1.0;
    } else {
        targetDataColor.set(0.0, 0.94, 1.0); // Cyan (Espera)
        bloomPass.strength = 0.5;
    }"""

new_logic = """    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.1, 0.2); // Red (Venta)
        bloomPass.strength = 1.0; 
        targetTriggerScale = 1.0;
        targetTriggerOpacity = 0.8;
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(0.2, 1.0, 0.3); // Green (Compra)
        bloomPass.strength = 1.0;
        targetTriggerScale = 1.0;
        targetTriggerOpacity = 0.8;
    } else {
        targetDataColor.set(0.0, 0.94, 1.0); // Cyan (Espera)
        bloomPass.strength = 0.5;
        targetTriggerScale = 0.5;
        targetTriggerOpacity = 0.0;
    }"""
js_code = js_code.replace(old_logic, new_logic)

# Apply scale and opacity
old_anim_vars = "    ringsGroup.rotation.x += 0.001;"
new_anim_vars = """    ringsGroup.rotation.x += 0.001;

    // Animate trigger geometry
    triggerGeometryMesh.rotation.y -= 0.01;
    triggerGeometryMesh.rotation.x -= 0.005;
    triggerGeometryMesh.scale.lerp(new THREE.Vector3(targetTriggerScale, targetTriggerScale, targetTriggerScale), 0.1);
    triggerGeometryMesh.material.opacity += (targetTriggerOpacity - triggerGeometryMesh.material.opacity) * 0.1;
    triggerGeometryMesh.material.color.setRGB(currentDataColor.x, currentDataColor.y, currentDataColor.z);
"""
js_code = js_code.replace(old_anim_vars, new_anim_vars)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
