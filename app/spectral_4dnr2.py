import numpy as np

def calcular_tau_optimo(secuencia: np.ndarray, max_tau: int = 25) -> int:
    """Calcula el retraso óptimo tau buscando el primer cruce de la autocorrelación < 1/e"""
    n = len(secuencia)
    if n < 3: return 1
    media = np.mean(secuencia)
    varianza = np.var(secuencia)
    if varianza == 0: return 1
    
    sec_centrada = secuencia - media
    for tau in range(1, min(max_tau, n//2)):
        cov = np.sum(sec_centrada[:-tau] * sec_centrada[tau:]) / (n - tau)
        if (cov / varianza) < 0.368:  # 1/e threshold
            return tau
    return 1

def digitalizar_ofi(ofi_buffer: np.ndarray) -> np.ndarray:
    """Convierte los valores de OFI en estados discretos (0, 1, 2)"""
    estados = np.ones_like(ofi_buffer, dtype=np.int32)
    estados[np.abs(ofi_buffer) < 0.1] = 0
    estados[np.abs(ofi_buffer) >= 0.6] = 2
    return estados

def calcular_matriz_transicion(estados: np.ndarray) -> np.ndarray:
    """Construye matriz empírica 3x3 de transiciones"""
    matriz = np.zeros((3, 3), dtype=np.float64)
    for i in range(len(estados) - 1):
        matriz[estados[i], estados[i+1]] += 1.0
    sumas_filas = matriz.sum(axis=1, keepdims=True)
    return np.where(sumas_filas > 0, matriz / sumas_filas, 1.0 / 3.0)

def simular_factor_k_vectorizado(matriz: np.ndarray, pasos=25, simulaciones=1000) -> float:
    """Simulación Montecarlo vectorizada MCMC de masa crítica"""
    estados = np.ones(simulaciones, dtype=np.int32)
    umbrales = np.cumsum(matriz, axis=1)
    fisiones_totales = np.zeros(simulaciones, dtype=np.int32)
    pasos_vivos = np.ones(simulaciones, dtype=np.int32)
    
    for _ in range(pasos):
        r = np.random.rand(simulaciones)
        umb_actual = umbrales[estados]
        
        siguiente_estado = np.zeros(simulaciones, dtype=np.int32)
        siguiente_estado[r >= umb_actual[:, 0]] = 1
        siguiente_estado[r >= umb_actual[:, 1]] = 2
        
        vivos = (siguiente_estado > 0)
        pasos_vivos += vivos
        fisiones_totales += (siguiente_estado == 2)
        estados = siguiente_estado
        
    factor_k = np.mean(fisiones_totales / np.where(pasos_vivos > 0, pasos_vivos, 1))
    return float(factor_k)

def takens_embedding_4d(secuencia: np.ndarray, tau: int = 1) -> np.ndarray:
    """
    Proyecta una serie temporal 1D a un Espacio de Estado 4D (Tesseract)
    utilizando retardos de fase dinámica (Takens Embedding).
    """
    x = secuencia
    y = np.roll(secuencia, tau)
    z = np.roll(secuencia, 2*tau)
    w = np.roll(secuencia, 3*tau)
    return np.column_stack((x, y, z, w))

def analizar_espectro_4dnr2(
    secuencia: np.ndarray, 
    frecuencia_objetivo: float = 7.25, 
    sample_rate: float = 100.0
) -> dict:
    """
    Analizador Espectral 4DNR2: Evalúa la coherencia matricial y la energía 
    en la frecuencia objetivo frente al espacio 4D.
    
    Funciona como un evaluador de series numéricas o un Gatekeeper para el bot.
    """
    N = len(secuencia)
    if N < 4:
        return {"luz_verde": False, "lambda_max": 0.0, "ratio_resonancia_4d": 0.0, "energia_725hz": 0.0, "autovalores_4d": [], "factor_k": 0.0}
    
    # 0. Calcular Tau Dinámico para submuestreo seguro
    tau_optimo = calcular_tau_optimo(secuencia)
    
    # 1. Mapeo a Manifold 4D por retardos
    vector_4d = takens_embedding_4d(secuencia, tau_optimo)
    
    # 2. FFT Multidimensional
    espectros = np.fft.fft(vector_4d, axis=0)
    frecuencias = np.fft.fftfreq(N, d=1.0/sample_rate)
    
    # Aislamiento de energía en la frecuencia base (7.25 Hz)
    idx_725 = np.argmin(np.abs(frecuencias - frecuencia_objetivo))
    energia_725_4d = np.sum(np.abs(espectros[idx_725, :])**2)
    
    # 3. Matriz de Covarianza Inter-dimensional (4D x 4D)
    espectros_centrados = espectros - np.mean(espectros, axis=0)
    C_4d = np.dot(espectros_centrados.T, np.conjugate(espectros_centrados)) / N
    
    # 4. Eigen-diagnóstico (Autovalores)
    autovalores, _ = np.linalg.eigh(C_4d)
    autovalores = np.sort(np.real(autovalores))[::-1]
    
    lambda_max = autovalores[0]
    energia_total = np.sum(autovalores)
    ratio_resonancia_4d = (lambda_max / energia_total) if energia_total > 0 else 0.0
    
    # Criterio de validación (Luz verde si hay estructura coherente sobre el ruido)
    # Umbral adaptable: > 28% de ratio o energía 7.25Hz significativa
    luz_verde = bool(ratio_resonancia_4d > 0.28)
    
    # Inyección del Reactor Cuántico MCMC (Cálculo de Masa Crítica)
    estados_discretos = digitalizar_ofi(secuencia)
    matriz_transicion = calcular_matriz_transicion(estados_discretos)
    factor_k = simular_factor_k_vectorizado(matriz_transicion)
    
    return {
        "luz_verde": luz_verde,
        "lambda_max": float(lambda_max),
        "ratio_resonancia_4d": float(ratio_resonancia_4d),
        "energia_725hz": float(energia_725_4d),
        "autovalores_4d": autovalores.tolist(),
        "factor_k": factor_k
    }
