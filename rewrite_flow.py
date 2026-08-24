import sys

new_core = """// TZANIX QUANTUM CORE - Spherical Curl Noise Neural Flow
let scene, camera, renderer, composer, bloomPass;
let particlesData = [];
let trailsPositions;
let headsPositions;
let trailsMesh, headsMesh;
let trailsMat, headsMat;

// Configurations
const particleCount = 400;
const trailLength = 15;
const maxRadius = 4.0;
const timeMult = 0.0005;

// Market State (Synced from app.js)
let currentOFI = 0.0;
let currentZScore = 0.0;
let currentVol = 0.0;

function initQuantumMesh() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;

    // 1. Scene & Camera Setup
    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.05);

    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.z = 10;
    camera.position.y = 0;
    camera.lookAt(0, 0, 0);

    // 2. Renderer
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // 3. Data Structures
    // We need segments for the trails. Number of segments per particle = trailLength - 1
    const totalSegments = particleCount * (trailLength - 1);
    
    trailsPositions = new Float32Array(totalSegments * 2 * 3); // 2 vertices per line segment, 3 floats per vertex
    headsPositions = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
        // Spherical distribution, concentrated at the core (power of 3)
        const u = Math.random();
        const v = Math.random();
        const theta = 2 * Math.PI * u;
        const phi = Math.acos(2 * v - 1);
        const r = maxRadius * Math.pow(Math.random(), 3); // Dense core!

        const x = r * Math.sin(phi) * Math.cos(theta);
        const y = r * Math.sin(phi) * Math.sin(theta);
        const z = r * Math.cos(phi);

        // Fill history array with starting position
        const history = [];
        for(let k=0; k<trailLength; k++) {
            history.push(new THREE.Vector3(x, y, z));
        }

        particlesData.push({
            pos: new THREE.Vector3(x, y, z),
            history: history,
            speedOffset: Math.random() * 2.0
        });
        
        headsPositions[i * 3] = x;
        headsPositions[i * 3 + 1] = y;
        headsPositions[i * 3 + 2] = z;
    }

    // 4. Geometries
    const headsGeo = new THREE.BufferGeometry();
    headsGeo.setAttribute('position', new THREE.BufferAttribute(headsPositions, 3).setUsage(THREE.DynamicDrawUsage));

    const trailsGeo = new THREE.BufferGeometry();
    trailsGeo.setAttribute('position', new THREE.BufferAttribute(trailsPositions, 3).setUsage(THREE.DynamicDrawUsage));

    // 5. Materials
    headsMat = new THREE.PointsMaterial({
        color: 0x00F0FF,
        size: 0.1,
        blending: THREE.AdditiveBlending,
        transparent: true,
        opacity: 1.0,
        sizeAttenuation: true
    });
    
    trailsMat = new THREE.LineBasicMaterial({
        color: 0x00F0FF,
        blending: THREE.AdditiveBlending,
        transparent: true,
        opacity: 0.25
    });

    headsMesh = new THREE.Points(headsGeo, headsMat);
    trailsMesh = new THREE.LineSegments(trailsGeo, trailsMat);

    scene.add(headsMesh);
    scene.add(trailsMesh);

    // 6. Post-Processing (Intense Bloom)
    const renderScene = new THREE.RenderPass(scene, camera);
    bloomPass = new THREE.UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight), 
        3.0, // STRONGER strength for neon core
        0.5, // radius
        0.5 // lower threshold so it blooms easier
    );
    bloomPass.tintColor = new THREE.Color(0x00F0FF);
    
    composer = new THREE.EffectComposer(renderer);
    composer.addPass(renderScene);
    composer.addPass(bloomPass);

    // Resize Handler
    window.addEventListener('resize', onWindowResize, false);

    // Start Loop
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

// Called by app.js WebSocket loop
window.updateQuantumMesh = function(tickData) {
    if (!tickData) return;
    if (tickData.z_score !== undefined) currentZScore = parseFloat(tickData.z_score);
    if (tickData.ofi !== undefined) currentOFI = parseFloat(tickData.ofi);
    if (tickData.vol !== undefined) currentVol = parseFloat(tickData.vol);
}

// Pseudo Curl Noise function for organic flow
function calculateFlowVector(v, t) {
    const freq = 0.8;
    const x = v.x * freq;
    const y = v.y * freq;
    const z = v.z * freq;

    // Organic swirly math (approximation of curl noise)
    const vx = Math.sin(y + t) + Math.cos(z + t);
    const vy = Math.sin(z + t) + Math.cos(x + t);
    const vz = Math.sin(x + t) + Math.cos(y + t);
    
    return new THREE.Vector3(vx, vy, vz).normalize();
}

function animate() {
    requestAnimationFrame(animate);

    const time = Date.now() * timeMult;

    // Target color logic (Red on Drop, Cyan on Rise)
    let targetColorHex = 0x00F0FF; 
    let bloomStrength = 3.0;
    
    if (window.globalMarketState === -1) {
        targetColorHex = 0xFF2E63; // Red
        bloomStrength = 4.0; 
    } else if (window.globalMarketState === 1) {
        targetColorHex = 0x00FF9D; // Green
        bloomStrength = 4.0;
    }

    headsMat.color.setHex(targetColorHex);
    trailsMat.color.setHex(targetColorHex);
    bloomPass.strength += (bloomStrength - bloomPass.strength) * 0.1;

    // Dynamic rotation of the entire system
    headsMesh.rotation.y += 0.002;
    headsMesh.rotation.x += 0.001;
    trailsMesh.rotation.y += 0.002;
    trailsMesh.rotation.x += 0.001;

    // Calculate flow speeds based on Market Volatility (OFI)
    let speedMult = 0.015 + (Math.abs(currentOFI) / 5000); 
    speedMult = Math.min(speedMult, 0.06);

    let trailIdx = 0;
    
    // Update physics
    for (let i = 0; i < particleCount; i++) {
        const p = particlesData[i];
        
        // Calculate new velocity from Flow Field (Curl Noise)
        const flow = calculateFlowVector(p.pos, time + p.speedOffset);
        
        // Add a gentle pull towards the center to maintain the dense core sphere
        const centerPull = p.pos.clone().multiplyScalar(-0.1);
        flow.add(centerPull);
        flow.normalize().multiplyScalar(speedMult);
        
        // Shift history (push current to index 0, pop last)
        for (let k = trailLength - 1; k > 0; k--) {
            p.history[k].copy(p.history[k-1]);
        }
        p.history[0].copy(p.pos);

        // Move position
        p.pos.add(flow);

        // If particle escapes the sphere, teleport it back to the dense core
        if (p.pos.lengthSq() > maxRadius * maxRadius) {
            const r = 0.2; // Spawns back in the dense center!
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            p.pos.set(
                r * Math.sin(phi) * Math.cos(theta),
                r * Math.sin(phi) * Math.sin(theta),
                r * Math.cos(phi)
            );
            // Reset history instantly so it doesn't draw a line across the screen
            for (let k = 0; k < trailLength; k++) {
                p.history[k].copy(p.pos);
            }
        }

        // Update Head Geometry
        headsPositions[i * 3] = p.pos.x;
        headsPositions[i * 3 + 1] = p.pos.y;
        headsPositions[i * 3 + 2] = p.pos.z;

        // Update Trails Geometry (LineSegments)
        for (let k = 0; k < trailLength - 1; k++) {
            // Point A
            trailsPositions[trailIdx++] = p.history[k].x;
            trailsPositions[trailIdx++] = p.history[k].y;
            trailsPositions[trailIdx++] = p.history[k].z;
            // Point B
            trailsPositions[trailIdx++] = p.history[k+1].x;
            trailsPositions[trailIdx++] = p.history[k+1].y;
            trailsPositions[trailIdx++] = p.history[k+1].z;
        }
    }

    headsMesh.geometry.attributes.position.needsUpdate = true;
    trailsMesh.geometry.attributes.position.needsUpdate = true;

    // Render using composer
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
