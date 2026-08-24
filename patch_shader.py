import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Modify the TorusKnot material to include onBeforeCompile
old_knot = """    // Mathematical Torus Knot (The Brain/Logic)
    const knotGeo = new THREE.TorusKnotGeometry(0.6, 0.15, 100, 16);
    const knotMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending });
    const botBrain = new THREE.Mesh(knotGeo, knotMat);
    centralFilament.add(botBrain);"""

new_knot = """    // Mathematical Torus Knot (The Brain/Logic)
    const knotGeo = new THREE.TorusKnotGeometry(0.6, 0.15, 100, 16);
    const knotMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, wireframe: true, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending });
    
    // Inject custom shader to make nodes vibrate/undulate (Living Neural Effect)
    knotMat.onBeforeCompile = function (shader) {
        shader.uniforms.time = { value: 0 };
        knotMat.userData.shader = shader;
        shader.vertexShader = 
            uniform float time;
             + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace(
            #include <begin_vertex>,
            
            #include <begin_vertex>
            // Generate a wave-like connection movement using sine waves on XYZ
            float wave = sin(position.x * 8.0 + time * 3.0) * cos(position.y * 8.0 + time * 2.0) * 0.04;
            float pulse = sin(position.z * 10.0 - time * 4.0) * 0.02;
            transformed += normal * (wave + pulse);
            
        );
    };
    
    const botBrain = new THREE.Mesh(knotGeo, knotMat);
    centralFilament.add(botBrain);"""

js = js.replace(old_knot, new_knot)

# Update the animate loop to update the shader time
old_animate = """        if (child.material && child.geometry.type === 'TorusKnotGeometry') {
            child.material.color.setHex(coreColor);
            child.rotation.y += 0.05 * speedMult;
            child.rotation.x += 0.02 * speedMult;
        }"""

new_animate = """        if (child.material && child.geometry.type === 'TorusKnotGeometry') {
            child.material.color.setHex(coreColor);
            child.rotation.y += 0.05 * speedMult;
            child.rotation.x += 0.02 * speedMult;
            if (child.material.userData.shader) {
                child.material.userData.shader.uniforms.time.value = time * speedMult;
            }
        }"""

js = js.replace(old_animate, new_animate)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
