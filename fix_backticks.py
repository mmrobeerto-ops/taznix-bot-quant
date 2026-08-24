import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

shaders = [
    "coreVertexShader",
    "coreFragmentShader",
    "ringVertexShader",
    "ringFragmentShader",
    "absorptionVertexShader",
    "absorptionFragmentShader",
    "fadeVertexShader"
]

for shader in shaders:
    # Find the const declaration
    pattern = r'(const\s+' + shader + r'\s*=\s*)(.*?)(?=const\s+|function\s+initQuantumMesh|\/\/ ---)'
    match = re.search(pattern, js_code, re.DOTALL)
    if match:
        content = match.group(2).strip()
        # If it doesn't already start with a backtick
        if not content.startswith(''):
            # It might have a trailing semicolon
            if content.endswith(';'):
                content = content[:-1].strip()
            
            new_decl = match.group(1) + '\n' + content + '\n;\n\n'
            js_code = js_code[:match.start()] + new_decl + js_code[match.end():]

# Ensure fadeFragmentShader has quotes (we fixed it earlier but let's be sure)
if "fragmentShader: 'uniform sampler2D tDiffuse" not in js_code:
    js_code = js_code.replace("fragmentShader: uniform sampler2D tDiffuse; varying vec2 vUv; void main() { gl_FragColor = texture2D(tDiffuse, vUv); }", "fragmentShader: 'uniform sampler2D tDiffuse; varying vec2 vUv; void main() { gl_FragColor = texture2D(tDiffuse, vUv); }'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
