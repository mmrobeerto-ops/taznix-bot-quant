import textwrap

js = textwrap.dedent('''\
/**
 * TZANiX Quantum Core V2 - Order Book Tunnel & Entropy Grid
 */

let scene, camera, renderer;
let asksMesh, bidsMesh, centralFilament;
let stopLossPlane, trailingStopPlane;
let pulseRing;

let currentZScore = 0;
let currentOFI = 0;
let isPositionActive = false;
let clock = new THREE.Clock();

function initQuantumEngine() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;

    // 1. Scene & Camera
    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x030508, 0.05);
    const width = container.clientWidth;
    const height = container.clientHeight;
    camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100);
    camera.position.set(0, 2, 12);
    camera.lookAt(0, 0, 0);

    // 2. Renderer
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.domElement.style.mixBlendMode = "screen";
    container.appendChild(renderer.domElement);

    // 3. Asks Grid (Top - Red)
    const gridGeo = new THREE.PlaneGeometry(30, 20, 30, 20);
    gridGeo.rotateX(-Math.PI / 2);
    const asksMat = new THREE.MeshBasicMaterial({ color: 0xFF2E63, wireframe: true, transparent: true, opacity: 0.3 });
    asksMesh = new THREE.Mesh(gridGeo, asksMat);
    asksMesh.position.y = 4;
    scene.add(asksMesh);

    // 4. Bids Grid (Bottom - Green)
    const bidsMat = new THREE.MeshBasicMaterial({ color: 0x00FF9D, wireframe: true, transparent: true, opacity: 0.3 });
    bidsMesh = new THREE.Mesh(gridGeo.clone(), bidsMat);
    bidsMesh.position.y = -4;
    scene.add(bidsMesh);

    // 5. Central Filament (VWAP/Price - Cyan)
    const filamentGeo = new THREE.CylinderGeometry(0.05, 0.05, 20, 8);
    filamentGeo.rotateZ(Math.PI / 2);
    const filamentMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, transparent: true, opacity: 0.8 });
    centralFilament = new THREE.Mesh(filamentGeo, filamentMat);
    scene.add(centralFilament);

    // 6. Tactical Planes (Risk Management)
    const planeGeo = new THREE.PlaneGeometry(30, 20);
    planeGeo.rotateX(-Math.PI / 2);
    
    stopLossPlane = new THREE.Mesh(planeGeo, new THREE.MeshBasicMaterial({ color: 0xFF0000, transparent: true, opacity: 0.15, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    stopLossPlane.position.y = 2;
    stopLossPlane.visible = false;
    scene.add(stopLossPlane);

    trailingStopPlane = new THREE.Mesh(planeGeo, new THREE.MeshBasicMaterial({ color: 0x00FF00, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    trailingStopPlane.position.y = -2;
    trailingStopPlane.visible = false;
    scene.add(trailingStopPlane);

    // 7. Pulse Ring
    const ringGeo = new THREE.TorusGeometry(1, 0.1, 16, 100);
    pulseRing = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: 0xFFD700, transparent: true, opacity: 0 }));
    pulseRing.rotation.y = Math.PI / 2;
    scene.add(pulseRing);

    window.addEventListener('resize', () => {
        if (!container) return;
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    animate();
}

function deformGrid(mesh, time, baseHeight, intensity, isAsk) {
    const positions = mesh.geometry.attributes.position;
    const dir = isAsk ? -1 : 1; // Asks push down, bids push up
    for (let i = 0; i < positions.count; i++) {
        const x = positions.getX(i);
        const z = positions.getZ(i);
        // Add wave/noise based on time and intensity (OFI)
        let yOffset = Math.sin(x * 0.5 + time) * Math.cos(z * 0.5 + time) * intensity;
        positions.setY(i, baseHeight + (yOffset * dir));
    }
    mesh.geometry.attributes.position.needsUpdate = true;
}

function animate() {
    requestAnimationFrame(animate);
    const time = clock.getElapsedTime();

    // Smooth Z-Score bend on the central filament
    const targetBend = currentZScore; // e.g. up to +/- 4
    centralFilament.position.y += (targetBend - centralFilament.position.y) * 0.05;
    
    // Filament glowing based on tension
    if (Math.abs(currentZScore) > 2.5) {
        centralFilament.material.color.setHex(currentZScore > 0 ? 0xFF2E63 : 0x00FF9D);
        centralFilament.scale.y = 1 + Math.abs(currentZScore) * 0.5; // Stretch length
    } else {
        centralFilament.material.color.setHex(0x00F0FF);
        centralFilament.scale.y = 1.0;
    }

    // OFI controls mesh deformation intensity
    let askIntensity = currentOFI < 0 ? Math.abs(currentOFI) / 500 : 0.2;
    let bidIntensity = currentOFI > 0 ? currentOFI / 500 : 0.2;
    
    // Cap intensities
    askIntensity = Math.min(askIntensity, 2.5);
    bidIntensity = Math.min(bidIntensity, 2.5);

    deformGrid(asksMesh, time * 2, 4, askIntensity, true);
    deformGrid(bidsMesh, time * 2, -4, bidIntensity, false);

    // Scroll effect for planes to simulate speed/flow
    asksMesh.position.x = (time * 5) % 1;
    bidsMesh.position.x = (time * 5) % 1;

    // Pulse animation
    if (pulseRing.material.opacity > 0) {
        pulseRing.scale.addScalar(0.2);
        pulseRing.material.opacity -= 0.02;
    }

    renderer.render(scene, camera);
}

// Public API
window.updateQuantumMesh = function(zScore, ofi, isActive) {
    if (!scene) return;
    currentZScore = zScore;
    currentOFI = ofi;
    
    // Trigger Entry Pulse Shield if toggled ON
    if (isActive && !isPositionActive) {
        pulseRing.scale.set(1,1,1);
        pulseRing.material.opacity = 1.0;
        pulseRing.position.y = currentZScore; // center on price
    }
    isPositionActive = isActive;

    if (isActive) {
        stopLossPlane.visible = true;
        trailingStopPlane.visible = true;
        
        // Simulating the trailing stop chasing the price
        const dist = Math.abs(currentZScore) + 1;
        stopLossPlane.position.y = currentZScore > 0 ? currentZScore - dist : currentZScore + dist;
        trailingStopPlane.position.y = currentZScore > 0 ? currentZScore + (dist*0.5) : currentZScore - (dist*0.5);
    } else {
        stopLossPlane.visible = false;
        trailingStopPlane.visible = false;
    }
};

document.addEventListener("DOMContentLoaded", () => {
    setTimeout(initQuantumEngine, 300);
});
''')

with open('static/tzanix_quantum-core.js', 'w', encoding='utf-8') as f:
    f.write(js)
