"""Risk management — the guardian of capital. Every trade must pass through here."""

from datetime import datetime
from models.signal import TradeSignal
from models.position import Position
from config.settings import RiskConfig
from utils.logger import setup_logger
from utils.helpers import is_trading_window, is_square_off_time

logger = setup_logger("risk_manager")


class RiskManager:
    """Enforces risk limits on every trade decision."""

    def __init__(self, config: RiskConfig = None, capital: float = 100000.0):
        self.config = config or RiskConfig()
        self.capital = capital

        # Daily tracking
        self.daily_realized_pnl: float = 0.0
        self.trades_today: int = 0
        self.is_halted: bool = False
        self.halt_reason: str = ""

        # Open positions tracked externally but referenced here
        self._open_positions: list[Position] = []

    @property
    def open_positions(self) -> list[Position]:
        return self._open_positions

    @open_positions.setter
    def open_positions(self, positions: list[Position]):
        self._open_positions = positions

    def check_trade_allowed(self, signal: TradeSignal) -> tuple[bool, str]:
        """
        Run all pre-trade checks. Returns (allowed, reason).
        ALL checks must pass for a trade to be allowed.
        """
        # Check 1: Is trading halted?
        if self.is_halted:
            return False, f"Trading halted: {self.halt_reason}"

        # Check 2: Is it within trading hours?
        if not is_trading_window():
            return False, "Outside trading window (09:30-14:30 IST)"

        # Check 3: Is it square-off time?
        if is_square_off_time():
            return False, "Square-off time — no new trades"

        # Check 4: Daily loss limit
        total_unrealized = sum(p.unrealized_pnl for p in self._open_positions)
        total_pnl = self.daily_realized_pnl + total_unrealized
        max_loss = self.capital * (self.config.max_daily_loss_pct / 100)

        if total_pnl < -max_loss:
            self.is_halted = True
            self.halt_reason = (
                f"Daily loss limit hit: ₹{total_pnl:.2f} "
                f"(limit: -₹{max_loss:.2f})"
            )
            logger.warning(self.halt_reason)
            return False, self.halt_reason

        # Check 5: Max open positions
        if len(self._open_positions) >= self.config.max_open_positions:
            return False, (
                f"Max open positions reached: {len(self._open_positions)}/"
                f"{self.config.max_open_positions}"
            )

        # Check 6: Don't open duplicate position in same symbol
        for pos in self._open_positions:
            if pos.symbol == signal.symbol:
                return False, f"Already have open position in {signal.symbol}"

        # Check 7: Capital reserve
        available = self.capital + self.daily_realized_pnl
        if available < self.config.min_capital_reserve:
            return False, (
                f"Capital below reserve: ₹{available:.2f} "
                f"(reserve: ₹{self.config.min_capital_reserve:.2f})"
            )

        return True, "All checks passed"

    def calculate_position_size(
        self, price: float, atr: float | None = None
    ) -> tuple[int, float, float]:
        """
        Calculate position size based on risk-per-trade rule.
        Returns (quantity, stop_loss_price, take_profit_price).
        """
        risk_amount = self.capital * (self.config.max_risk_per_trade_pct / 100)

        # Stop-loss distance: use ATR if available, otherwise fixed percentage
        if atr and atr > 0:
            sl_distance = max(atr * 1.5, price * self.config.stop_loss_pct / 100)
        else:
            sl_distance = price * self.config.stop_loss_pct / 100

        # Position size: risk_amount / sl_distance
        quantity = int(risk_amount / sl_distance) if sl_distance > 0 else 0

        # Minimum 1 share
        quantity = max(1, quantity)

        # Cap position value at 20% of capital
        max_value = self.capital * 0.20
        max_qty = int(max_value / price) if price > 0 else 0
        quantity = min(quantity, max_qty)

        # Calculate SL and TP prices
        stop_loss = round(price - sl_distance, 2)  # For BUY
        take_profit = round(price + (sl_distance * 2), 2)  # 2:1 reward-to-risk ratio

        logger.info(
            f"Position sizing: price=₹{price} qty={quantity} "
            f"SL=₹{stop_loss} TP=₹{take_profit} "
            f"risk=₹{risk_amount:.2f} sl_dist=₹{sl_distance:.2f}"
        )

        return quantity, stop_loss, take_profit

    def update_trailing_stop(self, position: Position, current_price: float) -> float | None:
        """
        Update trailing stop-loss for an open position.
        Returns the new trailing SL price, or None if not triggered.
        """
        if position.side == "BUY":
            profit_pct = ((current_price - position.entry_price) / position.entry_price) * 100

            if profit_pct >= self.config.trailing_activation_pct:
                # Trail by trailing_stop_pct below current price
                new_sl = current_price * (1 - self.config.trailing_stop_pct / 100)
                new_sl = round(new_sl, 2)

                # Only move SL up, never down
                if new_sl > position.trailing_sl:
                    position.trailing_sl = new_sl
                    logger.info(
                        f"Trailing SL updated for {position.symbol}: ₹{new_sl} "
                        f"(profit: {profit_pct:.2f}%)"
                    )
                    return new_sl

        elif position.side == "SELL":
            profit_pct = ((position.entry_price - current_price) / position.entry_price) * 100

            if profit_pct >= self.config.trailing_activation_pct:
                new_sl = current_price * (1 + self.config.trailing_stop_pct / 100)
                new_sl = round(new_sl, 2)

                if position.trailing_sl == 0 or new_sl < position.trailing_sl:
                    position.trailing_sl = new_sl
                    logger.info(
                        f"Trailing SL updated for {position.symbol}: ₹{new_sl} "
                        f"(profit: {profit_pct:.2f}%)"
                    )
                    return new_sl

        return None

    def should_exit_position(self, position: Position, current_price: float) -> tuple[bool, str]:
        """Check if a position should be exited."""
        # Time-based exit
        if position.hold_duration_minutes >= self.config.max_hold_minutes:
            return True, f"Max hold time reached ({self.config.max_hold_minutes} min)"

        # Square-off time
        if is_square_off_time():
            return True, "Square-off time (15:10 IST)"

        # Trailing stop-loss hit
        if position.trailing_sl > 0:
            if position.side == "BUY" and current_price <= position.trailing_sl:
                return True, f"Trailing SL hit at ₹{position.trailing_sl}"
            elif position.side == "SELL" and current_price >= position.trailing_sl:
                return True, f"Trailing SL hit at ₹{position.trailing_sl}"

        return False, ""

    def record_trade_result(self, pnl: float):
        """Record a completed trade's P&L."""
        self.daily_realized_pnl += pnl
        self.trades_today += 1
        logger.info(
            f"Trade #{self.trades_today} P&L: ₹{pnl:.2f} | "
            f"Daily total: ₹{self.daily_realized_pnl:.2f}"
        )

    def reset_daily(self):
        """Reset daily counters (call at start of each trading day)."""
        self.daily_realized_pnl = 0.0
        self.trades_today = 0
        self.is_halted = False
        self.halt_reason = ""
        logger.info("Daily risk counters reset")

    def get_status(self) -> dict:
        """Get current risk management status."""
        total_unrealized = sum(p.unrealized_pnl for p in self._open_positions)
        return {
            "capital": self.capital,
            "daily_realized_pnl": round(self.daily_realized_pnl, 2),
            "daily_unrealized_pnl": round(total_unrealized, 2),
            "daily_total_pnl": round(self.daily_realized_pnl + total_unrealized, 2),
            "trades_today": self.trades_today,
            "open_positions": len(self._open_positions),
            "max_open_positions": self.config.max_open_positions,
            "is_halted": self.is_halted,
            "halt_reason": self.halt_reason,
            "daily_loss_limit": round(
                self.capital * self.config.max_daily_loss_pct / 100, 2
            ),
        }
