import json
import os
import asyncio
from dotenv import load_dotenv
load_dotenv()
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db, SessionLocal, AuditLogModel, OrderModel, TickModel, log_to_db
from app.engine import TradingEngine
from app.feed import MarketDataFeed
from app.schemas import RiskConfig
from pydantic import BaseModel

class ErrorLogSchema(BaseModel):
    message: str
    source: str
    lineno: int
    colno: int
    error: str

app = FastAPI(title="SFA-IFA Pro Quantitative Platform")

# Setup Engine and Feed
engine = TradingEngine()
feed = MarketDataFeed(engine)

# Active WebSockets clients
active_connections: Set[WebSocket] = set()

async def self_healing_background_task(engine_inst: TradingEngine):
    """Loop de sincronización REST bidireccional cada 5 minutos para evitar desincronizaciones."""
    await asyncio.sleep(60)  # Esperar 1 minuto tras el arranque
    while True:
        try:
            engine_inst.run_self_healing_check()
        except Exception as e:
            log_to_db("WARNING", f"Error in self_healing_background_task loop: {e}")
        await asyncio.sleep(300)  # 5 minutos

# Initialize Database on Startup
@app.on_event("startup")
async def startup_event():
    init_db()
    log_to_db("INFO", "FastAPI server and SQLite database initialized.")
    
    # Define how feed updates are broadcasted to connected WebSockets
    def broadcast_to_clients(payload: dict):
        # Schedule the coroutine in the main event loop
        asyncio.create_task(broadcast_payload(payload))
        
    feed.start(broadcast_to_clients)
    asyncio.create_task(self_healing_background_task(engine))

@app.on_event("shutdown")
async def shutdown_event():
    feed.stop()
    log_to_db("INFO", "SFA-IFA Pro Platform shut down.")

async def broadcast_payload(payload: dict):
    """Sends a dictionary payload to all active WebSocket clients."""
    if not active_connections:
        return
    
    message = json.dumps(payload)
    disconnected_clients = []
    
    for client in list(active_connections):
        try:
            await client.send_text(message)
        except Exception:
            disconnected_clients.append(client)
            
    for client in disconnected_clients:
        active_connections.discard(client)

# WebSockets Endpoint
@app.exception_handler(Exception)
async def custom_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"message": str(exc)})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    
    db = SessionLocal()
    try:
        # 1. Send recent ticks history to populate the chart on connection (2000 ticks = ~33 mins history)
        recent_ticks = db.query(TickModel).order_by(TickModel.timestamp.desc()).limit(2000).all()
        # Sort chronologically
        recent_ticks = list(reversed(recent_ticks))
        
        history_payload = {
            "type": "history",
            "ticks": [
                {
                    "price": t.price,
                    "volume": t.volume,
                    "sma_200": t.sma_200,
                    "ema_9": t.ema_9,
                    "ema_21": t.ema_21,
                    "vwap": t.vwap,
                    "timestamp": t.timestamp
                }
                for t in recent_ticks
            ],
            "metrics": engine.get_dashboard_metrics().model_dump(),
            "active_position": engine.active_position
        }
        await websocket.send_text(json.dumps(history_payload))
        
        # 2. Keep connection open and handle incoming messages if any
        while True:
            # We can handle custom actions from UI if necessary
            data = await websocket.receive_text()
            # E.g. ping/pong
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        print(f"WebSocket connection error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)
    finally:
        db.close()

# REST APIs

@app.get("/api/status")
async def get_status():
    """Retrieves current platform metrics, active trades, and current configuration."""
    return {
        "metrics": engine.get_dashboard_metrics(),
        "config": engine.config,
        "active_position": engine.active_position
    }

@app.post("/api/config")
async def update_config(config: RiskConfig):
    """Updates the trading engine's risk settings dynamically."""
    engine.update_config(config)
    return {"message": "Configuration updated successfully", "config": engine.config}

@app.get("/api/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=500),
    level: str = Query(None, description="Filter by log level: INFO, WARNING, ERROR, CRITICAL")
):
    """Retrieves audit logs from SQLite database."""
    db = SessionLocal()
    try:
        query = db.query(AuditLogModel)
        if level:
            query = query.filter(AuditLogModel.level == level.upper())
        logs = query.order_by(AuditLogModel.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": l.id,
                "timestamp": l.timestamp,
                "level": l.level,
                "message": l.message
            } for l in logs
        ]
    finally:
        db.close()

@app.get("/api/orders")
async def get_orders(limit: int = Query(100, ge=1, le=500), exclude_rejected: bool = Query(False)):
    """Retrieves trade audit logs from SQLite database."""
    db = SessionLocal()
    try:
        query = db.query(OrderModel)
        if exclude_rejected:
            query = query.filter(OrderModel.status != "REJECTED")
        orders = query.order_by(OrderModel.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": o.id,
                "timestamp": o.timestamp,
                "type": o.type,
                "status": o.status,
                "entry_price": o.entry_price,
                "quantity": o.quantity,
                "stop_loss": o.stop_loss,
                "take_profit": o.take_profit,
                "reason": o.reason,
                "profit_loss": o.profit_loss,
                "close_price": o.close_price,
                "close_timestamp": o.close_timestamp
            } for o in orders
        ]
    finally:
        db.close()

@app.post("/api/killswitch/reset")
async def post_reset_killswitch():
    """Resets the active Kill-Switch state to resume execution."""
    engine.reset_kill_switch()
    return {"message": "Kill-Switch reset successfully", "metrics": engine.get_dashboard_metrics()}

@app.post("/api/database/reset")
async def post_reset_database():
    """Backs up the database and clears all orders and logs to start fresh."""
    import shutil
    from app.database import DB_PATH
    
    if os.path.exists(DB_PATH):
        backup_path = DB_PATH.replace(".db", "_backup_sim.db")
        shutil.copy2(DB_PATH, backup_path)
        
    db = SessionLocal()
    try:
        db.query(OrderModel).delete()
        db.query(AuditLogModel).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
        
    # Reset engine in-memory metrics
    engine.session_pnl = 0.0
    engine.total_trades = 0
    engine.winning_trades = 0
    engine.quarantine_zones = []
    engine.active_position = None
    
    log_to_db("INFO", "DATABASE RESET: Previous simulation history backed up. Ready for real trade logs.")
    
    return {"message": "Database and stats reset successfully", "metrics": engine.get_dashboard_metrics()}

@app.post("/api/trading/force")
async def post_force_entry(direction: str = Query(..., pattern="^(BUY|SELL|buy|sell)$")):
    """Forces the next tick to trigger an entry in the specified direction."""
    engine.force_instant_entry = direction.upper()
    return {"message": f"Successfully forced next crossover trigger to {direction.upper()}."}

@app.post("/api/simulate/spike")
async def post_simulate_spike(direction: str = Query(..., regex="^(UP|DOWN|up|down)$")):
    """Triggers an artificial price spike to test Risk Control parameters."""
    feed.force_market_spike(direction)
    return {"message": f"Market price spike {direction.upper()} forced successfully."}

@app.post("/api/log_error")
async def post_log_error(err: ErrorLogSchema):
    log_to_db("CRITICAL", f"BROWSER EXCEPTION: {err.message} at {err.source}:{err.lineno}:{err.colno} - {err.error}")
    print(f"BROWSER EXCEPTION: {err.message} at {err.source}:{err.lineno}:{err.colno} - {err.error}")
    return {"status": "ok"}

# Mount static folder
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path)

app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
