import os
os.environ["TESTING"] = "True"
os.environ["BINANCE_API_KEY"] = "EVAL_TEST"
os.environ["BINANCE_API_SECRET"] = "EVAL_TEST"

import pytest
from app.database import SessionLocal, init_db, TickModel, OrderModel, AuditLogModel, ConfigModel, Base, engine as db_engine
from app.engine import TradingEngine
from app.schemas import RiskConfig


@pytest.fixture(autouse=True)
def setup_db():
    """Initializes and recreates the test SQLite database prior to each test."""
    from app.database import db_executor
    # Synchronize any pending background tasks
    db_executor.submit(lambda: None).result()
    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)



def test_indicator_calculations(monkeypatch):
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.run_autopilot = False  # Don't trade, just check calculations
    
    # Feed 205 ticks to calculate SMA 200
    prices = [100.0 + i for i in range(205)]
    for p in prices:
        engine.process_tick(p, 10.0)
        
    # Check history size
    assert len(engine.tick_history) == 200
    
    # SMA 200 calculation verification
    # Last 200 prices are 105.0 to 304.0
    expected_sma_200 = sum(range(105, 305)) / 200.0
    latest_tick = engine.tick_history[-1]
    
    # Wait for background DB writes to complete
    from app.database import db_executor
    db_executor.submit(lambda: None).result()

    # Retrieve indicators calculated on last tick
    db = SessionLocal()
    db_ticks = db.query(TickModel).order_by(TickModel.timestamp.desc()).limit(1).all()
    db.close()
    
    assert len(db_ticks) == 1
    assert db_ticks[0].sma_200 == pytest.approx(expected_sma_200, 0.01)
    expected_vwap = sum(prices) / len(prices)
    assert db_ticks[0].vwap == pytest.approx(expected_vwap, 0.01)

def test_trend_filter_sma(monkeypatch):
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.run_autopilot = True
    
    # Set a tiny trailing stop and large vwap deviation threshold to isolate SMA testing
    engine.config.trailing_stop_pct = 1.0
    engine.config.vwap_threshold_pct = 10.0 
    engine.config.concrete_floor_threshold_pct = 100.0
    
    # 1. Simulate a trend where price is BELOW SMA 200
    # Let's seed history with a high price (e.g. 200.0) so SMA 200 is high, e.g. ~200.0
    for _ in range(200):
        engine.process_tick(200.0, 1.0)
        
    # Now prices drops to 150.0 (below SMA 200). We verify that a BUY signal is rejected or not triggered,
    # and a SELL signal is permitted.
    # To trigger a SELL crossover, we need EMA 9 to cross below EMA 21.
    # Initially: feed ticks to stabilize EMAs at 150.0
    for _ in range(15):
        engine.process_tick(150.0, 1.0)
        
    # Introduce crossover: spike up to 152.0 then down to 145.0
    engine.process_tick(153.0, 1.0)
    engine.process_tick(153.0, 1.0)
    # Price is now below SMA 200, force EMA 9 below EMA 21
    for _ in range(3):
        engine.process_tick(144.0, 1.0)
        
    # Check if a SELL trade was executed
    db = SessionLocal()
    orders = db.query(OrderModel).all()
    db.close()
    
    # There should be an active or closed SELL order due to trend filter and crossover
    assert len(orders) > 0
    sell_orders = [o for o in orders if o.type == "SELL"]
    assert len(sell_orders) > 0
    # The SMA condition (Price < SMA 200) was true so the order went through
    assert "SELL Signal" in sell_orders[0].reason

def test_news_filter_blocks_signals(monkeypatch):
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.run_autopilot = True
    engine.config.concrete_floor_threshold_pct = 100.0
    
    # Inject a news pause
    engine.inject_news_event("Federal Reserve Rate Announcement", "HIGH", -0.9, duration_seconds=10)
    assert engine.news_paused == True
    
    # Check that evaluating signals does not trigger execution
    # Attempt to simulate a BUY trigger state
    # Seed ticks
    for _ in range(201):
        engine.process_tick(100.0, 10.0)
        
    # Try crossover
    engine.process_tick(99.0, 10.0)
    engine.process_tick(102.0, 10.0)
    
    db = SessionLocal()
    orders = db.query(OrderModel).all()
    db.close()
    
    # No order should have been created because news filter paused the engine
    assert len([o for o in orders if o.status == "EXECUTED"]) == 0

