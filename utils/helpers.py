"""Utility helpers: market hours, IST time, TOTP generation."""

from datetime import datetime, time
import pyotp


# Indian Standard Time offset (UTC+5:30)
IST_OFFSET_HOURS = 5
IST_OFFSET_MINUTES = 30

# Market timing constants
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
TRADE_START = time(9, 30)   # Skip first 15 min volatility
TRADE_END = time(14, 30)    # Stop new trades
SQUARE_OFF = time(15, 10)   # Force close all


def get_ist_now() -> datetime:
    """Get current time in IST."""
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=IST_OFFSET_HOURS, minutes=IST_OFFSET_MINUTES))
    return datetime.now(ist)


def is_market_open() -> bool:
    """Check if NSE market is currently open."""
    now = get_ist_now().time()
    weekday = get_ist_now().weekday()
    # Monday=0 to Friday=4
    if weekday > 4:
        return False
    return MARKET_OPEN <= now <= MARKET_CLOSE


def is_trading_window() -> bool:
    """Check if we're within the safe trading window (09:30 - 14:30 IST)."""
    now = get_ist_now().time()
    weekday = get_ist_now().weekday()
    if weekday > 4:
        return False
    return TRADE_START <= now <= TRADE_END


def is_square_off_time() -> bool:
    """Check if it's time to square off all positions."""
    now = get_ist_now().time()
    return now >= SQUARE_OFF


def generate_totp(secret: str) -> str:
    """Generate TOTP for Shoonya login."""
    if not secret:
        raise ValueError("TOTP secret not configured. Set SHOONYA_TOTP_SECRET in .env")
    totp = pyotp.TOTP(secret)
    return totp.now()


def format_inr(amount: float) -> str:
    """Format a number as INR currency string."""
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 10000000:
        return f"{sign}₹{amount / 10000000:.2f} Cr"
    elif amount >= 100000:
        return f"{sign}₹{amount / 100000:.2f} L"
    else:
        return f"{sign}₹{amount:,.2f}"


def get_exchange_token(symbol: str) -> str:
    """Get NSE exchange format for a symbol."""
    return f"NSE|{symbol}-EQ"
