"""Trade signal data model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SignalDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    symbol: str
    direction: SignalDirection
    score: float  # -100 to +100
    timestamp: datetime
    indicators: dict = field(default_factory=dict)
    llm_confidence: float = 0.0
    llm_reasoning: str = ""
    llm_confirmed: bool = False
    suggested_sl: float = 0.0
    suggested_tp: float = 0.0

    @property
    def is_actionable(self) -> bool:
        return self.direction != SignalDirection.HOLD and abs(self.score) >= 60

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "score": self.score,
            "timestamp": self.timestamp.isoformat(),
            "indicators": self.indicators,
            "llm_confidence": self.llm_confidence,
            "llm_reasoning": self.llm_reasoning,
            "llm_confirmed": self.llm_confirmed,
            "suggested_sl": self.suggested_sl,
            "suggested_tp": self.suggested_tp,
        }
