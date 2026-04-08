"""Tests for the risk manager."""

import pytest
from unittest.mock import patch
from datetime import datetime
from core.risk_manager import RiskManager
from models.signal import TradeSignal, SignalDirection
from models.position import Position
from config.settings import RiskConfig


class TestRiskManager:
    def setup_method(self):
        self.config = RiskConfig()
        self.rm = RiskManager(self.config, capital=100000.0)

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_trade_allowed_basic(self, mock_sqoff, mock_tw):
        """Test basic trade approval with no restrictions."""
        signal = TradeSignal(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            score=75,
            timestamp=datetime.now(),
        )
        allowed, reason = self.rm.check_trade_allowed(signal)
        assert allowed is True
        assert reason == "All checks passed"

    @patch("core.risk_manager.is_trading_window", return_value=False)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_trade_blocked_outside_hours(self, mock_sqoff, mock_tw):
        """Test trade blocked outside trading window."""
        signal = TradeSignal(
            symbol="RELIANCE", direction=SignalDirection.BUY,
            score=75, timestamp=datetime.now(),
        )
        allowed, reason = self.rm.check_trade_allowed(signal)
        assert allowed is False
        assert "Outside trading window" in reason

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=True)
    def test_trade_blocked_squareoff_time(self, mock_sqoff, mock_tw):
        """Test trade blocked during square-off time."""
        signal = TradeSignal(
            symbol="RELIANCE", direction=SignalDirection.BUY,
            score=75, timestamp=datetime.now(),
        )
        allowed, reason = self.rm.check_trade_allowed(signal)
        assert allowed is False
        assert "Square-off" in reason

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_trade_blocked_max_positions(self, mock_sqoff, mock_tw):
        """Test trade blocked when max positions reached."""
        self.rm.open_positions = [
            Position(symbol="TCS", side="BUY", quantity=10, entry_price=3500),
            Position(symbol="INFY", side="BUY", quantity=10, entry_price=1500),
        ]
        signal = TradeSignal(
            symbol="RELIANCE", direction=SignalDirection.BUY,
            score=75, timestamp=datetime.now(),
        )
        allowed, reason = self.rm.check_trade_allowed(signal)
        assert allowed is False
        assert "Max open positions" in reason

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_trade_blocked_duplicate_symbol(self, mock_sqoff, mock_tw):
        """Test trade blocked for duplicate symbol."""
        self.rm.open_positions = [
            Position(symbol="RELIANCE", side="BUY", quantity=10, entry_price=2500),
        ]
        signal = TradeSignal(
            symbol="RELIANCE", direction=SignalDirection.BUY,
            score=75, timestamp=datetime.now(),
        )
        allowed, reason = self.rm.check_trade_allowed(signal)
        assert allowed is False
        assert "Already have open position" in reason

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_trade_blocked_daily_loss_limit(self, mock_sqoff, mock_tw):
        """Test trade halted when daily loss limit exceeded."""
        self.rm.daily_realized_pnl = -3100  # Over 3% of 100000
        signal = TradeSignal(
            symbol="RELIANCE", direction=SignalDirection.BUY,
            score=75, timestamp=datetime.now(),
        )
        allowed, reason = self.rm.check_trade_allowed(signal)
        assert allowed is False
        assert self.rm.is_halted is True

    def test_position_sizing_basic(self):
        """Test position sizing with ATR."""
        quantity, sl, tp = self.rm.calculate_position_size(price=2500, atr=25)

        # Risk per trade: 100000 * 0.01 = 1000
        # SL distance: max(25 * 1.5, 2500 * 0.005) = max(37.5, 12.5) = 37.5
        # Quantity: 1000 / 37.5 = 26
        assert quantity > 0
        assert sl < 2500  # SL below entry for BUY
        assert tp > 2500  # TP above entry for BUY

    def test_position_sizing_caps_at_20_pct(self):
        """Test position value capped at 20% of capital."""
        # Very cheap stock with tiny ATR -> lots of shares
        quantity, sl, tp = self.rm.calculate_position_size(price=10, atr=0.1)
        max_value = 100000 * 0.20
        assert quantity * 10 <= max_value

    def test_trailing_stop_buy(self):
        """Test trailing stop for BUY position."""
        pos = Position(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=2500, current_price=2515,  # 0.6% profit
        )
        new_sl = self.rm.update_trailing_stop(pos, 2515)
        assert new_sl is not None
        assert new_sl > 2500  # SL should be above entry

    def test_trailing_stop_not_triggered_yet(self):
        """Test trailing stop not activated with small profit."""
        pos = Position(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=2500, current_price=2505,  # 0.2% profit
        )
        new_sl = self.rm.update_trailing_stop(pos, 2505)
        assert new_sl is None  # Not yet at activation threshold

    @patch("core.risk_manager.is_square_off_time", return_value=True)
    def test_should_exit_squareoff(self, mock_sqoff):
        """Test position exit at square-off time."""
        pos = Position(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=2500, current_price=2510,
        )
        should_exit, reason = self.rm.should_exit_position(pos, 2510)
        assert should_exit is True
        assert "Square-off" in reason

    def test_record_trade_result(self):
        """Test P&L recording."""
        self.rm.record_trade_result(500)
        assert self.rm.daily_realized_pnl == 500
        assert self.rm.trades_today == 1

        self.rm.record_trade_result(-200)
        assert self.rm.daily_realized_pnl == 300
        assert self.rm.trades_today == 2

    def test_reset_daily(self):
        """Test daily counter reset."""
        self.rm.daily_realized_pnl = 1000
        self.rm.trades_today = 5
        self.rm.is_halted = True

        self.rm.reset_daily()
        assert self.rm.daily_realized_pnl == 0
        assert self.rm.trades_today == 0
        assert self.rm.is_halted is False
