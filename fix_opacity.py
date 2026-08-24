import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# 1. Lower core brightness / opacity
js_code = js_code.replace("gl_PointSize = (1.2 / -mvPosition.z)", "gl_PointSize = (0.8 / -mvPosition.z)")
js_code = js_code.replace("gl_FragColor = vec4(0.0, 0.94, 1.0, alpha * 0.8); // FIXED CYAN", "gl_FragColor = vec4(0.0, 0.94, 1.0, alpha * 0.3); // FIXED CYAN, highly transparent")

# 2. Make rings look more like data lines, less like solid walls
js_code = js_code.replace("new THREE.CylinderGeometry(ringRadii[i], ringRadii[i], 0.5, 128, 1, true)", "new THREE.CylinderGeometry(ringRadii[i], ringRadii[i], 0.5, 48, 1, true)")
js_code = js_code.replace("gl_FragColor = vec4(finalColor, 0.6); // Semi-transparent wireframe", "gl_FragColor = vec4(finalColor, 0.25); // Highly transparent wireframe")

# 3. Adjust Bloom so the core doesn't wash out (increase threshold)
js_code = js_code.replace("new THREE.UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 1.5, 0.5, 0.4)", "new THREE.UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 0.8, 0.5, 0.7)")

# 4. Make absorption rays dimmer
js_code = js_code.replace("gl_FragColor = vec4(uColor, vAlpha * 0.8);", "gl_FragColor = vec4(uColor, vAlpha * 0.4);")

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