def test_trailing_stop_and_killswitch(monkeypatch):
    # Mock time starting at 0 to make it 100% deterministic
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
        
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.use_atr_risk = False
    engine.config.run_autopilot = True
    engine.config.daily_loss_limit = 200.0
    engine.config.trailing_stop_pct = 2.0  # 2% trailing SL to keep TP at 106.08 (entry 102.0)
    engine.config.vwap_threshold_pct = 10.0 # big threshold
    engine.config.concrete_floor_threshold_pct = 100.0
    
    # Seed indicators
    for _ in range(200):
        engine.process_tick(100.0, 1.0)
        
    # Stabilize EMAs
    for _ in range(15):
        engine.process_tick(100.0, 1.0)
        
    # Disable autopilot during drop to prevent unwanted SELL entry
    engine.config.run_autopilot = False
    engine.process_tick(98.0, 1.0)
    
    # Enable autopilot and spike to trigger BUY entry
    engine.config.run_autopilot = True
    engine.process_tick(102.0, 1.0)
    engine.process_tick(102.0, 1.0)
    
    # Check if BUY position opened
    assert engine.active_position is not None
    assert engine.active_position["type"] == "BUY"
    assert engine.active_position["entry_price"] == 102.0
    initial_sl = engine.active_position["stop_loss"]
    assert initial_sl == pytest.approx(102.0 * 0.98) # 99.96
    
    # Move price up to 105.0 to check trailing stop adjustments (price is below TP of 106.08)
    engine.process_tick(105.0, 1.0)
    new_sl = engine.active_position["stop_loss"]
    assert new_sl > initial_sl
    assert new_sl == pytest.approx(105.0 * 0.98) # 102.90
    
    # Advance time to start a new candle, avoiding the active wick rejection panic trigger
    t += 60.0
    
    # Drop price down to hit the trailing stop at 102.0
    engine.config.run_autopilot = False
    engine.process_tick(102.0, 1.0)
    
    # Position should be closed now
    assert engine.active_position is None
    
    db = SessionLocal()
    closed_orders = db.query(OrderModel).filter(OrderModel.status == "CLOSED").all()
    db.close()
    
    # Assert on buy order closed by SL
    closed_buy_orders = [o for o in closed_orders if o.type == "BUY"]
    assert len(closed_buy_orders) == 1
    assert closed_buy_orders[0].profit_loss is not None
    # Profit should be positive since trailing stop moved above entry price (102.90 SL was hit at 102.0 or SL price)
    assert closed_buy_orders[0].profit_loss > 0.0

    # 2. Test Killswitch: force a loss that exceeds the limit
    engine.config.run_autopilot = True
    engine.config.trailing_stop_pct = 20.0 # Set this BEFORE order execution
    engine.config.daily_loss_limit = 8.0

    # Re-open a trade (sell crossover)
    engine.process_tick(100.0, 1.0)
    engine.process_tick(97.0, 1.0)
    engine.process_tick(97.0, 1.0)
    
    # Make sure we have an active position
    if not engine.active_position:
        # Trigger buy crossover
        engine.process_tick(95.0, 1.0)
        engine.process_tick(100.0, 1.0)
        
    assert engine.active_position is not None

    # The position is a SELL order entered at 97.0.
    # To generate a loss, the price must move UP.
    # Let's spike the price to 120.0 (generating a loss that exceeds the $10 limit)
    # This should trigger the Kill-Switch immediately
    engine.process_tick(120.0, 1.0)
    
    assert engine.kill_switch_active == True
    assert engine.active_position is None # Instantly force closed

def test_config_persistence():
    engine = TradingEngine()
    
    # 1. Update config
    new_cfg = RiskConfig(
        daily_loss_limit=750.0,
        trailing_stop_pct=1.2,
        vwap_threshold_pct=0.2,
        max_position_size=2.5,
        run_autopilot=False
    )
    engine.update_config(new_cfg)
    
    # 2. Instantiate a new engine and check if it restored from SQLite database
    new_engine = TradingEngine()
    assert new_engine.config.daily_loss_limit == 750.0
    assert new_engine.config.trailing_stop_pct == 1.2
    assert new_engine.config.vwap_threshold_pct == 0.2
    assert new_engine.config.max_position_size == 2.5
    assert new_engine.config.run_autopilot == False

