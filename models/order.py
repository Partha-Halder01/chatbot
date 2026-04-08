"""Order data model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    BUY = "B"
    SELL = "S"


class OrderStatus(Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    order_type: str = "MKT"  # MKT, LMT
    product_type: str = "I"  # I = Intraday
    exchange: str = "NSE"
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trail_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    fill_price: float = 0.0
    remarks: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "order_type": self.order_type,
            "product_type": self.product_type,
            "exchange": self.exchange,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status.value,
            "broker_order_id": self.broker_order_id,
            "timestamp": self.timestamp.isoformat(),
            "fill_price": self.fill_price,
            "remarks": self.remarks,
        }
