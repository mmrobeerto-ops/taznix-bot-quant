import numpy as np
from scipy.fft import fft, ifft

class SignalProcessor:
    """
    Módulo de Procesamiento Digital de Señales (DSP) para HFT.
    Aplica una Transformada Rápida de Fourier (FFT) para filtrar ruido de microestructura.
    """
    def __init__(self, window_size: int = 64, cutoff_ratio: float = 0.2):
        """
        :param window_size: Cantidad de ticks a mantener en el buffer circular.
        :param cutoff_ratio: Proporción de frecuencias a mantener (0.2 = mantiene 20% más bajas).
        """
        self.window_size = window_size
        self.cutoff_ratio = cutoff_ratio
        
    def apply_fft_filter(self, prices: np.ndarray) -> np.ndarray:
        """
        Aplica un filtro de paso bajo (Low-Pass Filter) en el dominio espectral.
        """
        n = len(prices)
        if n < 4:
            return prices
            
        # 1. Transformar al dominio de la frecuencia (FFT)
        spectrum = fft(prices)
        
        # 2. Calcular índices de corte
        cutoff_idx = max(1, int(n * self.cutoff_ratio))
        
        # 3. Anular las altas frecuencias (ruido de spoofing y fluctuaciones estocásticas)
        # La FFT es simétrica, por lo que anulamos el "centro" del array espectral.
        spectrum[cutoff_idx:-cutoff_idx] = 0
        
        # 4. Reconstruir la señal limpia al dominio temporal (iFFT)
        clean_signal = ifft(spectrum)
        
        # Retornar solo la parte real (los artefactos imaginarios son ~0)
        return np.real(clean_signal)
        
    def get_clean_price(self, prices: np.ndarray) -> float:
        """
        Procesa el array de precios históricos y devuelve el último precio "limpio".
        """
        if len(prices) == 0:
            return 0.0
        clean_signal = self.apply_fft_filter(prices)
        return float(clean_signal[-1])
