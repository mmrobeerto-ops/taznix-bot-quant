import asyncio
import json
import random
import time
import websockets
from typing import Callable, Optional
from app.engine import TradingEngine
from app.database import log_to_db

class MarketDataFeed:
    def __init__(self, engine: TradingEngine):
        self.engine = engine
        self.running = False
        
        # In-memory aggregators for live high-frequency trades
        self.latest_price: Optional[float] = None
        self.interval_volume: float = 0.0
        self.latest_imbalance: float = 0.0
        
        # IFA Institutional Block Tracking
        self.inst_buy_vol: float = 0.0
        self.inst_sell_vol: float = 0.0
        self.current_block_time: int = 0
        self.current_block_is_sell: bool = False
        self.current_block_volume: float = 0.0
        self.block_threshold: float = 0.5  # BTC
        
        # Standard variables for backward compatibility
        self.current_price = 100.0
        self.broadcast_callback: Optional[Callable[[dict], None]] = None
        
        # New Microstructure Variables
        self.latest_micro_price: Optional[float] = None
        self.latest_mid_price: Optional[float] = None
        self.latest_bids: list = []
        self.latest_asks: list = []
        self.latest_open_interest: float = 0.0
        self.cvd: float = 0.0
        
        # Spot Oracle and L2 OFI State Variables
        self.latest_spot_micro_price: Optional[float] = None
        self.prev_bid_price: Optional[float] = None
        self.prev_bid_qty: Optional[float] = None
        self.prev_ask_price: Optional[float] = None
        self.prev_ask_qty: Optional[float] = None
        self.latest_l2_ofi: float = 0.0
        
        # Concurrent tasks
        self.listener_task: Optional[asyncio.Task] = None
        self.spot_listener_task: Optional[asyncio.Task] = None
        self.timer_task: Optional[asyncio.Task] = None
        
        # Track ticks
        self.tick_counter = 0

    def start(self, broadcast_callback: Callable[[dict], None]):
        """Starts the live market feed connection to Binance and the timer loops."""
        if self.running:
            return
        self.running = True
        self.broadcast_callback = broadcast_callback
        
        # Launch WebSocket listener and 1-second aggregation timer loops
        self.listener_task = asyncio.create_task(self._listen_binance_websocket())
        self.spot_listener_task = asyncio.create_task(self._listen_binance_spot_websocket())
        self.timer_task = asyncio.create_task(self._timer_loop())
        log_to_db("INFO", "Market Data Feed: Connecting to live Binance Futures & Spot BTC/USDT streams...")

    def stop(self):
        """Stops the live market feed connection."""
        self.running = False
        if self.listener_task:
            self.listener_task.cancel()
        if self.spot_listener_task:
            self.spot_listener_task.cancel()
        if self.timer_task:
            self.timer_task.cancel()
        log_to_db("INFO", "Market Data Feed: Live Binance feeds stopped.")

    async def _listen_binance_websocket(self):
        """WebSocket consumer listening to live Binance Futures combined stream (Trade + Order Book + Open Interest)."""
        url = "wss://fstream.binance.com/stream?streams=btcusdt@trade/btcusdt@depth5@100ms/btcusdt@openInterest"
        backoff = 2
        
        while self.running:
            try:
                async with websockets.connect(url) as websocket:
                    backoff = 2 # Reset connection backoff
                    log_to_db("INFO", "Market Data Feed: WebSocket connected to Binance Futures (Trade + Order Book + Open Interest).")
                    
                    while self.running:
                        message = await websocket.recv()
                        local_recv_time = int(time.time() * 1000)
                        payload = json.loads(message)
                        
                        stream_name = payload.get("stream", "")
                        data = payload.get("data", {})
                        
                        # Latency-based Stale Data Filtering (Drop Ticks > 50ms)
                        event_time = data.get("E")
                        if event_time is not None:
                            time_offset = getattr(self.engine.broker, "time_offset", 0.0)
                            latency = local_recv_time + int(time_offset) - event_time
                            if latency > 50:
                                # Log warnings for high-latency packets and drop them
                                log_to_db("WARNING", f"[STALE DATA DETECTED] Discarding packet from stream {stream_name} (latency: {latency}ms > 50ms).")
                                continue
                        
                        if stream_name == "btcusdt@trade":
                            # Parse trade tick details
                            price = float(data["p"])
                            volume = float(data["q"])
                            trade_time = int(data["T"])
                            is_sell = bool(data["m"])
                            
                            # Update general aggregates
                            self.latest_price = price
                            self.interval_volume += volume
                            self.current_price = price
                            
                            # Update CVD (Cumulative Volume Delta)
                            if is_sell:
                                self.cvd -= volume
                            else:
                                self.cvd += volume
                            
                            # IFA: Millisecond Block Trade Aggregation
                            if trade_time == self.current_block_time and is_sell == self.current_block_is_sell:
                                self.current_block_volume += volume
                            else:
                                # Flush previous block if it meets institutional threshold
                                if self.current_block_volume >= self.block_threshold:
                                    if self.current_block_is_sell:
                                        self.inst_sell_vol += self.current_block_volume
                                    else:
                                        self.inst_buy_vol += self.current_block_volume
                                        
                                    # Update True IFA Imbalance
                                    total_inst = self.inst_buy_vol + self.inst_sell_vol
                                    if total_inst > 0:
                                        self.latest_imbalance = (self.inst_buy_vol - self.inst_sell_vol) / total_inst
                                        
                                # Start new block
                                self.current_block_time = trade_time
                                self.current_block_is_sell = is_sell
                                self.current_block_volume = volume
                                
                        elif stream_name == "btcusdt@depth5@100ms":
                            # Compute Micro-price and Mid-price
                            bids = data.get("b", [])
                            asks = data.get("a", [])
                            if bids and asks:
                                self.latest_bids = bids
                                self.latest_asks = asks
                                p_bid = float(bids[0][0])
                                v_bid = float(bids[0][1])
                                p_ask = float(asks[0][0])
                                v_ask = float(asks[0][1])
                                total_vol = v_bid + v_ask
                                if total_vol > 0:
                                    self.latest_micro_price = p_bid * (v_ask / total_vol) + p_ask * (v_bid / total_vol)
                                    self.latest_mid_price = (p_bid + p_ask) / 2.0
                                    
                                # Calculate Cont-Stoikov L2 Order Flow Imbalance (OFI)
                                delta_bid = 0.0
                                if self.prev_bid_price is not None:
                                    if p_bid > self.prev_bid_price:
                                        delta_bid = v_bid
                                    elif p_bid == self.prev_bid_price:
                                        delta_bid = v_bid - self.prev_bid_qty
                                    else:
                                        delta_bid = -self.prev_bid_qty
                                        
                                delta_ask = 0.0
                                if self.prev_ask_price is not None:
                                    if p_ask > self.prev_ask_price:
                                        delta_ask = -self.prev_ask_qty
                                    elif p_ask == self.prev_ask_price:
                                        delta_ask = v_ask - self.prev_ask_qty
                                    else:
                                        delta_ask = v_ask
                                        
                                self.latest_l2_ofi = delta_bid - delta_ask
                                
                                # Store state
                                self.prev_bid_price = p_bid
                                self.prev_bid_qty = v_bid
                                self.prev_ask_price = p_ask
                                self.prev_ask_qty = v_ask
                                    
                        elif stream_name == "btcusdt@openInterest":
                            # Parse Open Interest in BTC
                            self.latest_open_interest = float(data.get("o", 0.0))
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Set to None to alert UI of disconnection states if it persists
                log_to_db("WARNING", f"Market Data Feed: Binance connection lost ({e}). Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60) # Exponential capped at 1 minute

    async def _listen_binance_spot_websocket(self):
        """WebSocket consumer listening to live Binance Spot book depth to calculate Spot micro-price."""
        url = "wss://stream.binance.com/stream?streams=btcusdt@depth5@100ms"
        backoff = 2
        
        while self.running:
            try:
                async with websockets.connect(url) as websocket:
                    backoff = 2 # Reset connection backoff
                    log_to_db("INFO", "Market Data Feed: WebSocket connected to Binance Spot (depth5).")
                    
                    while self.running:
                        message = await websocket.recv()
                        payload = json.loads(message)
                        data = payload.get("data", {})
                        
                        bids = data.get("b", [])
                        asks = data.get("a", [])
                        if bids and asks:
                            p_bid = float(bids[0][0])
                            v_bid = float(bids[0][1])
                            p_ask = float(asks[0][0])
                            v_ask = float(asks[0][1])
                            total_vol = v_bid + v_ask
                            if total_vol > 0:
                                self.latest_spot_micro_price = p_bid * (v_ask / total_vol) + p_ask * (v_bid / total_vol)
                                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_to_db("WARNING", f"Market Data Feed: Binance Spot connection lost ({e}). Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _timer_loop(self):
        """Timer loop that runs every 1 second to process aggregated market ticks through SFA engine."""
        while self.running:
            try:
                await asyncio.sleep(1.0)
                
                # Decay institutional volume memory by 5% every second (rolling momentum)
                self.inst_buy_vol *= 0.95
                self.inst_sell_vol *= 0.95
                self.tick_counter += 1
                
                # Periodically simulate news events for filter demonstration (only in emulated fallback mode!)
                # if self.tick_counter % 80 == 0 and self.engine.broker.is_emulated:
                #    self._generate_mock_news()

                # Process tick if we have received at least one valid price update
                if self.latest_price is not None and self.latest_price > 0.0:
                    try:
                        price = self.latest_price
                        volume = self.interval_volume
                        imbalance = self.latest_imbalance
                        
                        # Reset volume aggregator
                        self.interval_volume = 0.0
                        
                        # Pass tick and imbalance to the engine with microstructure parameters
                        tick_data = self.engine.process_tick(
                            price, 
                            volume, 
                            imbalance, 
                            self.current_block_time,
                            micro_price=self.latest_micro_price,
                            mid_price=self.latest_mid_price,
                            cvd=self.cvd,
                            open_interest=self.latest_open_interest,
                            real_l2_ofi=self.latest_l2_ofi,
                            spot_micro_price=self.latest_spot_micro_price
                        )
                        
                        # Fetch latest metrics
                        metrics = self.engine.get_dashboard_metrics()
                        
                        # Package broadcast payload
                        payload = {
                            "type": "tick",
                            "price": price,
                            "volume": volume,
                            "sma_200": tick_data.get("sma_200"),
                            "vwap": tick_data.get("vwap"),
                            "vwap_upper": tick_data.get("vwap_upper"),
                            "vwap_lower": tick_data.get("vwap_lower"),
                            "ofi": tick_data.get("ofi"),
                            "z_score": tick_data.get("z_score"),
                            "micro_price": self.latest_micro_price,
                            "mid_price": self.latest_mid_price,
                            "spot_micro_price": self.latest_spot_micro_price,
                            "real_l2_ofi": self.latest_l2_ofi,
                            "bids": self.latest_bids,
                            "asks": self.latest_asks,
                            "adx_15m": self.engine.last_adx_15m,
                            "timestamp": tick_data.get("timestamp", time.time()),
                            "metrics": metrics.model_dump(),
                            "active_position": self.engine.active_position
                        }
                        
                        if self.broadcast_callback:
                            self.broadcast_callback(payload)
                    except Exception as e:
                        import traceback
                        err_str = traceback.format_exc()
                        log_to_db("ERROR", f"CRITICAL LOOP CRASH in process_tick: {e}\n{err_str}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in feed timer loop: {e}")

    def _generate_mock_news(self):
        """Injects simulated high-impact news into the trading engine to test trend freezes."""
        news_events = [
            {"title": "US Federal Reserve announces unexpected interest rate decision", "impact": "HIGH", "sentiment": -0.8},
            {"title": "CPI Inflation Rate data released above Wall Street consensus", "impact": "HIGH", "sentiment": -0.6},
            {"title": "Global Logistics Hub reports sudden shipping capacity bottleneck", "impact": "MEDIUM", "sentiment": -0.4},
            {"title": "Tech Sector Q3 Earnings reports outperform institutional forecasts", "impact": "MEDIUM", "sentiment": 0.7},
            {"title": "Economic Council reports retail sales increase by 1.8% year-over-year", "impact": "HIGH", "sentiment": 0.5}
        ]
        
        selected_news = random.choice(news_events)
        title = selected_news["title"]
        impact = selected_news["impact"]
        sentiment = selected_news["sentiment"]
        
        # Inject the news event into the Engine
        # Set pause duration to 20 seconds for demo purposes
        self.engine.inject_news_event(title, impact, sentiment, duration_seconds=20)
        
        # Broadcast news details to UI
        payload = {
            "type": "news",
            "timestamp": time.time(),
            "title": title,
            "impact": impact,
            "sentiment": sentiment,
            "duration": 20
        }
        
        if self.broadcast_callback:
            self.broadcast_callback(payload)

    def force_market_spike(self, direction: str):
        """Forces an artificial price spike on top of the latest live price to test SL / TP / Kill-Switch."""
        if self.latest_price is None:
            self.latest_price = 60000.0 # default fallback
            
        magnitude = 5.0 # 5% sudden spike
        if direction.upper() == "UP":
            self.latest_price *= (1.0 + magnitude / 100.0)
            log_to_db("WARNING", f"Live Feed: FORCED MARKET SPIKE UP (+{magnitude}%)")
        else:
            self.latest_price *= (1.0 - magnitude / 100.0)
            log_to_db("WARNING", f"Live Feed: FORCED MARKET SPIKE DOWN (-{magnitude}%)")
            
        self.current_price = self.latest_price
        
        # Instantly run a tick update to trigger the SL/Kill-Switch instantly
        price = self.latest_price
        volume = 10.0
        tick_data = self.engine.process_tick(price, volume)
        metrics = self.engine.get_dashboard_metrics()
        
        payload = {
            "type": "tick",
            "price": price,
            "volume": volume,
            "sma_200": tick_data.get("sma_200"),
            "ema_9": tick_data.get("ema_9"),
            "ema_21": tick_data.get("ema_21"),
            "vwap": tick_data.get("vwap"),
            "timestamp": tick_data["timestamp"],
            "metrics": metrics.model_dump(),
            "active_position": self.engine.active_position
        }
        if self.broadcast_callback:
            self.broadcast_callback(payload)
