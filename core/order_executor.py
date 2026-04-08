"""Order execution engine — translates signals into broker orders."""

from datetime import datetime
from models.order import Order, OrderSide, OrderStatus
from models.signal import TradeSignal, SignalDirection
from models.position import Position
from core.broker import ShoonyaBroker
from core.risk_manager import RiskManager
from utils.logger import setup_logger, get_trade_logger

logger = setup_logger("order_executor")


class OrderExecutor:
    """Executes trade orders with safety checks."""

    def __init__(self, broker: ShoonyaBroker, risk_manager: RiskManager):
        self.broker = broker
        self.risk_manager = risk_manager
        self.pending_orders: list[Order] = []
        self.completed_orders: list[Order] = []
        self.is_paper_mode = broker.is_paper_mode

    def execute_signal(
        self, signal: TradeSignal, current_price: float, atr: float | None = None
    ) -> Order | None:
        """
        Execute a confirmed trade signal.
        Returns the Order if placed, None if rejected.
        """
        # Pre-trade risk check
        allowed, reason = self.risk_manager.check_trade_allowed(signal)
        if not allowed:
            logger.info(f"Trade blocked for {signal.symbol}: {reason}")
            return None

        # Calculate position size and SL/TP
        quantity, stop_loss, take_profit = self.risk_manager.calculate_position_size(
            current_price, atr
        )

        if quantity <= 0:
            logger.warning(f"Position size is 0 for {signal.symbol}")
            return None

        # Adjust SL/TP for direction
        if signal.direction == SignalDirection.SELL:
            # Reverse SL/TP for short
            sl_distance = current_price - stop_loss
            stop_loss = round(current_price + sl_distance, 2)
            take_profit = round(current_price - (sl_distance * 2), 2)

        # Use LLM suggestions if available and reasonable
        if signal.suggested_sl > 0:
            # Only use if it's tighter than our calculated SL
            if signal.direction == SignalDirection.BUY and signal.suggested_sl > stop_loss:
                stop_loss = signal.suggested_sl
            elif signal.direction == SignalDirection.SELL and signal.suggested_sl < stop_loss:
                stop_loss = signal.suggested_sl

        # Create order
        order = Order(
            symbol=signal.symbol,
            side=OrderSide.BUY if signal.direction == SignalDirection.BUY else OrderSide.SELL,
            quantity=quantity,
            price=current_price,
            order_type="MKT",
            stop_loss=stop_loss,
            take_profit=take_profit,
            trail_price=round(
                current_price * self.risk_manager.config.trailing_stop_pct / 100, 2
            ),
            remarks=f"Score:{signal.score} LLM:{signal.llm_confidence}%",
        )

        # Place order
        order_id = self.broker.place_order(order)

        if order_id:
            order.broker_order_id = order_id
            self.pending_orders.append(order)

            # Create position tracking
            position = Position(
                symbol=order.symbol,
                side="BUY" if order.side == OrderSide.BUY else "SELL",
                quantity=order.quantity,
                entry_price=order.fill_price or current_price,
                current_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                broker_order_id=order_id,
                is_paper=self.is_paper_mode,
            )
            self.risk_manager.open_positions.append(position)

            # Log trade
            self._log_trade(order, signal)

            logger.info(
                f"{'[PAPER] ' if self.is_paper_mode else ''}"
                f"ORDER PLACED: {order.side.value} {order.quantity}x {order.symbol} "
                f"@ ₹{current_price} | SL: ₹{stop_loss} | TP: ₹{take_profit} | "
                f"Score: {signal.score} | LLM: {signal.llm_confidence}%"
            )

            return order
        else:
            logger.error(f"Order placement failed for {signal.symbol}: {order.remarks}")
            return None

    def close_position(self, position: Position, reason: str = "") -> Order | None:
        """Close an open position."""
        side = OrderSide.SELL if position.side == "BUY" else OrderSide.BUY

        order = Order(
            symbol=position.symbol,
            side=side,
            quantity=position.quantity,
            price=position.current_price,
            order_type="MKT",
            remarks=f"EXIT: {reason}",
        )

        order_id = self.broker.place_order(order)

        if order_id:
            # Record P&L
            pnl = position.unrealized_pnl
            self.risk_manager.record_trade_result(pnl)

            # Remove from open positions
            self.risk_manager.open_positions = [
                p for p in self.risk_manager.open_positions
                if p.broker_order_id != position.broker_order_id
            ]

            self.completed_orders.append(order)

            logger.info(
                f"{'[PAPER] ' if self.is_paper_mode else ''}"
                f"POSITION CLOSED: {position.side} {position.quantity}x {position.symbol} "
                f"| Entry: ₹{position.entry_price} | Exit: ₹{position.current_price} "
                f"| P&L: ₹{pnl:.2f} | Reason: {reason}"
            )

            return order

        logger.error(f"Failed to close position {position.symbol}")
        return None

    def close_all_positions(self, reason: str = "Emergency close"):
        """Emergency close all open positions."""
        positions = list(self.risk_manager.open_positions)
        logger.warning(f"CLOSING ALL {len(positions)} POSITIONS: {reason}")

        for position in positions:
            self.close_position(position, reason)

    def _log_trade(self, order: Order, signal: TradeSignal):
        """Log trade to CSV journal."""
        try:
            trade_logger = get_trade_logger()
            trade_logger.info(
                f"{datetime.now():%Y-%m-%d %H:%M:%S},{order.symbol},"
                f"{order.side.value},{order.quantity},"
                f"{order.fill_price or order.price},{order.stop_loss},"
                f"{order.take_profit},{signal.score},{signal.llm_confidence},"
                f"{order.status.value},0,{order.remarks}"
            )
        except Exception as e:
            logger.error(f"Trade logging failed: {e}")

    def get_order_history(self) -> list[dict]:
        """Get all orders for dashboard display."""
        orders = []
        for o in self.completed_orders[-50:]:
            orders.append(o.to_dict())
        for o in self.pending_orders[-50:]:
            orders.append(o.to_dict())
        return orders