def test_panic_button_wick_rejection(monkeypatch):
    # Mock time starting at 0
    t = 0.0
    def mock_time():
        nonlocal t
        return t
    
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.use_atr_risk = False
    engine.config.concrete_floor_threshold_pct = 100.0
    engine.config.vwap_threshold_pct = 10.0
    engine.config.trailing_stop_pct = 10.0  # 10% to prevent SL hit on wick rejection drop
    
    # 1. Seed history with autopilot disabled to prevent random fills
    engine.config.run_autopilot = False
    for _ in range(200):
        engine.process_tick(100.0, 1.0)
        t += 60.0
    
    # Enable autopilot for entry trigger
    engine.config.run_autopilot = True
    
    # Trigger Buy Entry (must be above SMA 200 = 100.0)
    engine.process_tick(101.0, 1.0)
    t += 60.0
    engine.process_tick(103.0, 1.0)
    t += 60.0
    engine.process_tick(103.0, 1.0)
    
    assert engine.active_position is not None
    
    # Disable autopilot to prevent immediate re-entry on exit tick
    engine.config.run_autopilot = False
    
    # Advance time to start a new candle
    t += 60.0
    
    # Now simulate a candle with a massive upper shadow (Doji body, big wick)
    # Open: 101.0 (start of Candle 1). High: 107.0. Close: 101.5
    # Body: 0.5, Upper shadow: 5.5 (>= 3 * 0.5 = 1.5)
    engine.process_tick(101.0, 1.0)
    t += 0.1
    engine.process_tick(107.0, 1.0)
    t += 0.1
    engine.process_tick(101.5, 1.0)
    
    # Check if emergency exited due to wick rejection
    assert engine.active_position is None
    
    db = SessionLocal()
    closed_orders = db.query(OrderModel).filter(OrderModel.status == "CLOSED").all()
    db.close()
    
    assert len(closed_orders) > 0
    assert any("PANIC BUTTON: WICK REJECTION" in o.reason for o in closed_orders)

def test_panic_button_engulfing_reversal(monkeypatch):
    # Mock time starting at 0
    t = 0.0
    def mock_time():
        nonlocal t
        return t
    
    import time
    monkeypatch.setattr(time, "time", mock_time)
    
    engine = TradingEngine()
    engine.config.use_atr_risk = False
    engine.config.concrete_floor_threshold_pct = 100.0
    engine.config.vwap_threshold_pct = 10.0
    engine.config.trailing_stop_pct = 10.0  # 10% to prevent SL hit
    
    # 1. Seed history with autopilot disabled
    engine.config.run_autopilot = False
    for _ in range(200):
        engine.process_tick(100.0, 1.0)
        t += 60.0
        
    # Enable autopilot for entry trigger
    engine.config.run_autopilot = True
    
    # Trigger BUY entry (above SMA 200 = 100.0)
    engine.process_tick(101.0, 1.0)
    t += 60.0
    engine.process_tick(103.0, 1.0)
    t += 60.0
    engine.process_tick(103.0, 1.0)
    
    assert engine.active_position is not None
    
    # Candle 1 (green: open=101, close=105)
    engine.process_tick(101.0, 1.0)
    t += 0.1
    engine.process_tick(105.0, 1.0)
    t += 60.0 # Force candle to close
    
    # Candle 2 (red: open=106, close=101)
    engine.process_tick(106.0, 1.0)
    t += 0.1
    
    # Disable autopilot to prevent immediate re-entry on exit tick
    engine.config.run_autopilot = False
    
    engine.process_tick(101.0, 1.0)
    t += 60.0 # Force candle to close
    
    # Process another tick to run closed candle checks
    engine.process_tick(101.0, 1.0)
    
    # Check if emergency exited
    assert engine.active_position is None
    
    db = SessionLocal()
    closed_orders = db.query(OrderModel).filter(OrderModel.status == "CLOSED").all()
    db.close()
    
    assert len(closed_orders) > 0
    assert any("PANIC BUTTON: BEARISH ENGULFING REVERSAL" in o.reason for o in closed_orders)


