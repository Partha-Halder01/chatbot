"""LLM analyst using Ollama for trade signal confirmation."""

import json
import re
import requests
from models.signal import TradeSignal, SignalDirection
from config.settings import LLMConfig
from utils.logger import setup_logger

logger = setup_logger("llm_analyst")

ANALYSIS_PROMPT = """You are a professional intraday stock trader analyzing Indian NSE stocks.
Analyze the following market data and provide your trading recommendation.

Stock: {symbol}
Current Price: ₹{price}
Time: {time} IST

Technical Indicators (5-min timeframe):
- RSI(14): {rsi} (trend: {rsi_trend})
- MACD Histogram: {macd_hist} (signal: {macd_crossover})
- Bollinger Band Position: {bb_position} (0=lower, 1=upper)
- Price vs VWAP: {vwap_relation}
- EMA9 vs EMA21: {ema_relation}
- Volume vs Average: {volume_ratio}x
- ATR(14): ₹{atr}

Recent 5-min candles (last 6):
{candle_data}

Support: ₹{support} | Resistance: ₹{resistance}

Technical Signal Score: {score}/100 ({direction})

IMPORTANT: You can only CONFIRM or REJECT the technical signal direction ({direction}).
You CANNOT suggest the opposite direction.

Respond in EXACTLY this JSON format and nothing else:
{{"action": "BUY" or "SELL" or "HOLD", "confidence": 0-100, "reasoning": "one sentence why", "stop_loss": price_number, "target": price_number}}"""


class LLMAnalyst:
    """Uses a local LLM via Ollama to confirm/reject technical trading signals."""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._available = None

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        if self._available is not None:
            return self._available

        try:
            resp = requests.get(
                f"{self.config.base_url}/api/tags",
                timeout=5,
            )
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                self._available = any(
                    self.config.model in name for name in model_names
                )
                if not self._available:
                    logger.warning(
                        f"Model '{self.config.model}' not found. "
                        f"Available: {model_names}. "
                        f"Install with: ollama pull {self.config.model}"
                    )
                return self._available
        except requests.ConnectionError:
            logger.warning(
                "Ollama not running. Start with: ollama serve"
            )
        except Exception as e:
            logger.warning(f"Ollama check failed: {e}")

        self._available = False
        return False

    def analyze(
        self,
        signal: TradeSignal,
        candle_summary: str,
    ) -> TradeSignal:
        """
        Send signal data to LLM for confirmation.
        Updates the signal with LLM confidence and reasoning.
        The LLM can only CONFIRM or REJECT — never reverse direction.
        """
        if not self.is_available():
            logger.info("LLM not available — using technical signal only")
            signal.llm_confidence = 0
            signal.llm_reasoning = "LLM unavailable"
            return signal

        ind = signal.indicators
        prompt = ANALYSIS_PROMPT.format(
            symbol=signal.symbol,
            price=ind.get("current_price", 0),
            time=signal.timestamp.strftime("%H:%M"),
            rsi=ind.get("rsi", "N/A"),
            rsi_trend=ind.get("rsi_trend", "N/A"),
            macd_hist=ind.get("macd_histogram", "N/A"),
            macd_crossover=ind.get("macd_crossover", "N/A"),
            bb_position=ind.get("bb_position", "N/A"),
            vwap_relation="Above" if ind.get("above_vwap") else "Below",
            ema_relation="Bullish (EMA9 > EMA21)" if ind.get("ema_bullish") else "Bearish (EMA9 < EMA21)",
            volume_ratio=ind.get("volume_ratio", "N/A"),
            atr=ind.get("atr", "N/A"),
            candle_data=candle_summary or "N/A",
            support=ind.get("support1", "N/A"),
            resistance=ind.get("resistance1", "N/A"),
            score=signal.score,
            direction=signal.direction.value,
        )

        try:
            resp = requests.post(
                f"{self.config.base_url}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 200,
                    },
                },
                timeout=self.config.timeout_seconds,
            )

            if resp.status_code != 200:
                logger.warning(f"LLM API error: {resp.status_code}")
                signal.llm_reasoning = f"API error: {resp.status_code}"
                return signal

            response_text = resp.json().get("response", "")
            result = self._parse_response(response_text, signal)

            logger.info(
                f"LLM Analysis for {signal.symbol}: "
                f"action={result.get('action')} confidence={result.get('confidence')} "
                f"reasoning={result.get('reasoning', '')[:80]}"
            )

            # Update signal with LLM results
            action = result.get("action", "HOLD")
            confidence = result.get("confidence", 0)

            # Safety: LLM can only confirm or hold, not reverse
            if signal.direction == SignalDirection.BUY and action == "SELL":
                action = "HOLD"
                confidence = 0
                logger.warning("LLM tried to reverse BUY signal — overriding to HOLD")
            elif signal.direction == SignalDirection.SELL and action == "BUY":
                action = "HOLD"
                confidence = 0
                logger.warning("LLM tried to reverse SELL signal — overriding to HOLD")

            signal.llm_confidence = confidence
            signal.llm_reasoning = result.get("reasoning", "")
            signal.llm_confirmed = action == signal.direction.value and confidence >= 70

            # Use LLM's SL/TP suggestions if provided
            if result.get("stop_loss"):
                signal.suggested_sl = result["stop_loss"]
            if result.get("target"):
                signal.suggested_tp = result["target"]

        except requests.Timeout:
            logger.warning("LLM timed out — using technical signal only")
            signal.llm_reasoning = "LLM timeout"
        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            signal.llm_reasoning = f"Error: {str(e)[:50]}"

        return signal

    def _parse_response(self, text: str, signal: TradeSignal) -> dict:
        """Parse LLM JSON response with fallback regex extraction."""
        # Try direct JSON parse
        try:
            # Find JSON in response
            json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "action": str(data.get("action", "HOLD")).upper(),
                    "confidence": min(100, max(0, int(data.get("confidence", 0)))),
                    "reasoning": str(data.get("reasoning", "")),
                    "stop_loss": float(data.get("stop_loss", 0)),
                    "target": float(data.get("target", 0)),
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: regex extraction
        result = {"action": "HOLD", "confidence": 0, "reasoning": "", "stop_loss": 0, "target": 0}

        action_match = re.search(r'"action"\s*:\s*"(BUY|SELL|HOLD)"', text, re.IGNORECASE)
        if action_match:
            result["action"] = action_match.group(1).upper()

        conf_match = re.search(r'"confidence"\s*:\s*(\d+)', text)
        if conf_match:
            result["confidence"] = min(100, int(conf_match.group(1)))

        reason_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', text)
        if reason_match:
            result["reasoning"] = reason_match.group(1)

        return result
