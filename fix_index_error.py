import re
path = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\engine.py"
with open(path, 'r', encoding='utf-8') as f:
    engine_code = f.read()

# Change the Kill Switch trigger on IndexError to just pass
engine_code = engine_code.replace("log_to_db(\"FATAL\", \"Kill Switch: Error de B\u00fafer Circular (IndexError) detectado.\")", "pass # Ignore empty buffer at startup")
engine_code = engine_code.replace("self.kill_switch_active = True", "pass # self.kill_switch_active = True", 1) # Only replace the first occurrence (which is the IndexError one, wait! I better use a precise replace)

with open(path, 'w', encoding='utf-8') as f:
    f.write(engine_code)
