"""Shoonya API wrapper for authentication, orders, and account management."""

import hashlib
from datetime import datetime
from utils.logger import setup_logger
from utils.helpers import generate_totp
from config.settings import Settings
from models.order import Order, OrderSide, OrderStatus

logger = setup_logger("broker")


class ShoonyaBroker:
    """Wraps the NorenRestApiPy ShoonyaApiPy class with safety and convenience."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api = None
        self.is_logged_in = False
        self.is_paper_mode = settings.trading_mode == "paper"

        if not self.is_paper_mode:
            try:
                from NorenRestApiPy import NorenApi

                class ShoonyaApi(NorenApi):
                    def __init__(self):
                        NorenApi.__init__(
                            self,
                            host=settings.broker.host,
                            websocket=settings.broker.websocket,
                        )

                self.api = ShoonyaApi()
            except ImportError:
                logger.warning(
                    "NorenRestApiPy not installed. Install with: pip install NorenRestApiPy"
                )
                logger.info("Falling back to paper trading mode")
                self.is_paper_mode = True

    def login(self) -> bool:
        """Authenticate with Shoonya API."""
        if self.is_paper_mode:
            logger.info("Paper trading mode — skipping broker login")
            self.is_logged_in = True
            return True

        cfg = self.settings.broker
        if not cfg.user_id or not cfg.password:
            logger.error("Broker credentials not configured. Check .env file")
            return False

        try:
            totp = generate_totp(cfg.totp_secret)
            pwd_hash = hashlib.sha256(cfg.password.encode()).hexdigest()

            ret = self.api.login(
                userid=cfg.user_id,
                password=pwd_hash,
                twoFA=totp,
                vendor_code=cfg.vendor_code,
                api_secret=cfg.api_secret,
                imei=cfg.imei,
            )

            if ret and ret.get("stat") == "Ok":
                self.is_logged_in = True
                logger.info(f"Logged in successfully as {cfg.user_id}")
                return True
            else:
                error_msg = ret.get("emsg", "Unknown error") if ret else "No response"
                logger.error(f"Login failed: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    def search_scrip(self, exchange: str, symbol: str) -> dict | None:
        """Search for a scrip token on the exchange."""
        if self.is_paper_mode:
            return {"tsym": f"{symbol}-EQ", "token": "0", "exch": exchange}

        try:
            ret = self.api.searchscrip(exchange=exchange, searchtext=symbol)
            if ret and ret.get("stat") == "Ok" and ret.get("values"):
                # Find exact equity match
                for scrip in ret["values"]:
                    if scrip.get("tsym") == f"{symbol}-EQ":
                        return scrip
                return ret["values"][0]
        except Exception as e:
            logger.error(f"Scrip search failed for {symbol}: {e}")
        return None

    def get_quotes(self, exchange: str, token: str) -> dict | None:
        """Get current quotes for a scrip."""
        if self.is_paper_mode:
            return None

        try:
            ret = self.api.get_quotes(exchange=exchange, token=token)
            if ret and ret.get("stat") == "Ok":
                return ret
        except Exception as e:
            logger.error(f"Get quotes failed: {e}")
        return None

    def place_order(self, order: Order) -> str:
        """Place an order. Returns broker order ID or empty string on failure."""
        if self.is_paper_mode:
            order.broker_order_id = f"PAPER_{datetime.now():%H%M%S%f}"
            order.status = OrderStatus.COMPLETED
            order.fill_price = order.price
            logger.info(
                f"[PAPER] Order placed: {order.side.value} {order.quantity}x "
                f"{order.symbol} @ {order.price}"
            )
            return order.broker_order_id

        try:
            # Search for the scrip token
            scrip = self.search_scrip(order.exchange, order.symbol)
            if not scrip:
                logger.error(f"Could not find scrip: {order.symbol}")
                order.status = OrderStatus.REJECTED
                return ""

            params = {
                "buy_or_sell": order.side.value,
                "product_type": order.product_type,
                "exchange": order.exchange,
                "tradingsymbol": scrip["tsym"],
                "quantity": order.quantity,
                "discloseqty": 0,
                "price_type": "MKT" if order.order_type == "MKT" else "LMT",
                "price": order.price if order.order_type == "LMT" else 0,
                "retention": "DAY",
            }

            # Add bracket order parameters if SL and TP are set
            if order.stop_loss > 0 and order.take_profit > 0:
                params["bookloss_price"] = order.stop_loss
                params["bookprofit_price"] = order.take_profit
                if order.trail_price > 0:
                    params["trail_price"] = order.trail_price

            ret = self.api.place_order(**params)

            if ret and ret.get("stat") == "Ok":
                order.broker_order_id = ret.get("norenordno", "")
                order.status = OrderStatus.PLACED
                logger.info(
                    f"Order placed: {order.side.value} {order.quantity}x "
                    f"{order.symbol} | ID: {order.broker_order_id}"
                )
                return order.broker_order_id
            else:
                error_msg = ret.get("emsg", "Unknown error") if ret else "No response"
                order.status = OrderStatus.REJECTED
                order.remarks = error_msg
                logger.error(f"Order rejected: {error_msg}")
                return ""

        except Exception as e:
            logger.error(f"Order placement exception: {e}")
            order.status = OrderStatus.REJECTED
            order.remarks = str(e)
            return ""

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if self.is_paper_mode:
            logger.info(f"[PAPER] Order cancelled: {order_id}")
            return True

        try:
            ret = self.api.cancel_order(orderno=order_id)
            if ret and ret.get("stat") == "Ok":
                logger.info(f"Order cancelled: {order_id}")
                return True
            else:
                logger.error(f"Cancel failed: {ret}")
                return False
        except Exception as e:
            logger.error(f"Cancel exception: {e}")
            return False

    def get_positions(self) -> list:
        """Get current open positions."""
        if self.is_paper_mode:
            return []

        try:
            ret = self.api.get_positions()
            if ret and isinstance(ret, list):
                return ret
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
        return []

    def get_order_book(self) -> list:
        """Get today's order book."""
        if self.is_paper_mode:
            return []

        try:
            ret = self.api.get_order_book()
            if ret and isinstance(ret, list):
                return ret
        except Exception as e:
            logger.error(f"Get order book failed: {e}")
        return []

    def get_limits(self) -> dict | None:
        """Get account margins/limits."""
        if self.is_paper_mode:
            return {
                "cash": str(self.settings.trading_capital),
                "marginused": "0",
            }

        try:
            ret = self.api.get_limits()
            if ret and ret.get("stat") == "Ok":
                return ret
        except Exception as e:
            logger.error(f"Get limits failed: {e}")
        return None

    def get_historical_data(
        self, exchange: str, token: str, start: str, end: str, interval: str = "1"
    ) -> list:
        """Get historical candle data. interval: '1','3','5','10','15','30','60','120','240'."""
        if self.is_paper_mode:
            return []

        try:
            ret = self.api.get_time_price_series(
                exchange=exchange, token=token, starttime=start, endtime=end,
                interval=interval,
            )
            if ret and isinstance(ret, list):
                return ret
        except Exception as e:
            logger.error(f"Historical data failed: {e}")
        return []

    def start_websocket(self, subscribe_callback, order_callback=None, error_callback=None):
        """Start WebSocket connection for live data."""
        if self.is_paper_mode:
            logger.info("[PAPER] WebSocket not started in paper mode")
            return

        def on_open():
            logger.info("WebSocket connected")

        def on_close():
            logger.warning("WebSocket disconnected")

        def on_error(error):
            logger.error(f"WebSocket error: {error}")
            if error_callback:
                error_callback(error)

        self.api.start_websocket(
            order_update_callback=order_callback or (lambda msg: None),
            subscribe_callback=subscribe_callback,
            socket_open_callback=on_open,
            socket_close_callback=on_close,
            socket_error_callback=on_error,
        )

    def subscribe(self, instrument: str, feed_type: str = "t"):
        """Subscribe to live data. feed_type: 't'=touchline, 'd'=depth."""
        if self.is_paper_mode:
            return
        self.api.subscribe(instrument, feed_type=feed_type)

    def unsubscribe(self, instrument: str):
        """Unsubscribe from live data."""
        if self.is_paper_mode:
            return
        self.api.unsubscribe(instrument)
