"""Trading strategy with weighted signal scoring system."""

from collections import defaultdict
from datetime import datetime
from models.signal import TradeSignal, SignalDirection
from config.settings import StrategyConfig, IndicatorConfig
from utils.logger import setup_logger

logger = setup_logger("strategy")


class TradingStrategy:
    """
    Generates composite trade signals by scoring multiple technical indicators.
    Score range: -100 (strong sell) to +100 (strong buy).
    """

    # Signal weights (must sum to 100)
    WEIGHTS = {
        "ema_crossover": 25,
        "rsi": 15,
        "macd": 20,
        "bollinger": 10,
        "vwap": 15,
        "volume": 15,
    }

    def __init__(
        self,
        strategy_config: StrategyConfig = None,
        indicator_config: IndicatorConfig = None,
    ):
        self.config = strategy_config or StrategyConfig()
        self.ind_config = indicator_config or IndicatorConfig()

        # Track signal persistence: {symbol: [last_N_scores]}
        self._signal_history: dict[str, list[float]] = defaultdict(list)

    def evaluate(self, symbol: str, indicators: dict) -> TradeSignal:
        """
        Evaluate all indicators and produce a composite trade signal.
        Returns a TradeSignal with score and direction.
        """
        if not indicators:
            return self._hold_signal(symbol, "No indicator data")

        scores = {}
        agreeing_buy = 0
        agreeing_sell = 0

        # 1. EMA Crossover (weight: 25)
        ema_score = self._score_ema(indicators)
        scores["ema_crossover"] = ema_score
        if ema_score > 0:
            agreeing_buy += 1
        elif ema_score < 0:
            agreeing_sell += 1

        # 2. RSI (weight: 15)
        rsi_score = self._score_rsi(indicators)
        scores["rsi"] = rsi_score
        if rsi_score > 0:
            agreeing_buy += 1
        elif rsi_score < 0:
            agreeing_sell += 1

        # 3. MACD (weight: 20)
        macd_score = self._score_macd(indicators)
        scores["macd"] = macd_score
        if macd_score > 0:
            agreeing_buy += 1
        elif macd_score < 0:
            agreeing_sell += 1

        # 4. Bollinger Bands (weight: 10)
        bb_score = self._score_bollinger(indicators)
        scores["bollinger"] = bb_score
        if bb_score > 0:
            agreeing_buy += 1
        elif bb_score < 0:
            agreeing_sell += 1

        # 5. VWAP (weight: 15)
        vwap_score = self._score_vwap(indicators)
        scores["vwap"] = vwap_score
        if vwap_score > 0:
            agreeing_buy += 1
        elif vwap_score < 0:
            agreeing_sell += 1

        # 6. Volume (weight: 15)
        volume_score = self._score_volume(indicators)
        scores["volume"] = volume_score
        if volume_score > 0:
            agreeing_buy += 1
        elif volume_score < 0:
            agreeing_sell += 1

        # Calculate weighted composite score
        composite = sum(
            scores[k] * (self.WEIGHTS[k] / 100.0) for k in scores
        )
        composite = max(-100, min(100, composite))  # Clamp

        # Determine direction
        if composite > 0:
            direction = SignalDirection.BUY
            agreeing_count = agreeing_buy
        elif composite < 0:
            direction = SignalDirection.SELL
            agreeing_count = agreeing_sell
        else:
            direction = SignalDirection.HOLD
            agreeing_count = 0

        # Conservative filter: need minimum agreeing signals
        if agreeing_count < self.config.min_agreeing_signals:
            return self._hold_signal(
                symbol,
                f"Only {agreeing_count} signals agree (need {self.config.min_agreeing_signals})",
            )

        # Signal persistence check
        self._signal_history[symbol].append(composite)
        if len(self._signal_history[symbol]) > 10:
            self._signal_history[symbol] = self._signal_history[symbol][-10:]

        if not self._check_persistence(symbol, direction):
            return self._hold_signal(symbol, "Signal not persistent enough")

        signal = TradeSignal(
            symbol=symbol,
            direction=direction,
            score=round(composite, 2),
            timestamp=datetime.now(),
            indicators=indicators,
        )

        logger.info(
            f"{symbol} | Score: {composite:+.1f} | Direction: {direction.value} | "
            f"Agreeing: {agreeing_count}/6 | "
            f"EMA:{scores['ema_crossover']:+.0f} RSI:{scores['rsi']:+.0f} "
            f"MACD:{scores['macd']:+.0f} BB:{scores['bollinger']:+.0f} "
            f"VWAP:{scores['vwap']:+.0f} VOL:{scores['volume']:+.0f}"
        )

        return signal

    def _score_ema(self, ind: dict) -> float:
        """Score EMA crossover signal: -100 to +100."""
        if "ema_bullish" not in ind:
            return 0

        if ind.get("ema_bullish_cross"):
            return 100  # Fresh bullish crossover
        elif ind.get("ema_bearish_cross"):
            return -100  # Fresh bearish crossover
        elif ind.get("ema_bullish"):
            return 60  # Already bullish trend
        else:
            return -60  # Already bearish trend

    def _score_rsi(self, ind: dict) -> float:
        """Score RSI signal: -100 to +100."""
        rsi = ind.get("rsi")
        if rsi is None:
            return 0

        trend = ind.get("rsi_trend", "flat")

        if rsi < 35 and trend == "rising":
            return 100  # Oversold and recovering
        elif rsi < 30:
            return 80  # Very oversold
        elif rsi > 65 and trend == "falling":
            return -100  # Overbought and declining
        elif rsi > 70:
            return -80  # Very overbought
        elif rsi < 45:
            return 30  # Slightly oversold
        elif rsi > 55:
            return -30  # Slightly overbought
        return 0

    def _score_macd(self, ind: dict) -> float:
        """Score MACD signal: -100 to +100."""
        crossover = ind.get("macd_crossover", "none")
        hist = ind.get("macd_histogram", 0)

        if crossover == "bullish":
            return 100  # Fresh bullish crossover
        elif crossover == "bearish":
            return -100  # Fresh bearish crossover
        elif hist > 0:
            return 50  # MACD above signal
        elif hist < 0:
            return -50  # MACD below signal
        return 0

    def _score_bollinger(self, ind: dict) -> float:
        """Score Bollinger Band signal: -100 to +100."""
        if "bb_position" not in ind:
            return 0

        pos = ind["bb_position"]

        if ind.get("bb_near_lower"):
            return 80  # Near lower band — potential reversal up
        elif ind.get("bb_near_upper"):
            return -80  # Near upper band — potential reversal down
        elif pos < 0.3:
            return 40
        elif pos > 0.7:
            return -40
        return 0

    def _score_vwap(self, ind: dict) -> float:
        """Score VWAP signal: -100 to +100."""
        if "above_vwap" not in ind:
            return 0

        vol_spike = ind.get("volume_spike", False)

        if ind["above_vwap"] and vol_spike:
            return 100  # Above VWAP with volume
        elif not ind["above_vwap"] and vol_spike:
            return -100  # Below VWAP with volume
        elif ind["above_vwap"]:
            return 40  # Above VWAP
        else:
            return -40  # Below VWAP

    def _score_volume(self, ind: dict) -> float:
        """Score volume signal: -100 to +100."""
        if ind.get("volume_spike_bullish"):
            return 100
        elif ind.get("volume_spike_bearish"):
            return -100
        elif ind.get("volume_spike"):
            return 0  # Spike but no clear direction
        return 0

    def _check_persistence(self, symbol: str, direction: SignalDirection) -> bool:
        """Check if the signal has persisted for enough candles."""
        history = self._signal_history.get(symbol, [])
        required = self.config.signal_persistence_candles

        if len(history) < required:
            return False

        recent = history[-required:]

        if direction == SignalDirection.BUY:
            return all(s > 0 for s in recent)
        elif direction == SignalDirection.SELL:
            return all(s < 0 for s in recent)
        return True

    def _hold_signal(self, symbol: str, reason: str = "") -> TradeSignal:
        """Create a HOLD signal."""
        return TradeSignal(
            symbol=symbol,
            direction=SignalDirection.HOLD,
            score=0,
            timestamp=datetime.now(),
            llm_reasoning=reason,
        )