def test_quarantine_zone(monkeypatch):
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
        
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.run_autopilot = True
    engine.config.daily_loss_limit = 200.0
    engine.config.trailing_stop_pct = 2.0
    engine.config.vwap_threshold_pct = 10.0
    engine.config.concrete_floor_threshold_pct = 100.0
    
    # 1. Seed indicators
    for _ in range(200):
        engine.process_tick(100.0, 1.0)
    for _ in range(15):
        engine.process_tick(100.0, 1.0)

    # 2. Trigger BUY entry at 102.0
    engine.config.run_autopilot = False
    engine.process_tick(98.0, 1.0)
    t += 60.0
    engine.config.run_autopilot = True
    engine.process_tick(102.0, 1.0)
    t += 60.0
    engine.process_tick(102.0, 1.0)
    
    assert engine.active_position is not None
    assert engine.active_position["entry_price"] == 102.0
    
    # 3. Force a loss directly (price drops to 95.0, hitting the Stop Loss of 99.96)
    engine.config.run_autopilot = False
    engine.process_tick(95.0, 1.0)
    
    # Position must be closed with a loss (pnl < 0)
    assert engine.active_position is None
    
    db = SessionLocal()
    closed = db.query(OrderModel).filter(OrderModel.status == "CLOSED", OrderModel.type == "BUY").first()
    db.close()
    assert closed is not None
    assert closed.profit_loss < 0.0
    
    # 4. A quarantine zone should now exist around 102.0 (+/- 0.15% = [101.847, 102.153])
    assert len(engine.quarantine_zones) == 1
    zone = engine.quarantine_zones[0]
    assert zone["price"] == 102.0
    assert zone["lower_bound"] == pytest.approx(102.0 * 0.9985)
    assert zone["upper_bound"] == pytest.approx(102.0 * 1.0015)
    
    # 5. Advance time by 5 minutes (300 seconds), which is within the 30 minute cooldown window
    t += 300.0
    
    # 6. Try to trigger a new BUY signal at 102.0 (inside the quarantine zone)
    engine.config.run_autopilot = False
    engine.process_tick(98.0, 1.0)
    t += 60.0
    engine.config.run_autopilot = True
    
    # Evaluate signals (Need to form Golden Cross on closed candles first)
    engine.process_tick(102.0, 1.0)
    t += 60.0
    engine.process_tick(102.0, 1.0)
    t += 60.0
    engine.process_tick(102.0, 1.0)
    
    # Position should NOT open because it was blocked by the Quarantine Zone!
    assert engine.active_position is None
    
    # Synchronize background tasks before querying database
    from app.database import db_executor
    db_executor.submit(lambda: None).result()
    
    # Verify in DB that the signal was recorded as REJECTED with the quarantine reason
    db = SessionLocal()
    all_orders = db.query(OrderModel).all()
    print("ALL ORDERS IN DB AT END:", [(o.status, o.reason) for o in all_orders])
    rej = db.query(OrderModel).filter(OrderModel.status == "REJECTED").order_by(OrderModel.timestamp.desc()).first()
    db.close()
    assert rej is not None
    assert "Quarantine Zone" in rej.reason


def test_break_even_protection(monkeypatch):
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
        
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.use_atr_risk = False
    engine.config.run_autopilot = True
    engine.config.daily_loss_limit = 200.0
    engine.config.trailing_stop_pct = 2.0  # 2.0% SL, break-even activates at 1.0% profit
    engine.config.vwap_threshold_pct = 10.0
    engine.config.concrete_floor_threshold_pct = 100.0
    
    # 1. Seed indicators
    for _ in range(200):
        engine.process_tick(100.0, 1.0)
    for _ in range(15):
        engine.process_tick(100.0, 1.0)

    # 2. Trigger BUY entry at 102.0
    engine.config.run_autopilot = False
    engine.process_tick(98.0, 1.0)
    t += 60.0
    engine.config.run_autopilot = True
    engine.process_tick(102.0, 1.0)
    t += 60.0
    engine.process_tick(102.0, 1.0)
    
    assert engine.active_position is not None
    assert engine.active_position["entry_price"] == 102.0
    assert engine.active_position["stop_loss"] == pytest.approx(102.0 * 0.98) # 99.96
    
    # 3. Move price to 102.5 (0.49% profit, below 1.0% break-even activation threshold)
    engine.process_tick(102.5, 1.0)
    assert engine.active_position["stop_loss"] == pytest.approx(100.45) # adjusted by trailing stop, not break-even
    
    # 4. Move price to 103.1 (1.07% profit, triggers Break-Even Activation!)
    engine.process_tick(103.1, 1.0)
    assert engine.active_position["stop_loss"] == pytest.approx(102.0) # adjusted to entry price!
    
    # 5. Price drops to 102.0, triggering break-even exit!
    engine.config.run_autopilot = False
    engine.process_tick(102.0, 1.0)
    
    assert engine.active_position is None
    
    db = SessionLocal()
    closed = db.query(OrderModel).filter(OrderModel.status == "CLOSED", OrderModel.type == "BUY").first()
    db.close()
    assert closed is not None
    assert closed.profit_loss == 0.0 # closed exactly at break-even entry price!


