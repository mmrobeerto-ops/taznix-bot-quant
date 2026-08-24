import wasmtime

# Test if wasmtime is working
store = wasmtime.Store()
module = wasmtime.Module.from_file(store.engine, r'C:\Users\52664\.gemini\antigravity\scratch\tzanix-quantum-engine\pkg\tzanix_quantum_engine_bg.wasm')
linker = wasmtime.Linker(store.engine)

try:
    linker.define_unknown_imports_as_traps(module)
    instance = linker.instantiate(store, module)
    exports = instance.exports(store)
    
    print("WASM Loaded Successfully!")
    print("Exports:")
    for name in exports:
        print(f" - {name}")
except Exception as e:
    print(f"Error: {e}")

