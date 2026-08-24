import sys

new_core = """// TZANIX QUANTUM CORE - Strict Spherical Curl Noise
let scene, camera, renderer, composer, bloomPass;
let particlesData = [];
let trailsPositions;
let headsPositions;
let trailsMesh, headsMesh;
let trailsMat, headsMat;

// Configurations
const particleCount = 2000; // 5x more dense
const trailLength = 30; // Longer trails
const sphereRadius = 3.5;
const timeMult = 0.0005;

// Market State
let currentOFI = 0.0;
let currentZScore = 0.0;
let currentVol = 0.0;

function initQuantumMesh() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;

    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.05);

    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.z = 10;
    camera.position.y = 0;
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    const totalSegments = particleCount * (trailLength - 1);
    trailsPositions = new Float32Array(totalSegments * 2 * 3);
    headsPositions = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
        // Spherical distribution, highly concentrated at the core
        const u = Math.random();
        const v = Math.random();
        const theta = 2 * Math.PI * u;
        const phi = Math.acos(2 * v - 1);
        
        // Use power of 4 for EXTREME core density
        const r = sphereRadius * Math.pow(Math.random(), 4); 

        const x = r * Math.sin(phi) * Math.cos(theta);
        const y = r * Math.sin(phi) * Math.sin(theta);
        const z = r * Math.cos(phi);

        const history = [];
        for(let k=0; k<trailLength; k++) {
            history.push(new THREE.Vector3(x, y, z));
        }

        particlesData.push({
            pos: new THREE.Vector3(x, y, z),
            history: history,
            baseRadius: r, // Keep track of the orbital shell
            speedOffset: Math.random() * 100.0
        });
        
        headsPositions[i * 3] = x;
        headsPositions[i * 3 + 1] = y;
        headsPositions[i * 3 + 2] = z;
    }

    const headsGeo = new THREE.BufferGeometry();
    headsGeo.setAttribute('position', new THREE.BufferAttribute(headsPositions, 3).setUsage(THREE.DynamicDrawUsage));

    const trailsGeo = new THREE.BufferGeometry();
    trailsGeo.setAttribute('position', new THREE.BufferAttribute(trailsPositions, 3).setUsage(THREE.DynamicDrawUsage));

    headsMat = new THREE.PointsMaterial({
        color: 0x00F0FF,
        size: 0.05, // Smaller points due to high density
        blending: THREE.AdditiveBlending,
        transparent: true,
        opacity: 0.8,
        sizeAttenuation: true
    });
    
    trailsMat = new THREE.LineBasicMaterial({
        color: 0x00F0FF,
        blending: THREE.AdditiveBlending,
        transparent: true,
        opacity: 0.15 // Lower opacity for trails so the core isn't completely blown out
    });

    headsMesh = new THREE.Points(headsGeo, headsMat);
    trailsMesh = new THREE.LineSegments(trailsGeo, trailsMat);

    scene.add(headsMesh);
    scene.add(trailsMesh);

    // Post-Processing
    const renderScene = new THREE.RenderPass(scene, camera);
    bloomPass = new THREE.UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight), 
        3.5, // Intense bloom
        0.5, 
        0.3  // Very low threshold
    );
    bloomPass.tintColor = new THREE.Color(0x00F0FF);
    
    composer = new THREE.EffectComposer(renderer);
    composer.addPass(renderScene);
    composer.addPass(bloomPass);

    window.addEventListener('resize', onWindowResize, false);
    animate();
}

function onWindowResize() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
    composer.setSize(container.clientWidth, container.clientHeight);
}

window.updateQuantumMesh = function(tickData) {
    if (!tickData) return;
    if (tickData.z_score !== undefined) currentZScore = parseFloat(tickData.z_score);
    if (tickData.ofi !== undefined) currentOFI = parseFloat(tickData.ofi);
    if (tickData.vol !== undefined) currentVol = parseFloat(tickData.vol);
}

// Pseudo Curl Noise: Tridimensional Swirl
function calculateCurlNoise(v, t) {
    const freq = 1.2;
    const x = v.x * freq;
    const y = v.y * freq;
    const z = v.z * freq;

    // A more complex 3D noise vector (Simplex approximation)
    const vx = Math.sin(y + t) * Math.cos(z + t);
    const vy = Math.sin(z + t) * Math.cos(x + t);
    const vz = Math.sin(x + t) * Math.cos(y + t);
    
    return new THREE.Vector3(vx, vy, vz);
}

function animate() {
    requestAnimationFrame(animate);

    const time = Date.now() * timeMult;

    // Color logic
    let targetColorHex = 0x00F0FF; 
    let bloomStrength = 3.5;
    
    if (window.globalMarketState === -1) {
        targetColorHex = 0xFF2E63; 
        bloomStrength = 4.5; 
    } else if (window.globalMarketState === 1) {
        targetColorHex = 0x00FF9D; 
        bloomStrength = 4.5;
    }

    headsMat.color.setHex(targetColorHex);
    trailsMat.color.setHex(targetColorHex);
    bloomPass.strength += (bloomStrength - bloomPass.strength) * 0.1;

    headsMesh.rotation.y += 0.001;
    headsMesh.rotation.x += 0.0005;
    trailsMesh.rotation.y += 0.001;
    trailsMesh.rotation.x += 0.0005;

    let speedMult = 0.02 + (Math.abs(currentOFI) / 5000); 
    speedMult = Math.min(speedMult, 0.08);

    let trailIdx = 0;
    
    for (let i = 0; i < particleCount; i++) {
        const p = particlesData[i];
        
        // 1. Get raw noise vector
        const noiseVel = calculateCurlNoise(p.pos, time + p.speedOffset);
        
        // 2. Strict Spherical Confinement (Tangent Projection)
        // By removing the radial component, the velocity is purely tangential
        // meaning the particle perfectly orbits on its shell!
        let normal = p.pos.clone().normalize();
        if (normal.lengthSq() === 0) { normal.set(0,1,0); }
        
        const radialComponent = normal.clone().multiplyScalar(noiseVel.dot(normal));
        let tangentVel = noiseVel.sub(radialComponent).normalize();
        
        tangentVel.multiplyScalar(speedMult);
        
        // Shift history
        for (let k = trailLength - 1; k > 0; k--) {
            p.history[k].copy(p.history[k-1]);
        }
        p.history[0].copy(p.pos);

        // Move position
        p.pos.add(tangentVel);

        // Enforce exact mathematical radius to prevent floating point drift
        p.pos.normalize().multiplyScalar(Math.max(0.01, p.baseRadius));

        // Update Geometries
        headsPositions[i * 3] = p.pos.x;
        headsPositions[i * 3 + 1] = p.pos.y;
        headsPositions[i * 3 + 2] = p.pos.z;

        for (let k = 0; k < trailLength - 1; k++) {
            trailsPositions[trailIdx++] = p.history[k].x;
            trailsPositions[trailIdx++] = p.history[k].y;
            trailsPositions[trailIdx++] = p.history[k].z;
            trailsPositions[trailIdx++] = p.history[k+1].x;
            trailsPositions[trailIdx++] = p.history[k+1].y;
            trailsPositions[trailIdx++] = p.history[k+1].z;
        }
    }

    headsMesh.geometry.attributes.position.needsUpdate = true;
    trailsMesh.geometry.attributes.position.needsUpdate = true;

    composer.render();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initQuantumMesh);
} else {
    initQuantumMesh();
}
"""

with open(r'C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js', 'w', encoding='utf-8') as f:
    f.write(new_core)