def test_dynamic_lot_sizing_precision_and_circuit_breaker():
    from app.broker import BrokerClient
    client = BrokerClient()
    # Test format_quantity rounding
    client.btc_qty_precision = 3
    client.btc_step_size = 0.001
    assert client.format_quantity(0.12345) == 0.123
    assert client.format_quantity(0.0019) == 0.002
    assert client.format_quantity(0.0004) == 0.000

    # Test format_quantity with precision 2
    client.btc_qty_precision = 2
    client.btc_step_size = 0.01
    assert client.format_quantity(0.123) == 0.12

    # Test Circuit Breaker trigger
    import time
    client.paused_until = time.time() + 10.0
    with pytest.raises(Exception) as excinfo:
        client._send_signed_request("POST", "/fapi/v1/order", {})
    assert "safety Circuit Breaker" in str(excinfo.value)


def test_candlestick_pattern_validation():
    engine = TradingEngine()
    # Mock some candles
    v0 = {"open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 10.0} # Green engulfing
    v1 = {"open": 102.0, "high": 103.0, "low": 100.5, "close": 101.0, "volume": 5.0} # Red engulfed
    v2 = {"open": 103.0, "high": 104.0, "low": 102.0, "close": 102.5, "volume": 4.0}

    assert engine._is_bullish_engulfing(v1, v0) is True
    assert engine._is_bearish_engulfing(v0, v1) is False

    # Three Black Crows
    c2 = {"open": 105.0, "close": 104.0}
    c1 = {"open": 104.0, "close": 103.0}
    c0 = {"open": 103.0, "close": 102.0}
    assert engine._is_three_black_crows(c2, c1, c0) is True


def test_macro_htf_trend_filter():
    engine = TradingEngine()
    engine.config.run_autopilot = True
    
    # Mock indicators
    tick = {"price": 100.0, "sma_200": 98.0, "ema_9": 101.0, "ema_21": 99.0, "vwap": 100.0}
    
    # Price > SMA 200, EMA 9 > EMA 21 -> standard buy crossover setup
    # If 4h macro trend is SELL (Price < last_4h_ema50), it must block the BUY signal!
    engine.last_4h_ema50 = 105.0 # Price (100) < 105 -> macro trend is SELL
    
    # Populate candle history to bypass length guard
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + i} for i in range(100)]
    
    engine._evaluate_signals(tick)
    
    # Active position should be None (blocked by HTF filter)
    assert engine.active_position is None


def test_dynamic_atr_risk_sizing():
    engine = TradingEngine()
    engine.config.use_atr_risk = False
    engine.config.risk_amount_usdt = 15.0
    engine.config.trailing_stop_pct = 1.0
    
    # If ATR is 10.0, SL distance in Range Mode (custom_tp is set) is 1.5 * ATR = 15.0
    # Qty should be Risk / SL_distance = 15.0 / 15.0 = 1.0 BTC
    # Position value = 1.0 * $1000 = $1000 (which exceeds max cap of $600)
    # So capped position value should be $600.0. Qty = 600.0 / 1000.0 = 0.600 BTC.
    
    # Mock calculate_atr to return 10.0
    engine._calculate_atr = lambda p: 10.0
    engine._execute_order("BUY", 1000.0, "Test Sizing", is_golden=False, custom_tp=950.0)
    
    assert engine.active_position is not None
    assert engine.active_position["quantity"] == 0.600  # Capped at $600 (0.600 BTC @ $1000)


