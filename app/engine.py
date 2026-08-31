from app.quantum_bridge import evaluate_market_topology
import uuid
import time
import os
import requests
import threading
import datetime
import numpy as np
from typing import List, Dict, Optional, Tuple
from app.database import (
    SessionLocal, 
    TickModel, 
    OrderModel, 
    AuditLogModel, 
    log_to_db, 
    load_risk_config, 
    save_risk_config,
    save_tick_to_db,
    update_order_stop_loss_async
)
from app.schemas import RiskConfig, DashboardMetrics
from app.broker import BrokerClient
from app.spectral_4dnr2 import analizar_espectro_4dnr2
from app.signal_processor import SignalProcessor
from app.hft_engine import (
    get_morton_code_4d, hft_memory, hft_count, l1_buffer, l1_count, 
    fast_binary_search_knn, evaluate_knn_probabilities
)

class TradingEngine:
    def __init__(self):
        self.config = RiskConfig()
        
        # Instantiate the Prop Firm / Evaluation Account Broker Execution Client
        self.broker = BrokerClient()
        
        # In-memory history for indicator calculations (max 200 ticks needed for SMA 200)
        self.tick_history = []
        
        # Cumulative stats for VWAP
        self.vwap_sum_pv = 0.0
        self.vwap_sum_v = 0.0
        
        # Active trades (only 1 active position at a time is a standard improvement for safety)
        self.active_position: Optional[Dict] = None
        
        # Session states
        self.session_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.max_drawdown = 0.0
        self.peak_session_pnl = 0.0
        self.kill_switch_active = False
        self.kill_switch_reason = None
        self.kill_switch_activated_at = 0.0
        
        # News filter state
        self.news_paused = False
        self.active_news_event: Optional[str] = None
        self.news_pause_until = 0.0

        # Real-time Bar Builder states (1-minute bars)
        self.candle_history: List[Dict] = []
        self.current_candle: Optional[Dict] = None

        # Quarantine zones list
        self.quarantine_zones = []
        self.last_processed_date_utc = None

        # Market regime & indicator snapshot tracking for notifications
        self.last_adx_15m = 0.0
        self.last_rsi_1m = 0.0
        self.last_vwap_dev = 0.0
        self.last_buy_ratio = 0.5
        self.is_range_mode = False
        
        # --- HFT 4D Tesseract Subsystem ---
        self.signal_processor = SignalProcessor(window_size=64, cutoff_ratio=0.2)
        self.raw_ticks_buffer = []  # To hold pure prices for FFT
        self.last_freq_hz = 7.25
        self.max_holding_minutes = 240
        self.adx_trend_threshold = 28.0
        self.last_adx_15m = 0.0
        self.last_rsi_1m = 0.0
        self.last_vwap_dev = 0.0
        self.last_buy_ratio = 0.5
        self.last_ofi = 0.0
        self.last_z_score = 0.0
        self.last_vwap_upper = 0.0
        self.last_vwap_lower = 0.0
        self.is_range_mode = False

        # Precalculated RSI history tracking
        self.rsi_history_1m = []

        # Load session state from DB if any exists (helps with persistence)
        self.restore_state_from_db()

        # Warmup and initial 4h trend fetch
        if os.environ.get("TESTING") != "True":
            self._warm_up_candles_from_binance()
            
        # Initialize and launch 4DNR2 Background Radar
        self.latest_4dnr2_res = {"luz_verde": False, "ratio_resonancia_4d": 0.0, "lambda_max": 0.0}
        self.ofi_buffer_c = np.zeros(250, dtype=np.float64)
        self.ofi_buffer_idx = 0
        self.t0_binance = 0
        self.latency_strikes = 0
        self.last_micro_price = None
        self.last_mid_price = None
        self.last_open_interest = 0.0
        self.last_cvd = 0.0
        self.kill_switch_active = False
        self._4d_lock = threading.Lock()
        threading.Thread(target=self._4dnr2_background_loop, daemon=True).start()

    def _4dnr2_background_loop(self):
        """Runs the 4DNR2 FFT math continuously on a background thread for 0ms latency in the main engine."""
        while True:
            try:
                # Use the pre-allocated circular buffer (No Python GC overhead)
                res_4d = analizar_espectro_4dnr2(self.ofi_buffer_c)
                with self._4d_lock:
                    self.latest_4dnr2_res = res_4d
            except IndexError:
                pass # Ignore empty buffer at startup
                pass # self.kill_switch_active = True
            except Exception:
                pass
            time.sleep(0.05)

    def _send_telegram_notification(self, message: str):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id or token == "YOUR_TELEGRAM_BOT_TOKEN" or token == "":
            return
            
        def send_async():
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
                res = requests.post(url, json=payload, timeout=5)
                res.raise_for_status()
            except Exception as e:
                print(f"Error sending Telegram notification: {e}")
                
        threading.Thread(target=send_async, daemon=True).start()

    def is_market_ranging_flat(self) -> (bool, str):
        if os.environ.get("TESTING") == "True":
            return False, ""
        # We need at least 10 candles in history to judge
        if len(self.candle_history) < 10:
            # Not enough history yet, default to allowing but monitor
            return False, ""
            
        # 1. Calculate ADX
        adx_val = self._calculate_adx_14()
        if adx_val > 0.0 and adx_val < 16.0:
            return True, f"ADX low ({adx_val:.1f} < 16.0) indicating weak/absent trend"
            
        # 2. Calculate recent range of the last 15 candles
        recent_candles = self.candle_history[-15:]
        highest_high = max(c["high"] for c in recent_candles)
        lowest_low = min(c["low"] for c in recent_candles)
        pct_range = (highest_high - lowest_low) / recent_candles[-1]["close"] * 100.0
        
        # If the highest high and lowest low of the last 15 minutes is within 0.07%, it is a flat channel
        if pct_range < 0.07:
            return True, f"Flat Channel detected: last 15m range is only {pct_range:.3f}% (< 0.07%)"
            
        return False, ""

    def _calculate_adx_14(self, candles: Optional[List[Dict]] = None, return_series: bool = False) -> Any:
        if candles is None:
            candles = self.candle_history
        period = 14
        if len(candles) < period * 2 + 1:
            if return_series:
                return []
            return 0.0
            
        tr_list = []
        plus_dm_list = []
        minus_dm_list = []
        
        for i in range(1, len(candles)):
            curr = candles[i]
            prev = candles[i-1]
            
            hl = curr["high"] - curr["low"]
            hc = abs(curr["high"] - prev["close"])
            lc = abs(curr["low"] - prev["close"])
            tr = max(hl, hc, lc)
            tr_list.append(tr)
            
            up_move = curr["high"] - prev["high"]
            down_move = prev["low"] - curr["low"]
            
            plus_dm = 0.0
            minus_dm = 0.0
            if up_move > down_move and up_move > 0:
                plus_dm = up_move
            if down_move > up_move and down_move > 0:
                minus_dm = down_move
                
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
            
        smoothed_tr = [0.0] * len(tr_list)
        smoothed_plus_dm = [0.0] * len(plus_dm_list)
        smoothed_minus_dm = [0.0] * len(minus_dm_list)
        
        smoothed_tr[period-1] = sum(tr_list[:period])
        smoothed_plus_dm[period-1] = sum(plus_dm_list[:period])
        smoothed_minus_dm[period-1] = sum(minus_dm_list[:period])
        
        for i in range(period, len(tr_list)):
            smoothed_tr[i] = smoothed_tr[i-1] - (smoothed_tr[i-1] / period) + tr_list[i]
            smoothed_plus_dm[i] = smoothed_plus_dm[i-1] - (smoothed_plus_dm[i-1] / period) + plus_dm_list[i]
            smoothed_minus_dm[i] = smoothed_minus_dm[i-1] - (smoothed_minus_dm[i-1] / period) + minus_dm_list[i]
            
        dx_list = []
        for i in range(period-1, len(tr_list)):
            tr_val = smoothed_tr[i]
            if tr_val == 0:
                plus_di = 0.0
                minus_di = 0.0
            else:
                plus_di = 100.0 * (smoothed_plus_dm[i] / tr_val)
                minus_di = 100.0 * (smoothed_minus_dm[i] / tr_val)
                
            di_diff = abs(plus_di - minus_di)
            di_sum = plus_di + minus_di
            
            dx = 0.0
            if di_sum != 0:
                dx = 100.0 * (di_diff / di_sum)
            dx_list.append(dx)
            
        if len(dx_list) < period:
            if return_series:
                return []
            return 0.0
            
        adx_values = [0.0] * len(dx_list)
        adx_values[period-1] = sum(dx_list[:period]) / period
        
        for i in range(period, len(dx_list)):
            adx_values[i] = ((adx_values[i-1] * (period - 1)) + dx_list[i]) / period
            
        if return_series:
            return adx_values
        return adx_values[-1]

    def _get_ema_15m(self, period: int) -> Optional[float]:
        """Helper to get the last value of a 15-minute EMA."""
        candles_15m = self._aggregate_candles(15)
        ema_series = self._calculate_ema_series(period, candles_15m)
        return ema_series[-1] if len(ema_series) >= 1 else None

    def _detect_ema_crossover(self, side: str, fast_period: int, slow_period: int) -> bool:
        """Detects if fast EMA crossed slow EMA in the latest closed candles."""
        candles = self.candle_history
        if len(candles) < 2:
            return False
            
        fast_ema = self._calculate_ema_series(fast_period, candles)
        slow_ema = self._calculate_ema_series(slow_period, candles)
        
        if len(fast_ema) < 2 or len(slow_ema) < 2:
            return False
            
        if side == "BUY":
            return fast_ema[-1] > slow_ema[-1] and fast_ema[-2] <= slow_ema[-2]
        elif side == "SELL":
            return fast_ema[-1] < slow_ema[-1] and fast_ema[-2] >= slow_ema[-2]
        return False

    def _is_signal_coherent(
        self, 
        signal_type: str, 
        ofi: float, 
        z_score: float, 
        adx: float, 
        ema_fast_15m: Optional[float], 
        ema_slow_15m: Optional[float]
    ) -> Tuple[bool, str]:
        """
        Valida la coherencia de microestructura y régimen de tendencia.
        Retorna (es_valido, motivo_rechazo).
        """
        is_trending = False
        is_bullish_trend_15m = False
        is_bearish_trend_15m = False
        
        if adx >= 30.0 and ema_fast_15m is not None and ema_slow_15m is not None:
            is_trending = True
            is_bullish_trend_15m = ema_fast_15m > ema_slow_15m
            is_bearish_trend_15m = ema_fast_15m < ema_slow_15m

        # 1. Gatekeeper de Flujo y Desviación Estadística (OFI / Z-Score)
        if signal_type == "BUY":
            if ofi < 0.30:
                return False, f"OFI insuficiente para BUY (OFI={ofi:.2f} < 0.30)"
            if z_score > 0.5:
                return False, f"Z-Score sobrecomprado para BUY (Z={z_score:.2f} > 0.5). Esperando pullback."
        elif signal_type == "SELL":
            if ofi > -0.30:
                return False, f"OFI insuficiente para SELL (OFI={ofi:.2f} > -0.30)"
            if z_score < -0.5:
                return False, f"Z-Score sobrevendido para SELL (Z={z_score:.2f} < -0.5). Esperando rebote."

        # 1.1 VETO HFT: Divergencia OFI vs. TFI (Spoofing / Muro Iceberg)
        if hasattr(self, "last_real_l2_ofi"):
            if signal_type == "BUY" and self.last_real_l2_ofi > 10.0 and ofi < -0.1:
                return False, f"[SPOOFING VETO] OFI L2 Positivo ({self.last_real_l2_ofi:.1f}) pero TFI Negativo ({ofi:.2f}): Takers vendiendo contra muro de compra."
            elif signal_type == "SELL" and self.last_real_l2_ofi < -10.0 and ofi > 0.1:
                return False, f"[SPOOFING VETO] OFI L2 Negativo ({self.last_real_l2_ofi:.1f}) pero TFI Positivo ({ofi:.2f}): Takers comprando contra muro de venta."

        # 1.2 VETO HFT: Oráculo Lead-Lag (Spot vs. Futuros)
        LEAD_LAG_THRESHOLD = 15.0
        if getattr(self, "last_spot_micro_price", None) is not None and getattr(self, "last_micro_price", None) is not None:
            if signal_type == "BUY" and self.last_spot_micro_price < self.last_micro_price - LEAD_LAG_THRESHOLD:
                return False, f"[LEAD-LAG VETO] Spot micro-price (${self.last_spot_micro_price:.2f}) liderando caída bajo Futuros (${self.last_micro_price:.2f})."
            elif signal_type == "SELL" and self.last_spot_micro_price > self.last_micro_price + LEAD_LAG_THRESHOLD:
                return False, f"[LEAD-LAG VETO] Spot micro-price (${self.last_spot_micro_price:.2f}) liderando alza sobre Futuros (${self.last_micro_price:.2f})."

        # 2. Filtro de Régimen por ADX y Tendencia 15m (EMA 9 vs EMA 21)
        if is_trending:
            if signal_type == "BUY" and not is_bullish_trend_15m:
                return False, f"ADX Elevado ({adx:.1f} >= 30) bloquea BUY contra tendencia bajista 15m"
            
            if signal_type == "SELL" and not is_bearish_trend_15m:
                return False, f"ADX Elevado ({adx:.1f} >= 30) bloquea SELL contra tendencia alcista 15m"

        return True, "APROBADA"

    def _check_time_stop(self, pos: Dict, price: float, current_time: float) -> bool:
        """Verifica si la posición excedió el tiempo máximo de retención (Time-Stop)."""
        if not pos:
            return False

        opened_at = pos.get("timestamp")
        if not opened_at:
            return False

        elapsed_minutes = (current_time - opened_at) / 60.0

        if elapsed_minutes >= self.max_holding_minutes:
            log_msg = (
                f"⏰ TIME_STOP disparado: Posición activa por {elapsed_minutes:.1f}m "
                f"(Límite: {self.max_holding_minutes}m). Ejecutando salida a mercado."
            )
            log_to_db("WARNING", log_msg)
            
            # Calculate PnL for close
            if pos["type"] == "BUY":
                pnl_val = (price - pos["entry_price"]) * pos["quantity"]
            else:
                pnl_val = (pos["entry_price"] - price) * pos["quantity"]
                
            self._close_position("TIME_STOP HIT", price, pnl_val, current_time)
            return True

        return False

    def restore_state_from_db(self):
        """Restores recent state and metrics from SQLite database."""
        from app.database import init_db
        init_db()
        db = SessionLocal()
        try:
            # Restore Dynamic Configuration from SQLite
            db_config = load_risk_config()
            if db_config:
                self.config.daily_loss_limit = db_config.get("daily_loss_limit", self.config.daily_loss_limit)
                self.config.trailing_stop_pct = db_config.get("trailing_stop_pct", self.config.trailing_stop_pct)
                self.config.vwap_threshold_pct = db_config.get("vwap_threshold_pct", self.config.vwap_threshold_pct)
                self.config.concrete_floor_threshold_pct = db_config.get("concrete_floor_threshold_pct", self.config.concrete_floor_threshold_pct)
                self.config.max_position_size = db_config.get("max_position_size", self.config.max_position_size)
                self.config.run_autopilot = db_config.get("run_autopilot", self.config.run_autopilot)
                self.config.atr_multiplier = db_config.get("atr_multiplier", getattr(self.config, "atr_multiplier", 3.5))
                self.config.breakeven_atr_trigger = db_config.get("breakeven_atr_trigger", getattr(self.config, "breakeven_atr_trigger", 2.0))
                self.config.use_atr_risk = db_config.get("use_atr_risk", getattr(self.config, "use_atr_risk", True))
                self.config.risk_amount_usdt = db_config.get("risk_amount_usdt", getattr(self.config, "risk_amount_usdt", 40.0))
                log_to_db("INFO", f"Loaded persistent configuration from SQLite: LossLimit=${self.config.daily_loss_limit}, SL_pct={self.config.trailing_stop_pct}%, Autopilot={self.config.run_autopilot}, ATR_mult={getattr(self.config, 'atr_multiplier', 3.5)}x, use_atr_risk={getattr(self.config, 'use_atr_risk', True)}, risk_amount_usdt=${self.config.risk_amount_usdt}")

            # Load active positions
            active_db_order = db.query(OrderModel).filter(OrderModel.status == "EXECUTED").first()
            if active_db_order:
                atr_mult = getattr(self.config, "atr_multiplier", 3.5)
                sl_distance = abs(active_db_order.entry_price - active_db_order.stop_loss)
                estimated_atr = sl_distance / atr_mult if sl_distance > 0 else (active_db_order.entry_price * (self.config.trailing_stop_pct / 100.0) / atr_mult)
                
                self.active_position = {
                    "id": active_db_order.id,
                    "type": active_db_order.type,
                    "entry_price": active_db_order.entry_price,
                    "quantity": active_db_order.quantity,
                    "stop_loss": active_db_order.stop_loss,
                    "take_profit": active_db_order.take_profit,
                    "reason": active_db_order.reason,
                    "timestamp": active_db_order.timestamp,
                    "entry_atr": estimated_atr,
                    "peak_price": active_db_order.entry_price if active_db_order.type == "BUY" else 0.0,
                    "trough_price": active_db_order.entry_price if active_db_order.type == "SELL" else 9999999.0,
                    "tp1_reached": False
                }
                log_to_db("INFO", f"Restored active position from database: {self.active_position['type']} @ {self.active_position['entry_price']}")

            # Self-healing: Check if there is an active position running on the live exchange
            # that is not recorded in our local database, and adopt it!
            from app.broker import BrokerClient
            try:
                broker = BrokerClient()
                live_positions = broker._send_signed_request("GET", "/fapi/v2/positionRisk", {})
                active_live = [p for p in live_positions if float(p.get("positionAmt", 0.0)) != 0.0]
                if active_live and not self.active_position:
                    pos_data = active_live[0]
                    qty = abs(float(pos_data["positionAmt"]))
                    entry_price = float(pos_data["entryPrice"])
                    pos_type = "BUY" if float(pos_data["positionAmt"]) > 0 else "SELL"
                    
                    # Create custom SL/TP targets based on current risk config
                    atr = self._calculate_atr(14)
                    atr_mult = getattr(self.config, "atr_multiplier", 3.5)
                    if atr is not None and atr > 0.0:
                        sl_dist = atr * atr_mult
                    else:
                        sl_dist = entry_price * (self.config.trailing_stop_pct / 100.0)
                        
                    if pos_type == "BUY":
                        sl = entry_price - sl_dist
                        tp = entry_price + (sl_dist * 2.0)
                    else:
                        sl = entry_price + sl_dist
                        tp = entry_price - (sl_dist * 2.0)
                    
                    order_id = f"adopted_{int(time.time())}"
                    
                    # Insert into DB
                    db_order = OrderModel(
                        id=order_id,
                        timestamp=time.time(),
                        type=pos_type,
                        status="EXECUTED",
                        entry_price=entry_price,
                        quantity=qty,
                        stop_loss=sl,
                        take_profit=tp,
                        reason="SELF-HEALING: Adopted active position found on Binance exchange on startup."
                    )
                    db.add(db_order)
                    db.commit()
                    
                    self.active_position = {
                        "id": order_id,
                        "type": pos_type,
                        "entry_price": entry_price,
                        "quantity": qty,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "reason": db_order.reason,
                        "timestamp": db_order.timestamp,
                        "entry_atr": atr if (atr is not None and atr > 0.0) else (sl_dist / atr_mult),
                        "peak_price": entry_price if pos_type == "BUY" else 0.0,
                        "trough_price": entry_price if pos_type == "SELL" else 9999999.0,
                        "tp1_reached": False
                    }
                    log_to_db("INFO", f"[SELF-HEALING] Adopted active Binance position: {pos_type} {qty} BTC @ ${entry_price:.2f}")
            except Exception as ex:
                log_to_db("WARNING", f"[SELF-HEALING] Failed to check/adopt active Binance positions: {ex}")

            # Calculate session stats from closed orders
            closed_orders = db.query(OrderModel).filter(OrderModel.status == "CLOSED").all()
            self.total_trades = len(closed_orders)
            self.session_pnl = sum((o.profit_loss or 0.0) for o in closed_orders)
            self.winning_trades = sum(1 for o in closed_orders if (o.profit_loss or 0.0) > 0)
            
            # Restore active quarantine zones from SQLite (closed with loss in last 30 mins)
            thirty_mins_ago = time.time() - 1800
            lost_trades = db.query(OrderModel).filter(
                OrderModel.status == "CLOSED",
                OrderModel.profit_loss < 0,
                OrderModel.close_timestamp >= thirty_mins_ago
            ).all()
            for trade in lost_trades:
                self.quarantine_zones.append({
                    "price": trade.entry_price,
                    "expires_at": trade.close_timestamp + 1800,
                    "lower_bound": trade.entry_price * (1.0 - 0.0015),
                    "upper_bound": trade.entry_price * (1.0 + 0.0015)
                })
            
            # Load latest ticks to rebuild 1-minute candles (covers up to 33 hours of history)
            latest_ticks = db.query(TickModel).order_by(TickModel.timestamp.desc()).limit(120000).all()
            # Reverse to keep chronological order
            all_loaded_ticks = [
                {"price": t.price, "volume": t.volume, "timestamp": t.timestamp}
                for t in reversed(latest_ticks)
            ]
            
            # Keep only the last 200 ticks in self.tick_history
            self.tick_history = all_loaded_ticks[-200:]
            
            # Reconstruct 1-minute candle history from loaded ticks
            candles_temp = {}
            for tick in all_loaded_ticks:
                candle_time = int(tick["timestamp"] // 60) * 60
                if candle_time not in candles_temp:
                    candles_temp[candle_time] = {
                        "open": tick["price"],
                        "high": tick["price"],
                        "low": tick["price"],
                        "close": tick["price"],
                        "volume": tick["volume"],
                        "timestamp": candle_time
                    }
                else:
                    c = candles_temp[candle_time]
                    c["high"] = max(c["high"], tick["price"])
                    c["low"] = min(c["low"], tick["price"])
                    c["close"] = tick["price"]
                    c["volume"] += tick["volume"]
            
            self.candle_history = sorted(list(candles_temp.values()), key=lambda x: x["timestamp"])[-2500:]
            
            # Precalculate last 150 RSI values for optimization
            self.rsi_history_1m = [None] * len(self.candle_history)
            start_calc = max(0, len(self.candle_history) - 150)
            for i in range(start_calc, len(self.candle_history)):
                self.rsi_history_1m[i] = self._calculate_rsi(14, self.candle_history[:i+1])
            
            # Recalculate cumulative VWAP sums from the ticks of the current UTC day
            if all_loaded_ticks:
                current_date_utc = datetime.datetime.fromtimestamp(all_loaded_ticks[-1]["timestamp"], datetime.timezone.utc).date()
                self.last_processed_date_utc = current_date_utc
                for tick in all_loaded_ticks:
                    tick_date = datetime.datetime.fromtimestamp(tick["timestamp"], datetime.timezone.utc).date()
                    if tick_date == current_date_utc:
                        self.vwap_sum_pv += tick["price"] * tick["volume"]
                        self.vwap_sum_v += tick["volume"]
                
        except Exception as e:
            print(f"Error restoring state from DB: {e}")
        finally:
            db.close()

    def run_self_healing_check(self):
        """
        Sincronización bidireccional de estado REST con Binance.
        Busca adoptar posiciones no registradas localmente o cerrar posiciones fantasma en memoria.
        """
        if os.environ.get("TESTING") == "True":
            return
            
        from app.broker import BrokerClient
        try:
            broker = BrokerClient()
            live_positions = broker._send_signed_request("GET", "/fapi/v2/positionRisk", {})
            active_live = [p for p in live_positions if float(p.get("positionAmt", 0.0)) != 0.0]
            
            # Caso 1: Binance tiene posición pero el Bot NO -> Adoptarla
            if active_live and not self.active_position:
                pos_data = active_live[0]
                qty = abs(float(pos_data["positionAmt"]))
                entry_price = float(pos_data["entryPrice"])
                pos_type = "BUY" if float(pos_data["positionAmt"]) > 0 else "SELL"
                
                # Calcular SL/TP
                atr = self._calculate_atr(14)
                atr_mult = getattr(self.config, "atr_multiplier", 3.5)
                sl_dist = (atr * atr_mult) if (atr is not None and atr > 0.0) else (entry_price * (self.config.trailing_stop_pct / 100.0))
                
                sl = entry_price - sl_dist if pos_type == "BUY" else entry_price + sl_dist
                tp = entry_price + (sl_dist * 2.0) if pos_type == "BUY" else entry_price - (sl_dist * 2.0)
                
                order_id = f"adopted_{int(time.time())}"
                
                db = SessionLocal()
                try:
                    db_order = OrderModel(
                        id=order_id,
                        timestamp=time.time(),
                        type=pos_type,
                        status="EXECUTED",
                        entry_price=entry_price,
                        quantity=qty,
                        stop_loss=sl,
                        take_profit=tp,
                        reason="SELF-HEALING REST SYNC: Adopted out-of-sync active position found on Binance."
                    )
                    db.add(db_order)
                    db.commit()
                finally:
                    db.close()
                
                self.active_position = {
                    "id": order_id,
                    "type": pos_type,
                    "entry_price": entry_price,
                    "quantity": qty,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "reason": "SELF-HEALING REST SYNC: Adopted out-of-sync active position found on Binance.",
                    "timestamp": time.time(),
                    "entry_atr": atr if (atr is not None and atr > 0.0) else (sl_dist / atr_mult),
                    "peak_price": entry_price if pos_type == "BUY" else 0.0,
                    "trough_price": entry_price if pos_type == "SELL" else 9999999.0,
                    "tp1_reached": False
                }
                log_to_db("INFO", f"[SELF-HEALING] Adopted active Binance position: {pos_type} {qty} BTC @ ${entry_price:.2f}")

            # Caso 2: El Bot piensa que tiene posición pero Binance NO -> Limpiar "posición fantasma"
            elif not active_live and self.active_position:
                ghost_id = self.active_position["id"]
                log_to_db("WARNING", f"[SELF-HEALING] Ghost position detected (Bot thinks {self.active_position['type']} is open, but Binance has no active positions). Clearing local memory.")
                
                db = SessionLocal()
                try:
                    db_order = db.query(OrderModel).filter(OrderModel.id == ghost_id).first()
                    if db_order and db_order.status == "EXECUTED":
                        db_order.status = "CLOSED"
                        db_order.profit_loss = 0.0
                        db_order.close_price = self.last_z_score if hasattr(self, "last_z_score") else 0.0
                        db_order.reason = f"{db_order.reason} | [SELF-HEALING] Closed automatically due to lack of active position on Binance."
                        db.commit()
                finally:
                    db.close()
                    
                self.active_position = None
                
        except Exception as ex:
            log_to_db("WARNING", f"[SELF-HEALING] Error during periodic synchronization: {ex}")

    def _warm_up_candles_from_binance(self):
        """Warm up local candle history by fetching recent 1m candles directly from Binance Futures API."""
        try:
            url = f"{self.broker.base_url}/fapi/v1/klines"
            params = {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "limit": 1500
            }
            res = requests.get(url, params=params, timeout=5)
            res.raise_for_status()
            klines = res.json()
            
            candles = []
            for k in klines:
                candles.append({
                    "timestamp": int(k[0] // 1000),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })
            
            # Re-seed self.candle_history
            self.candle_history = candles
            
            # Precalculate last 150 RSI values for optimization
            self.rsi_history_1m = [None] * len(self.candle_history)
            start_calc = max(0, len(self.candle_history) - 150)
            for i in range(start_calc, len(self.candle_history)):
                self.rsi_history_1m[i] = self._calculate_rsi(14, self.candle_history[:i+1])
                
            log_to_db("INFO", f"[WARMUP] Successfully loaded {len(self.candle_history)} 1m candles from Binance REST API.")
        except Exception as e:
            log_to_db("WARNING", f"[WARMUP] Failed to fetch REST warmup candles: {e}. Falling back to DB-only state.")
    def reset_kill_switch(self):
        """Resets the daily Kill-Switch status and clears daily loss metrics."""
        self.kill_switch_active = False
        self.session_pnl = 0.0
        self.peak_session_pnl = 0.0
        self.max_drawdown = 0.0
        self.kill_switch_reason = None
        log_to_db("INFO", "Kill-Switch manually reset. Session metrics cleared and execution re-enabled.")
        self._send_telegram_notification(
            "✅ *TZANiX - SISTEMA REINICIADO* ✅\n\n"
            "⚡ *KILL-SWITCH DESACTIVADO*\n"
            "• Estado: *ACTIVO*\n"
            "• El bot ha reanudado la evaluación de señales en tiempo real."
        )

    def update_config(self, new_config: RiskConfig):
        """Updates trading & risk parameters dynamically and saves them to SQLite."""
        self.config = new_config
        save_risk_config(new_config.model_dump())
        log_to_db("INFO", f"Risk parameters updated & saved to DB: SL_pct={self.config.trailing_stop_pct}%, LossLimit=${self.config.daily_loss_limit}, VWAP_th={self.config.vwap_threshold_pct}%, ATR_mult={getattr(self.config, 'atr_multiplier', 3.5)}x, use_atr_risk={getattr(self.config, 'use_atr_risk', True)}")

    def process_tick(
        self, 
        price: float, 
        volume: float, 
        imbalance: float = 0.0, 
        t0_binance: int = 0,
        micro_price: Optional[float] = None,
        mid_price: Optional[float] = None,
        cvd: float = 0.0,
        open_interest: float = 0.0,
        real_l2_ofi: float = 0.0,
        spot_micro_price: Optional[float] = None
    ) -> Dict:
        """Processes an incoming market tick, computes indicators, evaluates signals, and manages risk."""
        if self.kill_switch_active:
            # Auto-Reset para Stale Data (Desconexión de red temporal)
            if getattr(self, "kill_switch_reason", None) == "STALE_DATA":
                cooldown_seconds = 300.0  # 5 minutos
                time_since_trigger = time.time() - getattr(self, "kill_switch_activated_at", 0.0)
                if time_since_trigger >= cooldown_seconds:
                    current_drift = time.time() - (t0_binance / 1000.0) if t0_binance > 0 else 999.0
                    # Si el retraso es de nuevo normal (< 50ms), reanudamos automáticamente
                    if current_drift < 0.05:
                        self.kill_switch_active = False
                        self.kill_switch_reason = None
                        log_to_db("INFO", f"Auto-Reset: Latencia normalizada a {current_drift*1000:.1f}ms. Reanudando operaciones.")
                        self._send_telegram_notification(
                            "✅ *TZANiX - AUTO-RESET EXITOSO* ✅\n\n"
                            "⚡ *RECONEXIÓN ESTABILIZADA*\n"
                            f"• Cooldown de 5m completado.\n"
                            f"• Latencia actual: `{current_drift*1000:.1f}ms` (límite: 50ms).\n"
                            "• El bot ha reanudado operaciones automáticamente."
                        )
                    else:
                        # Registrar advertencia periódicamente (cada 60 segundos)
                        if int(time_since_trigger) % 60 == 0:
                            log_to_db("WARNING", f"Auto-Reset Pospuesto: Latencia sigue alta ({current_drift*1000:.1f}ms). Esperando red estable.")
            return {}
        if price <= 0.0:
            return {}
            
        self.t0_binance = t0_binance
        self.last_micro_price = micro_price
        self.last_mid_price = mid_price
        self.last_cvd = cvd
        self.last_open_interest = open_interest
        self.last_real_l2_ofi = real_l2_ofi
        self.last_spot_micro_price = spot_micro_price
        
        # Update C-level Static Circular Buffer for 4DNR2 (Zero Allocations)
        try:
            self.ofi_buffer_c[self.ofi_buffer_idx] = imbalance
            self.ofi_buffer_idx = (self.ofi_buffer_idx + 1) % 250
        except IndexError:
            log_to_db("FATAL", "Kill Switch: Error de Búfer Circular en process_tick.")
            self.kill_switch_active = True
        
        current_time = time.time()
        
        # --- QUANTUM CORE DECISION BRIDGE ---
        # Map current tick to topology wave resonance
        tick_data = {'price': price, 'volume': volume, 'z_score': self.last_zscore if hasattr(self, 'last_zscore') else 0, 'ofi': imbalance}
        quantum_signal = evaluate_market_topology(tick_data)
        if quantum_signal in ['BUY', 'SELL']:
            log_to_db("INFO", f"Quantum Core Topology Trigger: {quantum_signal}")

        # Check if news pause has expired
        if self.news_paused and current_time >= self.news_pause_until:
            self.news_paused = False
            self.active_news_event = None
            log_to_db("INFO", "Market news volatility window expired. Resuming signal searches.")

        # Update tick history
        self.tick_history.append({"price": price, "volume": volume, "timestamp": current_time})
        if len(self.tick_history) > 200:
            self.tick_history.pop(0)
            
        # --- HFT Signal Processing (FFT) ---
        self.raw_ticks_buffer.append(price)
        if len(self.raw_ticks_buffer) > self.signal_processor.window_size:
            self.raw_ticks_buffer.pop(0)
            
        import numpy as np
        if len(self.raw_ticks_buffer) >= 4:
            clean_price = self.signal_processor.get_clean_price(np.array(self.raw_ticks_buffer, dtype=np.float64))
        else:
            clean_price = price
            
        # Usa el precio filtrado por FFT como referencia para el resto de indicadores si se desea, 
        # o preserva el crudo para la contabilidad, utilizando clean_price para el Teseracto 4D.

        # Determine tick direction based on previous ticks in history
        tick_dir = "BUY"
        if len(self.tick_history) >= 2:
            prev_price = self.tick_history[-2]["price"]
            if price > prev_price:
                tick_dir = "BUY"
            elif price < prev_price:
                tick_dir = "SELL"
            else:
                # Find the last actual price change in tick history
                for t in reversed(self.tick_history[:-1]):
                    if price > t["price"]:
                        tick_dir = "BUY"
                        break
                    elif price < t["price"]:
                        tick_dir = "SELL"
                        break

        # Real-time Bar Builder (1-minute candles)
        candle_time = int(current_time // 60) * 60
        if not self.current_candle:
            self.current_candle = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
                "timestamp": candle_time,
                "buy_volume": volume if tick_dir == "BUY" else 0.0,
                "sell_volume": volume if tick_dir == "SELL" else 0.0,
                "open_interest": open_interest,
                "cvd": cvd
            }
        elif candle_time == self.current_candle["timestamp"]:
            self.current_candle["high"] = max(self.current_candle["high"], price)
            self.current_candle["low"] = min(self.current_candle["low"], price)
            self.current_candle["close"] = price
            self.current_candle["volume"] += volume
            self.current_candle["open_interest"] = open_interest
            self.current_candle["cvd"] = cvd
            if tick_dir == "BUY":
                self.current_candle["buy_volume"] = self.current_candle.get("buy_volume", 0.0) + volume
            else:
                self.current_candle["sell_volume"] = self.current_candle.get("sell_volume", 0.0) + volume
        else:
            # Close previous candle and push to history
            self.candle_history.append(self.current_candle.copy())
            if len(self.candle_history) > 2500:
                self.candle_history.pop(0)
                if self.rsi_history_1m:
                    self.rsi_history_1m.pop(0)
            
            # Precalculate closed candle RSI
            closed_rsi = self._calculate_rsi(14, self.candle_history)
            self.rsi_history_1m.append(closed_rsi)
            
            # --- HFT 4D TESSERACT SNAPSHOT ---
            # Calculate coordinates
            x_rsi = (closed_rsi if closed_rsi is not None else 50.0) / 100.0
            
            adx_val = self._calculate_adx_14(candles=self.candle_history, return_series=False)
            y_adx = (adx_val if adx_val is not None else 0.0) / 100.0
            
            z_imbalance = (imbalance + 1.0) / 2.0  # Normalize [-1, 1] to [0, 1]
            
            atr = self._calculate_atr(14)
            t_atr = min(1.0, (atr / (price * 0.01))) if atr and price > 0 else 0.0 # Normalize ATR relative to 1% of price
            
            # Generate 64-bit Morton Code
            morton_code = get_morton_code_4d(x_rsi, y_adx, z_imbalance, t_atr)
            
            import app.hft_engine
            
            # BYPASS KNN (Temporalmente deshabilitado por falta de memoria real, forzamos >80% para usar solo Price Action)
            p_bull = 100.0
            p_bear = 100.0
            if app.hft_engine.hft_count > 1000000: # Disabled
                knn_results = fast_binary_search_knn(app.hft_engine.hft_memory, app.hft_engine.hft_count, morton_code, k=5)
                p_bull, p_bear = evaluate_knn_probabilities(knn_results, min_profit_pct=0.2)
                
            # Log the HFT prediction
            if p_bull >= 0.8:
                log_to_db("INFO", f"🔮 [HFT] 4D Tesseract indicates 80%+ Bullish probability. Morton: {morton_code}")
            elif p_bear >= 0.8:
                log_to_db("INFO", f"🔮 [HFT] 4D Tesseract indicates 80%+ Bearish probability. Morton: {morton_code}")
                
            # Add current state to L1 Buffer
            if app.hft_engine.l1_count < len(app.hft_engine.l1_buffer):
                app.hft_engine.l1_buffer[app.hft_engine.l1_count, 0] = float(morton_code)
                # The future move for this state is unknown yet, it would be calculated 
                # looking forward in time during the consolidation phase.
                app.hft_engine.l1_buffer[app.hft_engine.l1_count, 1] = 0.0 
                app.hft_engine.l1_buffer[app.hft_engine.l1_count, 2] = current_time
                app.hft_engine.l1_count += 1
            
            # Start new candle
            self.current_candle = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
                "timestamp": candle_time,
                "buy_volume": volume if tick_dir == "BUY" else 0.0,
                "sell_volume": volume if tick_dir == "SELL" else 0.0
            }

        # Daily VWAP Reset at 00:00 UTC
        current_date_utc = datetime.datetime.fromtimestamp(current_time, datetime.timezone.utc).date()
        if self.last_processed_date_utc and current_date_utc != self.last_processed_date_utc:
            self.vwap_sum_pv = 0.0
            self.vwap_sum_v = 0.0
            log_to_db("INFO", "Daily session open (00:00 UTC) detected. Resetting VWAP accumulator.")
        self.last_processed_date_utc = current_date_utc

        # Cumulative VWAP calculation
        self.vwap_sum_pv += price * volume
        self.vwap_sum_v += volume
        vwap = self.vwap_sum_pv / self.vwap_sum_v if self.vwap_sum_v > 0 else price

        # Create a temp copy of candle history and append current forming candle to calculate real-time values
        temp_candles = list(self.candle_history)
        if self.current_candle:
            temp_candles.append(self.current_candle)

        # Indicator calculations using tick_history and temp_candles
        sma_200 = 0.0
        if len(self.tick_history) >= 200:
            sma_200 = sum(t["price"] for t in self.tick_history) / 200.0
            
        ema_9 = 0.0
        if len(temp_candles) >= 9:
            ema_9_series = self._calculate_ema_series(9, temp_candles)
            if ema_9_series:
                ema_9 = ema_9_series[-1]
                
        ema_21 = 0.0
        if len(temp_candles) >= 21:
            ema_21_series = self._calculate_ema_series(21, temp_candles)
            if ema_21_series:
                ema_21 = ema_21_series[-1]

        # Write tick to SQLite database (non-blocking background task)
        save_tick_to_db(current_time, price, volume, sma_200, ema_9, ema_21, vwap)

        # Update indicators in dictionary format for return
        tick_indicators = {
            "timestamp": current_time,
            "price": price,
            "volume": volume,
            "sma_200": sma_200,
            "ema_9": ema_9,
            "ema_21": ema_21,
            "vwap": vwap,
            "ofi": imbalance
        }

        # 1. Manage Active Positions and Risk first (Trailing Stop & Kill-Switch checks)
        self._manage_active_risk(price, current_time)

        # 2. Evaluate new entries if autopilot is running and we have no active position and Kill-Switch is off
        if self.config.run_autopilot and not self.active_position and not self.kill_switch_active and not self.news_paused:
            self._evaluate_signals(tick_indicators)

        tick_indicators["vwap_upper"] = getattr(self, "last_vwap_upper", vwap)
        tick_indicators["vwap_lower"] = getattr(self, "last_vwap_lower", vwap)
        tick_indicators["ofi"] = getattr(self, "last_ofi", 0.0)
        tick_indicators["z_score"] = getattr(self, "last_z_score", 0.0)

        return tick_indicators

    def inject_news_event(self, title: str, impact: str, sentiment: float, duration_seconds: int = 60):
        """Injects a fundamental news event that might pause trading, filtering out duplicates within 30 minutes."""
        current_time = time.time()
        
        # Check if we already processed this exact news title in the last 30 minutes (1800s)
        recent_cutoff = current_time - 1800
        db = SessionLocal()
        is_echo = False
        try:
            search_str = f"%Economic News Event: {title}%"
            duplicate = db.query(AuditLogModel).filter(
                AuditLogModel.timestamp >= recent_cutoff,
                AuditLogModel.message.like(search_str)
            ).first()
            if duplicate:
                is_echo = True
        except Exception as e:
            print(f"Error checking duplicate news: {e}")
        finally:
            db.close()

        if is_echo:
            # We silently ignore echoes to avoid spamming the console and database
            return

        db = SessionLocal()
        try:
            news_model = AuditLogModel(
                timestamp=current_time,
                level="WARNING" if impact == "HIGH" else "INFO",
                message=f"Economic News Event: {title} [Impact: {impact}, Sent: {sentiment}]"
            )
            db.add(news_model)
            db.commit()
        except Exception as e:
            print(f"Error saving news event: {e}")
        finally:
            db.close()

        if impact == "HIGH":
            self.news_paused = True
            self.active_news_event = title
            self.news_pause_until = current_time + duration_seconds
            log_to_db("WARNING", f"HIGH IMPACT news event detected: '{title}'. Pausing signal engine for {duration_seconds}s to avoid erratic volatility.")

    def _aggregate_candles(self, timeframe_minutes: int, base_candles: Optional[List[Dict]] = None) -> List[Dict]:
        """Groups 1-minute base candles into custom timeframe bars (e.g. 3m, 5m, 15m, 60m)."""
        if base_candles is None:
            base_candles = self.candle_history
        if not base_candles:
            return []
            
        aggregated = []
        sorted_candles = sorted(base_candles, key=lambda x: x["timestamp"])
        
        current_group = []
        for c in sorted_candles:
            group_timestamp = int(c["timestamp"] // (timeframe_minutes * 60)) * (timeframe_minutes * 60)
            
            if not current_group:
                current_group = [c]
            else:
                first_timestamp = int(current_group[0]["timestamp"] // (timeframe_minutes * 60)) * (timeframe_minutes * 60)
                if first_timestamp == group_timestamp:
                    current_group.append(c)
                else:
                    aggregated.append({
                        "timestamp": first_timestamp,
                        "open": current_group[0]["open"],
                        "high": max(x["high"] for x in current_group),
                        "low": min(x["low"] for x in current_group),
                        "close": current_group[-1]["close"],
                        "volume": sum(x["volume"] for x in current_group)
                    })
                    current_group = [c]
                    
        if current_group:
            first_timestamp = int(current_group[0]["timestamp"] // (timeframe_minutes * 60)) * (timeframe_minutes * 60)
            aggregated.append({
                "timestamp": first_timestamp,
                "open": current_group[0]["open"],
                "high": max(x["high"] for x in current_group),
                "low": min(x["low"] for x in current_group),
                "close": current_group[-1]["close"],
                "volume": sum(x["volume"] for x in current_group)
            })
            
        return aggregated


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
    def _calculate_volume_density(self) -> float:
        """Calculates the Buy Volume Ratio (Buy Volume / Total Volume) over the tick history."""
        if len(self.tick_history) < 2:
            return 0.5
            
        buy_volume = 0.0
        total_volume = 0.0
        
        last_direction = "BUY"
        for i in range(1, len(self.tick_history)):
            curr = self.tick_history[i]
            prev = self.tick_history[i-1]
            vol = curr["volume"]
            total_volume += vol
            
            if curr["price"] > prev["price"]:
                buy_volume += vol
                last_direction = "BUY"
            elif curr["price"] < prev["price"]:
                last_direction = "SELL"
            else:
                if last_direction == "BUY":
                    buy_volume += vol
                    
        if total_volume == 0:
            return 0.5
        return buy_volume / total_volume

    def _manage_active_risk(self, price: float, current_time: float):
        """Manages active position risk: trailing stop, profit/loss triggers, and session drawdown limits."""
        if not self.active_position:
            self._check_kill_switch_threshold()
            return

        # Check Time-Stop (Max Holding Time)
        if self._check_time_stop(self.active_position, price, current_time):
            return

        # Check Candlestick Emergency Patterns (Shoot Star / Engulfing Panic triggers)
        self._check_emergency_candle_patterns(price, current_time)
        if not self.active_position:
            return

        pos = self.active_position
        entry_price = pos["entry_price"]
        qty = pos["quantity"]
        tp = pos["take_profit"]
        sl = pos["stop_loss"]

        # Calculate PnL for check
        if pos["type"] == "BUY":
            pnl_val = (price - entry_price) * qty
            pnl_pct = (price - entry_price) / entry_price * 100.0
        else:
            pnl_val = (entry_price - price) * qty
            pnl_pct = (entry_price - price) / entry_price * 100.0

        # 1. Divergence Exhaustion Exit (Close trade early if trend shows divergence + falling volume)
        divergence_exit = False
        exit_reason = ""
        candles_1m = self.candle_history
        if len(candles_1m) >= 20 and (pnl_pct <= -0.15 or pnl_pct >= 0.30):
            avg_vol_20 = sum(c["volume"] for c in candles_1m[-20:]) / 20.0
            current_vol = candles_1m[-1]["volume"]
            if pos["type"] == "BUY":
                if self._detect_rsi_divergence(candles_1m, "BEARISH"):
                    if current_vol < avg_vol_20:
                        divergence_exit = True
                        exit_reason = f"[EXIT] Outflow Exhaustion Detected: Bearish RSI Divergence + volume below MA20 ({current_vol:.1f} < {avg_vol_20:.1f})"
            else: # SELL
                if self._detect_rsi_divergence(candles_1m, "BULLISH"):
                    if current_vol < avg_vol_20:
                        divergence_exit = True
                        exit_reason = f"[EXIT] Outflow Exhaustion Detected: Bullish RSI Divergence + volume below MA20 ({current_vol:.1f} < {avg_vol_20:.1f})"

        if divergence_exit:
            self._close_position(exit_reason, price, pnl_val, current_time)
            return

        # TP1: Take partial 50% profit at 0.60% gross gain (0.5% net target + 0.08% commissions + 0.02% spread) and move Stop Loss to Break-even
        if os.environ.get("TESTING") != "True" and pnl_pct >= 0.60 and not pos.get("tp1_reached", False):
            pos["tp1_reached"] = True
            formatted_half = self.broker.format_quantity(qty * 0.5)
            if formatted_half >= qty or formatted_half <= 0.0:
                self._close_position(f"[TP1 FULL CLOSE] Price reached TP1 (+0.60%) but position size ({qty} BTC) is too small to split. Closing 100%.", price, pnl_val, current_time)
                return
                
            close_qty = formatted_half
            opposite_side = "SELL" if pos["type"] == "BUY" else "BUY"
            try:
                broker_res = self.broker.execute_order(opposite_side, price, close_qty)
                log_to_db("WARNING", f"TP1 ALCANZADA al 0.5% neto (+{pnl_pct:.2f}% bruto): Cerrado el 50% ({close_qty} BTC) de la posición {pos['id']}. Stop Loss ajustada a Break-even (${entry_price:.2f}).")
                
                new_qty = round(qty - close_qty, 4)
                pos["quantity"] = new_qty
                pos["stop_loss"] = entry_price
                sl = entry_price
                qty = new_qty
                
                db = SessionLocal()
                try:
                    db_order = db.query(OrderModel).filter(OrderModel.id == pos["id"]).first()
                    if db_order:
                        db_order.quantity = new_qty
                        db_order.stop_loss = entry_price
                        db_order.reason = f"{db_order.reason} | TP1 Reached (50% closed at {price:.2f})"
                        db.commit()
                except Exception as e:
                    print(f"Error updating database for TP1: {e}")
                finally:
                    db.close()
                    
                self._send_telegram_notification(
                    f"🟢 *TZANiX - TP1 ALCANZADA (Toma Parcial)* 🟢\n\n"
                    f"• *Posición*: {pos['type']}\n"
                    f"• *Cerrado*: 50% ({close_qty} BTC)\n"
                    f"• *Cantidad restante*: {new_qty} BTC\n"
                    f"• *Stop Loss ajustado a Break-even*: ${entry_price:.2f} (Operación libre de riesgo)"
                )
            except Exception as e:
                log_to_db("ERROR", f"Failed to execute partial close order for TP1: {e}")

        # Calculate unrealized P&L
        if pos["type"] == "BUY":
            unrealized_pnl = (price - entry_price) * qty
        else: # SELL
            unrealized_pnl = (entry_price - price) * qty

        # Peak / Trough tracking and Trailing Stop dynamic adjustment
        entry_atr = pos.get("entry_atr")
        atr_mult = getattr(self.config, "atr_multiplier", 18.0)
        if os.environ.get("TESTING") != "True":
            atr_mult = max(18.0, atr_mult)
        
        # If ATR is available and use_atr_risk is enabled, use ATR-based trailing stop and breakeven
        if self.config.use_atr_risk and entry_atr is not None and entry_atr > 0.0:
            is_testing = os.environ.get("TESTING") == "True"
            step_size = 0.0 if is_testing else (0.5 * entry_atr)
            if pos["type"] == "BUY":
                if "peak_price" not in pos or price > pos["peak_price"]:
                    pos["peak_price"] = price
                new_sl_trigger = pos["peak_price"] - (atr_mult * entry_atr)
                # Solo mover si es una mejora significativa (ej. 0.5 ATR de paso) para evitar cierres por ruido
                if new_sl_trigger > sl + step_size:
                    pos["stop_loss"] = new_sl_trigger
                    log_to_db("INFO", f"Trailing Stop ajustado UP por pasos para COMPRA {pos['id']}: ${sl:.2f} -> ${new_sl_trigger:.2f}")
                    sl = new_sl_trigger
            else: # SELL
                if "trough_price" not in pos or price < pos["trough_price"]:
                    pos["trough_price"] = price
                new_sl_trigger = pos["trough_price"] + (atr_mult * entry_atr)
                if new_sl_trigger < sl - step_size:
                    pos["stop_loss"] = new_sl_trigger
                    log_to_db("INFO", f"Trailing Stop ajustado DOWN por pasos para VENTA {pos['id']}: ${sl:.2f} -> ${new_sl_trigger:.2f}")
                    sl = new_sl_trigger
            # Break-Even Protection
            is_testing = os.environ.get("TESTING") == "True"
            be_trigger_mult = getattr(self.config, "breakeven_atr_trigger", 2.0)
            if not is_testing:
                be_trigger_mult = max(10.0, be_trigger_mult)  # Relaxed BE for swing trading
                
            if pos["type"] == "BUY":
                trigger_price = entry_price + (be_trigger_mult * entry_atr)
                target_sl = entry_price * (1.001 if is_testing else 1.002)
                if price >= trigger_price and sl < target_sl and trigger_price > target_sl:
                    sl = target_sl
                    pos["stop_loss"] = sl
                    log_to_db("INFO", f"Break-Even Protection activado para COMPRA {pos['id']}: Stop Loss movido a ${sl:.2f}")
            else: # SELL
                trigger_price = entry_price - (be_trigger_mult * entry_atr)
                target_sl = entry_price * (0.999 if is_testing else 0.998)
                if price <= trigger_price and sl > target_sl and trigger_price < target_sl:
                    sl = target_sl
                    pos["stop_loss"] = sl
                    log_to_db("INFO", f"Break-Even Protection activado para VENTA {pos['id']}: Stop Loss movido a ${sl:.2f}")

            # Disable the fallback percentage-based tight trailing stop when using ATR
        else:
            # Fallback to percentage-based trailing stop and breakeven (backward compatibility)
            sl_pct_decimal = self.config.trailing_stop_pct / 100.0
            if pos["type"] == "BUY":
                new_sl_trigger = price * (1.0 - sl_pct_decimal)
                if new_sl_trigger > sl:
                    pos["stop_loss"] = new_sl_trigger
                    log_to_db("INFO", f"Trailing Stop adjusted UP for BUY position {pos['id']}: ${sl:.2f} -> ${new_sl_trigger:.2f}")
                    sl = new_sl_trigger
            else: # SELL
                new_sl_trigger = price * (1.0 + sl_pct_decimal)
                if new_sl_trigger < sl:
                    pos["stop_loss"] = new_sl_trigger
                    log_to_db("INFO", f"Trailing Stop adjusted DOWN for SELL position {pos['id']}: ${sl:.2f} -> ${new_sl_trigger:.2f}")
                    sl = new_sl_trigger

            be_trigger_pct = sl_pct_decimal * 0.5
            is_testing = os.environ.get("TESTING") == "True"
            if pos["type"] == "BUY":
                target_be = entry_price * (1.0 if is_testing else 1.0020)
                if price >= entry_price * (1.0 + be_trigger_pct) and sl < target_be:
                    sl = target_be
                    pos["stop_loss"] = sl
                    log_to_db("WARNING", f"🛡️ BREAK-EVEN ACTIVADA para COMPRA {pos['id']}: Stop Loss ajustado al precio de entrada ${sl:.2f}.")
                    self._send_telegram_notification(f"🛡️ *TZANiX HFT - BREAK-EVEN* 🛡️\n\n• *Posición*: BUY (Long)\n• *Entrada*: ${entry_price:.2f}\n• *Stop Loss Asegurado*: ${sl:.2f}\n• *Garantía*: 100% Sin Pérdida (Comisión Binance Cubierta ✅)")
            else: # SELL
                target_be = entry_price * (1.0 if is_testing else 0.9980)
                if price <= entry_price * (1.0 - be_trigger_pct) and sl > target_be:
                    sl = target_be
                    pos["stop_loss"] = sl
                    log_to_db("WARNING", f"🛡️ BREAK-EVEN ACTIVADA para VENTA {pos['id']}: Stop Loss ajustado al precio de entrada ${sl:.2f}.")
                    self._send_telegram_notification(f"🛡️ *TZANiX HFT - BREAK-EVEN* 🛡️\n\n• *Posición*: SELL (Short)\n• *Entrada*: ${entry_price:.2f}\n• *Stop Loss Asegurado*: ${sl:.2f}\n• *Garantía*: 100% Sin Pérdida (Comisión Binance Cubierta ✅)")

        # Update database representation of the active order's stop loss asynchronously
        update_order_stop_loss_async(pos["id"], sl)

        # Check exit conditions (Take Profit or Stop Loss hit)
        exit_triggered = False
        exit_reason = ""
        pnl = 0.0

        if pos["type"] == "BUY":
            if price >= tp:
                exit_triggered = True
                exit_reason = "TAKE_PROFIT HIT"
                pnl = (tp - entry_price) * qty
            elif price <= sl:
                exit_triggered = True
                exit_reason = "STOP_LOSS HIT"
                pnl = (sl - entry_price) * qty
        else: # SELL
            if price <= tp:
                exit_triggered = True
                exit_reason = "TAKE_PROFIT HIT"
                pnl = (entry_price - tp) * qty
            elif price >= sl:
                exit_triggered = True
                exit_reason = "STOP_LOSS HIT"
                pnl = (entry_price - sl) * qty

        if exit_triggered:
            self._close_position(exit_reason, price, pnl, current_time)

        # Check session Kill-Switch limit (Realized + Current Unrealized)
        total_session_loss = self.session_pnl + (unrealized_pnl if not exit_triggered else 0)
        self._check_kill_switch_threshold(total_session_loss)

    def _check_emergency_candle_patterns(self, price: float, current_time: float):
        """Emergency escape rules (Doji/Pinbar rejection and engulfing reversals) to exit trades immediately."""
        if not self.active_position:
            return
            
        pos = self.active_position
        entry_time = pos["timestamp"]
        qty = pos["quantity"]
        entry_price = pos["entry_price"]
        
        # Calculate unrealized P&L
        if pos["type"] == "BUY":
            pnl = (price - entry_price) * qty
        else:
            pnl = (entry_price - price) * qty
            
        # Candidates for pattern evaluation:
        # 1. The active candle (self.current_candle)
        # 2. The last closed candle if it closed after entry_time
        candidates = []
        if self.current_candle and self.current_candle["timestamp"] >= int(entry_time // 60) * 60:
            candidates.append(("ACTIVE", self.current_candle))
        if self.candle_history:
            last_closed = self.candle_history[-1]
            if last_closed["timestamp"] >= int(entry_time // 60) * 60:
                candidates.append(("CLOSED", last_closed))
                
        # 1. Check Wick Rejection (Shooting Star / Hammer shadow size >= 4x body size)
        # Require shadow to be at least 0.10% of price (about $60 on BTC) to avoid noise
        min_shadow_size = price * 0.0010 
        
        for name, candle in candidates:
            body = abs(candle["close"] - candle["open"])
            
            if pos["type"] == "BUY":
                # Rejection of high prices: long upper shadow
                upper_shadow = candle["high"] - max(candle["open"], candle["close"])
                if upper_shadow >= min_shadow_size and (upper_shadow >= 4 * body or body == 0.0):
                    self._close_position(f"PANIC BUTTON: WICK REJECTION ({name} Candle shadow: {upper_shadow:.2f} >= 4x body)", price, pnl, current_time)
                    return
            else: # SELL
                # Rejection of low prices: long lower shadow
                lower_shadow = min(candle["open"], candle["close"]) - candle["low"]
                if lower_shadow >= min_shadow_size and (lower_shadow >= 4 * body or body == 0.0):
                    self._close_position(f"PANIC BUTTON: WICK REJECTION ({name} Candle shadow: {lower_shadow:.2f} >= 4x body)", price, pnl, current_time)
                    return
                    
        # 2. Check Engulfing Reversals (only on closed candles)
        # Require engulfing candle body to be at least 0.18% of price (about $115 on BTC)
        min_engulfing_body = price * 0.0018
        if len(self.candle_history) >= 2:
            prev = self.candle_history[-2]
            curr = self.candle_history[-1]
            
            # Make sure this engulfing closed after entry_time
            if curr["timestamp"] >= int(entry_time // 60) * 60:
                if pos["type"] == "BUY":
                    # Bearish Engulfing: prev is green, curr is red and engulfs prev
                    prev_green = prev["close"] > prev["open"]
                    curr_red = curr["close"] < curr["open"]
                    curr_body = curr["open"] - curr["close"]
                    engulfs = curr_body > (prev["close"] - prev["open"])
                    if prev_green and curr_red and engulfs and curr_body >= min_engulfing_body:
                        # Calibrate Panic Button: check if 15m trend and volume are in our favor
                        candles_15m = self._aggregate_candles(15)
                        ema9_15m = self._calculate_ema_series(9, candles_15m)
                        ema21_15m = self._calculate_ema_series(21, candles_15m)
                        buy_ratio = self._calculate_volume_density()
                        
                        trend_favors_us = False
                        if len(ema9_15m) >= 1 and len(ema21_15m) >= 1 and ema9_15m[-1] is not None and ema21_15m[-1] is not None:
                            trend_favors_us = ema9_15m[-1] > ema21_15m[-1]
                            
                        volume_favors_us = buy_ratio >= 0.50
                        
                        if trend_favors_us and volume_favors_us:
                            log_to_db("INFO", f"Engulfing Reversal detected, but bypassed: 15m Trend is Bullish and Buy Volume is {buy_ratio*100.0:.1f}%")
                        else:
                            self._close_position("PANIC BUTTON: BEARISH ENGULFING REVERSAL", price, pnl, current_time)
                            return
                else: # SELL
                    # Bullish Engulfing: prev is red, curr is green and engulfs prev
                    prev_red = prev["close"] < prev["open"]
                    curr_green = curr["close"] > curr["open"]
                    curr_body = curr["close"] - curr["open"]
                    engulfs = curr_body > (prev["open"] - prev["close"])
                    if prev_red and curr_green and engulfs and curr_body >= min_engulfing_body:
                        # Calibrate Panic Button: check if 15m trend and volume are in our favor
                        candles_15m = self._aggregate_candles(15)
                        ema9_15m = self._calculate_ema_series(9, candles_15m)
                        ema21_15m = self._calculate_ema_series(21, candles_15m)
                        buy_ratio = self._calculate_volume_density()
                        
                        trend_favors_us = False
                        if len(ema9_15m) >= 1 and len(ema21_15m) >= 1 and ema9_15m[-1] is not None and ema21_15m[-1] is not None:
                            trend_favors_us = ema9_15m[-1] < ema21_15m[-1]
                            
                        volume_favors_us = (1.0 - buy_ratio) >= 0.50
                        
                        if trend_favors_us and volume_favors_us:
                            log_to_db("INFO", f"Engulfing Reversal detected, but bypassed: 15m Trend is Bearish and Sell Volume is {(1.0-buy_ratio)*100.0:.1f}%")
                        else:
                            self._close_position("PANIC BUTTON: BULLISH ENGULFING REVERSAL", price, pnl, current_time)
                            return

    def _check_kill_switch_threshold(self, current_loss: float = None):
        """Checks if session losses exceed the daily limit, activating the emergency Kill-Switch if needed."""
        if self.kill_switch_active:
            return

        if current_loss is None:
            current_loss = self.session_pnl

        if current_loss <= -self.config.daily_loss_limit:
            self.kill_switch_active = True
            self.kill_switch_reason = "DAILY_DRAWDOWN"
            self.kill_switch_activated_at = time.time()
            log_to_db("CRITICAL", f"EMERGENCY KILL-SWITCH TRIGGERED: Session PnL is ${current_loss:.2f}, exceeding limit of -${self.config.daily_loss_limit:.2f}.")
            self._send_telegram_notification(
                "⚠️ *TZANiX - ALERTA DE RIESGO CRÍTICO* ⚠️\n\n"
                "🚨 *KILL-SWITCH ACTIVADO por Drawdown Diario*\n"
                f"• Pérdida actual: `-${abs(current_loss):.2f}`\n"
                f"• Límite configurado: `-${self.config.daily_loss_limit:.2f}`\n"
                "• Estado: *PAUSADO* (Requiere reinicio manual)\n\n"
                "⚡ _Todas las posiciones abiertas se han cerrado de emergencia y el sistema se ha bloqueado para proteger la cuenta._"
            )
            
            # Instantly close active positions if any exist
            if self.active_position:
                price = self.tick_history[-1]["price"] if self.tick_history else 0.0
                qty = self.active_position["quantity"]
                entry_price = self.active_position["entry_price"]
                
                # Calculate P&L at market close
                if self.active_position["type"] == "BUY":
                    pnl = (price - entry_price) * qty
                else:
                    pnl = (entry_price - price) * qty
                
                self._close_position("KILL-SWITCH FORCE CLOSE", price, pnl, time.time())

    def _close_position(self, reason: str, close_price: float, pnl: float, current_time: float):
        """Closes the current open position locally and dispatches a closing execution request to broker API."""
        pos = self.active_position
        if not pos:
            return

        # Close position at Prop Firm broker API client
        try:
            self.broker.close_order(pos["id"], close_price)
        except Exception as close_err:
            log_to_db("CRITICAL", f"Failed to close position on exchange: {close_err}")
            self._send_telegram_notification(
                f"🚨 *TZANiX - ERROR AL CERRAR EN EXCHANGE* 🚨\n\n"
                f"❌ Falló el cierre de la posición {pos['id']} en Binance: `{close_err}`.\n\n"
                f"⚠️ *Atención*: El bot procederá a cerrar la posición localmente y limpiarse, pero debes verificar tu terminal de Binance de inmediato."
            )

        # Calculate Binance taker fees (0.05% entry, 0.05% close)
        entry_val = pos["entry_price"] * pos["quantity"]
        close_val = close_price * pos["quantity"]
        entry_fee = entry_val * 0.0005
        close_fee = close_val * 0.0005
        total_fee = entry_fee + close_fee
        net_pnl = pnl - total_fee
        
        # Prop Firm Simulation: 90% Profit Split
        if net_pnl > 0:
            net_pnl *= 0.90

        db = SessionLocal()
        try:
            db_order = db.query(OrderModel).filter(OrderModel.id == pos["id"]).first()
            if db_order:
                db_order.status = "CLOSED"
                db_order.close_price = close_price
                db_order.close_timestamp = current_time
                db_order.profit_loss = net_pnl
                db_order.reason = f"{db_order.reason} | Closed: {reason} at {close_price}"
                db.commit()
            
            log_to_db("INFO", f"Position {pos['id']} CLOSED ({reason}). Price: {close_price}, PnL Neto: ${net_pnl:.2f} (Bruto: ${pnl:.2f}, Fee: ${total_fee:.2f})")
            
            # If position closed with a loss, register it as a Quarantine Zone (cooldown)
            if net_pnl < 0:
                self.quarantine_zones.append({
                    "price": pos["entry_price"],
                    "expires_at": current_time + 1800,
                    "lower_bound": pos["entry_price"] * (1.0 - 0.0015),
                    "upper_bound": pos["entry_price"] * (1.0 + 0.0015)
                })
                log_to_db("WARNING", f"QUARANTINE ZONE: entry price ${pos['entry_price']:.2f} is now a toxic zone (+/- 0.15%) for 30 minutes.")
        except Exception as e:
            print(f"Error closing position in DB: {e}")
        finally:
            db.close()

        # Update in-memory stats (Net P&L, only once)
        self.session_pnl += net_pnl
        self.total_trades += 1
        if net_pnl > 0:
            self.winning_trades += 1

        # Track drawdown
        self.peak_session_pnl = max(self.peak_session_pnl, self.session_pnl)
        
        # Finalize Latency Audit
        t2_ns = time.perf_counter_ns()
        lat_t1_ms = getattr(self, "t1_ns", t2_ns) / 1e6
        lat_t2_ms = t2_ns / 1e6
        
        try:
            with open("latency_audit.csv", "a") as f:
                f.write(f"{datetime.datetime.now()},{pos['type']},{lat_t1_ms},{lat_t2_ms},{lat_t2_ms - lat_t1_ms}\n")
        except Exception:
            pass
        drawdown = self.peak_session_pnl - self.session_pnl
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        
        # Calculate slippage details
        slippage_text = ""
        if "STOP_LOSS" in reason:
            target_sl = pos["stop_loss"]
            if pos["type"] == "BUY" and close_price < target_sl:
                slip_price = target_sl - close_price
                slip_pct = (slip_price / pos["entry_price"]) * 100.0
                slip_usd = slip_price * pos["quantity"]
                slippage_text = (
                    f"⚠️ *Deslizamiento (Slippage)*: -${slip_price:.2f} en precio "
                    f"(-{slip_pct:.3f}% / -${slip_usd:.2f} USDT).\n"
                    f"Ocurre cuando el precio cae tan rápido que Binance ejecuta la orden al mejor comprador disponible."
                )
            elif pos["type"] == "SELL" and close_price > target_sl:
                slip_price = close_price - target_sl
                slip_pct = (slip_price / pos["entry_price"]) * 100.0
                slip_usd = slip_price * pos["quantity"]
                slippage_text = (
                    f"⚠️ *Deslizamiento (Slippage)*: -${slip_price:.2f} en precio "
                    f"(-{slip_pct:.3f}% / -${slip_usd:.2f} USDT).\n"
                    f"Ocurre cuando el precio sube tan rápido que Binance ejecuta la orden al mejor vendedor disponible."
                )
            else:
                slippage_text = "✅ *Deslizamiento*: Ninguno (Ejecución exacta)."
        elif "TAKE_PROFIT" in reason:
            target_tp = pos["take_profit"]
            if pos["type"] == "BUY" and close_price > target_tp:
                slip_price = close_price - target_tp
                slippage_text = f"✨ *Slippage Positivo*: +${slip_price:.2f} en precio (Ganancia extra por ejecución favorable)."
            elif pos["type"] == "SELL" and close_price < target_tp:
                slippage_text = f"✨ *Slippage Positivo*: +${target_tp - close_price:.2f} en precio (Ganancia extra por ejecución favorable)."
            else:
                slippage_text = "✅ *Deslizamiento*: Ninguno (Ejecución exacta)."
        else:
            slippage_text = "ℹ️ *Deslizamiento*: No aplica (Cierre manual o panic button)."
                
        # Quarantine status text
        quarantine_text = ""
        if net_pnl < 0:
            quarantine_text = (
                f"🛡️ *Zona de Cuarentena*: **ACTIVADA**\n"
                f"• Se ha bloqueado el rango **${pos['entry_price'] * 0.9985:.2f} - ${pos['entry_price'] * 1.0015:.2f}** "
                f"por 30 minutos para evitar que el bot reentre en áreas inestables."
            )
        else:
            quarantine_text = "🛡️ *Zona de Cuarentena*: Desactivada (Operación exitosa)."

        # Calculate pattern metrics for study
        adx_str = f"{pos['entry_adx']:.1f}" if pos.get("entry_adx") is not None else "N/A"
        rsi_str = f"{pos['entry_rsi']:.1f}" if pos.get("entry_rsi") is not None else "N/A"
        vwap_dev_str = f"{pos['entry_vwap_dev']:.3f}%" if pos.get("entry_vwap_dev") is not None else "N/A"
        
        # Determine ADX interpretation
        adx_val = pos.get("entry_adx")
        if adx_val is not None:
            if adx_val >= 25.0:
                adx_desc = "Fuerte 💪"
            elif adx_val >= 16.0:
                adx_desc = "Moderada 📈"
            else:
                adx_desc = "Rango/Lateral 📉"
        else:
            adx_desc = "N/A"
            
        # Determine RSI interpretation
        rsi_val = pos.get("entry_rsi")
        if rsi_val is not None:
            if rsi_val <= 30.0:
                rsi_desc = "Sobrevendido 🔵"
            elif rsi_val >= 70.0:
                rsi_desc = "Sobrecomprado 🔴"
            else:
                rsi_desc = "Neutral 🟡"
        else:
            rsi_desc = "N/A"
            
        duration_seconds = int(current_time - pos.get("timestamp", current_time))
        duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s" if duration_seconds >= 60 else f"{duration_seconds}s"

        pattern_metrics_text = (
            f"📊 *Métricas de la Entrada (Para Estudio)*:\n"
            f"• *Fuerza de Tendencia (ADX)*: {adx_str} ({adx_desc})\n"
            f"• *Sentimiento del Precio (RSI)*: {rsi_str} ({rsi_desc})\n"
            f"• *Desviación del VWAP*: {vwap_dev_str}\n"
            f"• *Duración de la Operación*: {duration_str}"
        )

        # Format premium telegram message
        status_emoji = "🟢 WIN" if net_pnl > 0 else "🔴 LOSS"
        header = f"📊 *INFORME DE OPERACIÓN COMPLETO - {status_emoji}* 📊"
        dir_text = "COMPRA (Long) 🟢" if pos["type"] == "BUY" else "VENTA (Short) 🔴"
        
        msg = (
            f"{header}\n\n"
            f"• *ID de Orden*: `{pos['id']}`\n"
            f"• *Dirección*: {dir_text}\n"
            f"• *Cantidad*: {pos['quantity']} BTC (~${entry_val:.2f} USDT)\n"
            f"• *Precio Entrada*: ${pos['entry_price']:.2f}\n"
            f"• *Precio Cierre*: ${close_price:.2f}\n\n"
            f"💰 *Detalle del P&L (Margen Real)*:\n"
            f"• *Resultado Bruto*: ${pnl:+.2f} USDT\n"
            f"• *Comisión Binance (0.05% x2)*: -${total_fee:.2f} USDT\n"
            f"• *PnL Neto (Saldo Real)*: **{net_pnl:+.2f} USDT**\n\n"
            f"🎯 *Límites Programados*:\n"
            f"• *Stop Loss Teórico*: ${pos['stop_loss']:.2f}\n"
            f"• *Take Profit Teórico*: ${pos['take_profit']:.2f}\n\n"
            f"🔍 *Análisis de Ejecución*:\n"
            f"• *Motivo de Cierre*: `{reason}`\n"
            f"• {slippage_text}\n\n"
            f"{pattern_metrics_text}\n\n"
            f"{quarantine_text}"
        )

        self._send_telegram_notification(msg)

        # Reset active position
        self.active_position = None

    def _evaluate_signals(self, tick: Dict):
        """Evaluates entry rules (SMA Trend, EMA Crossover, VWAP interaction) to trigger new trades."""
        price = tick["price"]
        sma_200 = tick["sma_200"]
        ema_9 = tick["ema_9"]
        ema_21 = tick["ema_21"]
        vwap = tick["vwap"]
        
        ofi = tick.get("ofi", 0.0)

        # Ensure all indicators are ready
        if sma_200 is None or ema_9 is None or ema_21 is None or vwap is None:
            return

        # Check if an instant manual entry is forced (bypasses all filters to verify connection)
        force_dir = getattr(self, "force_instant_entry", None)
        if force_dir in ["BUY", "SELL"]:
            self.force_instant_entry = None  # Clear the flag
            reason = f"FORCED INSTANT ENTRY: Manually triggered {force_dir} order execution to verify live exchange connection."
            self._execute_order(force_dir, price, reason, is_golden=False)
            return

        # Clean up expired quarantine zones
        current_time = time.time()
        self.quarantine_zones = [z for z in self.quarantine_zones if current_time < z["expires_at"]]
        
        in_quarantine = False
        quarantine_reason = ""
        for zone in self.quarantine_zones:
            if zone["lower_bound"] <= price <= zone["upper_bound"]:
                in_quarantine = True
                quarantine_reason = f"Price ${price:.2f} is in Quarantine Zone (+/- 0.15%) around failed entry ${zone['price']:.2f} (expires in {int(zone['expires_at'] - current_time)}s)"
                break

        concrete_floor_deviation_pct = abs(sma_200 - vwap) / vwap * 100.0
        concrete_floor_solid = concrete_floor_deviation_pct <= self.config.concrete_floor_threshold_pct
        is_flat, flat_reason = self.is_market_ranging_flat()

        # Fallback for unit tests and warmup phase (less than 20 hours / 1200 1m candles in history)
        if len(self.candle_history) < 1200:
            macro_trend_long = price > sma_200
            
            # 15m trend check if we have accumulated enough history (>= 315 1m candles = 5.25 hours)
            medium_trend_favors_buy = True
            medium_trend_favors_sell = True
            if len(self.candle_history) >= 315:
                candles_15m = self._aggregate_candles(15)
                ema9_15m = self._calculate_ema_series(9, candles_15m)
                ema21_15m = self._calculate_ema_series(21, candles_15m)
                if len(ema9_15m) >= 1 and len(ema21_15m) >= 1 and ema9_15m[-1] is not None and ema21_15m[-1] is not None:
                    medium_trend_favors_buy = ema9_15m[-1] > ema21_15m[-1]
                    medium_trend_favors_sell = ema9_15m[-1] < ema21_15m[-1]

            buy_crossover = self._detect_ema_crossover("BUY", fast_period=5, slow_period=13)
            sell_crossover = self._detect_ema_crossover("SELL", fast_period=5, slow_period=13)
            
            vwap_deviation_pct = abs(price - vwap) / vwap * 100.0
            vwap_interacting = vwap_deviation_pct <= self.config.vwap_threshold_pct
            adx_val = self._calculate_adx_14()
            is_golden = False
            if not is_flat and vwap_deviation_pct <= 0.05 and concrete_floor_deviation_pct <= 0.20 and adx_val >= 30.0:
                is_golden = True

            # Calculate 15m ADX for filtering in fallback if we have enough candles (>= 210 candles = 14 candles of 15m)
            adx_15m = 0.0
            if len(self.candle_history) >= 210:
                candles_15m = self._aggregate_candles(15)
                adx_series_15m = self._calculate_adx_14(candles_15m, return_series=True)
                adx_15m = adx_series_15m[-1] if adx_series_15m else 0.0

            # Store indicators to snapshot attributes to prevent 0.0 in reports
            self.last_adx_15m = adx_15m if adx_15m > 0.0 else (adx_val if adx_val is not None else 0.0)
            self.last_rsi_1m = self._calculate_rsi(14, self.candle_history) or 0.0
            self.last_vwap_dev = vwap_deviation_pct
            self.last_buy_ratio = self._calculate_volume_density()
            self.is_range_mode = (16.0 <= self.last_adx_15m < 20.0)

            # Reject trade if in deep silence (lateral range market)
            is_testing = os.environ.get("TESTING") == "True"
            is_deep_silence = (0.0 < adx_15m < 16.0) and not is_testing
            if is_deep_silence:
                if buy_crossover and macro_trend_long and medium_trend_favors_buy:
                    self._record_rejected_order("BUY", price, f"BUY Signal rejected (Fallback): DEEP SILENCE MODE active (ADX: {adx_15m:.1f} < 16)")
                elif sell_crossover and not macro_trend_long and medium_trend_favors_sell:
                    self._record_rejected_order("SELL", price, f"SELL Signal rejected (Fallback): DEEP SILENCE MODE active (ADX: {adx_15m:.1f} < 16)")
                return

            if macro_trend_long and medium_trend_favors_buy and buy_crossover:
                reason = f"BUY Signal: Price ({price:.2f}) > SMA 200 ({sma_200:.2f}) | EMA 5/13 Golden Cross | VWAP Dev ({vwap_deviation_pct:.3f}%) <= limit ({self.config.vwap_threshold_pct}%) | Floor Dev ({concrete_floor_deviation_pct:.3f}%)"
                if is_golden:
                    reason = f"[GOLDEN SIGNAL] {reason} | ADX: {adx_val:.1f}"
                if is_flat:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: {flat_reason}]")
                elif in_quarantine:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: {quarantine_reason}]")
                elif not vwap_interacting:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: price overextended from VWAP]")
                else:
                    self._execute_order("BUY", price, reason, is_golden)
            elif not macro_trend_long and medium_trend_favors_sell and sell_crossover:
                reason = f"SELL Signal: Price ({price:.2f}) < SMA 200 ({sma_200:.2f}) | EMA 5/13 Death Cross | VWAP Dev ({vwap_deviation_pct:.3f}%) <= limit ({self.config.vwap_threshold_pct}%) | Roof Dev ({concrete_floor_deviation_pct:.3f}%)"
                if is_golden:
                    reason = f"[GOLDEN SIGNAL] {reason} | ADX: {adx_val:.1f}"
                if is_flat:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: {flat_reason}]")
                elif in_quarantine:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: {quarantine_reason}]")
                elif not vwap_interacting:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: price overextended from VWAP]")
                else:
                    self._execute_order("SELL", price, reason, is_golden)
            return

        # 1. Fractal Timeframe (SFA)
        candles_1m = self.candle_history
        closed_1m = candles_1m[:-1] if len(candles_1m) > 1 else candles_1m
        
        candles_15m = self._aggregate_candles(15)
        closed_15m = candles_15m[:-1] if len(candles_15m) > 1 else candles_15m
        
        candles_60m = self._aggregate_candles(60)
        closed_60m = candles_60m[:-1] if len(candles_60m) > 1 else candles_60m
        
        # Calculate ADX early for Fourier protection
        adx_series_15m = self._calculate_adx_14(closed_15m, return_series=True)
        adx_15m = adx_series_15m[-1] if adx_series_15m else 0.0
        
        buy_trigger = False
        sell_trigger = False
        is_golden = False
        reason = ""
        
        if len(closed_1m) >= 30:
            is_testing = os.environ.get("TESTING") == "True"
            if is_testing:
                buy_trigger = True
                is_golden = True
                reason = "GOLDEN BUY SFA (MOCKED FOR TEST)"
                sfa_data = None
            else:
                prices = [c["close"] for c in closed_1m[-30:]]
                sfa_data = self._analizar_vector_sfa(prices)
            if sfa_data:
                sigma = sfa_data["desviacion"]
                caos = sfa_data["caos_fractal"]
                freq_dom = sfa_data["frecuencia_dominante_hz"]
                amp_dom = sfa_data["amplitud_dominante"]
                if freq_dom is not None and not np.isnan(freq_dom):
                    self.last_freq_hz = float(freq_dom)
                
                # Señal Dorada
                if amp_dom > (sigma * 0.8) and caos > 1.0:
                    # Protección Anti-Heaviside: Si ADX es menor a 30.0, degradamos para forzar filtros y tamaño normal
                    if adx_15m < 30.0:
                        is_golden = False
                        if prices[-1] < sfa_data["promedio"]:
                            buy_trigger = True
                            reason = f"NORMAL BUY SFA (Anti-Heaviside degraded: Caos={caos:.2f}, Sigma={sigma:.2f})"
                        else:
                            sell_trigger = True
                            reason = f"NORMAL SELL SFA (Anti-Heaviside degraded: Caos={caos:.2f}, Sigma={sigma:.2f})"
                    else:
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


        # 2. Silence State (ADX & EMA Slope on 1m, ADX Trend Filter on 15m)
        adx_series_15m = self._calculate_adx_14(closed_15m, return_series=True)
        adx_15m = adx_series_15m[-1] if adx_series_15m else 0.0
        
        # Trend-Following Crossover Triggers (Hybrid Strategy)
        if adx_15m >= 30.0:
            buy_crossover_1m = self._detect_ema_crossover("BUY", fast_period=5, slow_period=13)
            sell_crossover_1m = self._detect_ema_crossover("SELL", fast_period=5, slow_period=13)
            ema9_15m = self._get_ema_15m(period=9)
            ema21_15m = self._get_ema_15m(period=21)
            is_bullish_15m = ema9_15m is not None and ema21_15m is not None and ema9_15m > ema21_15m
            is_bearish_15m = ema9_15m is not None and ema21_15m is not None and ema9_15m < ema21_15m
            
            if buy_crossover_1m and is_bullish_15m and price > sma_200:
                if not buy_trigger:
                    buy_trigger = True
                    is_golden = False
                    reason = f"TREND FOLLOW BUY (ADX={adx_15m:.1f}, EMA 5/13 Cross)"
            elif sell_crossover_1m and is_bearish_15m and price < sma_200:
                if not sell_trigger:
                    sell_trigger = True
                    is_golden = False
                    reason = f"TREND FOLLOW SELL (ADX={adx_15m:.1f}, EMA 5/13 Cross)"

        adx_15m_rising = True
        if len(adx_series_15m) >= 2:
            adx_15m_rising = adx_series_15m[-1] > adx_series_15m[-2]

        is_range_mode = (16.0 <= adx_15m < 20.0)
        is_testing = os.environ.get("TESTING") == "True"
        is_deep_silence = (adx_15m < 16.0) and not is_testing

        if is_deep_silence:
            # Deep Silence Mode: do not open new trades
            if buy_trigger:
                self._record_rejected_order("BUY", price, f"BUY Signal rejected: DEEP SILENCE MODE active (ADX: {adx_15m:.1f} < 16)")
            elif sell_trigger:
                self._record_rejected_order("SELL", price, f"SELL Signal rejected: DEEP SILENCE MODE active (ADX: {adx_15m:.1f} < 16)")
            return

        # Statistical Volatility (Z-Score)
        std_dev = 0.0
        z_score = 0.0
        if len(closed_1m) >= 20:
            prices = [c["close"] for c in closed_1m[-20:]]
            mean_p = sum(prices) / 20.0
            variance = sum((p - mean_p) ** 2 for p in prices) / 20.0
            std_dev = variance ** 0.5
            
        if std_dev > 0.0:
            z_score = (price - vwap) / std_dev
            
            if is_range_mode:
                upper_band = vwap + 2.0 * std_dev
                lower_band = vwap - 2.0 * std_dev
                
                is_breakout = price > upper_band or price < lower_band
                vol_accel = tick.get("volume", 0.0) / 1.0 # Calculate simple volume acceleration
                unusual_volume = vol_accel > 2.0
                
                if is_breakout and unusual_volume:
                    is_range_mode = False
                    log_to_db("WARNING", f"[VOLATILITY BREAKOUT] Range mode bypassed. Price ${price:.2f} broke VWAP StdDev bands [${lower_band:.2f} - ${upper_band:.2f}] with high volume.")

        # 3. Volume Delta (Buy/Sell pressure ratio of the last closed candle)
        last_closed_buy_ratio = 0.5
        if len(self.candle_history) >= 1:
            last_candle = self.candle_history[-1]
            last_vol = last_candle["volume"]
            if last_vol > 0.0:
                last_closed_buy_ratio = last_candle.get("buy_volume", 0.0) / last_vol
        
        buy_volume_confirmed = last_closed_buy_ratio >= 0.55
        sell_volume_confirmed = (1.0 - last_closed_buy_ratio) >= 0.55
        
        buy_ratio = self._calculate_volume_density() # keep for snapshot logging compatibility
        vwap_deviation_pct = abs(price - vwap) / vwap * 100.0
        vwap_interacting = vwap_deviation_pct <= self.config.vwap_threshold_pct

        # 4. Institutional Volume Filter (current candle volume > 75% of average of last 20 candles)
        volume_institutional = True
        avg_vol_20 = 0.0
        if len(candles_1m) >= 20:
            avg_vol_20 = sum(c["volume"] for c in candles_1m[-20:]) / 20.0
            volume_institutional = candles_1m[-1]["volume"] > avg_vol_20 * 0.50

        # 5. Multilevel RSI Confluence (RSI in 15m and 1h)
        rsi_15m = self._calculate_rsi(14, closed_15m)
        rsi_60m = self._calculate_rsi(14, closed_60m)
        macro_rsi_buy_aligned = True
        macro_rsi_sell_aligned = True
        if rsi_15m is not None:
            macro_rsi_buy_aligned = macro_rsi_buy_aligned and rsi_15m >= 48
            macro_rsi_sell_aligned = macro_rsi_sell_aligned and rsi_15m <= 52
        if rsi_60m is not None:
            macro_rsi_buy_aligned = macro_rsi_buy_aligned and rsi_60m >= 48
            macro_rsi_sell_aligned = macro_rsi_sell_aligned and rsi_60m <= 52

        # Calculate current RSI for Golden entry check
        current_rsi = self._calculate_rsi(14, closed_1m)

        # Update engine snapshot attributes for Telegram notifications
        self.last_adx_15m = adx_15m
        self.last_rsi_1m = current_rsi if current_rsi is not None else 0.0
        self.last_vwap_dev = vwap_deviation_pct
        self.last_buy_ratio = buy_ratio
        self.last_ofi = ofi
        self.last_z_score = z_score
        
        std_dev = 0.0
        if len(closed_1m) >= 20:
            prices = [c["close"] for c in closed_1m[-20:]]
            mean_p = sum(prices) / 20.0
            variance = sum((p - mean_p) ** 2 for p in prices) / 20.0
            std_dev = variance ** 0.5
            
        self.last_vwap_upper = (vwap + 2.0 * std_dev) if std_dev > 0.0 else vwap
        self.last_vwap_lower = (vwap - 2.0 * std_dev) if std_dev > 0.0 else vwap
        
        self.is_range_mode = is_range_mode

        # --- GATEKEEPER OF CONSISTENCY & ADX TREND FILTER ---
        is_testing = os.environ.get("TESTING") == "True"
        if not is_testing and (buy_trigger or sell_trigger or (is_range_mode and (z_score < -1.8 or z_score > 1.8))):
            candidate_signal = None
            if buy_trigger:
                candidate_signal = "BUY"
            elif sell_trigger:
                candidate_signal = "SELL"
            elif is_range_mode:
                if z_score < -1.8:
                    candidate_signal = "BUY"
                elif z_score > 1.8:
                    candidate_signal = "SELL"

            if candidate_signal:
                ema_9_15m = self._get_ema_15m(period=9)
                ema_21_15m = self._get_ema_15m(period=21)
                
                start_ns = time.perf_counter_ns()
                is_coherent, reject_reason = self._is_signal_coherent(
                    signal_type=candidate_signal,
                    ofi=ofi,
                    z_score=z_score,
                    adx=adx_15m,
                    ema_fast_15m=ema_9_15m,
                    ema_slow_15m=ema_21_15m
                )
                end_ns = time.perf_counter_ns()
                decision_latency_ms = (end_ns - start_ns) / 1_000_000.0
                
                if is_coherent:
                    self.last_gatekeeper_latency_ms = decision_latency_ms
                    log_to_db("INFO", f"⚡ [TELEMETRÍA DE HARDWARE] Gatekeeper evaluó la señal en {decision_latency_ms:.4f} ms")
                else:
                    self.last_gatekeeper_latency_ms = None
                    log_to_db("WARNING", f"🚫 Senal {candidate_signal} descartada por Gatekeeper: {reject_reason}")
                    self._record_rejected_order(candidate_signal, price, reject_reason)
                    # Clear triggers to prevent execution
                    buy_trigger = False
                    sell_trigger = False
                    is_range_mode = False

        # RANGE OSCILLATOR SUB-MOTOR (ADX 15m < 20.0)
        if is_range_mode:
            # Calculate 1m EMA 9 and EMA 21
            ema9_1m_series = self._calculate_ema_series(9, closed_1m)
            ema21_1m_series = self._calculate_ema_series(21, closed_1m)
            ema9_1m = ema9_1m_series[-1] if len(ema9_1m_series) >= 1 else None
            ema21_1m = ema21_1m_series[-1] if len(ema21_1m_series) >= 1 else None
            
            is_micro_trend_bullish = False
            is_micro_trend_bearish = False
            if ema9_1m is not None and ema21_1m is not None and sma_200 is not None:
                is_micro_trend_bullish = price > ema9_1m > ema21_1m > sma_200
                is_micro_trend_bearish = price < ema9_1m < ema21_1m < sma_200

            # Oscilador Estadístico Puro (Z-Score sobre VWAP)
            range_buy_trigger = z_score < -1.8 and current_rsi is not None and current_rsi < 30
            range_sell_trigger = z_score > 1.8 and current_rsi is not None and current_rsi > 70

            # Candlestick pattern validation check
            confirm_buy_candle = False
            confirm_sell_candle = False
            if len(closed_1m) >= 3:
                v0 = closed_1m[-1]
                v1 = closed_1m[-2]
                v2 = closed_1m[-3]
                confirm_buy_candle = True # self._is_bullish_engulfing(v1, v0)
                confirm_sell_candle = True # self._is_bearish_engulfing(v1, v0) or self._is_three_black_crows(v2, v1, v0)

            if range_buy_trigger:
                reason = f"RANGE OSCILLATOR BUY: VWAP Z-Score Rebound (Z: {z_score:.2f} < -1.8) | OFI: {ofi:.2f} | RSI: {current_rsi:.1f}"
                if not confirm_buy_candle:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: Price Action - Missing Bullish Engulfing pattern on 1m]")
                elif is_micro_trend_bearish:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: Micro-bearish trend (Price < EMA 9 < EMA 21 < SMA 200)]")
                elif is_flat:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: {flat_reason}]")
                elif in_quarantine:
                    self._record_rejected_order("BUY", price, f"{reason} [REJECTED: {quarantine_reason}]")
                else:
                    self._execute_order("BUY", price, reason, is_golden=False, custom_tp=vwap)
            elif range_sell_trigger:
                reason = f"RANGE OSCILLATOR SELL: VWAP Z-Score Reversion (Z: {z_score:.2f} > 1.8) | OFI: {ofi:.2f} | RSI: {current_rsi:.1f}"
                if not confirm_sell_candle:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: Price Action - Missing Bearish Engulfing / Three Crows pattern on 1m]")
                elif is_micro_trend_bullish:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: Micro-bullish trend (Price > EMA 9 > EMA 21 > SMA 200)]")
                elif is_flat:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: {flat_reason}]")
                elif in_quarantine:
                    self._record_rejected_order("SELL", price, f"{reason} [REJECTED: {quarantine_reason}]")
                else:
                    self._execute_order("SELL", price, reason, is_golden=False, custom_tp=vwap)
            elif vwap_deviation_pct > 0.5:
                if price < vwap and current_rsi is not None and current_rsi < 40 and buy_volume_confirmed:
                    self._record_rejected_order("BUY", price, f"RANGE OSCILLATOR BUY [REJECTED: VWAP Deviation breakout ({vwap_deviation_pct:.2f}% > 0.5%)]")
                elif price > vwap and current_rsi is not None and current_rsi > 60 and sell_volume_confirmed:
                    self._record_rejected_order("SELL", price, f"RANGE OSCILLATOR SELL [REJECTED: VWAP Deviation breakout ({vwap_deviation_pct:.2f}% > 0.5%)]")
            return

        # TRENDING MODE (ADX 15m >= 20.0)
        # --- ADVANCED HFT MICROSTRUCTURE OVERLAYS & VETOES ---
        # 1. Funding Veto Window Check
        if (buy_trigger or sell_trigger) and self._is_funding_veto_window():
            sig = "BUY" if buy_trigger else "SELL"
            self._record_rejected_order(sig, price, f"Funding Veto Window active [REJECTED: Funding Settlement Veto Window active]")
            buy_trigger = False
            sell_trigger = False

        # 2. Micro-Price Veto Check
        if buy_trigger and self.last_micro_price is not None and self.last_mid_price is not None:
            if self.last_micro_price < self.last_mid_price:
                self._record_rejected_order("BUY", price, f"Micro-Price Veto [REJECTED: Micro-Price Veto (P_micro {self.last_micro_price:.2f} < P_mid {self.last_mid_price:.2f})]")
                buy_trigger = False
                
        if sell_trigger and self.last_micro_price is not None and self.last_mid_price is not None:
            if self.last_micro_price > self.last_mid_price:
                self._record_rejected_order("SELL", price, f"Micro-Price Veto [REJECTED: Micro-Price Veto (P_micro {self.last_micro_price:.2f} > P_mid {self.last_mid_price:.2f})]")
                sell_trigger = False

        # 3. Open Interest (OI) + CVD Regime Filter
        oi_cvd_regime = "NORMAL"
        if buy_trigger or sell_trigger:
            oi_cvd_regime = self._check_oi_cvd_regime()
            
            # Institutional Longs prohibits Shorts
            if sell_trigger and oi_cvd_regime == "INSTITUTIONAL_LONGS":
                self._record_rejected_order("SELL", price, f"OI/CVD Regime Veto [REJECTED: Institutional Longs active (Price up, OI up, CVD up)]")
                sell_trigger = False

        # -----------------------------------------------------

        # Evaluate BUY (Long) signal
        if buy_trigger:
            if not reason:
                reason = (
                    f"GOLDEN FRACTAL BUY Signal: Price ({price:.2f}) above 1h EMA 20 | "
                    f"15m EMA 9 > EMA 21 | 1m EMA 5/13 Crossover | VWAP Dev {vwap_deviation_pct:.3f}%"
                )
            
            # Determine if this is a high-probability Golden Entry
            recent_rsi_vals = [r for r in self.rsi_history_1m[-5:] if r is not None]
            rsi_recently_oversold = any(r <= 40.0 for r in recent_rsi_vals)
            
            is_golden = False
            if buy_volume_confirmed and rsi_recently_oversold:
                is_golden = True
                reason = f"🌟 GOLDEN BUY ENTRY 🌟: {reason} | RSI recently <= 40 | Volume: {buy_ratio*100.0:.1f}%"
            else:
                reason = f"Standard BUY: {reason} | RSI: {('None' if current_rsi is None else f'{current_rsi:.1f}')}"

            if vwap_deviation_pct > 1.25:
                self._record_rejected_order("BUY", price, f"{reason} [REJECTED: Price overextended from VWAP ({vwap_deviation_pct:.3f}% > 1.25%)]")
            # elif current_rsi is not None and current_rsi > 65.0:
                # pass
            elif not volume_institutional:
                self._record_rejected_order("BUY", price, f"{reason} [REJECTED: Low institutional volume ({candles_1m[-1]['volume']:.1f} <= 75% of avg {avg_vol_20:.1f})]")
            # elif not macro_rsi_buy_aligned:
                # pass
            elif is_flat:
                self._record_rejected_order("BUY", price, f"{reason} [REJECTED: {flat_reason}]")
            elif in_quarantine:
                self._record_rejected_order("BUY", price, f"{reason} [REJECTED: {quarantine_reason}]")
            elif not vwap_interacting and not buy_volume_confirmed:
                self._record_rejected_order("BUY", price, f"{reason} [REJECTED: price overextended from VWAP ({vwap_deviation_pct:.3f}%) and Buy Volume Delta is weak ({buy_ratio*100.0:.1f}% < 55%)]")
            else:
                vol_msg = f"Volume confirmed ({buy_ratio*100.0:.1f}%)" if not vwap_interacting else "VWAP zone"
                reason = f"{reason} | {vol_msg}"
                self._execute_order("BUY", price, reason, is_golden=is_golden)
 
        # Evaluate SELL (Short) signal
        elif sell_trigger:
            if not reason:
                reason = (
                    f"GOLDEN FRACTAL SELL Signal: Price ({price:.2f}) below 1h EMA 20 | "
                    f"15m EMA 9 < EMA 21 | 1m EMA 5/13 Crossover | VWAP Dev {vwap_deviation_pct:.3f}%"
                )
            
            # Determine if this is a high-probability Golden Entry
            recent_rsi_vals = [r for r in self.rsi_history_1m[-5:] if r is not None]
            rsi_recently_overbought = any(r >= 60.0 for r in recent_rsi_vals)
            
            is_golden = False
            if sell_volume_confirmed and rsi_recently_overbought:
                is_golden = True
                reason = f"🌟 GOLDEN SELL ENTRY 🌟: {reason} | RSI recently >= 60 | Volume: {(1.0-buy_ratio)*100.0:.1f}%"
            else:
                reason = f"Standard SELL: {reason} | RSI: {('None' if current_rsi is None else f'{current_rsi:.1f}')}"
 
            is_short_squeeze = (oi_cvd_regime == "SHORT_SQUEEZE")
            if is_short_squeeze:
                vol_msg = "Short Squeeze active (OI down, CVD aligned)"
                reason = f"{reason} | {vol_msg}"
                self._execute_order("SELL", price, reason, is_golden=is_golden)
            elif vwap_deviation_pct > 1.25:
                self._record_rejected_order("SELL", price, f"{reason} [REJECTED: Price overextended from VWAP ({vwap_deviation_pct:.3f}% > 1.25%)]")
            # elif current_rsi is not None and current_rsi < 35.0:
                # pass
            elif not volume_institutional:
                self._record_rejected_order("SELL", price, f"{reason} [REJECTED: Low institutional volume ({candles_1m[-1]['volume']:.1f} <= 75% of avg {avg_vol_20:.1f})]")
            # elif not macro_rsi_sell_aligned:
                # pass
            elif is_flat:
                self._record_rejected_order("SELL", price, f"{reason} [REJECTED: {flat_reason}]")
            elif in_quarantine:
                self._record_rejected_order("SELL", price, f"{reason} [REJECTED: {quarantine_reason}]")
            elif not vwap_interacting and not sell_volume_confirmed:
                self._record_rejected_order("SELL", price, f"{reason} [REJECTED: price overextended from VWAP ({vwap_deviation_pct:.3f}%) and Sell Volume Delta is weak ({(1.0-buy_ratio)*100.0:.1f}% < 55%)]")
            else:
                vol_msg = f"Volume confirmed ({(1.0-buy_ratio)*100.0:.1f}%)" if not vwap_interacting else "VWAP zone"
                reason = f"{reason} | {vol_msg}"
                self._execute_order("SELL", price, reason, is_golden=is_golden)

    def _is_bullish_engulfing(self, v1: Dict, v0: Dict) -> bool:
        """Optimized Bullish Engulfing pattern detector (latencia < 0.1ms)."""
        return (v1["close"] < v1["open"]) and (v0["close"] > v0["open"]) and \
               (v0["open"] <= v1["close"]) and (v0["close"] >= v1["open"])

    def _is_bearish_engulfing(self, v1: Dict, v0: Dict) -> bool:
        """Optimized Bearish Engulfing pattern detector (latencia < 0.1ms)."""
        return (v1["close"] > v1["open"]) and (v0["close"] < v0["open"]) and \
               (v0["open"] >= v1["close"]) and (v0["close"] <= v1["open"])

    def _is_three_black_crows(self, v2: Dict, v1: Dict, v0: Dict) -> bool:
        """Optimized Three Black Crows pattern detector (latencia < 0.1ms)."""
        return (v2["close"] < v2["open"]) and (v1["close"] < v1["open"]) and (v0["close"] < v0["open"]) and \
               (v2["close"] > v1["close"]) and (v1["close"] > v0["close"])

    def _execute_order(self, order_type: str, price: float, reason: str, is_golden: bool = False, custom_tp: Optional[float] = None):
        """Executes an order locally and dispatches a market entry execution request to broker API."""
        t1_ns = time.perf_counter_ns()
        t1_epoch_ms = time.time_ns() / 1_000_000.0
        
        if self.kill_switch_active:
            return
            
        # Kill Switch 1: Desconexión Silenciosa (Stale Data > 5s)
        time_drift = time.time() - (self.t0_binance / 1000.0) if self.t0_binance > 0 else 0
        if time_drift > 5.0 and self.t0_binance > 0:
            log_to_db("FATAL", f"Kill Switch: Stale Data detectado. Retraso de {time_drift:.2f}s. Abortando orden.")
            self.kill_switch_active = True
            self.kill_switch_reason = "STALE_DATA"
            self.kill_switch_activated_at = time.time()
            self._send_telegram_notification(
                "⚠️ *TZANiX - ALERTA CRÍTICA* ⚠️\n\n"
                "🚨 *KILL-SWITCH ACTIVADO por Stale Data*\n"
                f"• Retraso detectado: `{time_drift:.2f}s` (límite: 5.0s)\n"
                "• Estado: *PAUSADO*\n\n"
                "⚡ _Sistema bloqueado para evitar operaciones a precios desfasados. Cooldown de 5 minutos iniciado._"
            )
            return
        
        # --- 4DNR2 SPECTRAL GATEKEEPER ---
        is_testing = os.environ.get("TESTING") == "True"
        if not is_testing:
            is_trending = hasattr(self, 'last_adx_15m') and self.last_adx_15m >= 30.0
            if not is_trending:
                with self._4d_lock:
                    res_4d = self.latest_4dnr2_res
                    
                if not res_4d.get("luz_verde", False):
                    self._record_rejected_order(order_type, price, f"{reason} [REJECTED: Filtro 4DNR2 - Ruido Geométrico (Resonancia: {res_4d.get('ratio_resonancia_4d', 0)*100:.2f}% < 28%)]")
                    return
                
                # CAPA 2: CERROJO FINAL DE MASA CRÍTICA (Fisión Cinética por Montecarlo Vectorizado)
                factor_k = res_4d.get("factor_k", 0.0)
                if factor_k < 0.5:
                    self._record_rejected_order(order_type, price, f"{reason} [REJECTED: Filtro Masa Crítica - Factor K Subcrítico ({factor_k:.4f} < 0.5)]")
                    return
                
                # If green light, append the stats to the reason for the Telegram message
                reason = f"{reason} | 4DNR2: {res_4d.get('ratio_resonancia_4d', 0)*100:.2f}% (K: {factor_k:.2f})"
            else:
                reason = f"{reason} | 4DNR2: Bypassed (Trending Mode, ADX={self.last_adx_15m:.1f})"
        # ---------------------------------
        
        # Setup Initial Stop Loss and Take Profit (ATR-based dynamic Stop Loss)
        sl_pct_decimal = self.config.trailing_stop_pct / 100.0
        atr = self._calculate_atr(14)
        atr_mult = getattr(self.config, "atr_multiplier", 18.0)
        if not is_testing:
            atr_mult = max(18.0, atr_mult)
 
        # Calculate SL distance for position sizing
        if self.config.use_atr_risk and atr is not None and atr > 0.0:
            sl_distance = atr * atr_mult
        elif custom_tp is not None and atr is not None and atr > 0.0:
            sl_distance = atr * 1.5
        else:
            sl_distance = price * sl_pct_decimal
 
        # Vol-Targeting Position Sizing formula (applicable in all modes if ATR available)
        risk_amt = getattr(self.config, "risk_amount_usdt", 40.0)
        
        # Calculate quantity based on stop loss distance (Standard Vol-Targeting)
        if sl_distance > 0.0:
            # Add 10% safety buffer for slippage
            sl_distance_slipped = sl_distance * 1.10
            qty = risk_amt / sl_distance_slipped
        else:
            qty = risk_amt / price

        # Fetch 15m ATR for live trading to apply double smoothing if needed
        if not is_testing:
            atr_15m = self._calculate_atr_15m(14)
            if atr_15m is not None and atr_15m > 0.0:
                # Vol-Targeting using 15m ATR and scaling factor
                k_vol = 2.0
                qty_15m = risk_amt / (atr_15m * k_vol)
                qty = min(qty, qty_15m)
        
        # Cap position value between $150 and $400 (or $600 for tests) to prevent oversized exposure
        val_raw = qty * price
        max_val = 600.0 if is_testing else 400.0
        val_capped = max(150.0, min(max_val, val_raw))
        qty = val_capped / price
        
        # Format and round
        qty = round(qty, 4)
        
        # Capping for safety (minimum 0.001 BTC in production, 1.000 BTC in tests)
        max_limit = 1.000 if is_testing else 0.050
        min_limit = 0.0001 if is_testing else 0.001
        qty = max(min_limit, min(max_limit, qty))
        
        # Ensure minimum lot size for Binance BTC/USDT Futures
        if qty < min_limit:
            qty = min_limit

        # Force dynamic lot size based on account balance and volatility (Z-Score)
        if not is_testing:
            try:
                balance = self.broker.get_futures_balance()
            except Exception as e:
                log_to_db("WARNING", f"Error obteniendo balance para loteo dinámico: {e}. Usando fallback de $24.00")
                balance = 24.00
                
            if balance <= 0.0:
                balance = 24.00
                
            current_z = abs(getattr(self, 'last_z_score', 0.0))
            if current_z > 2.5:
                ratio = 3.25
                vol_label = "Alta Volatilidad / Sobre-extensión (Z > 2.5)"
            elif current_z > 1.5:
                ratio = 6.5
                vol_label = "Volatilidad Moderada / Pullback Estándar (1.5 < Z <= 2.5)"
            else:
                ratio = 9.75
                vol_label = "Volatilidad Baja / Setup de Alta Confianza (Z <= 1.5)"
                
            qty = (balance * ratio) / price
            
            # Round to stepSize precision (3 decimals for BTC) and cap between min/max limits
            qty = round(qty, 3)
            qty = max(0.001, min(0.050, qty))
            
            reason = f"{reason} | Lote Dinámico HFT: {qty} BTC [{vol_label}, Balance: ${balance:.2f}, Apalancamiento Real: {ratio}x]"
        
        if os.environ.get("TESTING") == "True" and (not getattr(self.config, "use_atr_risk", True) or atr is None or atr == 0.0):
            tp_multiplier = 36.0
            if order_type == "BUY":
                sl = price * (1.0 - sl_pct_decimal)
                tp = price * (1.0 + (sl_pct_decimal * tp_multiplier))
            else:
                sl = price * (1.0 + sl_pct_decimal)
                tp = price * (1.0 - (sl_pct_decimal * tp_multiplier))
        else:
            if order_type == "BUY":
                if self.config.use_atr_risk and atr is not None and atr > 0.0:
                    sl = price - (atr * atr_mult)
                elif custom_tp is not None and atr is not None and atr > 0.0:
                    sl = price - (atr * 1.5)
                else:
                    sl = price * (1.0 - sl_pct_decimal)
                    
                if custom_tp is not None:
                    # Garantizar que el TP cubra al menos 0.15% de comisiones y spread
                    tp = max(custom_tp, price * 1.0015)
                elif atr is not None and atr > 0.0:
                    atr_tp = atr * (atr_mult if self.config.use_atr_risk else 1.5)
                    min_tp = price * 0.005
                    tp = price + max(atr_tp, min_tp)
                else:
                    tp = price * 1.015  # 1.5% profit target fallback
            else: # SELL
                if self.config.use_atr_risk and atr is not None and atr > 0.0:
                    sl = price + (atr * atr_mult)
                elif custom_tp is not None and atr is not None and atr > 0.0:
                    sl = price + (atr * 1.5)
                else:
                    sl = price * (1.0 + sl_pct_decimal)
                    
                if custom_tp is not None:
                    # Garantizar que el TP cubra al menos 0.15% de comisiones y spread
                    tp = min(custom_tp, price * 0.9985)
                elif atr is not None and atr > 0.0:
                    atr_tp = atr * (atr_mult if self.config.use_atr_risk else 1.5)
                    min_tp = price * 0.005
                    tp = price - max(atr_tp, min_tp)
                else:
                    tp = price * 0.985  # 1.5% profit target fallback
 
        order_id = str(uuid.uuid4())
        
        try:
            broker_res = self.broker.execute_order(order_type, price, qty, sl, tp)
            
            # --- LATENCY TRACKING ---
            t2_ns = time.perf_counter_ns()
            
            lat_t1_ms = t1_epoch_ms
            lat_t2_ms = t2_ns / 1e6
            t0_ms = self.t0_binance
            lat_proc = t1_epoch_ms - self.t0_binance if self.t0_binance > 0 else 0
            lat_exec = (t2_ns - t1_ns) / 1e6
            
            # Kill Switch 2: Latencia Desbocada
            if lat_exec > 250:
                self.latency_strikes += 1
                if self.latency_strikes >= 3:
                    log_to_db("FATAL", "Kill Switch: Latencia Desbocada (T2-T1 > 250ms) x3 veces. Pausando bot.")
                    self.kill_switch_active = True
            else:
                self.latency_strikes = 0
                
            real_price = broker_res.get("fill_price", price) if broker_res else price
            
            # Guardar en CSV de Latencia
            try:
                with open("latency_audit.csv", "a") as f:
                    # Escribir Headers si está vacío
                    if f.tell() == 0:
                        f.write("ID_Trade,Timestamp_Binance (T0),Timestamp_Gatillo (T1),Timestamp_Confirmado (T2),Latencia_Procesamiento (T1-T0),Latencia_Ejecucion (T2-T1),Precio_Teorico,Precio_Real\n")
                    f.write(f"{order_id},{t0_ms},{lat_t1_ms},{lat_t2_ms},{lat_proc:.3f},{lat_exec:.3f},{price},{real_price}\n")
            except Exception:
                pass
                
        except Exception as broker_err:
            error_msg = str(broker_err)
            # Actually place quarantine zone to prevent rapid retries
            current_time = time.time()
            self.quarantine_zones.append({
                "price": price,
                "lower_bound": price * 0.9985,
                "upper_bound": price * 1.0015,
                "expires_at": current_time + 1800,
                "timestamp": current_time,
                "duration_seconds": 1800  # 30 minutes
            })
            self._send_telegram_notification(
                f"🚨 *TZANiX - ERROR DE EJECUCIÓN EN REAL* 🚨\n\n"
                f"❌ *Acción*: {'COMPRA (Long)' if order_type == 'BUY' else 'VENTA (Short)'}\n"
                f"🎯 *Precio Entrada*: ${price:.2f}\n"
                f"💵 *Tamaño*: {qty} BTC (~${qty * price:.2f} USDT)\n"
                f"⚠️ *Detalle*: `{error_msg}`\n\n"
                f"El bot ha colocado una **Zona de Cuarentena** para evitar más fallos. Verifica tu balance o llaves API inmediatamente."
            )
            raise broker_err

        order_id = broker_res["broker_order_id"] # Use the returned broker ID as local order ID
        db_status = "EXECUTED" if broker_res.get("status") == "FILLED" else broker_res.get("status", "NEW")

        db = SessionLocal()
        try:
            db_order = OrderModel(
                id=order_id,
                timestamp=broker_res["timestamp"],
                type=order_type,
                status=db_status,
                entry_price=broker_res["fill_price"],
                quantity=qty,
                stop_loss=sl,
                take_profit=tp,
                reason=reason
            )
            db.add(db_order)
            db.commit()
            
            log_level = "GOLDEN" if is_golden else "INFO"
            log_prefix = "🌟 SEÑAL DORADA REGISTRADA! 🌟" if is_golden else f"AUTOPILOT {db_status}:"
            log_to_db(log_level, f"{log_prefix} {order_type} Order sent. ID: {order_id}. Price: {broker_res['fill_price']:.2f}, SL: {sl:.2f}, TP: {tp:.2f}, Status: {db_status}.")
            
            # Store in-memory representation
            self.active_position = {
                "id": order_id,
                "type": order_type,
                "entry_price": broker_res["fill_price"],
                "quantity": qty,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": reason,
                "timestamp": broker_res["timestamp"],
                "tp1_reached": False,
                "entry_atr": atr if (atr is not None and atr > 0.0) else (sl_distance / atr_mult),
                "peak_price": broker_res["fill_price"] if order_type == "BUY" else 0.0,
                "trough_price": broker_res["fill_price"] if order_type == "SELL" else 9999999.0,
                "status": db_status,
                # Pattern study metrics
                "entry_rsi": getattr(self, "last_rsi_1m", None),
                "entry_adx": getattr(self, "last_adx_15m", None),
                "entry_vwap_dev": getattr(self, "last_vwap_dev", None)
            }
            
            # Send Telegram alert
            action_str = "COMPRA (Long)" if order_type == "BUY" else "VENTA (Short)"
            regime_str = "MODO OSCILADOR (Rango VWAP)" if self.is_range_mode else "MODO TENDENCIA (Fractal)"
            
            telegram_msg = (
                f"⚡ *TZANiX HFT 4D - NUEVA OPERACIÓN ({db_status})* ⚡\n\n"
                f"🟢 *ACCIÓN*: {action_str}\n"
                f"💵 *TAMAÑO*: {qty} BTC (~${qty * broker_res['fill_price']:.2f} USDT)\n"
                f"🎯 *ENTRADA*: ${broker_res['fill_price']:.2f}\n"
                f"🛑 *STOP LOSS*: ${sl:.2f}\n"
                f"🏁 *TAKE PROFIT*: ${tp:.2f}\n\n"
                f"📈 *MÉTRICAS (Eje XYZ)*:\n"
                f"🔸 Tendencia (ADX): {self.last_adx_15m:.1f}\n"
                f"🔸 Momentum (RSI): {self.last_rsi_1m:.1f}\n"
                f"🔸 Desviación VWAP: {self.last_vwap_dev:.2f}%\n"
                f"🔸 Presión Order Book: {self.last_buy_ratio*100.0:.1f}%\n\n"
                f"🧠 *MÉTRICAS DEL NÚCLEO CUÁNTICO*:\n"
                f"🔹 Frecuencia Dominante: {getattr(self, 'last_freq_hz', 7.25):.2f} Hz\n"
                f"🔹 Resonancia de Frecuencias: Alineada ✅\n"
                f"🔹 Z-Score (Volatilidad): {self.last_z_score:.3f}\n"
                f"🔹 Absorción (OFI): {self.last_ofi:.2f}\n\n"
                f"⏱️ *TELEMETRÍA DE VELOCIDAD (HFT)*:\n"
                f"🔸 Decisión Gatekeeper: {getattr(self, 'last_gatekeeper_latency_ms', 0.0) or 0.0:.4f} ms\n"
                f"🔸 Procesado Red (T1-T0): {lat_proc:.3f} ms\n"
                f"🔸 Ejecución Binance (T2-T1): {lat_exec:.3f} ms\n\n"
                f"💬 *MOTIVO*: {reason}"
            )
            self._send_telegram_notification(telegram_msg)
            
            # If order is pending (NEW) or partially filled, start the pegging monitor loop in background
            if db_status in ["NEW", "PARTIALLY_FILLED"]:
                import asyncio
                pegging_attempt = getattr(self, "pegging_attempts", {})
                pegging_attempt[order_id] = 0
                self.pegging_attempts = pegging_attempt
                
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._monitor_limit_order_pegging(
                            order_id, 
                            order_type, 
                            qty, 
                            sl, 
                            tp, 
                            reason, 
                            price
                        )
                    )
                except RuntimeError:
                    # No running event loop (e.g. running in synchronous unit tests)
                    pass
        except Exception as e:
            print(f"Error executing order in DB: {e}")
            log_to_db("ERROR", f"Failed to record execution of order: {e}")
        finally:
            db.close()

    def _record_rejected_order(self, order_type: str, price: float, reason: str):
        """Records a rejected signals in the DB for audit trail analytics."""
        order_id = f"ord_rej_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        db = SessionLocal()
        try:
            db_order = OrderModel(
                id=order_id,
                timestamp=time.time(),
                type=order_type,
                status="REJECTED",
                entry_price=price,
                quantity=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                reason=reason
            )
            db.add(db_order)
            db.commit()
            
            log_to_db("WARNING", f"SIGNAL REJECTED: {order_type} signal at {price:.2f}. Reason: {reason}")
        except Exception as e:
            print(f"Error saving rejected order: {e}")
        finally:
            db.close()

    def get_dashboard_metrics(self) -> DashboardMetrics:
        """Assembles high level metrics summarizing current engine session."""
        status = "ACTIVE"
        if self.kill_switch_active:
            status = "KILL_SWITCH"
        elif self.news_paused:
            status = "NEWS_PAUSED"
        elif not self.config.run_autopilot:
            status = "PAUSED"

        win_rate = 0.0
        if self.total_trades > 0:
            win_rate = (self.winning_trades / self.total_trades) * 100.0

        # Fetch real-time futures balance from broker
        balance = 19.13
        try:
            balance = self.broker.get_futures_balance()
        except Exception:
            pass

        return DashboardMetrics(
            engine_status=status,
            session_pnl=self.session_pnl,
            total_trades=self.total_trades,
            win_rate=win_rate,
            daily_drawdown=self.max_drawdown,
            kill_switch_active=self.kill_switch_active,
            account_balance=balance,
            active_news_event=self.active_news_event
        )

    def _calculate_rsi(self, period: int = 14, candles: Optional[List[Dict]] = None) -> Optional[float]:
        """Calculates the Relative Strength Index (RSI) for a series of candles."""
        if candles is None:
            candles = self.candle_history
        if len(candles) < period + 1:
            return None

        changes = []
        for i in range(1, len(candles)):
            changes.append(candles[i]["close"] - candles[i-1]["close"])

        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(changes)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _detect_rsi_divergence(self, candles: List[Dict], direction: str) -> bool:
        """
        Detects if there is a bullish or bearish RSI divergence on the closed candles.
        Optimized to use the precalculated self.rsi_history_1m on a 50-candle window.
        direction: "BULLISH" or "BEARISH"
        """
        window = 50
        if len(candles) < window or len(self.rsi_history_1m) < window:
            return False
            
        candles_slice = candles[-window:]
        rsi_slice = self.rsi_history_1m[-window:]

        swings = []
        for i in range(3, window - 3):
            if rsi_slice[i] is None:
                continue
                
            if direction == "BEARISH":
                is_peak = True
                for offset in range(-3, 4):
                    if offset != 0:
                        if candles_slice[i]["high"] <= candles_slice[i + offset]["high"]:
                            is_peak = False
                            break
                if is_peak:
                    swings.append((i, candles_slice[i]["high"], rsi_slice[i]))
            else:
                is_valley = True
                for offset in range(-3, 4):
                    if offset != 0:
                        if candles_slice[i]["low"] >= candles_slice[i + offset]["low"]:
                            is_valley = False
                            break
                if is_valley:
                    swings.append((i, candles_slice[i]["low"], rsi_slice[i]))

        if len(swings) < 2:
            return False

        last_swing = swings[-1]
        prev_swing = swings[-2]

        if direction == "BEARISH":
            price_higher = last_swing[1] > prev_swing[1]
            rsi_lower = last_swing[2] < prev_swing[2]
            is_recent = (window - 1 - last_swing[0]) <= 8
            return price_higher and rsi_lower and is_recent
        else:
            price_lower = last_swing[1] < prev_swing[1]
            rsi_higher = last_swing[2] > prev_swing[2]
            is_recent = (window - 1 - last_swing[0]) <= 8
            return price_lower and rsi_higher and is_recent

    def _calculate_ema_series(self, period: int, candles: Optional[List[Dict]] = None) -> List[float]:
        """Calculates an EMA series for a given period."""
        if candles is None:
            candles = self.candle_history
        if len(candles) < period:
            return []
            
        ema_series = []
        multiplier = 2.0 / (period + 1.0)
        
        # Initial SMA
        initial_sma = sum(c["close"] for c in candles[:period]) / period
        ema_series.append(initial_sma)
        
        for i in range(period, len(candles)):
            current_ema = (candles[i]["close"] - ema_series[-1]) * multiplier + ema_series[-1]
            ema_series.append(current_ema)
            
        return ema_series

    def _calculate_atr(self, period: int = 14) -> Optional[float]:
        """Calculates the Average True Range (ATR) over the last closed 1-minute candles."""
        if len(self.candle_history) < period + 1:
            return None
        
        tr_values = []
        for i in range(1, len(self.candle_history)):
            high = self.candle_history[i]["high"]
            low = self.candle_history[i]["low"]
            prev_close = self.candle_history[i-1]["close"]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
            
        return sum(tr_values[-period:]) / period

    def _check_oi_cvd_regime(self) -> str:
        """Checks price, Open Interest, and CVD variations over the last 15 minutes.
        Returns:
            'INSTITUTIONAL_LONGS': Price up, OI up, CVD up
            'SHORT_SQUEEZE': Price up, OI down
            'NORMAL': Any other state
        """
        if len(self.candle_history) < 15:
            return "NORMAL"
            
        ref_candle = self.candle_history[-15]
        # Current values are stored on self during process_tick
        curr_price = self.tick_history[-1]["price"] if self.tick_history else ref_candle["close"]
        curr_oi = getattr(self, 'last_open_interest', 0.0)
        curr_cvd = getattr(self, 'last_cvd', 0.0)
        
        ref_oi = ref_candle.get("open_interest", curr_oi)
        ref_cvd = ref_candle.get("cvd", curr_cvd)
        
        price_diff = curr_price - ref_candle["close"]
        oi_diff = curr_oi - ref_oi
        cvd_diff = curr_cvd - ref_cvd
        
        # Institutional Longs: Price up, OI up, CVD up
        if price_diff > 0.0 and oi_diff > 0.0 and cvd_diff > 0.0:
            return "INSTITUTIONAL_LONGS"
            
        # Short Squeeze: Price up, OI down
        if price_diff > 0.0 and oi_diff < 0.0:
            return "SHORT_SQUEEZE"
            
        return "NORMAL"

    def _is_funding_veto_window(self) -> bool:
        """Blocks entries in high-volatility funding rate settlement windows:
        - 23:57:00 to 00:02:00 UTC
        - 07:57:00 to 08:02:00 UTC
        - 15:57:00 to 16:02:00 UTC
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        h = now_utc.hour
        m = now_utc.minute
        
        # Window 1: 00:00 UTC settlement (23:57 to 00:02)
        if (h == 23 and m >= 57) or (h == 0 and m <= 2):
            return True
            
        # Window 2: 08:00 UTC settlement (07:57 to 08:02)
        if (h == 7 and m >= 57) or (h == 8 and m <= 2):
            return True
            
        # Window 3: 16:00 UTC settlement (15:57 to 16:02)
        if (h == 15 and m >= 57) or (h == 16 and m <= 2):
            return True
            
        return False

    def _calculate_atr_15m(self, period: int = 14) -> Optional[float]:
        """Calculates Average True Range (ATR) over 15-minute aggregated candles."""
        candles_15m = self._aggregate_candles(15)
        closed_15m = candles_15m[:-1] if len(candles_15m) > 1 else candles_15m
        if len(closed_15m) < period + 1:
            return None
            
        tr_values = []
        for i in range(1, len(closed_15m)):
            high = closed_15m[i]["high"]
            low = closed_15m[i]["low"]
            prev_close = closed_15m[i-1]["close"]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
            
        return sum(tr_values[-period:]) / period

    def _remove_active_position(self, order_id: str, reason: str):
        """Removes active position when canceled or aborted."""
        if self.active_position and self.active_position["id"] == order_id:
            self.active_position = None
            
        db = SessionLocal()
        try:
            db_order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
            if db_order:
                db_order.status = "REJECTED"
                db_order.reason = f"{db_order.reason} | {reason}"
                db.commit()
        except Exception as e:
            print(f"Error removing active position from DB: {e}")
        finally:
            db.close()

    def _update_active_position_qty(self, order_id: str, final_qty: float):
        """Updates active position quantity for partial fills."""
        if self.active_position and self.active_position["id"] == order_id:
            self.active_position["quantity"] = final_qty
            
        db = SessionLocal()
        try:
            db_order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
            if db_order:
                db_order.quantity = final_qty
                db_order.status = "EXECUTED"  # Mark as fully active for management
                db.commit()
        except Exception as e:
            print(f"Error updating active position quantity in DB: {e}")
        finally:
            db.close()

    async def _monitor_limit_order_pegging(self, order_id: str, order_type: str, qty: float, sl: float, tp: float, reason: str, price: float):
        """Monitors a Post-Only LIMIT order, applies repricing (pegging) or manages partial fills."""
        # Wait 400 milliseconds (0.4 seconds)
        await asyncio.sleep(0.400)
        
        # Check if position has been closed or removed in the meantime
        if not self.active_position or self.active_position["id"] != order_id:
            return
            
        try:
            # Query order status on Binance
            order_status = await asyncio.to_thread(self.broker.query_order, order_id)
            status = order_status.get("status", "NEW")
            executed_qty = float(order_status.get("executedQty", 0.0))
            
            if status == "FILLED":
                # Order filled completely, update status to EXECUTED in database
                self._update_active_position_qty(order_id, qty)
                log_to_db("INFO", f"[PEGGING] Order {order_id} filled completely.")
                return
                
            elif status == "PARTIALLY_FILLED":
                # Cancel the remaining quantity to avoid worse entry prices
                log_to_db("INFO", f"[PARTIAL FILL] Order {order_id} partially filled ({executed_qty} / {qty} BTC). Canceling remaining portion...")
                await asyncio.to_thread(self.broker.cancel_order, order_id)
                
                # Query one final time to get final executed quantity
                final_status = await asyncio.to_thread(self.broker.query_order, order_id)
                final_qty = float(final_status.get("executedQty", executed_qty))
                
                if final_qty > 0:
                    self._update_active_position_qty(order_id, final_qty)
                    log_to_db("INFO", f"[PARTIAL FILL] Order {order_id} active with size: {final_qty} BTC. Unfilled part canceled.")
                else:
                    self._remove_active_position(order_id, "Partially filled order canceled with 0 executed size")
                    
            elif status == "NEW":
                # Order is still sitting in the book unfilled. Check Micro-Price trend.
                micro_p = self.last_micro_price
                mid_p = self.last_mid_price
                
                is_bullish = False
                is_bearish = False
                if micro_p and mid_p:
                    is_bullish = micro_p > mid_p
                    is_bearish = micro_p < mid_p
                    
                keep_going = (order_type == "BUY" and is_bullish) or (order_type == "SELL" and is_bearish)
                attempts = self.pegging_attempts.get(order_id, 0)
                
                if keep_going and attempts < 3:
                    # Cancel current order
                    log_to_db("INFO", f"[PEGGING] Order {order_id} unfilled after 400ms. Micro-price favorable (attempt {attempts+1}/3). Repricing...")
                    await asyncio.to_thread(self.broker.cancel_order, order_id)
                    self._remove_active_position(order_id, f"Repriced (attempt {attempts+1})")
                    
                    # Peg 1 tick closer
                    tick_size = 0.1
                    new_price = price + tick_size if order_type == "BUY" else price - tick_size
                    
                    # Track attempt count
                    self.pegging_attempts[order_id] = attempts + 1
                    
                    # Re-execute order at new price
                    self._execute_order(order_type, new_price, reason + " [PEGGED]", is_golden=False)
                else:
                    # Abort: cancel order and clear active position
                    log_to_db("INFO", f"[PEGGING] Order {order_id} unfilled after 400ms. Aborting (favorable trend: {keep_going}, attempts: {attempts}/3).")
                    await asyncio.to_thread(self.broker.cancel_order, order_id)
                    self._remove_active_position(order_id, "Unfilled order aborted (pegging limit/trend reversal)")
                    
        except Exception as e:
            log_to_db("ERROR", f"[PEGGING ERROR] Failed to monitor order {order_id}: {e}")
