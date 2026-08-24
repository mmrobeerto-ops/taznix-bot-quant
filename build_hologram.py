import sys

glsl_code = """// TZANIX QUANTUM CORE - 3-Part Hologram Scene
// 1. Fixed Cyan Core
// 2. Data Frequency Rings
// 3. Absorption Streams

let scene, camera, renderer, composer, bloomPass;
let coreMesh, ringsGroup, absorptionMesh;
let coreMaterial, ringMaterial, absorptionMaterial;

// FBO Variables for Trails (Core & Absorption)
let rtA, rtB;
let fadeScene, fadeCamera, fadeMaterial;

// Configurations
const coreParticleCount = 25000;
const absorptionParticleCount = 8000;
const timeMult = 0.0003;
let lastTime = 0;

// Market State
let currentOFI = 0.0;
let currentZScore = 0.0;
let currentVol = 0.0;
let targetDataColor = new THREE.Vector3(1.0, 0.75, 0.0); // Amber base for rings
let currentDataColor = new THREE.Vector3(1.0, 0.75, 0.0);

// --- SHADERS PARA EL NUCLEO (FIJO CIAN) ---
const coreVertexShader = 
uniform float uTime;
attribute float aRadius;
attribute float aPhase;
attribute float aLayer;
varying float vAlpha;

vec3 curlNoise(vec3 p) {
    float x = sin(p.y) * cos(p.z);
    float y = sin(p.z) * cos(p.x);
    float z = sin(p.x) * cos(p.y);
    return vec3(x, y, z);
}

void main() {
    float shellRadius = aRadius;
    vec3 basePos = position;
    float t = uTime * 0.5 + aPhase;
    vec3 noise = curlNoise(basePos * 2.0 + t);
    vec3 normal = normalize(basePos);
    vec3 tangentNoise = noise - dot(noise, normal) * normal;
    float neuralFactor = 0.5 + (aLayer * 1.5);
    vec3 animatedPos = normalize(basePos + tangentNoise * neuralFactor) * shellRadius;
    
    float c = cos(t * 0.2);
    float s = sin(t * 0.2);
    mat3 rotY = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c);
    animatedPos = rotY * animatedPos;

    vec4 mvPosition = modelViewMatrix * vec4(animatedPos, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = (1.2 / -mvPosition.z) * (1.0 - aLayer * 0.5); 
    vAlpha = 1.0 - (aLayer * 0.7);
}
;

const coreFragmentShader = 
varying float vAlpha;
void main() {
    vec2 xy = gl_PointCoord.xy - vec2(0.5);
    float ll = length(xy);
    if(ll > 0.5) discard;
    float alpha = (0.5 - ll) * 2.0 * vAlpha;
    gl_FragColor = vec4(0.0, 0.94, 1.0, alpha * 0.8); // FIXED CYAN
}
;

// --- SHADERS PARA LOS ANILLOS DE FRECUENCIA ---
const ringVertexShader = 
uniform float uTime;
uniform float uAmplitude;
varying float vIntensity;

void main() {
    // We add high-frequency noise based on angle and time
    float angle = atan(position.z, position.x);
    
    // Create multiple overlapping waves
    float wave1 = sin(angle * 15.0 + uTime * 2.0);
    float wave2 = cos(angle * 30.0 - uTime * 3.0) * 0.5;
    float wave3 = sin(angle * 5.0 + uTime * 5.0) * 2.0;
    
    // Combine waves and modulate with amplitude from market data
    float totalWave = (wave1 + wave2 + wave3) * uAmplitude;
    
    // The ring is a cylinder, so normal is pointing outwards horizontally
    vec3 newPos = position + normal * totalWave;
    
    vIntensity = (totalWave / uAmplitude) * 0.5 + 0.5; // Normalized 0-1 for coloring
    
    gl_Position = projectionMatrix * modelViewMatrix * vec4(newPos, 1.0);
}
;

const ringFragmentShader = 
uniform vec3 uColor;
varying float vIntensity;
void main() {
    // Brighten the peaks of the waves
    vec3 finalColor = mix(uColor * 0.3, uColor * 1.5, vIntensity);
    gl_FragColor = vec4(finalColor, 0.6); // Semi-transparent wireframe
}
;

// --- SHADERS PARA RAYOS DE ABSORCION ---
const absorptionVertexShader = 
uniform float uTime;
attribute float aSpeed;
attribute float aOffset;
varying float vAlpha;

void main() {
    vec3 dir = normalize(position);
    // Particles move from radius 12.0 down to 0.0
    float progress = fract(uTime * aSpeed + aOffset);
    float currentRadius = 12.0 * (1.0 - progress);
    
    vec3 newPos = dir * currentRadius;
    
    vec4 mvPosition = modelViewMatrix * vec4(newPos, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = 2.0 / -mvPosition.z;
    
    // Fade out as they get very close to the center
    vAlpha = smoothstep(0.0, 2.0, currentRadius) * smoothstep(12.0, 10.0, currentRadius);
}
;

const absorptionFragmentShader = 
uniform vec3 uColor;
varying float vAlpha;
void main() {
    vec2 xy = gl_PointCoord.xy - vec2(0.5);
    if(length(xy) > 0.5) discard;
    gl_FragColor = vec4(uColor, vAlpha * 0.8);
}
;

// --- FBO FADE SHADERS ---
const fadeVertexShader = 
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position, 1.0); }
;
const fadeFragmentShader = 
uniform sampler2D tDiffuse;
varying vec2 vUv;
void main() {
    vec4 texColor = texture2D(tDiffuse, vUv);
    gl_FragColor = vec4(texColor.rgb * 0.88, texColor.a);
}
;


function initQuantumMesh() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.set(0, 5, 15);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ alpha: false, antialias: true, preserveDrawingBuffer: true }); 
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.autoClear = false; 
    container.appendChild(renderer.domElement);

    // FBO Ping-Pong Setup for Trails (Core & Absorption)
    const rtParams = { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, format: THREE.RGBAFormat, type: THREE.FloatType };
    rtA = new THREE.WebGLRenderTarget(container.clientWidth, container.clientHeight, rtParams);
    rtB = new THREE.WebGLRenderTarget(container.clientWidth, container.clientHeight, rtParams);

    fadeScene = new THREE.Scene();
    fadeCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    fadeMaterial = new THREE.ShaderMaterial({ uniforms: { tDiffuse: { value: null } }, vertexShader: fadeVertexShader, fragmentShader: fadeFragmentShader, depthTest: false, depthWrite: false });
    fadeScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), fadeMaterial));

    // 1. CORE GEOMETRY
    const coreGeo = new THREE.BufferGeometry();
    const cPos = new Float32Array(coreParticleCount * 3);
    const cRad = new Float32Array(coreParticleCount);
    const cPha = new Float32Array(coreParticleCount);
    const cLay = new Float32Array(coreParticleCount);
    for (let i = 0; i < coreParticleCount; i++) {
        const u = Math.random(), v = Math.random();
        const theta = 2 * Math.PI * u, phi = Math.acos(2 * v - 1);
        const layerLevel = Math.pow(Math.random(), 2.0); 
        const discreteLayer = Math.floor(layerLevel * 8.0) / 8.0; 
        const r = 2.5 * (discreteLayer + 0.1); // Slightly smaller core
        cPos[i*3] = Math.sin(phi)*Math.cos(theta); cPos[i*3+1] = Math.sin(phi)*Math.sin(theta); cPos[i*3+2] = Math.cos(phi);
        cRad[i] = r; cPha[i] = Math.random() * Math.PI * 2; cLay[i] = discreteLayer;
    }
    coreGeo.setAttribute('position', new THREE.BufferAttribute(cPos, 3));
    coreGeo.setAttribute('aRadius', new THREE.BufferAttribute(cRad, 1));
    coreGeo.setAttribute('aPhase', new THREE.BufferAttribute(cPha, 1));
    coreGeo.setAttribute('aLayer', new THREE.BufferAttribute(cLay, 1));

    coreMaterial = new THREE.ShaderMaterial({
        uniforms: { uTime: { value: 0.0 } },
        vertexShader: coreVertexShader, fragmentShader: coreFragmentShader,
        transparent: true, blending: THREE.AdditiveBlending, depthWrite: false
    });
    coreMesh = new THREE.Points(coreGeo, coreMaterial);
    scene.add(coreMesh);

    // 2. DATA RINGS GEOMETRY
    ringsGroup = new THREE.Group();
    ringMaterial = new THREE.ShaderMaterial({
        uniforms: { uTime: { value: 0.0 }, uAmplitude: { value: 0.2 }, uColor: { value: currentDataColor } },
        vertexShader: ringVertexShader, fragmentShader: ringFragmentShader,
        transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, wireframe: true
    });
    
    // Create 3 rings at different radii and slight tilts
    const ringRadii = [4.5, 6.0, 7.5];
    for (let i = 0; i < 3; i++) {
        const rGeo = new THREE.CylinderGeometry(ringRadii[i], ringRadii[i], 0.5, 128, 1, true);
        const rMesh = new THREE.Mesh(rGeo, ringMaterial);
        rMesh.rotation.x = (Math.random() - 0.5) * 0.5;
        rMesh.rotation.z = (Math.random() - 0.5) * 0.5;
        ringsGroup.add(rMesh);
    }
    scene.add(ringsGroup);

    // 3. ABSORPTION STREAMS GEOMETRY
    const absGeo = new THREE.BufferGeometry();
    const aPos = new Float32Array(absorptionParticleCount * 3);
    const aSpeed = new Float32Array(absorptionParticleCount);
    const aOffset = new Float32Array(absorptionParticleCount);
    for (let i = 0; i < absorptionParticleCount; i++) {
        const u = Math.random(), v = Math.random();
        const theta = 2 * Math.PI * u, phi = Math.acos(2 * v - 1);
        aPos[i*3] = Math.sin(phi)*Math.cos(theta); aPos[i*3+1] = Math.sin(phi)*Math.sin(theta); aPos[i*3+2] = Math.cos(phi);
        aSpeed[i] = 0.2 + Math.random() * 0.8;
        aOffset[i] = Math.random();
    }
    absGeo.setAttribute('position', new THREE.BufferAttribute(aPos, 3));
    absGeo.setAttribute('aSpeed', new THREE.BufferAttribute(aSpeed, 1));
    absGeo.setAttribute('aOffset', new THREE.BufferAttribute(aOffset, 1));
    
    absorptionMaterial = new THREE.ShaderMaterial({
        uniforms: { uTime: { value: 0.0 }, uColor: { value: currentDataColor } },
        vertexShader: absorptionVertexShader, fragmentShader: absorptionFragmentShader,
        transparent: true, blending: THREE.AdditiveBlending, depthWrite: false
    });
    absorptionMesh = new THREE.Points(absGeo, absorptionMaterial);
    scene.add(absorptionMesh);


    // POST PROCESSING
    const finalScene = new THREE.Scene();
    finalScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
        uniforms: { tDiffuse: { value: null } }, vertexShader: fadeVertexShader,
        fragmentShader: uniform sampler2D tDiffuse; varying vec2 vUv; void main() { gl_FragColor = texture2D(tDiffuse, vUv); }
    })));

    composer = new THREE.EffectComposer(renderer);
    composer.addPass(new THREE.RenderPass(finalScene, fadeCamera));
    
    bloomPass = new THREE.UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 1.5, 0.5, 0.4);
    composer.addPass(bloomPass);

    window.addEventListener('resize', onWindowResize, false);
    
    lastTime = Date.now();
    animate();
}

function onWindowResize() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h);
    rtA.setSize(w, h); rtB.setSize(w, h);
    composer.setSize(w, h);
}

window.updateQuantumMesh = function(tickData) {
    if (!tickData) return;
    if (tickData.z_score !== undefined) currentZScore = parseFloat(tickData.z_score);
    if (tickData.ofi !== undefined) currentOFI = parseFloat(tickData.ofi);
    if (tickData.vol !== undefined) currentVol = parseFloat(tickData.vol);
}

function animate() {
    requestAnimationFrame(animate);

    const now = Date.now();
    const delta = (now - lastTime) * timeMult;
    lastTime = now;

    // The core is ALWAYS Cyan. The DATA (Rings & Absorption) changes color based on market.
    if (window.globalMarketState === -1) {
        targetDataColor.set(1.0, 0.0, 0.05); // Red
        bloomPass.strength = 2.5; 
    } else if (window.globalMarketState === 1) {
        targetDataColor.set(1.0, 0.84, 0.0); // Bright Gold
        bloomPass.strength = 2.0;
    } else {
        targetDataColor.set(1.0, 0.75, 0.0); // Amber
        bloomPass.strength = 1.5;
    }

    currentDataColor.lerp(targetDataColor, 0.1);
    ringMaterial.uniforms.uColor.value.copy(currentDataColor);
    absorptionMaterial.uniforms.uColor.value.copy(currentDataColor);
    
    // Animate uniforms
    coreMaterial.uniforms.uTime.value += delta * 1.5;
    ringMaterial.uniforms.uTime.value += delta * 2.0;
    absorptionMaterial.uniforms.uTime.value += delta * 2.5;

    // Amplitude of rings based on volatility (Z-Score or OFI)
    let marketVolatility = Math.abs(currentOFI) / 1000 + Math.abs(currentZScore) * 0.1;
    let targetAmplitud = 0.2 + marketVolatility * 0.5;
    if (targetAmplitud > 1.5) targetAmplitud = 1.5;
    ringMaterial.uniforms.uAmplitude.value += (targetAmplitud - ringMaterial.uniforms.uAmplitude.value) * 0.05;

    // Rotate rings slightly
    ringsGroup.rotation.y += 0.002;
    ringsGroup.rotation.x += 0.001;

    // --- FBO PING-PONG FEEDBACK LOOP (Trails) ---
    renderer.setRenderTarget(rtB);
    renderer.clear();
    
    // 1. Draw faded previous frame
    fadeMaterial.uniforms.tDiffuse.value = rtA.texture;
    renderer.render(fadeScene, fadeCamera);

    // 2. Draw elements that need trails (Core & Absorption)
    // Hide rings temporarily so they don't get trails (wireframe trails look messy)
    ringsGroup.visible = false;
    renderer.render(scene, camera);
    
    // 3. Draw Rings WITHOUT trails on top of the FBO
    ringsGroup.visible = true;
    renderer.render(scene, camera); // Note: Since autoClear is false, rings are additive over trails

    // Swap RTs
    let temp = rtA; rtA = rtB; rtB = temp;

    // Render to Screen + Bloom
    renderer.setRenderTarget(null);
    renderer.clear();
    composer.passes[0].scene.children[0].material.uniforms.tDiffuse.value = rtA.texture;
    composer.render();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initQuantumMesh);
} else {
    initQuantumMesh();
}
"""

with open(r'C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js', 'w', encoding='utf-8') as f:
    f.write(glsl_code)