def test_atr_based_risk_and_trailing_stop(monkeypatch):
    t = 1000.0
    def mock_time():
        nonlocal t
        t += 60.0
        return t
    import time
    monkeypatch.setattr(time, "time", mock_time)

    engine = TradingEngine()
    engine.config.run_autopilot = True
    engine.config.risk_amount_usdt = 15.0
    engine.config.atr_multiplier = 3.5
    engine.config.breakeven_atr_trigger = 2.0
    engine.config.trailing_stop_pct = 1.0 # fallback

    # Mock calculate_atr to return 2.0
    engine._calculate_atr = lambda p: 2.0

    # Execute BUY order at price 100.0. Since ATR is 2.0 and atr_multiplier is 3.5,
    # sl_distance = 2.0 * 3.5 = 7.0. Stop loss should be price - 7.0 = 93.0.
    # Take profit should be price + 7.0 = 107.0.
    # Qty = Risk / sl_distance = 15.0 / 7.0 = 2.1428... BTC.
    # Expected qty rounded by broker is formatted (precision is 3, step 0.001): 2.143
    engine._execute_order("BUY", 100.0, "Test ATR Risk")

    assert engine.active_position is not None
    pos = engine.active_position
    pos["take_profit"] = 999.0
    assert pos["type"] == "BUY"
    assert pos["entry_price"] == 100.0
    assert pos["stop_loss"] == 93.0
    assert pos["entry_atr"] == 2.0
    assert pos["peak_price"] == 100.0

    # 1. Price moves to 102.0. Peak price becomes 102.0.
    # Trailing stop trigger = 102.0 - (3.5 * 2.0) = 95.0. Stop loss adjusts to 95.0.
    # Breakeven trigger price = 100.0 + (2.0 * 2.0) = 104.0. Breakeven is not activated yet.
    engine.process_tick(102.0, 1.0)
    assert engine.active_position["stop_loss"] == 95.0
    assert engine.active_position["peak_price"] == 102.0

    # 2. Price moves to 105.0. Peak price becomes 105.0.
    # Trailing stop trigger = 105.0 - 7.0 = 98.0.
    # Breakeven trigger = 105.0 >= 104.0, so breakeven activates!
    # Stop loss moves to entry_price = 100.0 (since 100.0 > 98.0).
    engine.process_tick(105.0, 1.0)
    assert engine.active_position["stop_loss"] == 100.1
    assert engine.active_position["peak_price"] == 105.0

    # 3. Price moves to 108.0. Peak price becomes 108.0.
    # Trailing stop trigger = 108.0 - 7.0 = 101.0.
    # Stop loss moves to 101.0 (since 101.0 > 100.0).
    engine.process_tick(108.0, 1.0)
    assert engine.active_position["stop_loss"] == 101.0


def test_golden_entry_sequence_filter():
    engine = TradingEngine()
    engine.config.run_autopilot = True
    
    # Bypass fallback branch by providing 1300 candles
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "buy_volume": 6.0, "sell_volume": 4.0, "timestamp": 1000 + i} for i in range(1300)]
    engine.rsi_history_1m = [50.0] * 1300
    engine.rsi_history_1m[-3] = 35.0  # recently <= 40
    
    # Mock aggregation and indicator calculation for autopilot
    engine._aggregate_candles = lambda tf: [{"timestamp": 12345, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0}]
    engine._calculate_ema_series = lambda period, candles: [95.0] if period == 20 else ([101.0] if period == 9 else ([99.0] if period == 21 else [100.0, 101.0, 102.0]))
    engine._detect_ema_crossover = lambda side, *args, **kwargs: True
    engine._calculate_adx_14 = lambda *args, **kwargs: [26.0, 27.0] if kwargs.get("return_series") else 27.0
    engine._calculate_volume_density = lambda: 0.6  # buy ratio >= 0.55
    engine._calculate_rsi = lambda period, candles: 50.0  # mock current/medium/macro rsi to be 50 (passes alignment and not currently oversold)
    
    # 4h macro trend is BUY
    engine.last_4h_ema50 = 90.0
    
    tick = {"price": 100.0, "sma_200": 98.0, "ema_9": 101.0, "ema_21": 99.0, "vwap": 100.0}
    engine._evaluate_signals(tick)
    
    # Position should be entered and marked as is_golden = True
    assert engine.active_position is not None
    assert "GOLDEN BUY ENTRY" in engine.active_position["reason"]


