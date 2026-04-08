"""Central configuration for the trading bot. All tunable parameters live here."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BrokerConfig:
    host: str = "https://api.shoonya.com/NorenWClientTP/"
    websocket: str = "wss://api.shoonya.com/NorenWSTP/"
    user_id: str = ""
    password: str = ""
    vendor_code: str = ""
    api_secret: str = ""
    imei: str = ""
    totp_secret: str = ""


@dataclass
class StrategyConfig:
    candle_intervals: list = field(default_factory=lambda: [1, 5, 15])
    signal_threshold: int = 60
    llm_confidence_threshold: int = 70
    max_hold_minutes: int = 120
    trade_start_time: str = "09:30"
    trade_end_time: str = "14:30"
    square_off_time: str = "15:10"
    # Minimum number of agreeing signals to trigger a trade
    min_agreeing_signals: int = 3
    # Signal must persist for this many 1-min candles
    signal_persistence_candles: int = 2


@dataclass
class IndicatorConfig:
    rsi_period: int = 14
    rsi_overbought: int = 70
    rsi_oversold: int = 30
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    ema_short: int = 9
    ema_long: int = 21
    atr_period: int = 14
    volume_avg_period: int = 20
    volume_spike_threshold: float = 1.5


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_open_positions: int = 2
    stop_loss_pct: float = 0.5
    take_profit_pct: float = 1.0
    trailing_stop_pct: float = 0.3
    trailing_activation_pct: float = 0.5
    min_capital_reserve: float = 10000.0
    max_hold_minutes: int = 120


@dataclass
class LLMConfig:
    model: str = "phi3:mini"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = 10
    max_retries: int = 2


@dataclass
class Settings:
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    trading_mode: str = "paper"  # "paper" or "live"
    trading_capital: float = 100000.0
    dashboard_port: int = 5000

    watchlist: list = field(default_factory=lambda: [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
    ])


def get_settings() -> Settings:
    """Load settings from environment variables with defaults."""
    settings = Settings()

    # Broker credentials from env
    settings.broker.user_id = os.getenv("SHOONYA_USER_ID", "")
    settings.broker.password = os.getenv("SHOONYA_PASSWORD", "")
    settings.broker.vendor_code = os.getenv("SHOONYA_VENDOR_CODE", "")
    settings.broker.api_secret = os.getenv("SHOONYA_API_SECRET", "")
    settings.broker.imei = os.getenv("SHOONYA_IMEI", "")
    settings.broker.totp_secret = os.getenv("SHOONYA_TOTP_SECRET", "")

    # Trading config from env
    settings.trading_mode = os.getenv("TRADING_MODE", "paper")
    settings.trading_capital = float(os.getenv("TRADING_CAPITAL", "100000"))

    # LLM config from env
    settings.llm.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    settings.llm.model = os.getenv("OLLAMA_MODEL", "phi3:mini")

    return settings
