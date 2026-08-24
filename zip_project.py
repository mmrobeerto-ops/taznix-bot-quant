import os
import zipfile

source_dir = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro"
output_zip = r"C:\Users\52664\.gemini\antigravity\brain\94180d30-e149-4b48-91ff-c722398319a1\TZANiX_Quant_X_Source.zip"

def should_exclude(file_name, root):
    if file_name.endswith('.db') or file_name.endswith('.db-shm') or file_name.endswith('.db-wal'):
        return True
    if '__pycache__' in root or '.pytest_cache' in root:
        return True
    if file_name.endswith('.zip') or file_name.endswith('.log'):
        return True
    return False

with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(source_dir):
        for file in files:
            if not should_exclude(file, root):
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, source_dir)
                zipf.write(abs_path, rel_path)

print(f"Zip created at {output_zip}")
