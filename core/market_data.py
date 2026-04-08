"""WebSocket feed manager and candle aggregation."""

import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from models.candle import Candle
from utils.logger import setup_logger

logger = setup_logger("market_data")

IST = timezone(timedelta(hours=5, minutes=30))


class MarketDataManager:
    """Manages live tick data and aggregates into OHLCV candles."""

    def __init__(self, broker, symbols: list[str], intervals: list[int] = None):
        self.broker = broker
        self.symbols = symbols
        self.intervals = intervals or [1, 5, 15]

        # Last traded price per symbol
        self.ltp: dict[str, float] = {}

        # Candle buffers: {symbol: {interval: [Candle, ...]}}
        self._candles: dict[str, dict[int, list[Candle]]] = defaultdict(
            lambda: {i: [] for i in self.intervals}
        )

        # Current building candle: {symbol: {interval: Candle}}
        self._current_candle: dict[str, dict[int, Candle | None]] = defaultdict(
            lambda: {i: None for i in self.intervals}
        )

        # Thread lock for candle access
        self._lock = threading.Lock()

        # Callbacks for new candle events
        self._candle_callbacks: list = []

        # Scrip tokens: {symbol: {"token": str, "tsym": str}}
        self._scrip_info: dict[str, dict] = {}

        # Max candles to keep per symbol per interval
        self._max_candles = 200

    def on_new_candle(self, callback):
        """Register a callback for when a new candle completes: callback(symbol, interval, candle)."""
        self._candle_callbacks.append(callback)

    def start(self):
        """Start receiving live market data."""
        if self.broker.is_paper_mode:
            logger.info("[PAPER] Market data running in simulation mode")
            return

        # Resolve scrip tokens
        for symbol in self.symbols:
            scrip = self.broker.search_scrip("NSE", symbol)
            if scrip:
                self._scrip_info[symbol] = scrip
                logger.info(f"Resolved {symbol} -> {scrip.get('tsym')} (token: {scrip.get('token')})")
            else:
                logger.warning(f"Could not resolve scrip for {symbol}")

        # Backfill historical candles
        self._backfill_history()

        # Start WebSocket
        self.broker.start_websocket(
            subscribe_callback=self._on_tick,
            error_callback=self._on_error,
        )

        # Subscribe to all symbols
        for symbol, info in self._scrip_info.items():
            instrument = f"NSE|{info['token']}"
            self.broker.subscribe(instrument)
            logger.info(f"Subscribed to {symbol}")

    def _backfill_history(self):
        """Load historical candles so indicators have warm-up data."""
        now = datetime.now(IST)
        start = (now - timedelta(days=5)).strftime("%d-%m-%Y")
        end = now.strftime("%d-%m-%Y")

        for symbol, info in self._scrip_info.items():
            for interval in self.intervals:
                try:
                    data = self.broker.get_historical_data(
                        exchange="NSE",
                        token=info["token"],
                        start=start,
                        end=end,
                        interval=str(interval),
                    )
                    if data:
                        candles = self._parse_historical(data, symbol, interval)
                        with self._lock:
                            self._candles[symbol][interval] = candles[-self._max_candles:]
                        logger.info(
                            f"Backfilled {len(candles)} candles for {symbol} ({interval}m)"
                        )
                except Exception as e:
                    logger.error(f"Backfill failed for {symbol} ({interval}m): {e}")

    def _parse_historical(self, data: list, symbol: str, interval: int) -> list[Candle]:
        """Parse historical data from Shoonya API into Candle objects."""
        candles = []
        for bar in reversed(data):  # API returns newest first
            try:
                ts = datetime.strptime(bar.get("time", ""), "%d-%m-%Y %H:%M:%S")
                ts = ts.replace(tzinfo=IST)
                candle = Candle(
                    timestamp=ts,
                    symbol=symbol,
                    open=float(bar.get("into", 0)),
                    high=float(bar.get("inth", 0)),
                    low=float(bar.get("intl", 0)),
                    close=float(bar.get("intc", 0)),
                    volume=int(bar.get("intv", 0)),
                    interval=interval,
                )
                candles.append(candle)
            except (ValueError, KeyError) as e:
                logger.debug(f"Skipping malformed bar: {e}")
        return candles

    def _on_tick(self, tick: dict):
        """Handle incoming tick data from WebSocket."""
        try:
            token = tick.get("tk", "")
            ltp = float(tick.get("lp", 0))
            volume = int(tick.get("v", 0))

            if ltp == 0:
                return

            # Find symbol by token
            symbol = None
            for sym, info in self._scrip_info.items():
                if info.get("token") == token:
                    symbol = sym
                    break

            if not symbol:
                return

            self.ltp[symbol] = ltp
            now = datetime.now(IST)

            # Update candles for each interval
            for interval in self.intervals:
                self._update_candle(symbol, interval, ltp, volume, now)

        except Exception as e:
            logger.error(f"Tick processing error: {e}")

    def _update_candle(
        self, symbol: str, interval: int, price: float, volume: int, now: datetime
    ):
        """Update or create candle from tick data."""
        # Calculate candle boundary
        minute_boundary = (now.minute // interval) * interval
        candle_start = now.replace(minute=minute_boundary, second=0, microsecond=0)

        with self._lock:
            current = self._current_candle[symbol][interval]

            if current is None or current.timestamp < candle_start:
                # New candle — finalize old one if it exists
                if current is not None:
                    self._candles[symbol][interval].append(current)
                    # Trim buffer
                    if len(self._candles[symbol][interval]) > self._max_candles:
                        self._candles[symbol][interval] = self._candles[symbol][interval][
                            -self._max_candles:
                        ]
                    # Notify callbacks
                    for cb in self._candle_callbacks:
                        try:
                            cb(symbol, interval, current)
                        except Exception as e:
                            logger.error(f"Candle callback error: {e}")

                # Start new candle
                self._current_candle[symbol][interval] = Candle(
                    timestamp=candle_start,
                    symbol=symbol,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=volume,
                    interval=interval,
                )
            else:
                # Update existing candle
                current.high = max(current.high, price)
                current.low = min(current.low, price)
                current.close = price
                current.volume = volume

    def _on_error(self, error):
        """Handle WebSocket errors."""
        logger.error(f"Market data error: {error}")

    def get_candles(self, symbol: str, interval: int, count: int = 100) -> list[Candle]:
        """Get the last N completed candles for a symbol and interval."""
        with self._lock:
            candles = self._candles.get(symbol, {}).get(interval, [])
            return candles[-count:]

    def get_ltp(self, symbol: str) -> float:
        """Get the last traded price for a symbol."""
        return self.ltp.get(symbol, 0.0)

    def get_all_ltp(self) -> dict[str, float]:
        """Get LTP for all symbols."""
        return dict(self.ltp)

    def inject_candle(self, candle: Candle):
        """Inject a candle manually (for paper trading / backtesting)."""
        with self._lock:
            self._candles[candle.symbol][candle.interval].append(candle)
            if len(self._candles[candle.symbol][candle.interval]) > self._max_candles:
                self._candles[candle.symbol][candle.interval] = self._candles[
                    candle.symbol
                ][candle.interval][-self._max_candles:]
            self.ltp[candle.symbol] = candle.close

        for cb in self._candle_callbacks:
            try:
                cb(candle.symbol, candle.interval, candle)
            except Exception as e:
                logger.error(f"Candle callback error: {e}")
