"""Tests for the order executor."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from core.order_executor import OrderExecutor
from core.broker import ShoonyaBroker
from core.risk_manager import RiskManager
from models.signal import TradeSignal, SignalDirection
from models.order import OrderStatus
from config.settings import Settings, RiskConfig


class TestOrderExecutor:
    def setup_method(self):
        settings = Settings()
        settings.trading_mode = "paper"
        self.broker = ShoonyaBroker(settings)
        self.broker.is_paper_mode = True
        self.broker.is_logged_in = True
        self.risk_manager = RiskManager(RiskConfig(), capital=100000.0)
        self.executor = OrderExecutor(self.broker, self.risk_manager)

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_execute_buy_signal(self, mock_sqoff, mock_tw):
        """Test executing a BUY signal in paper mode."""
        signal = TradeSignal(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            score=75,
            timestamp=datetime.now(),
            llm_confirmed=True,
            llm_confidence=85,
        )
        order = self.executor.execute_signal(signal, current_price=2500, atr=25)

        assert order is not None
        assert order.status == OrderStatus.COMPLETED
        assert order.broker_order_id.startswith("PAPER_")
        assert len(self.risk_manager.open_positions) == 1

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_execute_sell_signal(self, mock_sqoff, mock_tw):
        """Test executing a SELL signal."""
        signal = TradeSignal(
            symbol="RELIANCE",
            direction=SignalDirection.SELL,
            score=-80,
            timestamp=datetime.now(),
        )
        order = self.executor.execute_signal(signal, current_price=2500, atr=25)

        assert order is not None
        assert order.stop_loss > 2500  # SL above entry for SELL
        assert order.take_profit < 2500  # TP below entry for SELL

    @patch("core.risk_manager.is_trading_window", return_value=False)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_execute_blocked_by_risk(self, mock_sqoff, mock_tw):
        """Test order blocked by risk manager."""
        signal = TradeSignal(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            score=75,
            timestamp=datetime.now(),
        )
        order = self.executor.execute_signal(signal, current_price=2500)
        assert order is None

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_close_position(self, mock_sqoff, mock_tw):
        """Test closing an open position."""
        # First open a position
        signal = TradeSignal(
            symbol="RELIANCE", direction=SignalDirection.BUY,
            score=75, timestamp=datetime.now(),
        )
        self.executor.execute_signal(signal, current_price=2500, atr=25)
        assert len(self.risk_manager.open_positions) == 1

        # Close it
        position = self.risk_manager.open_positions[0]
        position.current_price = 2520  # Price moved up
        order = self.executor.close_position(position, "Test close")

        assert order is not None
        assert len(self.risk_manager.open_positions) == 0
        assert self.risk_manager.daily_realized_pnl != 0

    @patch("core.risk_manager.is_trading_window", return_value=True)
    @patch("core.risk_manager.is_square_off_time", return_value=False)
    def test_close_all_positions(self, mock_sqoff, mock_tw):
        """Test emergency close all."""
        # Open two positions
        for symbol in ["RELIANCE", "TCS"]:
            signal = TradeSignal(
                symbol=symbol, direction=SignalDirection.BUY,
                score=75, timestamp=datetime.now(),
            )
            self.executor.execute_signal(signal, current_price=2500, atr=25)

        assert len(self.risk_manager.open_positions) == 2

        # Close all
        self.executor.close_all_positions("Emergency test")
        assert len(self.risk_manager.open_positions) == 0
