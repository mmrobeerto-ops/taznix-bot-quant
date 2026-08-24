import sys

glsl_core = """// TZANIX QUANTUM CORE - Quant-X Edition
// GLSL GPU Animation + FBO Trails Feedback Loop

let scene, camera, renderer, composer, bloomPass;
let particlesMesh;
let customShaderMaterial;

// FBO Variables for Trails
let rtA, rtB;
let fadeScene, fadeCamera, fadeMaterial;

// Configurations
const particleCount = 50000;
const timeMult = 0.0003;
let lastTime = 0;

// Market State
let currentOFI = 0.0;
let currentZScore = 0.0;
let currentVol = 0.0;
let targetColor = new THREE.Vector3(0.0, 0.94, 1.0); // Cyan base
let currentColor = new THREE.Vector3(0.0, 0.94, 1.0);

// --- GLSL SHADERS ---
const vertexShader = 
uniform float uTime;
uniform float uSpeed;

attribute float aRadius;
attribute float aPhase;
attribute float aLayer;

varying float vAlpha;
varying vec3 vColor;

// 3D Simplex Noise Approximation (Pseudo Curl)
vec3 curlNoise(vec3 p) {
    float x = sin(p.y) * cos(p.z);
    float y = sin(p.z) * cos(p.x);
    float z = sin(p.x) * cos(p.y);
    return vec3(x, y, z);
}

void main() {
    // Determine orbital shell (Layering like an onion)
    // aLayer is a value from 0 to 1, heavily weighted towards 0.
    float shellRadius = aRadius;
    
    // Base position on the shell
    vec3 basePos = position;
    
    // Add time-based rotation and Curl Noise displacement
    float t = uTime * uSpeed + aPhase;
    
    // Flow field
    vec3 noise = curlNoise(basePos * 2.0 + t);
    
    // Project noise onto the tangent plane of the sphere to strictly confine it to the shell
    vec3 normal = normalize(basePos);
    vec3 tangentNoise = noise - dot(noise, normal) * normal;
    
    // Calculate final position
    // Particles move along the surface of their specific onion layer
    vec3 animatedPos = normalize(basePos + tangentNoise * 0.5) * shellRadius;
    
    // Add a slight global rotation
    float c = cos(t * 0.2);
    float s = sin(t * 0.2);
    mat3 rotY = mat3(
        c, 0.0, s,
        0.0, 1.0, 0.0,
        -s, 0.0, c
    );
    animatedPos = rotY * animatedPos;

    vec4 mvPosition = modelViewMatrix * vec4(animatedPos, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = (1.5 / -mvPosition.z) * (1.0 - aLayer * 0.5); // Core is brighter/bigger

    // Opacity based on depth and layer
    vAlpha = 1.0 - (aLayer * 0.5);
}
;

const fragmentShader = 
uniform vec3 uColor;
varying float vAlpha;

void main() {
    // Make points circular and soft
    vec2 xy = gl_PointCoord.xy - vec2(0.5);
    float ll = length(xy);
    if(ll > 0.5) discard;
    
    // Soft glow falloff
    float alpha = (0.5 - ll) * 2.0 * vAlpha;
    gl_FragColor = vec4(uColor, alpha * 0.8);
}
;

const fadeVertexShader = 
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = vec4(position, 1.0);
}
;

const fadeFragmentShader = 
uniform sampler2D tDiffuse;
varying vec2 vUv;
void main() {
    vec4 texColor = texture2D(tDiffuse, vUv);
    // Darken the previous frame to create the fading trail effect
    // Multiply by a factor slightly less than 1 (e.g. 0.9)
    gl_FragColor = vec4(texColor.rgb * 0.90, texColor.a);
}
;

function initQuantumMesh() {
    const container = document.getElementById('threejs-canvas-container');
    if (!container) return;

    // 1. Scene & Camera
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.z = 8;

    renderer = new THREE.WebGLRenderer({ alpha: false, antialias: false, preserveDrawingBuffer: true }); // Alpha false for FBO blending
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.autoClear = false; // We manage clearing manually for the feedback loop
    container.appendChild(renderer.domElement);

    // 2. FBO Ping-Pong Setup for Trails
    const rtParams = {
        minFilter: THREE.LinearFilter,
        magFilter: THREE.LinearFilter,
        format: THREE.RGBAFormat,
        type: THREE.FloatType
    };
    rtA = new THREE.WebGLRenderTarget(container.clientWidth, container.clientHeight, rtParams);
    rtB = new THREE.WebGLRenderTarget(container.clientWidth, container.clientHeight, rtParams);

    fadeScene = new THREE.Scene();
    fadeCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    fadeMaterial = new THREE.ShaderMaterial({
        uniforms: { tDiffuse: { value: null } },
        vertexShader: fadeVertexShader,
        fragmentShader: fadeFragmentShader,
        depthTest: false,
        depthWrite: false
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), fadeMaterial);
    fadeScene.add(plane);

    // 3. Geometry (Static, heavily concentrated at core, distinct onion layers)
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const radii = new Float32Array(particleCount);
    const phases = new Float32Array(particleCount);
    const layers = new Float32Array(particleCount);

    const maxRadius = 3.5;
    
    for (let i = 0; i < particleCount; i++) {
        const u = Math.random();
        const v = Math.random();
        const theta = 2 * Math.PI * u;
        const phi = Math.acos(2 * v - 1);
        
        // Quantize the radius into distinct layers (Onion effect)
        // Heavily weight towards the innermost layers for the solid core
        const layerLevel = Math.pow(Math.random(), 5); // 0.0 is center, 1.0 is edge
        
        // Create 8 discrete shells
        const discreteLayer = Math.floor(layerLevel * 8.0) / 8.0; 
        
        // Base sphere is small so the core is dense, add some padding
        const r = maxRadius * (discreteLayer + 0.1);

        const x = Math.sin(phi) * Math.cos(theta);
        const y = Math.sin(phi) * Math.sin(theta);
        const z = Math.cos(phi);

        positions[i * 3] = x;
        positions[i * 3 + 1] = y;
        positions[i * 3 + 2] = z;

        radii[i] = r;
        phases[i] = Math.random() * Math.PI * 2;
        layers[i] = discreteLayer;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aRadius', new THREE.BufferAttribute(radii, 1));
    geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
    geometry.setAttribute('aLayer', new THREE.BufferAttribute(layers, 1));

    // 4. Custom Shader Material
    customShaderMaterial = new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0.0 },
            uSpeed: { value: 1.0 },
            uColor: { value: currentColor }
        },
        vertexShader: vertexShader,
        fragmentShader: fragmentShader,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    particlesMesh = new THREE.Points(geometry, customShaderMaterial);
    scene.add(particlesMesh);

    // 5. Post-Processing (Bloom over the FBO result)
    // We will render the final RT into the composer
    const passThroughShader = {
        uniforms: { tDiffuse: { value: null } },
        vertexShader: fadeVertexShader,
        fragmentShader: 
            uniform sampler2D tDiffuse;
            varying vec2 vUv;
            void main() { gl_FragColor = texture2D(tDiffuse, vUv); }
        
    };
    
    // We create a dummy scene to feed the Composer
    const finalScene = new THREE.Scene();
    const finalMat = new THREE.ShaderMaterial(passThroughShader);
    const finalPlane = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), finalMat);
    finalScene.add(finalPlane);

    composer = new THREE.EffectComposer(renderer);
    composer.addPass(new THREE.RenderPass(finalScene, fadeCamera));
    
    bloomPass = new THREE.UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight), 
        3.0, // High strength for the solid core
        0.5, 
        0.2  // Low threshold
    );
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
    
    const w = container.clientWidth;
    const h = container.clientHeight;
    renderer.setSize(w, h);
    rtA.setSize(w, h);
    rtB.setSize(w, h);
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

    // Color logic
    if (window.globalMarketState === -1) {
        targetColor.set(1.0, 0.18, 0.39); // Red
        bloomPass.strength = 4.0; 
    } else if (window.globalMarketState === 1) {
        targetColor.set(0.0, 1.0, 0.61); // Green
        bloomPass.strength = 4.0;
    } else {
        targetColor.set(0.0, 0.94, 1.0); // Cyan
        bloomPass.strength = 3.0;
    }

    currentColor.lerp(targetColor, 0.1);
    customShaderMaterial.uniforms.uColor.value.copy(currentColor);
    bloomPass.tintColor = new THREE.Color(currentColor.x, currentColor.y, currentColor.z);

    let speedMult = 1.0 + (Math.abs(currentOFI) / 2000); 
    customShaderMaterial.uniforms.uTime.value += delta;
    customShaderMaterial.uniforms.uSpeed.value = speedMult;

    // --- FBO PING-PONG FEEDBACK LOOP ---
    
    // 1. Draw previous frame (RT A) faded into RT B
    renderer.setRenderTarget(rtB);
    renderer.clear();
    fadeMaterial.uniforms.tDiffuse.value = rtA.texture;
    renderer.render(fadeScene, fadeCamera);

    // 2. Draw current particles into RT B (Additive over the faded background)
    renderer.render(scene, camera);

    // 3. Swap RTs
    let temp = rtA;
    rtA = rtB;
    rtB = temp;

    // 4. Render final RT A to screen via Composer
    renderer.setRenderTarget(null); // Back to screen
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
    f.write(glsl_core)
