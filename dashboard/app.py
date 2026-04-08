"""Flask web dashboard for monitoring the trading bot."""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from utils.logger import setup_logger

logger = setup_logger("dashboard")


def create_dashboard(trading_engine):
    """Create Flask dashboard app with reference to the trading engine."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    CORS(app)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/status")
    def get_status():
        """Get overall bot status."""
        return jsonify({
            "mode": trading_engine.settings.trading_mode,
            "is_running": trading_engine.is_running,
            "market_open": trading_engine.is_market_open(),
            "risk": trading_engine.get_risk_status(),
            "portfolio": trading_engine.get_portfolio_summary(),
            "uptime_minutes": trading_engine.get_uptime_minutes(),
        })

    @app.route("/api/positions")
    def get_positions():
        """Get open positions."""
        return jsonify(trading_engine.get_open_positions())

    @app.route("/api/signals")
    def get_signals():
        """Get recent signals for all watchlist stocks."""
        return jsonify(trading_engine.get_recent_signals())

    @app.route("/api/trades")
    def get_trades():
        """Get trade history."""
        return jsonify(trading_engine.get_trade_history())

    @app.route("/api/indicators/<symbol>")
    def get_indicators(symbol):
        """Get current indicator values for a symbol."""
        return jsonify(trading_engine.get_indicators(symbol.upper()))

    @app.route("/api/ltp")
    def get_ltp():
        """Get last traded prices."""
        return jsonify(trading_engine.get_all_ltp())

    @app.route("/api/llm-log")
    def get_llm_log():
        """Get recent LLM analysis log."""
        return jsonify(trading_engine.get_llm_log())

    @app.route("/api/ai-thinking")
    def get_ai_thinking():
        """Get AI thinking state and analysis entries for live dashboard."""
        entries = trading_engine.get_llm_log()
        confirmed = sum(1 for e in entries if e.get("llm_confirmed"))
        rejected = sum(1 for e in entries if not e.get("llm_confirmed") and e.get("llm_confidence", 0) > 0)
        confidences = [e.get("llm_confidence", 0) for e in entries if e.get("llm_confidence", 0) > 0]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0

        return jsonify({
            "is_thinking": trading_engine.is_ai_thinking(),
            "current_symbol": trading_engine.get_ai_current_symbol(),
            "entries": entries[-20:],  # Last 20 analyses
            "total_analyses": len(entries),
            "confirmed": confirmed,
            "rejected": rejected,
            "avg_confidence": avg_conf,
        })

    @app.route("/api/control/start", methods=["POST"])
    def start_trading():
        """Start trading."""
        trading_engine.start()
        return jsonify({"status": "started"})

    @app.route("/api/control/stop", methods=["POST"])
    def stop_trading():
        """Stop trading (keeps positions open)."""
        trading_engine.stop()
        return jsonify({"status": "stopped"})

    @app.route("/api/control/close-all", methods=["POST"])
    def close_all():
        """Emergency close all positions."""
        trading_engine.close_all_positions()
        return jsonify({"status": "all positions closed"})

    @app.route("/api/control/mode", methods=["POST"])
    def switch_mode():
        """Switch between paper and live mode."""
        data = request.get_json()
        mode = data.get("mode", "paper")
        if mode not in ("paper", "live"):
            return jsonify({"error": "Invalid mode"}), 400
        trading_engine.settings.trading_mode = mode
        return jsonify({"status": f"Mode switched to {mode}"})

    return app
