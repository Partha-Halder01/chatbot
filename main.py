"""
AI Stock Trading Bot - Main Orchestrator
=========================================
Connects to Indian NSE market via Shoonya API, analyzes market data using
technical indicators + local LLM (Ollama), and executes intraday trades
with strict risk management.

Usage:
    python main.py                    # Paper trading (default)
    python main.py --mode live        # Live trading (use with caution!)
    python main.py --port 8080        # Custom dashboard port
"""

import argparse
import signal
import sys
import threading
import time
from datetime import datetime

from config.settings import get_settings
from core.broker import ShoonyaBroker
from core.market_data import MarketDataManager
from core.technical_analysis import TechnicalAnalyzer
from core.strategy import TradingStrategy
from core.llm_analyst import LLMAnalyst
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor
from core.portfolio_tracker import PortfolioTracker
from dashboard.app import create_dashboard
from models.signal import SignalDirection
from utils.logger import setup_logger
from utils.helpers import is_market_open, is_trading_window, is_square_off_time, get_ist_now

logger = setup_logger("main")


class TradingEngine:
    """Main trading engine that orchestrates all components."""

    def __init__(self, settings):
        self.settings = settings
        self.is_running = False
        self.start_time = None
        self._analysis_thread = None
        self._stop_event = threading.Event()

        # Initialize components
        logger.info("=" * 60)
        logger.info("AI STOCK TRADING BOT - Initializing")
        logger.info(f"Mode: {settings.trading_mode.upper()}")
        logger.info(f"Capital: ₹{settings.trading_capital:,.2f}")
        logger.info(f"Watchlist: {', '.join(settings.watchlist)}")
        logger.info("=" * 60)

        # Broker
        self.broker = ShoonyaBroker(settings)

        # Market data
        self.market_data = MarketDataManager(
            broker=self.broker,
            symbols=settings.watchlist,
            intervals=settings.strategy.candle_intervals,
        )

        # Technical analysis
        self.analyzer = TechnicalAnalyzer(settings.indicators)

        # Strategy
        self.strategy = TradingStrategy(settings.strategy, settings.indicators)

        # LLM analyst
        self.llm = LLMAnalyst(settings.llm)

        # Risk manager
        self.risk_manager = RiskManager(settings.risk, settings.trading_capital)

        # Order executor
        self.executor = OrderExecutor(self.broker, self.risk_manager)

        # Portfolio tracker
        self.portfolio = PortfolioTracker()

        # Recent signals and LLM log for dashboard
        self._recent_signals: list[dict] = []
        self._llm_log: list[dict] = []

        # AI thinking state for live dashboard
        self._ai_thinking: bool = False
        self._ai_current_symbol: str = ""

        # Register candle callback
        self.market_data.on_new_candle(self._on_candle_complete)

    def initialize(self) -> bool:
        """Initialize broker connection and market data."""
        # Login to broker
        if not self.broker.login():
            if not self.broker.is_paper_mode:
                logger.error("Broker login failed. Cannot start.")
                return False

        # Check LLM availability
        if self.llm.is_available():
            logger.info(f"LLM available: {self.settings.llm.model}")
        else:
            logger.warning(
                "LLM not available. Trading will use technical signals only. "
                "Start Ollama with: ollama serve && ollama pull phi3:mini"
            )

        # Start market data
        self.market_data.start()
        logger.info("Market data initialized")

        return True

    def start(self):
        """Start the trading analysis loop."""
        if self.is_running:
            logger.warning("Trading engine already running")
            return

        self.is_running = True
        self.start_time = datetime.now()
        self._stop_event.clear()

        # Reset daily counters
        self.risk_manager.reset_daily()
        self.portfolio.reset_daily()

        # Start analysis thread
        self._analysis_thread = threading.Thread(
            target=self._analysis_loop, daemon=True
        )
        self._analysis_thread.start()
        logger.info("Trading engine STARTED")

    def stop(self):
        """Stop the trading analysis loop."""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()
        logger.info("Trading engine STOPPED")

    def _analysis_loop(self):
        """Main analysis loop — runs every minute."""
        logger.info("Analysis loop started")

        while not self._stop_event.is_set():
            try:
                if not is_market_open():
                    self._stop_event.wait(30)
                    continue

                # Square-off check
                if is_square_off_time():
                    if self.risk_manager.open_positions:
                        logger.warning("SQUARE-OFF TIME — closing all positions")
                        self.executor.close_all_positions("Square-off time (15:10 IST)")
                    self._stop_event.wait(60)
                    continue

                # Update position prices
                ltp_map = self.market_data.get_all_ltp()
                self.portfolio.update_positions(
                    self.risk_manager.open_positions, ltp_map
                )

                # Check exits for open positions
                self._check_position_exits(ltp_map)

                # Only analyze new trades during trading window
                if is_trading_window():
                    self._analyze_watchlist()

            except Exception as e:
                logger.error(f"Analysis loop error: {e}", exc_info=True)

            # Wait for next cycle (60 seconds = 1 candle)
            self._stop_event.wait(60)

        logger.info("Analysis loop stopped")

    def _analyze_watchlist(self):
        """Run analysis on all watchlist symbols."""
        for symbol in self.settings.watchlist:
            try:
                self._analyze_symbol(symbol)
            except Exception as e:
                logger.error(f"Analysis error for {symbol}: {e}")

    def _analyze_symbol(self, symbol: str):
        """Full analysis pipeline for a single symbol."""
        # Get candles (5-min is primary timeframe)
        candles_5m = self.market_data.get_candles(symbol, 5, 100)
        candles_15m = self.market_data.get_candles(symbol, 15, 50)

        if len(candles_5m) < 30:
            return  # Not enough data yet

        # Compute indicators on 5-min timeframe
        indicators = self.analyzer.compute_all(candles_5m)
        if not indicators:
            return

        # Multi-timeframe check: 15-min trend alignment
        if len(candles_15m) >= 30:
            ind_15m = self.analyzer.compute_all(candles_15m)
            if ind_15m:
                indicators["ema_bullish_15m"] = ind_15m.get("ema_bullish")

                # Reject if 15m trend doesn't agree with 5m signal
                ema_5m = indicators.get("ema_bullish")
                ema_15m = ind_15m.get("ema_bullish")
                if ema_5m is not None and ema_15m is not None and ema_5m != ema_15m:
                    indicators["_mtf_conflict"] = True

        # Generate signal
        signal = self.strategy.evaluate(symbol, indicators)

        # Store for dashboard
        self._recent_signals = [
            s for s in self._recent_signals if s["symbol"] != symbol
        ]
        self._recent_signals.append(signal.to_dict())
        if len(self._recent_signals) > 20:
            self._recent_signals = self._recent_signals[-20:]

        # Check if signal is actionable
        if not signal.is_actionable:
            return

        # Multi-timeframe conflict check
        if indicators.get("_mtf_conflict"):
            logger.info(f"{symbol}: Signal rejected — 5m/15m timeframe conflict")
            return

        # Check if signal meets threshold for LLM review
        if abs(signal.score) >= self.settings.strategy.signal_threshold:
            # Set AI thinking state for dashboard
            self._ai_thinking = True
            self._ai_current_symbol = symbol

            # Get candle summary for LLM
            candle_summary = self.analyzer.get_recent_candle_summary(candles_5m)

            # LLM analysis
            signal = self.llm.analyze(signal, candle_summary)

            # Clear AI thinking state
            self._ai_thinking = False
            self._ai_current_symbol = ""

            # Log LLM analysis
            self._llm_log.append(signal.to_dict())
            if len(self._llm_log) > 50:
                self._llm_log = self._llm_log[-50:]

            # Check LLM confirmation
            if (
                self.llm.is_available()
                and not signal.llm_confirmed
                and signal.llm_confidence < self.settings.strategy.llm_confidence_threshold
            ):
                logger.info(
                    f"{symbol}: LLM rejected signal (confidence: {signal.llm_confidence}%)"
                )
                return

        # Execute trade
        current_price = self.market_data.get_ltp(symbol)
        if current_price <= 0:
            current_price = indicators.get("current_price", 0)
        if current_price <= 0:
            return

        atr = indicators.get("atr")
        order = self.executor.execute_signal(signal, current_price, atr)

        if order:
            logger.info(f"TRADE EXECUTED: {signal.direction.value} {symbol}")

    def _check_position_exits(self, ltp_map: dict[str, float]):
        """Check if any open positions should be exited."""
        for position in list(self.risk_manager.open_positions):
            current_price = ltp_map.get(position.symbol, position.current_price)
            if current_price <= 0:
                continue

            position.current_price = current_price

            # Update trailing stop
            self.risk_manager.update_trailing_stop(position, current_price)

            # Check exit conditions
            should_exit, reason = self.risk_manager.should_exit_position(
                position, current_price
            )

            if should_exit:
                order = self.executor.close_position(position, reason)
                if order:
                    self.portfolio.record_closed_trade(
                        position, current_price, reason
                    )

    def _on_candle_complete(self, symbol: str, interval: int, candle):
        """Callback when a new candle completes."""
        logger.debug(f"Candle complete: {symbol} {interval}m {candle.close}")

    def close_all_positions(self):
        """Emergency close all positions."""
        self.executor.close_all_positions("Manual emergency close")

    # Dashboard API helpers
    def is_market_open(self) -> bool:
        return is_market_open()

    def get_risk_status(self) -> dict:
        return self.risk_manager.get_status()

    def get_portfolio_summary(self) -> dict:
        return self.portfolio.get_summary()

    def get_open_positions(self) -> list[dict]:
        return [p.to_dict() for p in self.risk_manager.open_positions]

    def get_recent_signals(self) -> list[dict]:
        return self._recent_signals

    def get_trade_history(self) -> list[dict]:
        return self.portfolio.get_recent_trades()

    def get_indicators(self, symbol: str) -> dict:
        candles = self.market_data.get_candles(symbol, 5, 100)
        if len(candles) >= 30:
            return self.analyzer.compute_all(candles)
        return {}

    def get_all_ltp(self) -> dict:
        return self.market_data.get_all_ltp()

    def get_llm_log(self) -> list[dict]:
        return self._llm_log

    def is_ai_thinking(self) -> bool:
        return self._ai_thinking

    def get_ai_current_symbol(self) -> str:
        return self._ai_current_symbol

    def get_uptime_minutes(self) -> float:
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds() / 60
        return 0


def main():
    parser = argparse.ArgumentParser(description="AI Stock Trading Bot")
    parser.add_argument(
        "--mode", choices=["paper", "live"], default=None,
        help="Trading mode (default: from .env or paper)",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Dashboard port (default: 5000)",
    )
    args = parser.parse_args()

    # Load settings
    settings = get_settings()
    if args.mode:
        settings.trading_mode = args.mode
    if args.port:
        settings.dashboard_port = args.port

    # Create trading engine
    engine = TradingEngine(settings)

    # Initialize
    if not engine.initialize():
        logger.error("Initialization failed. Exiting.")
        sys.exit(1)

    # Create dashboard
    dashboard = create_dashboard(engine)

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        engine.stop()
        if engine.risk_manager.open_positions:
            logger.warning("Closing all open positions before shutdown...")
            engine.close_all_positions()
        logger.info("Shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start trading
    engine.start()

    # Run dashboard (blocking)
    logger.info(f"Dashboard running at http://localhost:{settings.dashboard_port}")
    logger.info("Press Ctrl+C to stop")

    dashboard.run(
        host="0.0.0.0",
        port=settings.dashboard_port,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
