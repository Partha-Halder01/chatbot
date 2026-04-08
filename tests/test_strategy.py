"""Tests for the trading strategy signal scorer."""

import pytest
from datetime import datetime
from core.strategy import TradingStrategy
from models.signal import SignalDirection
from config.settings import StrategyConfig, IndicatorConfig


class TestTradingStrategy:
    def setup_method(self):
        config = StrategyConfig()
        config.signal_persistence_candles = 1  # Simplify for testing
        self.strategy = TradingStrategy(config, IndicatorConfig())

    def test_hold_on_empty_indicators(self):
        """Test HOLD signal when no indicators provided."""
        signal = self.strategy.evaluate("TEST", {})
        assert signal.direction == SignalDirection.HOLD

    def test_strong_buy_signal(self):
        """Test BUY signal with all bullish indicators."""
        indicators = {
            "ema_bullish": True,
            "ema_bullish_cross": True,
            "ema_bearish_cross": False,
            "rsi": 30,
            "rsi_trend": "rising",
            "macd_histogram": 0.5,
            "macd_hist_prev": -0.1,
            "macd_crossover": "bullish",
            "bb_position": 0.05,
            "bb_near_lower": True,
            "bb_near_upper": False,
            "above_vwap": True,
            "volume_spike": True,
            "volume_spike_bullish": True,
            "volume_spike_bearish": False,
            "volume_ratio": 2.0,
        }
        signal = self.strategy.evaluate("TEST", indicators)
        assert signal.score > 0
        assert signal.direction == SignalDirection.BUY

    def test_strong_sell_signal(self):
        """Test SELL signal with all bearish indicators."""
        indicators = {
            "ema_bullish": False,
            "ema_bullish_cross": False,
            "ema_bearish_cross": True,
            "rsi": 75,
            "rsi_trend": "falling",
            "macd_histogram": -0.5,
            "macd_hist_prev": 0.1,
            "macd_crossover": "bearish",
            "bb_position": 0.95,
            "bb_near_lower": False,
            "bb_near_upper": True,
            "above_vwap": False,
            "volume_spike": True,
            "volume_spike_bullish": False,
            "volume_spike_bearish": True,
            "volume_ratio": 2.0,
        }
        signal = self.strategy.evaluate("TEST", indicators)
        assert signal.score < 0
        assert signal.direction == SignalDirection.SELL

    def test_hold_on_mixed_signals(self):
        """Test HOLD when signals are mixed (fewer than 3 agree)."""
        indicators = {
            "ema_bullish": True,
            "ema_bullish_cross": False,
            "ema_bearish_cross": False,
            "rsi": 50,
            "rsi_trend": "flat",
            "macd_histogram": 0.01,
            "macd_hist_prev": 0.01,
            "macd_crossover": "none",
            "bb_position": 0.5,
            "bb_near_lower": False,
            "bb_near_upper": False,
            "above_vwap": False,
            "volume_spike": False,
            "volume_spike_bullish": False,
            "volume_spike_bearish": False,
            "volume_ratio": 0.8,
        }
        signal = self.strategy.evaluate("TEST", indicators)
        # With mixed signals, should be HOLD
        assert signal.direction == SignalDirection.HOLD

    def test_score_clamped(self):
        """Test that scores are clamped to -100 to +100."""
        indicators = {
            "ema_bullish": True,
            "ema_bullish_cross": True,
            "ema_bearish_cross": False,
            "rsi": 25,
            "rsi_trend": "rising",
            "macd_crossover": "bullish",
            "macd_histogram": 1.0,
            "macd_hist_prev": -0.5,
            "bb_position": 0.02,
            "bb_near_lower": True,
            "bb_near_upper": False,
            "above_vwap": True,
            "volume_spike": True,
            "volume_spike_bullish": True,
            "volume_spike_bearish": False,
            "volume_ratio": 3.0,
        }
        signal = self.strategy.evaluate("TEST", indicators)
        assert -100 <= signal.score <= 100

    def test_signal_persistence_required(self):
        """Test that signal must persist for N candles."""
        config = StrategyConfig()
        config.signal_persistence_candles = 3
        config.min_agreeing_signals = 1
        strategy = TradingStrategy(config, IndicatorConfig())

        bullish = {
            "ema_bullish": True, "ema_bullish_cross": True, "ema_bearish_cross": False,
            "rsi": 30, "rsi_trend": "rising",
            "macd_crossover": "bullish", "macd_histogram": 0.5, "macd_hist_prev": -0.1,
            "bb_position": 0.05, "bb_near_lower": True, "bb_near_upper": False,
            "above_vwap": True, "volume_spike": True,
            "volume_spike_bullish": True, "volume_spike_bearish": False,
            "volume_ratio": 2.0,
        }

        # First call — not enough persistence
        s1 = strategy.evaluate("TEST", bullish)
        assert s1.direction == SignalDirection.HOLD

        # Second call — still not enough
        s2 = strategy.evaluate("TEST", bullish)
        assert s2.direction == SignalDirection.HOLD

        # Third call — now persistent enough
        s3 = strategy.evaluate("TEST", bullish)
        assert s3.direction == SignalDirection.BUY
