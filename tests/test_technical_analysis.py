"""Tests for the technical analysis engine."""

import pytest
from datetime import datetime, timedelta
from models.candle import Candle
from core.technical_analysis import TechnicalAnalyzer
from config.settings import IndicatorConfig


def make_candles(prices: list[float], interval: int = 5) -> list[Candle]:
    """Create a list of candles from close prices with synthetic OHLCV."""
    candles = []
    base_time = datetime(2026, 4, 8, 9, 30)
    for i, price in enumerate(prices):
        candles.append(Candle(
            timestamp=base_time + timedelta(minutes=i * interval),
            symbol="TEST",
            open=price * 0.999,
            high=price * 1.002,
            low=price * 0.998,
            close=price,
            volume=100000 + (i * 1000),
            interval=interval,
        ))
    return candles


class TestTechnicalAnalyzer:
    def setup_method(self):
        self.analyzer = TechnicalAnalyzer(IndicatorConfig())

    def test_candles_to_df(self):
        """Test candle list to DataFrame conversion."""
        candles = make_candles([100, 101, 102])
        df = self.analyzer.candles_to_df(candles)
        assert len(df) == 3
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df["close"].iloc[-1] == 102

    def test_candles_to_df_empty(self):
        """Test empty candle list."""
        df = self.analyzer.candles_to_df([])
        assert df.empty

    def test_compute_all_insufficient_data(self):
        """Test that compute_all returns empty with insufficient data."""
        candles = make_candles([100] * 10)
        result = self.analyzer.compute_all(candles)
        assert result == {}

    def test_compute_all_with_enough_data(self):
        """Test full indicator computation with sufficient data."""
        # Generate 50 candles with uptrend
        prices = [100 + i * 0.5 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        assert result != {}
        assert "rsi" in result
        assert "current_price" in result
        assert result["current_price"] == prices[-1]

    def test_rsi_computation(self):
        """Test RSI is within valid range."""
        prices = [100 + i * 0.5 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "rsi" in result:
            assert 0 <= result["rsi"] <= 100

    def test_rsi_uptrend(self):
        """Test RSI is high in strong uptrend."""
        prices = [100 + i * 2 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "rsi" in result:
            assert result["rsi"] > 50

    def test_ema_crossover_detection(self):
        """Test EMA bullish/bearish detection."""
        prices = [100 + i * 0.5 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "ema_bullish" in result:
            # Uptrend should have short EMA above long EMA
            assert result["ema_bullish"] is True

    def test_bollinger_bands(self):
        """Test Bollinger Band values are logical."""
        prices = [100 + i * 0.3 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "bb_upper" in result and "bb_lower" in result:
            assert result["bb_upper"] > result["bb_lower"]
            assert result["bb_upper"] > result["bb_middle"]
            assert result["bb_lower"] < result["bb_middle"]

    def test_volume_analysis(self):
        """Test volume ratio computation."""
        prices = [100 + i * 0.2 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "volume_ratio" in result:
            assert result["volume_ratio"] > 0

    def test_atr_positive(self):
        """Test ATR is always positive."""
        prices = [100 + i * 0.5 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "atr" in result:
            assert result["atr"] > 0

    def test_support_resistance(self):
        """Test pivot-based S/R levels."""
        prices = [100 + i * 0.2 for i in range(50)]
        candles = make_candles(prices)
        result = self.analyzer.compute_all(candles)

        if "support1" in result and "resistance1" in result:
            assert result["support1"] < result["resistance1"]

    def test_candle_summary(self):
        """Test candle summary text generation."""
        prices = [100, 101, 102, 103, 104, 105]
        candles = make_candles(prices)
        summary = self.analyzer.get_recent_candle_summary(candles, count=3)
        assert "105.00" in summary
        assert len(summary.split("\n")) == 3
