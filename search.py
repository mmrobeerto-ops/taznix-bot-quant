import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
search_dir = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app"
for root, _, files in os.walk(search_dir):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if 'multinivel' in line.lower() or 'rechazado' in line.lower():
                        print(f"{file}:{i+1}: {line.strip()}")
