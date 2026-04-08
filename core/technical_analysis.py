"""Technical analysis engine using pure pandas/numpy for indicator computation."""

import pandas as pd
import numpy as np
from models.candle import Candle
from utils.logger import setup_logger
from config.settings import IndicatorConfig

logger = setup_logger("technical_analysis")


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Compute Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    """Compute Simple Moving Average."""
    return series.rolling(window=period).mean()


class TechnicalAnalyzer:
    """Computes technical indicators on OHLCV candle data."""

    def __init__(self, config: IndicatorConfig = None):
        self.config = config or IndicatorConfig()

    def candles_to_df(self, candles: list[Candle]) -> pd.DataFrame:
        """Convert a list of Candle objects to a pandas DataFrame."""
        if not candles:
            return pd.DataFrame()

        data = {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df

    def compute_all(self, candles: list[Candle]) -> dict:
        """Compute all indicators and return a summary dictionary."""
        df = self.candles_to_df(candles)
        if df.empty or len(df) < 30:
            return {}

        result = {}

        # RSI
        rsi_series = self._compute_rsi(df)
        if rsi_series is not None and len(rsi_series) >= 2:
            rsi = rsi_series.iloc[-1]
            rsi_prev = rsi_series.iloc[-2]
            if not np.isnan(rsi):
                result["rsi"] = round(float(rsi), 2)
                result["rsi_prev"] = round(float(rsi_prev), 2) if not np.isnan(rsi_prev) else 0.0
                result["rsi_trend"] = "rising" if rsi > rsi_prev else "falling"
                result["rsi_overbought"] = rsi > self.config.rsi_overbought
                result["rsi_oversold"] = rsi < self.config.rsi_oversold

        # MACD
        macd_data = self._compute_macd(df)
        result.update(macd_data)

        # Bollinger Bands
        bb_data = self._compute_bollinger(df)
        result.update(bb_data)

        # EMA crossover
        ema_data = self._compute_ema(df)
        result.update(ema_data)

        # VWAP
        vwap = self._compute_vwap(df)
        if vwap is not None:
            result["vwap"] = vwap
            result["price_vs_vwap"] = df["close"].iloc[-1] - vwap
            result["above_vwap"] = df["close"].iloc[-1] > vwap

        # Volume analysis
        vol_data = self._compute_volume(df)
        result.update(vol_data)

        # ATR
        atr = self._compute_atr(df)
        if atr is not None:
            result["atr"] = atr

        # Support / Resistance (pivot points)
        sr_data = self._compute_support_resistance(df)
        result.update(sr_data)

        # Current price
        result["current_price"] = df["close"].iloc[-1]

        return result

    def _compute_rsi(self, df: pd.DataFrame) -> pd.Series | None:
        """Compute RSI using Wilder's smoothing method."""
        try:
            period = self.config.rsi_period
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)

            avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

            # When avg_loss is 0, RSI = 100; when avg_gain is 0, RSI = 0
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            # Handle edge cases: no losses -> RSI=100, no gains -> RSI=0
            rsi = rsi.fillna(100)
            rsi[avg_gain == 0] = 0
            return rsi
        except Exception as e:
            logger.debug(f"RSI computation failed: {e}")
        return None

    def _compute_macd(self, df: pd.DataFrame) -> dict:
        """Compute MACD, signal line, and histogram."""
        try:
            fast_ema = _ema(df["close"], self.config.macd_fast)
            slow_ema = _ema(df["close"], self.config.macd_slow)
            macd_line = fast_ema - slow_ema
            signal_line = _ema(macd_line, self.config.macd_signal)
            histogram = macd_line - signal_line

            macd_val = float(macd_line.iloc[-1])
            signal_val = float(signal_line.iloc[-1])
            hist_val = float(histogram.iloc[-1])
            prev_hist = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0

            if np.isnan(macd_val) or np.isnan(signal_val) or np.isnan(hist_val):
                return {}

            return {
                "macd": round(macd_val, 4),
                "macd_signal": round(signal_val, 4),
                "macd_histogram": round(hist_val, 4),
                "macd_hist_prev": round(prev_hist, 4),
                "macd_crossover": (
                    "bullish" if hist_val > 0 and prev_hist <= 0
                    else "bearish" if hist_val < 0 and prev_hist >= 0
                    else "none"
                ),
            }
        except Exception as e:
            logger.debug(f"MACD computation failed: {e}")
        return {}

    def _compute_bollinger(self, df: pd.DataFrame) -> dict:
        """Compute Bollinger Bands."""
        try:
            period = self.config.bb_period
            std_dev = self.config.bb_std

            mid = _sma(df["close"], period)
            std = df["close"].rolling(window=period).std()
            upper = mid + (std * std_dev)
            lower = mid - (std * std_dev)

            upper_val = float(upper.iloc[-1])
            mid_val = float(mid.iloc[-1])
            lower_val = float(lower.iloc[-1])
            price = df["close"].iloc[-1]

            if np.isnan(upper_val) or np.isnan(lower_val):
                return {}

            width = upper_val - lower_val
            bb_position = (price - lower_val) / width if width > 0 else 0.5

            return {
                "bb_upper": round(upper_val, 2),
                "bb_middle": round(mid_val, 2),
                "bb_lower": round(lower_val, 2),
                "bb_position": round(bb_position, 4),
                "bb_near_lower": bb_position < 0.1,
                "bb_near_upper": bb_position > 0.9,
            }
        except Exception as e:
            logger.debug(f"Bollinger computation failed: {e}")
        return {}

    def _compute_ema(self, df: pd.DataFrame) -> dict:
        """Compute EMA crossover signals."""
        try:
            ema_short = _ema(df["close"], self.config.ema_short)
            ema_long = _ema(df["close"], self.config.ema_long)

            short_val = float(ema_short.iloc[-1])
            long_val = float(ema_long.iloc[-1])
            prev_short = float(ema_short.iloc[-2]) if len(ema_short) >= 2 else short_val
            prev_long = float(ema_long.iloc[-2]) if len(ema_long) >= 2 else long_val

            if np.isnan(short_val) or np.isnan(long_val):
                return {}

            bullish_cross = prev_short <= prev_long and short_val > long_val
            bearish_cross = prev_short >= prev_long and short_val < long_val

            return {
                "ema_short": round(short_val, 2),
                "ema_long": round(long_val, 2),
                "ema_bullish": short_val > long_val,
                "ema_bullish_cross": bullish_cross,
                "ema_bearish_cross": bearish_cross,
            }
        except Exception as e:
            logger.debug(f"EMA computation failed: {e}")
        return {}

    def _compute_vwap(self, df: pd.DataFrame) -> float | None:
        """Compute VWAP (Volume Weighted Average Price)."""
        try:
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            cumulative_tp_vol = (typical_price * df["volume"]).cumsum()
            cumulative_vol = df["volume"].cumsum()

            vwap_series = cumulative_tp_vol / cumulative_vol.replace(0, np.nan)
            val = vwap_series.iloc[-1]
            return round(float(val), 2) if not np.isnan(val) else None
        except Exception as e:
            logger.debug(f"VWAP computation failed: {e}")
        return None

    def _compute_volume(self, df: pd.DataFrame) -> dict:
        """Analyze volume relative to average."""
        try:
            avg_vol = df["volume"].rolling(self.config.volume_avg_period).mean().iloc[-1]
            current_vol = df["volume"].iloc[-1]

            if not np.isnan(avg_vol) and avg_vol > 0:
                vol_ratio = current_vol / avg_vol
            else:
                vol_ratio = 1.0

            price_change = df["close"].iloc[-1] - df["close"].iloc[-2] if len(df) >= 2 else 0
            is_spike = vol_ratio >= self.config.volume_spike_threshold

            return {
                "volume_current": int(current_vol),
                "volume_average": int(avg_vol) if not np.isnan(avg_vol) else 0,
                "volume_ratio": round(vol_ratio, 2),
                "volume_spike": is_spike,
                "volume_spike_bullish": is_spike and price_change > 0,
                "volume_spike_bearish": is_spike and price_change < 0,
            }
        except Exception as e:
            logger.debug(f"Volume computation failed: {e}")
        return {}

    def _compute_atr(self, df: pd.DataFrame) -> float | None:
        """Compute Average True Range for stop-loss calculation."""
        try:
            period = self.config.atr_period
            high = df["high"]
            low = df["low"]
            prev_close = df["close"].shift(1)

            tr1 = high - low
            tr2 = (high - prev_close).abs()
            tr3 = (low - prev_close).abs()
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            atr = true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
            val = atr.iloc[-1]
            return round(float(val), 2) if not np.isnan(val) else None
        except Exception as e:
            logger.debug(f"ATR computation failed: {e}")
        return None

    def _compute_support_resistance(self, df: pd.DataFrame) -> dict:
        """Compute support and resistance levels using pivot points."""
        try:
            if len(df) < 2:
                return {}

            prev_high = df["high"].iloc[-2]
            prev_low = df["low"].iloc[-2]
            prev_close = df["close"].iloc[-2]

            pivot = (prev_high + prev_low + prev_close) / 3
            support1 = (2 * pivot) - prev_high
            resistance1 = (2 * pivot) - prev_low
            support2 = pivot - (prev_high - prev_low)
            resistance2 = pivot + (prev_high - prev_low)

            return {
                "pivot": round(pivot, 2),
                "support1": round(support1, 2),
                "support2": round(support2, 2),
                "resistance1": round(resistance1, 2),
                "resistance2": round(resistance2, 2),
            }
        except Exception as e:
            logger.debug(f"S/R computation failed: {e}")
        return {}

    def get_recent_candle_summary(self, candles: list[Candle], count: int = 6) -> str:
        """Format recent candles as a text summary for LLM input."""
        recent = candles[-count:] if len(candles) >= count else candles
        lines = []
        for c in recent:
            direction = "UP" if c.is_bullish else "DN"
            lines.append(
                f"  {c.timestamp:%H:%M} | O:{c.open:.2f} H:{c.high:.2f} "
                f"L:{c.low:.2f} C:{c.close:.2f} V:{c.volume} [{direction}]"
            )
        return "\n".join(lines)
