import re

with open('static/app.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Remove LightweightCharts code
js = re.sub(r'function initChart\(\) \{.*?\n\}', 'function initChart() { console.log("3D engine handled by tzanix_quantum-core.js"); }', js, flags=re.DOTALL)

# In handleLiveTick, update updateQuantumMesh
tick_logic = '''
    // Update DOM Metrics
    document.getElementById("lbl-zscore").textContent = tick.z_score ? tick.z_score.toFixed(2) : "0.00";
    document.getElementById("lbl-ofi").textContent = tick.ofi ? tick.ofi.toFixed(2) : "0.00";

    // Forward to 3D engine
    const activeState = document.getElementById("pos-active-state");
    let isActive = false;
    if (activeState && !activeState.classList.contains("hide")) {
        isActive = true;
    }
    
    if (window.updateQuantumMesh) {
        window.updateQuantumMesh(tick.z_score || 0, tick.ofi || 0, isActive);
    }
'''

# Find the end of handleLiveTick and insert the call
js = re.sub(r'// Pulse effect.*?\} catch\(e\) \{\}', tick_logic, js, flags=re.DOTALL)

# Remove series.update calls
js = re.sub(r'if \(tick\.sma_200 !== null.*?\}\);[\s\r\n]*\}', '', js, flags=re.DOTALL)
js = re.sub(r'priceSeries\.update\(currentCandle\);', '', js)

with open('static/app.js', 'w', encoding='utf-8') as f:
    f.write(js)
