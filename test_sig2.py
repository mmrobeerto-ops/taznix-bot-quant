import wasmtime

store = wasmtime.Store()
module = wasmtime.Module.from_file(store.engine, r'C:\Users\52664\.gemini\antigravity\scratch\tzanix-quantum-engine\pkg\tzanix_quantum_engine_bg.wasm')
linker = wasmtime.Linker(store.engine)
linker.define_unknown_imports_as_traps(module)
instance = linker.instantiate(store, module)
exports = instance.exports(store)

print("get_graph_edges params:", exports["quantumenginewasm_get_graph_edges"].type(store).params)
print("get_graph_edges results:", exports["quantumenginewasm_get_graph_edges"].type(store).results)

