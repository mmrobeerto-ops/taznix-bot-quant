import textwrap

js = textwrap.dedent('''\
/**
 * TZANiX Quantum-X Core - Order Book Tunnel & Entropy Grid
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
    
    // Add canvas as the FIRST child so it doesn't overwrite floating toolbars
    container.insertBefore(renderer.domElement, container.firstChild);

    // 3. Asks Grid (Top - Red)
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
    scene.add(bidsMesh);

    // 5. Central Filament (VWAP/Price - Cyan)
    const filamentGeo = new THREE.CylinderGeometry(0.15, 0.15, 30, 12);
    filamentGeo.rotateZ(Math.PI / 2);
    const filamentMat = new THREE.MeshBasicMaterial({ color: 0x00F0FF, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
    centralFilament = new THREE.Mesh(filamentGeo, filamentMat);
    scene.add(centralFilament);

    // 6. Tactical Planes (Risk Management)
    const planeGeo = new THREE.PlaneGeometry(30, 20);
    planeGeo.rotateX(-Math.PI / 2);
    
    // Red Plane = Stop Loss (Top/Bottom depending on trade)
    stopLossPlane = new THREE.Mesh(planeGeo, new THREE.MeshBasicMaterial({ color: 0xFF2E63, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    stopLossPlane.position.y = 2;
    stopLossPlane.visible = false;
    scene.add(stopLossPlane);

    // Green Plane = Trailing Stop / Take Profit
    trailingStopPlane = new THREE.Mesh(planeGeo, new THREE.MeshBasicMaterial({ color: 0x00FF9D, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    trailingStopPlane.position.y = -2;
    trailingStopPlane.visible = false;
    scene.add(trailingStopPlane);

    // 7. Pulse Ring
    const ringGeo = new THREE.TorusGeometry(1.5, 0.3, 32, 100);
    pulseRing = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: 0xFFFFFF, transparent: true, opacity: 0, blending: THREE.AdditiveBlending }));
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

function deformGrid(mesh, time, baseHeight, intensity, isAsk, flashWhite) {
    const positions = mesh.geometry.attributes.position;
    const dir = isAsk ? -1 : 1;
    for (let i = 0; i < positions.count; i++) {
        const x = positions.getX(i);
        const z = positions.getZ(i);
        let yOffset = Math.sin(x * 0.8 + time) * Math.cos(z * 0.8 + time) * intensity;
        positions.setY(i, baseHeight + (yOffset * dir));
    }
    mesh.geometry.attributes.position.needsUpdate = true;
    
    // Flash white on extreme Z-Score
    if (flashWhite) {
        mesh.material.color.setHex(0xFFFFFF);
        mesh.material.opacity = 0.8;
    } else {
        mesh.material.color.setHex(isAsk ? 0xFF2E63 : 0x00FF9D);
        mesh.material.opacity = 0.35;
    }
}

function animate() {
    requestAnimationFrame(animate);
    const time = clock.getElapsedTime();

    // Z-Score logic
    const targetBend = currentZScore;
    centralFilament.position.y += (targetBend - centralFilament.position.y) * 0.05;
    
    // Filament pulse
    if (Math.abs(currentZScore) > 2.0) {
        centralFilament.material.color.setHex(currentZScore > 0 ? 0xFF2E63 : 0x00FF9D);
        centralFilament.scale.y = 1 + Math.abs(currentZScore) * 1.5; 
        centralFilament.scale.x = 1 + Math.abs(currentZScore) * 0.5; 
        centralFilament.scale.z = 1 + Math.abs(currentZScore) * 0.5;
    } else {
        centralFilament.material.color.setHex(0x00F0FF);
        centralFilament.scale.set(1,1,1);
    }

    // OFI determines speed of rotation and scrolling
    let speedMult = 1 + Math.abs(currentOFI) / 200;
    speedMult = Math.min(speedMult, 5.0); // Cap speed
    
    let askIntensity = currentOFI < 0 ? Math.abs(currentOFI) / 300 : 0.3;
    let bidIntensity = currentOFI > 0 ? currentOFI / 300 : 0.3;
    askIntensity = Math.min(askIntensity, 3.5);
    bidIntensity = Math.min(bidIntensity, 3.5);
    
    // Flash trigger logic if Z-Score > 3.0
    const flashAsk = currentZScore > 3.0;
    const flashBid = currentZScore < -3.0;

    deformGrid(asksMesh, time * speedMult, 4, askIntensity, true, flashAsk);
    deformGrid(bidsMesh, time * speedMult, -4, bidIntensity, false, flashBid);

    // Scroll
    asksMesh.position.x = (time * speedMult * 2) % 1;
    bidsMesh.position.x = (time * speedMult * 2) % 1;

    // Pulse animation
    if (pulseRing.material.opacity > 0) {
        pulseRing.scale.addScalar(0.4);
        pulseRing.material.opacity -= 0.03;
    }

    renderer.render(scene, camera);
}

// Public API
window.updateQuantumMesh = function(zScore, ofi, isActive) {
    if (!scene) return;
    currentZScore = zScore;
    currentOFI = ofi;
    
    if (isActive && !isPositionActive) {
        pulseRing.scale.set(1,1,1);
        pulseRing.material.opacity = 1.0;
        pulseRing.position.y = currentZScore; 
    }
    isPositionActive = isActive;

    if (isActive) {
        stopLossPlane.visible = true;
        trailingStopPlane.visible = true;
        
        const atrDist = 1.5; // Represents 1.5x ATR
        
        // Stop Loss is Red, Trailing Stop is Green
        // For a BUY (price going up), SL is below, TP is above
        if (currentZScore > 0) { // Assume short if price is spiking up? Let's say ZScore>0 means overbought (sell signal)
            stopLossPlane.position.y = currentZScore + atrDist; // SL above for Short
            trailingStopPlane.position.y = currentZScore - (atrDist*0.5); // TS below
        } else {
            stopLossPlane.position.y = currentZScore - atrDist; // SL below for Long
            trailingStopPlane.position.y = currentZScore + (atrDist*0.5); // TS above
        }
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
