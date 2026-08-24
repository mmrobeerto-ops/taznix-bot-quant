import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\index.html"
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Add the post processing scripts after three.js
old_three = """    <!-- Three.js CDN -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <link rel="stylesheet" href="style.css?v=1783184">"""

new_three = """    <!-- Three.js CDN & Post-Processing -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/EffectComposer.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/RenderPass.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/ShaderPass.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/UnrealBloomPass.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/CopyShader.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/LuminosityHighPassShader.js"></script>
    
    <link rel="stylesheet" href="style.css?v=1783184">"""

html = html.replace(old_three, new_three)

# Update cache buster
html = re.sub(r'tzanix_quantum-core\.js\??[^"]*"', r'tzanix_quantum-core.js?v=particles1"', html)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