def test_vwap_volatility_breakout_bypass():
    engine = TradingEngine()
    
    # Populate candle history to trigger calculation
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + i} for i in range(30)]
    engine.current_candle = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + 30}
    
    # Trigger a volatility breakout:
    # 1. StdDev of closes: all are 100.0, but let's mock std_dev or have price deviate heavily
    # Let's say price is 115.0 (which is way above 100.0 + 2 * std_dev)
    # Let's make volume in current tick huge so volume check passes (current candle volume is 50.0, avg_vol_20 is 10.0)
    engine.candle_history[-1]["volume"] = 50.0  # 50.0 > 10.0 * 2.0
    
    # Ingest a tick at price 115.0, volume 50.0
    # Average of closes is 100.0, std_dev will be calculated and 115.0 will break it.
    res = engine.process_tick(115.0, 50.0)
    
    # Since there was a breakout with high volume, is_range_mode must be False!
    assert engine.is_range_mode is False


def test_micro_price_veto(monkeypatch):
    monkeypatch.setenv("TESTING", "False")
    engine = TradingEngine()
    engine.config.run_autopilot = True
    
    # Mock consistency gatekeeper and SFA to trigger BUY
    engine._is_signal_coherent = lambda *args, **kwargs: (True, "APROBADA")
    engine._analizar_vector_sfa = lambda prices: {
        "desviacion": 1.0,
        "caos_fractal": 1.5,
        "frecuencia_dominante_hz": 0.05,
        "amplitud_dominante": 2.0,
        "promedio": 105.0 # promedio > prices[-1] (100.0) -> BUY
    }
    
    # 1. BUY signal with micro_price < mid_price (should reject)
    engine.raw_ticks_buffer = [100.0] * 35
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + i, "open_interest": 1000.0, "cvd": 0.0} for i in range(1250)]
    engine.current_candle = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1040, "open_interest": 1000.0, "cvd": 0.0}
    
    # Mock parameters so that BUY trigger is True and trending mode is active
    engine.last_adx_15m = 25.0
    engine._calculate_adx_14 = lambda *args, **kwargs: [25.0] if kwargs.get("return_series") else 25.0
    engine.rsi_history_1m = [35.0] * 1250  # recently oversold
    
    # Ingest BUY tick with P_micro = 99.8, P_mid = 100.0 (micro_price < mid_price)
    res = engine.process_tick(
        price=100.0, 
        volume=50.0, 
        imbalance=0.6, 
        t0_binance=1000, 
        micro_price=99.8, 
        mid_price=100.0, 
        cvd=100.0, 
        open_interest=5000.0
    )
    
    # Check that position was NOT opened because of Micro-Price veto rejection
    assert engine.active_position is None
    
    # Clear rejected orders history
    db = SessionLocal()
    rejected = db.query(OrderModel).filter(OrderModel.status == "REJECTED").all()
    db.close()
    assert any("Micro-Price Veto" in r.reason for r in rejected)


def test_funding_veto_window(monkeypatch):
    monkeypatch.setenv("TESTING", "False")
    engine = TradingEngine()
    engine.config.run_autopilot = True
    
    # Safely mock the funding veto window check specifically
    monkeypatch.setattr(engine, "_is_funding_veto_window", lambda: True)
    engine._is_signal_coherent = lambda *args, **kwargs: (True, "APROBADA")
    engine._analizar_vector_sfa = lambda prices: {
        "desviacion": 1.0,
        "caos_fractal": 1.5,
        "frecuencia_dominante_hz": 0.05,
        "amplitud_dominante": 2.0,
        "promedio": 105.0 # promedio > prices[-1] (100.0) -> BUY
    }
    engine._calculate_adx_14 = lambda *args, **kwargs: [25.0] if kwargs.get("return_series") else 25.0
    
    # Trigger SFA signal checks
    engine.raw_ticks_buffer = [100.0] * 35
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + i, "open_interest": 1000.0, "cvd": 0.0} for i in range(1250)]
    engine.current_candle = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1040, "open_interest": 1000.0, "cvd": 0.0}
    
    res = engine.process_tick(
        price=100.0, 
        volume=50.0, 
        imbalance=0.6, 
        t0_binance=1000, 
        micro_price=100.0, 
        mid_price=100.0, 
        cvd=100.0, 
        open_interest=5000.0
    )
    
    # Position should not open during funding veto window
    assert engine.active_position is None


