"""Position data model."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Position:
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: int
    entry_price: float
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_sl: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)
    broker_order_id: str = ""
    is_paper: bool = True

    @property
    def unrealized_pnl(self) -> float:
        if self.current_price == 0:
            return 0.0
        if self.side == "BUY":
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == "BUY":
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

    @property
    def hold_duration_minutes(self) -> float:
        return (datetime.now() - self.entry_time).total_seconds() / 60

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_sl": self.trailing_sl,
            "entry_time": self.entry_time.isoformat(),
            "hold_duration_minutes": round(self.hold_duration_minutes, 1),
            "is_paper": self.is_paper,
        }
