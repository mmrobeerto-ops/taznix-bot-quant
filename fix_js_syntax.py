import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# Fix the missing quotes for fragmentShader
old_str = "fragmentShader: uniform sampler2D tDiffuse; varying vec2 vUv; void main() { gl_FragColor = texture2D(tDiffuse, vUv); }"
new_str = "fragmentShader: 'uniform sampler2D tDiffuse; varying vec2 vUv; void main() { gl_FragColor = texture2D(tDiffuse, vUv); }'"

js_code = js_code.replace(old_str, new_str)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
