import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\static\tzanix_quantum-core.js"
with open(path, 'r', encoding='utf-8') as f:
    js = f.read()

# Update color logic
old_color_logic = """    // Core Pulse (Singularity)
    let coreColor = 0x00F0FF;
    let s = 1;
    if (Math.abs(currentZScore) > 2.0) {
        coreColor = currentZScore > 0 ? 0xFF2E63 : 0x00FF9D;
        s = 1 + Math.abs(currentZScore) * 0.3;
    }"""

new_color_logic = """    // Core Pulse (Singularity) linked to BTC Price
    let coreColor = 0x00F0FF;
    let s = 1;
    
    // React to global market state (set in app.js based on BTC price)
    if (window.globalMarketState === -1) {
        coreColor = 0xFF2E63; // Red on Drop
        s = 1.1; // Slight pulse
    } else if (window.globalMarketState === 1) {
        coreColor = 0x00FF9D; // Green on Rise
        s = 1.1;
    }
    
    // Extreme Z-Score overrides with bigger pulse
    if (Math.abs(currentZScore) > 2.0) {
        s = 1 + Math.abs(currentZScore) * 0.3;
    }"""

js = js.replace(old_color_logic, new_color_logic)

# Enhance the shader to add the "frequency/creation" fragment effect
old_shader = """            vec3 dispNormal = normalize(position);
            transformed += dispNormal * (wave + pulse);
            
        );
    };"""

new_shader = """            vec3 dispNormal = normalize(position);
            transformed += dispNormal * (wave + pulse);
            // Pass world position to fragment shader
            vWorldPosition = (modelMatrix * vec4(transformed, 1.0)).xyz;
            
        );
        
        // Add varying to vertex shader
        shader.vertexShader = arying vec3 vWorldPosition;\n + shader.vertexShader;
        
        // Fragment shader modification
        shader.fragmentShader = 
            uniform float time;
            varying vec3 vWorldPosition;
         + shader.fragmentShader;
        
        shader.fragmentShader = shader.fragmentShader.replace(
            #include <dithering_fragment>,
            
            #include <dithering_fragment>
            // Create a frequency wave that makes parts of the mesh disappear/reappear
            // This simulates particles interconnecting and creating the figure
            float freq = sin(vWorldPosition.y * 15.0 - time * 10.0) * 0.5 + 0.5;
            float freq2 = sin(vWorldPosition.x * 10.0 + time * 5.0) * 0.5 + 0.5;
            float combinedFreq = (freq * freq2) + 0.2; // Minimum opacity 0.2
            gl_FragColor.a *= combinedFreq;
            
        );
    };"""

js = js.replace(old_shader, new_shader)

with open(path, 'w', encoding='utf-8') as f:
    f.write(js)
