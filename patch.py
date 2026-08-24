import re
import os

engine_path = "C:/Users/52664/.gemini/antigravity/scratch/sfa-ifa-pro/app/engine.py"

with open(engine_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add numpy import if not present
if "import numpy as np" not in content:
    content = content.replace("import math\n", "import math\nimport numpy as np\n")
    if "import numpy as np" not in content:
        content = "import numpy as np\n" + content

# Add the SFA logic method
sfa_method = """
    def _analizar_vector_sfa(self, lecturas_numericas):
        if len(lecturas_numericas) == 0:
            return None
        frequency_m = 7.25
        phi = 1.618033988749895
        fs = 1.0 # 1 sample per minute
        
        datos = np.array(lecturas_numericas, dtype=float)
        N = len(datos)
        
        promedio = np.mean(datos)
        desviacion = np.std(datos)
        
        # Caos Fractal
        residuos_caos = np.abs((datos / frequency_m) % phi)
        indice_caos = float(np.mean(residuos_caos))
        
        # FFT
        datos_ac = datos - promedio
        espectro = np.fft.rfft(datos_ac)
        frecuencias = np.fft.rfftfreq(N, 1.0 / fs)
        magnitudes = np.abs(espectro) / N
        
        frecuencia_dominante = 0.0
        amplitud_dominante = 0.0
        if len(magnitudes) > 0:
            idx_pico = np.argmax(magnitudes)
            frecuencia_dominante = float(frecuencias[idx_pico])
            amplitud_dominante = float(magnitudes[idx_pico])
            
        return {
            "promedio": float(promedio),
            "desviacion": float(desviacion),
            "caos_fractal": indice_caos,
            "frecuencia_dominante_hz": frecuencia_dominante,
            "amplitud_dominante": amplitud_dominante
        }
"""

if "_analizar_vector_sfa" not in content:
    content = content.replace("    def _calculate_ema_series", sfa_method + "\n    def _calculate_ema_series")


logic_start_pattern = r"# 1\. Fractal Timeframe candle reconstructions.*?# Triggers \(Anticipation via OFI\)\s+buy_trigger = [^\n]+\s+sell_trigger = [^\n]+"

replacement = """# 1. Fractal Timeframe (SFA)
        candles_1m = self.candle_history
        closed_1m = candles_1m[:-1] if len(candles_1m) > 1 else candles_1m
        
        buy_trigger = False
        sell_trigger = False
        is_golden = False
        reason = ""
        
        if len(closed_1m) >= 30:
            prices = [c["close"] for c in closed_1m[-30:]]
            sfa_data = self._analizar_vector_sfa(prices)
            if sfa_data:
                sigma = sfa_data["desviacion"]
                caos = sfa_data["caos_fractal"]
                freq_dom = sfa_data["frecuencia_dominante_hz"]
                amp_dom = sfa_data["amplitud_dominante"]
                
                # Señal Dorada
                if amp_dom > (sigma * 0.8) and caos > 1.0:
                    is_golden = True
                    if prices[-1] < sfa_data["promedio"]:
                        buy_trigger = True
                        reason = f"GOLDEN BUY SFA (Caos={caos:.2f}, Freq={freq_dom:.2f}, Sigma={sigma:.2f})"
                    else:
                        sell_trigger = True
                        reason = f"GOLDEN SELL SFA (Caos={caos:.2f}, Freq={freq_dom:.2f}, Sigma={sigma:.2f})"
                        
                # Señal Normal
                elif sigma > 1.0 and caos > 0.5:
                    if prices[-1] < sfa_data["promedio"]:
                        buy_trigger = True
                        reason = f"NORMAL BUY SFA (Caos={caos:.2f}, Sigma={sigma:.2f})"
                    else:
                        sell_trigger = True
                        reason = f"NORMAL SELL SFA (Caos={caos:.2f}, Sigma={sigma:.2f})"
"""

content = re.sub(logic_start_pattern, replacement, content, flags=re.DOTALL)

# Take profit dynamic exit logic
exit_logic_pattern = r"if open_order\.side == \"BUY\":\s+if price >= tp:\s+exit_reason = \"TAKE_PROFIT HIT\""

exit_logic_replacement = """if open_order.side == "BUY":
                    # Dinámico Take Profit: Si el Caos bajó de 0.2 (Volvió a Nominal), salimos
                    sfa_data = self._analizar_vector_sfa([c["close"] for c in self.candle_history[-30:]]) if len(self.candle_history) >= 30 else None
                    if sfa_data and sfa_data["caos_fractal"] < 0.2:
                        exit_reason = "TAKE_PROFIT HIT (SFA NOMINAL)"
                    elif price >= tp:
                        exit_reason = "TAKE_PROFIT HIT" """

content = re.sub(exit_logic_pattern, exit_logic_replacement, content, flags=re.DOTALL)

exit_logic_pattern_sell = r"elif open_order\.side == \"SELL\":\s+if price <= tp:\s+exit_reason = \"TAKE_PROFIT HIT\""

exit_logic_replacement_sell = """elif open_order.side == "SELL":
                    sfa_data = self._analizar_vector_sfa([c["close"] for c in self.candle_history[-30:]]) if len(self.candle_history) >= 30 else None
                    if sfa_data and sfa_data["caos_fractal"] < 0.2:
                        exit_reason = "TAKE_PROFIT HIT (SFA NOMINAL)"
                    elif price <= tp:
                        exit_reason = "TAKE_PROFIT HIT" """

content = re.sub(exit_logic_pattern_sell, exit_logic_replacement_sell, content, flags=re.DOTALL)


with open(engine_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Pached successfully!")
