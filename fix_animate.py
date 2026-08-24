import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Replace everything from function animate() to the end of the function
new_animate = '''function animate() {
    requestAnimationFrame(animate);
    const time = clock.getElapsedTime();

    // OFI determines speed of rotation and scrolling
    let speedMult = 1 + Math.abs(currentOFI) / 200;
    speedMult = Math.min(speedMult, 5.0); // Cap speed

    // Z-Score logic
    const targetBend = currentZScore;
    centralFilament.rotation.x += 0.02 * speedMult;
    centralFilament.rotation.y += 0.03 * speedMult;
    centralFilament.rotation.z += 0.01 * speedMult;
    centralFilament.position.y += (targetBend - centralFilament.position.y) * 0.05;

    // Filament pulse
    if (Math.abs(currentZScore) > 2.0) {
        centralFilament.material.color.setHex(currentZScore > 0 ? 0xFF2E63 : 0x00FF9D);
        const s = 1 + Math.abs(currentZScore) * 0.5;
        centralFilament.scale.set(s, s, s);
    } else {
        centralFilament.material.color.setHex(0x00F0FF);
        centralFilament.scale.set(1,1,1);
    }

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
}'''

js = re.sub(r'function animate\(\) \{.*?(?=\n// Public API)', new_animate + '\n\n', js, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
