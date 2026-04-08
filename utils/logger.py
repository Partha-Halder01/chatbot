"""Structured logging setup for the trading bot."""

import logging
import os
from datetime import datetime


def setup_logger(name: str = "trading_bot", level: str = "INFO") -> logging.Logger:
    """Create a logger that writes to both console and daily log file."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler (daily rotation)
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"trading_{datetime.now():%Y%m%d}.log")

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Trade-specific logger for the journal
def get_trade_logger() -> logging.Logger:
    """Logger specifically for trade executions — writes to trades CSV."""
    logger = logging.getLogger("trade_journal")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    trade_file = os.path.join(data_dir, f"trades_{datetime.now():%Y%m%d}.csv")

    # Write CSV header if file is new
    write_header = not os.path.exists(trade_file)
    file_handler = logging.FileHandler(trade_file)
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)

    if write_header:
        logger.info(
            "timestamp,symbol,side,quantity,price,stop_loss,take_profit,"
            "signal_score,llm_confidence,status,pnl,remarks"
        )

    return logger
