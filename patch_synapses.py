import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Add glowing points to the knot
old_knot = """    const botBrain = new THREE.Mesh(knotGeo, knotMat);
    centralFilament.add(botBrain);"""

new_knot = """    const botBrain = new THREE.Mesh(knotGeo, knotMat);
    centralFilament.add(botBrain);
    
    // Glowing Synapse Nodes (Points) at the vertices of the knot
    const synapseMat = new THREE.PointsMaterial({ color: 0xFFFFFF, size: 0.08, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
    synapseMat.onBeforeCompile = knotMat.onBeforeCompile; // Share the same vertex displacement shader!
    const botSynapses = new THREE.Points(knotGeo, synapseMat);
    centralFilament.add(botSynapses);"""

js = js.replace(old_knot, new_knot)

# Update animate to spin the synapses in sync with the brain
old_animate = """        if (child.material && child.geometry.type === 'TorusKnotGeometry') {
            child.material.color.setHex(coreColor);
            child.rotation.y += 0.05 * speedMult;
            child.rotation.x += 0.02 * speedMult;
            if (child.material.userData.shader) {
                child.material.userData.shader.uniforms.time.value = time * speedMult;
            }
        }"""

new_animate = """        if (child.material && child.geometry.type === 'TorusKnotGeometry') {
            // Keep points and wireframe in sync!
            if (child.type === 'Points') {
                child.material.color.setHex(0xFFFFFF); // Synapses stay bright white/cyan
            } else {
                child.material.color.setHex(coreColor);
            }
            child.rotation.y += 0.05 * speedMult;
            child.rotation.x += 0.02 * speedMult;
            if (child.material.userData.shader) {
                child.material.userData.shader.uniforms.time.value = time * speedMult;
            }
        }"""

js = js.replace(old_animate, new_animate)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
