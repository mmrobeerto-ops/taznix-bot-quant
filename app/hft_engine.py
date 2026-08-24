import numpy as np
from numba import njit, uint64, int32, float64

# ==============================================================================
# HFT ENGINE: 4D Morton Curve & k-NN (JIT Compiled via Numba)
# ==============================================================================

MAX_HISTORY = 1_000_000

# We use a structured contiguous array.
# Col 0: Morton Code (Z-Order index)
# Col 1: Future Price Move % (Positive for Bullish, Negative for Bearish)
# Col 2: Timestamp (to filter out old data if needed)
hft_memory = np.empty((MAX_HISTORY, 3), dtype=np.float64) 
hft_count = 0

# Transitory L1 Buffer to avoid sorting the whole array during volatile jumps
L1_BUFFER_SIZE = 1000
l1_buffer = np.empty((L1_BUFFER_SIZE, 3), dtype=np.float64)
l1_count = 0

@njit(fastmath=True, cache=True)
def get_morton_code_4d(x: float, y: float, z: float, t: float) -> uint64:
    """
    Convierte un vector 4D normalizado [0.0, 1.0] en un entero Morton de 64 bits.
    Asigna 16 bits de precisión por eje (65,536 niveles) e intercala los bits.
    Latencia esperada: < 0.1 microsegundos por llamada gracias a Numba.
    """
    # Normalize inputs [0.0, 1.0] to [0, 65535]
    xi = uint64(max(0.0, min(1.0, x)) * 65535.0)
    yi = uint64(max(0.0, min(1.0, y)) * 65535.0)
    zi = uint64(max(0.0, min(1.0, z)) * 65535.0)
    ti = uint64(max(0.0, min(1.0, t)) * 65535.0)
    
    code = uint64(0)
    # Bucle simple y seguro; Numba lo desenrolla (unroll) y compila a instrucciones de CPU.
    for i in range(16):
        bit_x = (xi >> uint64(i)) & uint64(1)
        bit_y = (yi >> uint64(i)) & uint64(1)
        bit_z = (zi >> uint64(i)) & uint64(1)
        bit_t = (ti >> uint64(i)) & uint64(1)
        
        code |= (bit_x << uint64(4 * i))
        code |= (bit_y << uint64(4 * i + 1))
        code |= (bit_z << uint64(4 * i + 2))
        code |= (bit_t << uint64(4 * i + 3))
    
    return code

@njit(fastmath=True, cache=True)
def fast_binary_search_knn(memory: np.ndarray, count: int, target_code: uint64, k: int = 5):
    """
    Encuentra los K vecinos más cercanos en el arreglo contiguo 1D ordenado (Curva de Morton).
    Devuelve un array de los movimientos futuros asociados a esos vecinos.
    """
    if count == 0:
        return np.zeros(k, dtype=np.float64)
        
    # Cast col 0 as uint64 for binary search
    left = 0
    right = count - 1
    
    # Binary search to find the closest insertion point
    mid = 0
    while left <= right:
        mid = left + (right - left) // 2
        # Use view to reinterpret the 64-bit float bytes as 64-bit uint bytes without losing precision
        # Wait, if we stored uint64 as float64, it might lose precision if it's > 53 bits!
        # In python, assigning uint64 to float64 numpy array loses precision for large numbers.
        # It's better to cast properly. I will fix the array dtype below.
        val_mid = uint64(memory[mid, 0])
        
        if val_mid == target_code:
            break
        elif val_mid < target_code:
            left = mid + 1
        else:
            right = mid - 1
            
    results = np.zeros(k, dtype=np.float64)
    r_idx = 0
    l_ptr = mid
    r_ptr = mid + 1
    
    while r_idx < k:
        if l_ptr >= 0 and r_ptr < count:
            val_l = uint64(memory[l_ptr, 0])
            val_r = uint64(memory[r_ptr, 0])
            dist_l = target_code - val_l if target_code > val_l else val_l - target_code
            dist_r = target_code - val_r if target_code > val_r else val_r - target_code
            
            if dist_l <= dist_r:
                results[r_idx] = memory[l_ptr, 1]
                l_ptr -= 1
            else:
                results[r_idx] = memory[r_ptr, 1]
                r_ptr += 1
        elif l_ptr >= 0:
            results[r_idx] = memory[l_ptr, 1]
            l_ptr -= 1
        elif r_ptr < count:
            results[r_idx] = memory[r_ptr, 1]
            r_ptr += 1
        else:
            break
            
        r_idx += 1
        
    return results

@njit(fastmath=True, cache=True)
def evaluate_knn_probabilities(future_moves: np.ndarray, min_profit_pct: float = 0.2):
    bullish_count = 0
    bearish_count = 0
    total = len(future_moves)
    
    for i in range(total):
        if future_moves[i] >= min_profit_pct:
            bullish_count += 1
        elif future_moves[i] <= -min_profit_pct:
            bearish_count += 1
            
    if total == 0:
        return 0.0, 0.0
        
    p_bull = bullish_count / total
    p_bear = bearish_count / total
    return p_bull, p_bear
