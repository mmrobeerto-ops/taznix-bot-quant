import os
import time
from sqlalchemy import create_engine, Column, Integer, Float, String, Text, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Database Path
DB_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("TESTING") == "True":
    DB_PATH = os.path.join(DB_DIR, "sfa_ifa_pro_test.db")
else:
    DB_PATH = os.path.join(DB_DIR, "sfa_ifa_pro.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, 
    connect_args={
        "check_same_thread": False,
        "timeout": 15
    } # Required for SQLite multi-thread access in FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TickModel(Base):
    __tablename__ = "ticks"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(Float, nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    sma_200 = Column(Float, nullable=True)
    ema_9 = Column(Float, nullable=True)
    ema_21 = Column(Float, nullable=True)
    vwap = Column(Float, nullable=True)

class OrderModel(Base):
    __tablename__ = "orders"
    
    id = Column(String(50), primary_key=True, index=True)
    timestamp = Column(Float, nullable=False)
    type = Column(String(10), nullable=False)  # BUY, SELL
    status = Column(String(20), nullable=False) # EXECUTED, REJECTED, CLOSED
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    profit_loss = Column(Float, nullable=True)
    close_price = Column(Float, nullable=True)
    close_timestamp = Column(Float, nullable=True)

class NewsEventModel(Base):
    __tablename__ = "news_events"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(Float, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    sentiment = Column(Float, nullable=False)  # -1.0 to 1.0
    impact = Column(String(10), nullable=False)     # HIGH, MEDIUM, LOW

class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(Float, nullable=False, index=True)
    level = Column(String(15), nullable=False)      # INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)

class ConfigModel(Base):
    __tablename__ = "config"
    
    id = Column(String(20), primary_key=True, default="default")
    daily_loss_limit = Column(Float, nullable=False, default=500.0)
    trailing_stop_pct = Column(Float, nullable=False, default=0.5)
    vwap_threshold_pct = Column(Float, nullable=False, default=3.5)
    concrete_floor_threshold_pct = Column(Float, nullable=False, default=4.0)
    max_position_size = Column(Float, nullable=False, default=1.0)
    run_autopilot = Column(Boolean, nullable=False, default=True)
    atr_multiplier = Column(Float, nullable=False, default=3.5)
    breakeven_atr_trigger = Column(Float, nullable=False, default=2.0)
    use_atr_risk = Column(Boolean, nullable=False, default=True)
    risk_amount_usdt = Column(Float, nullable=False, default=40.0)

# Init Database
def init_db():
    Base.metadata.create_all(bind=engine)
    # Self-healing migrations for new config columns
    db = SessionLocal()
    try:
        try:
            db.execute(text("ALTER TABLE config ADD COLUMN atr_multiplier FLOAT DEFAULT 3.5"))
            db.commit()
        except Exception:
            db.rollback()
        try:
            db.execute(text("ALTER TABLE config ADD COLUMN breakeven_atr_trigger FLOAT DEFAULT 2.0"))
            db.commit()
        except Exception:
            db.rollback()
        try:
            db.execute(text("ALTER TABLE config ADD COLUMN use_atr_risk BOOLEAN DEFAULT 1"))
            db.commit()
        except Exception:
            db.rollback()
        try:
            db.execute(text("ALTER TABLE config ADD COLUMN risk_amount_usdt FLOAT DEFAULT 40.0"))
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()

# Helper functions to log into DB (Non-blocking background executor)
import concurrent.futures
db_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

def _sync_log_to_db(level: str, message: str, ts: float):
    db = SessionLocal()
    try:
        log_entry = AuditLogModel(
            timestamp=ts,
            level=level.upper(),
            message=message
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"Error logging to DB: {e}")
    finally:
        db.close()

def log_to_db(level: str, message: str):
    """Submits the database log write to a background thread to prevent latency spikes."""
    ts = time.time()
    db_executor.submit(_sync_log_to_db, level, message, ts)

def _sync_save_tick_to_db(timestamp: float, price: float, volume: float, sma_200: float, ema_9: float, ema_21: float, vwap: float):
    db = SessionLocal()
    try:
        db_tick = TickModel(
            timestamp=timestamp,
            price=price,
            volume=volume,
            sma_200=sma_200,
            ema_9=ema_9,
            ema_21=ema_21,
            vwap=vwap
        )
        db.add(db_tick)
        db.commit()
    except Exception as e:
        print(f"Error saving tick to DB: {e}")
    finally:
        db.close()

def save_tick_to_db(timestamp: float, price: float, volume: float, sma_200: float, ema_9: float, ema_21: float, vwap: float):
    """Submits the tick write to a background thread to prevent latency spikes."""
    db_executor.submit(_sync_save_tick_to_db, timestamp, price, volume, sma_200, ema_9, ema_21, vwap)

# Persistent Configuration Helpers
def load_risk_config() -> dict:
    db = SessionLocal()
    try:
        cfg = db.query(ConfigModel).filter(ConfigModel.id == "default").first()
        if cfg:
            return {
                "daily_loss_limit": cfg.daily_loss_limit,
                "trailing_stop_pct": cfg.trailing_stop_pct,
                "vwap_threshold_pct": cfg.vwap_threshold_pct,
                "concrete_floor_threshold_pct": cfg.concrete_floor_threshold_pct,
                "max_position_size": cfg.max_position_size,
                "run_autopilot": cfg.run_autopilot,
                "atr_multiplier": getattr(cfg, "atr_multiplier", 3.5),
                "breakeven_atr_trigger": getattr(cfg, "breakeven_atr_trigger", 2.0),
                "use_atr_risk": getattr(cfg, "use_atr_risk", True),
                "risk_amount_usdt": getattr(cfg, "risk_amount_usdt", 40.0)
            }
        return {}
    except Exception as e:
        print(f"Error loading config from DB: {e}")
        return {}
    finally:
        db.close()

def save_risk_config(config_dict: dict):
    db = SessionLocal()
    try:
        cfg = db.query(ConfigModel).filter(ConfigModel.id == "default").first()
        if not cfg:
            cfg = ConfigModel(id="default")
            db.add(cfg)
        
        cfg.daily_loss_limit = config_dict.get("daily_loss_limit", cfg.daily_loss_limit)
        cfg.trailing_stop_pct = config_dict.get("trailing_stop_pct", cfg.trailing_stop_pct)
        cfg.vwap_threshold_pct = config_dict.get("vwap_threshold_pct", cfg.vwap_threshold_pct)
        cfg.concrete_floor_threshold_pct = config_dict.get("concrete_floor_threshold_pct", cfg.concrete_floor_threshold_pct)
        cfg.max_position_size = config_dict.get("max_position_size", cfg.max_position_size)
        cfg.run_autopilot = config_dict.get("run_autopilot", cfg.run_autopilot)
        if "atr_multiplier" in config_dict:
            cfg.atr_multiplier = config_dict["atr_multiplier"]
        if "breakeven_atr_trigger" in config_dict:
            cfg.breakeven_atr_trigger = config_dict["breakeven_atr_trigger"]
        if "use_atr_risk" in config_dict:
            cfg.use_atr_risk = config_dict["use_atr_risk"]
        if "risk_amount_usdt" in config_dict:
            cfg.risk_amount_usdt = config_dict["risk_amount_usdt"]
        
        db.commit()
    except Exception as e:
        print(f"Error saving config to DB: {e}")
    finally:
        db.close()

def update_order_stop_loss_async(order_id: str, stop_loss: float):
    """Asynchronously updates an order's stop loss in the database using the background executor."""
    def task():
        db = SessionLocal()
        try:
            db_order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
            if db_order:
                db_order.stop_loss = stop_loss
                db.commit()
        except Exception as e:
            print(f"Error updating stop loss in DB: {e}")
        finally:
            db.close()
            
    db_executor.submit(task)

# Always initialize the database when this module is loaded
init_db()

