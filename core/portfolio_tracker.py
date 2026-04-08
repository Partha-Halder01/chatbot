"""Portfolio tracker — monitors open positions, updates P&L, manages exits."""

from datetime import datetime
from models.position import Position
from utils.logger import setup_logger

logger = setup_logger("portfolio_tracker")


class PortfolioTracker:
    """Tracks open positions, updates current prices, and manages the trade journal."""

    def __init__(self):
        self.trade_history: list[dict] = []
        self.daily_pnl: float = 0.0

    def update_positions(
        self, positions: list[Position], ltp_map: dict[str, float]
    ):
        """Update current prices for all open positions."""
        for pos in positions:
            if pos.symbol in ltp_map:
                pos.current_price = ltp_map[pos.symbol]

    def record_closed_trade(self, position: Position, exit_price: float, reason: str):
        """Record a completed trade in the journal."""
        if position.side == "BUY":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        trade = {
            "symbol": position.symbol,
            "side": position.side,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "pnl_pct": round(
                ((exit_price - position.entry_price) / position.entry_price) * 100
                if position.side == "BUY"
                else ((position.entry_price - exit_price) / position.entry_price) * 100,
                2,
            ),
            "entry_time": position.entry_time.isoformat(),
            "exit_time": datetime.now().isoformat(),
            "hold_minutes": round(position.hold_duration_minutes, 1),
            "reason": reason,
            "is_paper": position.is_paper,
        }
        self.trade_history.append(trade)
        self.daily_pnl += pnl

        logger.info(
            f"Trade recorded: {trade['side']} {trade['symbol']} | "
            f"P&L: ₹{trade['pnl']} ({trade['pnl_pct']}%) | "
            f"Hold: {trade['hold_minutes']}min | {reason}"
        )

    def get_summary(self) -> dict:
        """Get portfolio summary for dashboard."""
        winning = [t for t in self.trade_history if t["pnl"] > 0]
        losing = [t for t in self.trade_history if t["pnl"] < 0]

        total_trades = len(self.trade_history)
        win_rate = (len(winning) / total_trades * 100) if total_trades > 0 else 0

        avg_win = (
            sum(t["pnl"] for t in winning) / len(winning) if winning else 0
        )
        avg_loss = (
            sum(t["pnl"] for t in losing) / len(losing) if losing else 0
        )

        return {
            "total_trades": total_trades,
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": round(win_rate, 1),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_pnl": round(sum(t["pnl"] for t in self.trade_history), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "best_trade": round(max((t["pnl"] for t in self.trade_history), default=0), 2),
            "worst_trade": round(min((t["pnl"] for t in self.trade_history), default=0), 2),
        }

    def get_recent_trades(self, count: int = 20) -> list[dict]:
        """Get recent trade history."""
        return self.trade_history[-count:]

    def reset_daily(self):
        """Reset daily tracking."""
        self.daily_pnl = 0.0
        logger.info("Daily portfolio tracking reset")
