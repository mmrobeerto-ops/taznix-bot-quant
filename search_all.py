import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
search_dir = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro"
for root, _, files in os.walk(search_dir):
    for file in files:
        if file.endswith(('.py', '.js', '.json', '.txt')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        if 'multinivel' in line.lower() or 'rechazado' in line.lower():
                            print(f"{path}:{i+1}: {line.strip()}")
            except Exception:
                pass