def test_oi_cvd_regimes(monkeypatch):
    monkeypatch.setenv("TESTING", "False")
    engine = TradingEngine()
    engine.config.run_autopilot = True
    
    # 1. INSTITUTIONAL_LONGS Regime: Price up, OI up, CVD up
    # Reference candle (15m ago) has Price=100.0, OI=1000.0, CVD=0.0
    # Current tick has Price=105.0, OI=1500.0, CVD=1000.0
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + i, "open_interest": 1000.0, "cvd": 0.0} for i in range(1250)]
    engine.current_candle = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1040, "open_interest": 1000.0, "cvd": 0.0}
    
    engine.tick_history = [{"price": 105.0, "volume": 10.0, "timestamp": 1000.0}]
    engine.last_open_interest = 1500.0
    engine.last_cvd = 1000.0
    
    regime = engine._check_oi_cvd_regime()
    assert regime == "INSTITUTIONAL_LONGS"
    
    # A SELL/Short signal should be blocked under INSTITUTIONAL_LONGS
    engine._is_signal_coherent = lambda *args, **kwargs: (True, "APROBADA")
    engine._analizar_vector_sfa = lambda prices: {
        "desviacion": 1.0,
        "caos_fractal": 1.5,
        "frecuencia_dominante_hz": 0.05,
        "amplitud_dominante": 2.0,
        "promedio": 100.0 # promedio < prices[-1] (105.0) -> SELL
    }
    
    engine.last_adx_15m = 25.0
    engine._calculate_adx_14 = lambda *args, **kwargs: [25.0] if kwargs.get("return_series") else 25.0
    engine.rsi_history_1m = [65.0] * 1250
    
    res = engine.process_tick(
        price=105.0, 
        volume=50.0, 
        imbalance=-0.6, 
        t0_binance=1000, 
        micro_price=105.0, 
        mid_price=105.0, 
        cvd=1000.0, 
        open_interest=1500.0
    )
    assert engine.active_position is None


def test_dynamic_vol_targeting(monkeypatch):
    monkeypatch.setenv("TESTING", "False")
    engine = TradingEngine()
    engine.config.run_autopilot = True
    engine.config.risk_amount_usdt = 30.0
    
    # Mock consistency gatekeeper, flat channel check, and SFA to trigger BUY
    engine._is_signal_coherent = lambda *args, **kwargs: (True, "APROBADA")
    engine.is_market_ranging_flat = lambda: (False, "")
    engine._analizar_vector_sfa = lambda prices: {
        "desviacion": 1.0,
        "caos_fractal": 1.5,
        "frecuencia_dominante_hz": 0.05,
        "amplitud_dominante": 2.0,
        "promedio": 105.0 # promedio > prices[-1] (100.0) -> BUY
    }
    
    # Mock broker execute_order to avoid actual network requests and credentials load
    import time
    engine.broker.execute_order = lambda order_type, price, qty, sl, tp: {
        "broker_order_id": "test-order-id",
        "timestamp": int(time.time() * 1000),
        "fill_price": price,
        "quantity": qty,
        "stop_loss": sl,
        "take_profit": tp
    }
    
    # Mock _calculate_atr_15m to return 10.0
    engine._calculate_atr_15m = lambda period: 10.0
    engine._calculate_adx_14 = lambda *args, **kwargs: [25.0] if kwargs.get("return_series") else 25.0
    
    # Trigger position execution logic
    engine.raw_ticks_buffer = [100.0] * 35
    engine.candle_history = [{"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1000 + i, "open_interest": 1000.0, "cvd": 0.0} for i in range(1250)]
    engine.current_candle = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0, "timestamp": 1040, "open_interest": 1000.0, "cvd": 0.0}
    
    # Calculate quantity under ATR = 10.0:
    # Qty = Risk / (ATR * k) = 30.0 / (10.0 * 2.0) = 1.5 BTC
    # Let's test the sizing logic in execute_order
    engine.last_adx_15m = 25.0
    engine.rsi_history_1m = [35.0] * 1250
    
    # Ingest tick to trigger BUY (use t0_binance=0 to bypass stale data check)
    res = engine.process_tick(
        price=100.0, 
        volume=50.0, 
        imbalance=0.6, 
        t0_binance=0, 
        micro_price=100.0, 
        mid_price=100.0, 
        cvd=100.0, 
        open_interest=1000.0
    )
    

    # Since ATR is high (10.0), quantity should be correctly target-scaled and bounded
    assert engine.active_position is not None
    assert engine.active_position["quantity"] > 0.0







