import sys

new_core = """// TZANIX QUANTUM CORE - 3D Holographic Particle Network
let scene, camera, renderer, composer, bloomPass;
let particlesData = [];
let particlePositions;
let linesMesh;
let particlesMesh;
let pMaterial, lMaterial;

// Configurations
const particleCount = 200;
const r = 3.5; // Radius/Size of the central network
const maxConnectionDistance = 0.8;

// Market State (Synced from app.js)
let currentOFI = 0.0;
let currentZScore = 0.0;
let currentVol = 0.0;

function initQuantumMesh() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;

    // 1. Scene & Camera Setup
    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.02);

    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.z = 10;
    camera.position.y = 1;
    camera.lookAt(0, 0, 0);

    // 2. Renderer
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // 3. Setup Particles
    const segments = particleCount * particleCount;
    const pGeometry = new THREE.BufferGeometry();
    particlePositions = new Float32Array(particleCount * 3);
    const particleColors = new Float32Array(particleCount * 3);
    
    for (let i = 0; i < particleCount; i++) {
        const x = (Math.random() - 0.5) * r * 2;
        const y = (Math.random() - 0.5) * r * 2;
        const z = (Math.random() - 0.5) * r * 2;
        
        particlePositions[i * 3] = x;
        particlePositions[i * 3 + 1] = y;
        particlePositions[i * 3 + 2] = z;

        // Velocity vector
        particlesData.push({
            velocity: new THREE.Vector3(-0.01 + Math.random() * 0.02, -0.01 + Math.random() * 0.02, -0.01 + Math.random() * 0.02),
            numConnections: 0
        });
    }

    pGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3).setUsage(THREE.DynamicDrawUsage));

    pMaterial = new THREE.PointsMaterial({
        color: 0x00F0FF,
        size: 0.06,
        blending: THREE.AdditiveBlending,
        transparent: true,
        sizeAttenuation: true
    });

    particlesMesh = new THREE.Points(pGeometry, pMaterial);
    scene.add(particlesMesh);

    // 4. Setup Dynamic Lines
    const lGeometry = new THREE.BufferGeometry();
    const positions = new Float32Array(segments * 3);
    lGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));

    lMaterial = new THREE.LineBasicMaterial({
        color: 0x00F0FF,
        transparent: true,
        opacity: 0.4,
        blending: THREE.AdditiveBlending
    });

    linesMesh = new THREE.LineSegments(lGeometry, lMaterial);
    scene.add(linesMesh);

    // 5. Post-Processing (Bloom)
    const renderScene = new THREE.RenderPass(scene, camera);
    bloomPass = new THREE.UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight), 
        1.5, // strength
        0.4, // radius
        0.85 // threshold
    );
    // Tint the bloom to match the primary color
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

function animate() {
    requestAnimationFrame(animate);

    // Determine target color based on globalMarketState from app.js
    let targetColorHex = 0x00F0FF; // Default Cyan
    let bloomStrength = 1.5;
    
    if (window.globalMarketState === -1) {
        targetColorHex = 0xFF2E63; // Red
        bloomStrength = 2.0; // Flash brighter on drop
    } else if (window.globalMarketState === 1) {
        targetColorHex = 0x00FF9D; // Green
        bloomStrength = 2.0; // Flash brighter on rise
    }

    // Apply color to materials
    pMaterial.color.setHex(targetColorHex);
    lMaterial.color.setHex(targetColorHex);
    bloomPass.strength = bloomStrength;

    // Optional: slowly rotate the whole cluster
    particlesMesh.rotation.y += 0.002;
    particlesMesh.rotation.x += 0.001;
    linesMesh.rotation.y += 0.002;
    linesMesh.rotation.x += 0.001;
    
    // Physics & connections
    let vertexpos = 0;
    let numConnected = 0;
    const positions = linesMesh.geometry.attributes.position.array;
    
    for ( let i = 0; i < particleCount; i++ ) {
        particlesData[i].numConnections = 0;
    }

    // Move particles based on speed multiplier (market volatility)
    let speedMult = 1 + Math.abs(currentOFI) / 300;
    speedMult = Math.min(speedMult, 3.0);
    
    for ( let i = 0; i < particleCount; i++ ) {
        const particleData = particlesData[i];
        
        particlePositions[i*3] += particleData.velocity.x * speedMult;
        particlePositions[i*3+1] += particleData.velocity.y * speedMult;
        particlePositions[i*3+2] += particleData.velocity.z * speedMult;

        // Bounce bounds
        if (particlePositions[i*3] < -r || particlePositions[i*3] > r) particleData.velocity.x = -particleData.velocity.x;
        if (particlePositions[i*3+1] < -r || particlePositions[i*3+1] > r) particleData.velocity.y = -particleData.velocity.y;
        if (particlePositions[i*3+2] < -r || particlePositions[i*3+2] > r) particleData.velocity.z = -particleData.velocity.z;

        // Check distances for lines
        for ( let j = i + 1; j < particleCount; j++ ) {
            const particleDataB = particlesData[j];

            const dx = particlePositions[i*3] - particlePositions[j*3];
            const dy = particlePositions[i*3+1] - particlePositions[j*3+1];
            const dz = particlePositions[i*3+2] - particlePositions[j*3+2];
            const distSq = dx*dx + dy*dy + dz*dz;

            if ( distSq < maxConnectionDistance * maxConnectionDistance ) {
                particleData.numConnections++;
                particleDataB.numConnections++;

                positions[vertexpos++] = particlePositions[i*3];
                positions[vertexpos++] = particlePositions[i*3+1];
                positions[vertexpos++] = particlePositions[i*3+2];

                positions[vertexpos++] = particlePositions[j*3];
                positions[vertexpos++] = particlePositions[j*3+1];
                positions[vertexpos++] = particlePositions[j*3+2];
                numConnected++;
            }
        }
    }

    linesMesh.geometry.setDrawRange( 0, numConnected * 2 );
    linesMesh.geometry.attributes.position.needsUpdate = true;
    particlesMesh.geometry.attributes.position.needsUpdate = true;

    // Use Composer instead of Renderer for Post-Processing
    composer.render();
}

// Initial Bootstrap if DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initQuantumMesh);
} else {
    initQuantumMesh();
}
"""

with open(r'C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js', 'w', encoding='utf-8') as f:
    f.write(new_core)
