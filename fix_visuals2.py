import re

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js_code = f.read()

# 1. Reduce Bloom Strength
js_code = re.sub(r'bloomPass\.strength = 3\.5;', 'bloomPass.strength = 1.2;', js_code)
js_code = re.sub(r'bloomPass\.strength = 5\.0;', 'bloomPass.strength = 2.0;', js_code)
js_code = re.sub(r'bloomPass\.strength = 7\.0;', 'bloomPass.strength = 3.5;', js_code)
js_code = js_code.replace('3.0, // High strength for the solid core', '1.2, // Lower strength')
js_code = js_code.replace('0.2  // Low threshold', '0.6  // Higher threshold')

# 2. Spread out particles more to outer shells
js_code = js_code.replace('Math.pow(Math.random(), 5);', 'Math.pow(Math.random(), 2.0); // Less core bias')

# 3. Modify Vertex Shader Curl Noise so outer layers move faster/differently
old_tangent = """    vec3 tangentNoise = noise - dot(noise, normal) * normal;
    
    // Calculate final position
    // Particles move along the surface of their specific onion layer
    vec3 animatedPos = normalize(basePos + tangentNoise * 0.5) * shellRadius;"""

new_tangent = """    vec3 tangentNoise = noise - dot(noise, normal) * normal;
    
    // Outer layers should have more pronounced neural pathways
    float neuralFactor = 0.5 + (aLayer * 1.5);
    
    // Calculate final position
    vec3 animatedPos = normalize(basePos + tangentNoise * neuralFactor) * shellRadius;"""
    
js_code = js_code.replace(old_tangent, new_tangent)

# 4. Make particles slightly smaller so it doesn't get totally solid
js_code = js_code.replace('gl_PointSize = (2.0 / -mvPosition.z) * (1.0 - aLayer * 0.8);', 'gl_PointSize = (1.2 / -mvPosition.z) * (1.0 - aLayer * 0.5);')

with open(path, 'w', encoding='utf-8') as f:
    f.write(js_code)
