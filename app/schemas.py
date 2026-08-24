from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class RiskConfig(BaseModel):
    daily_loss_limit: float = Field(500.0, description="Max dollar loss for the session before Kill-Switch")
    trailing_stop_pct: float = Field(0.8, description="Trailing stop percentage (e.g. 0.8%)")
    vwap_threshold_pct: float = Field(3.5, description="Max deviation from VWAP allowed for entries (e.g. 3.5%)")
    concrete_floor_threshold_pct: float = Field(4.0, description="Max distance between SMA 200 and VWAP for floor confirmation (e.g. 4.0%)")
    max_position_size: float = Field(1.0, description="Position size in lots/units")
    run_autopilot: bool = Field(True, description="True for autonomous trading, False to pause signal execution")
    risk_amount_usdt: float = Field(40.0, description="Target risk in USD per trade for dynamic sizing by ATR")
    atr_multiplier: float = Field(2.5, description="ATR multiplier for dynamic stop loss and trailing stop")
    breakeven_atr_trigger: float = Field(4.0, description="ATR multiplier above entry to trigger Breakeven protection")
    use_atr_risk: bool = Field(True, description="True to use ATR-based dynamic risk and stops, False for percentage-based")




class TickSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: float
    price: float
    volume: float
    sma_200: Optional[float] = None
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    vwap: Optional[float] = None

class OrderSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: float
    type: str
    status: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    reason: str
    profit_loss: Optional[float] = None
    close_price: Optional[float] = None
    close_timestamp: Optional[float] = None

class NewsEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: float
    title: str
    sentiment: float
    impact: str

class AuditLogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: float
    level: str
    message: str

class DashboardMetrics(BaseModel):
    engine_status: str  # ACTIVE, PAUSED, news_PAUSED, KILL_SWITCH
    session_pnl: float
    total_trades: int
    win_rate: float
    daily_drawdown: float
    kill_switch_active: bool
    account_balance: float
    active_news_event: Optional[str] = None

