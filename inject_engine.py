import re
import sys

path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    engine_code = f.read()

# 1. Add import at the top
if 'from app.quantum_bridge import evaluate_market_topology' not in engine_code:
    engine_code = "from app.quantum_bridge import evaluate_market_topology\n" + engine_code

# 2. Inject evaluation in process_tick
old_code = """        current_time = time.time()

        # Check if news pause has expired"""

new_code = """        current_time = time.time()
        
        # --- QUANTUM CORE DECISION BRIDGE ---
        # Map current tick to topology wave resonance
        tick_data = {'price': price, 'volume': volume, 'z_score': self.last_zscore if hasattr(self, 'last_zscore') else 0, 'ofi': imbalance}
        quantum_signal = evaluate_market_topology(tick_data)
        if quantum_signal in ['BUY', 'SELL']:
            log_to_db("INFO", f"Quantum Core Topology Trigger: {quantum_signal}")

        # Check if news pause has expired"""

engine_code = engine_code.replace(old_code, new_code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(engine_code)

print("Injected Quantum Bridge successfully.")
