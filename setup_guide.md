# AI Stock Trading Bot - Setup Guide

## Prerequisites

1. **Python 3.10+** installed on your system
2. **Finvasia (Shoonya) demat account**
3. **Ollama** for local LLM (optional but recommended)
4. **NVIDIA drivers** installed for GPU acceleration

---

## Step 1: Enable Shoonya API Access

1. Log in to your Finvasia account at https://shoonya.finvasia.com/
2. Go to **Profile → API Access** and enable it
3. Note down your credentials:
   - **User ID** (e.g., FA12345)
   - **Password**
   - **Vendor Code** (provided by Finvasia)
   - **API Secret** (generated when you enable API)
   - **IMEI** (any unique identifier string, e.g., "abc1234")
4. Set up **TOTP (2FA)**:
   - Go to **Profile → Security → Two Factor Authentication**
   - When setting up Google Authenticator, copy the **TOTP secret key**
   - This is the base32 secret (looks like `JBSWY3DPEHPK3PXP`)
   - You'll need this for automatic login

---

## Step 2: Install Ollama & LLM Model

### Install Ollama

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download from https://ollama.com/download

### Pull the Phi-3 model (optimized for your RTX 2050)
```bash
ollama pull phi3:mini
```

### Verify it's working
```bash
ollama run phi3:mini "Say hello in one word"
```

This model uses ~2.3GB VRAM, leaving enough room on your 4GB RTX 2050.

---

## Step 3: Set Up the Trading Bot

### Clone and install dependencies
```bash
cd /path/to/chatbot
pip install -r requirements.txt
```

### Configure credentials
```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:
```
SHOONYA_USER_ID=FA12345
SHOONYA_PASSWORD=your_actual_password
SHOONYA_VENDOR_CODE=your_vendor_code
SHOONYA_API_SECRET=your_api_secret
SHOONYA_IMEI=abc1234
SHOONYA_TOTP_SECRET=JBSWY3DPEHPK3PXP

TRADING_MODE=paper
TRADING_CAPITAL=100000

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi3:mini
```

**IMPORTANT:** Never share your `.env` file or commit it to git!

---

## Step 4: Run the Bot

### Start Ollama (in a separate terminal)
```bash
ollama serve
```

### Start the trading bot (paper trading mode)
```bash
python main.py
```

### Or specify mode explicitly
```bash
python main.py --mode paper      # Simulated trades (default)
python main.py --mode live       # Real trades (be careful!)
python main.py --port 8080       # Custom dashboard port
```

### Access the dashboard
Open your browser: **http://localhost:5000**

---

## Step 5: Paper Trading (Recommended First!)

Run in paper trading mode for **at least 1-2 weeks** before going live.

Paper trading mode:
- Uses **real market data** from Shoonya WebSocket
- **Simulates order execution** (no real money at risk)
- Tracks virtual P&L to validate strategy
- Full dashboard with all features

Monitor these metrics before going live:
- **Win rate** should be > 50%
- **Average win > Average loss** (positive expectancy)
- **Max drawdown** should be within your comfort level
- **No unexpected behavior** during volatile market hours

---

## Step 6: Going Live

Once paper trading results are satisfactory:

1. Change mode in `.env`:
   ```
   TRADING_MODE=live
   ```
2. Start with a **small capital** (e.g., ₹25,000)
3. Monitor the dashboard closely for the first few days
4. Use the **Emergency Close All** button if anything looks wrong

---

## Trading Hours (IST)

| Time | Activity |
|------|----------|
| 09:15 | Market opens |
| 09:15 - 09:30 | No trading (high volatility period) |
| 09:30 - 14:30 | Active trading window |
| 14:30 | Stop opening new trades |
| 15:10 | Auto square-off all positions |
| 15:30 | Market closes |

---

## Risk Management Settings

Edit `config/settings.py` or set via `.env` to adjust:

| Parameter | Default | Description |
|-----------|---------|-------------|
| max_risk_per_trade_pct | 1% | Max capital risk per trade |
| max_daily_loss_pct | 3% | Stop trading if daily loss exceeds this |
| max_open_positions | 2 | Maximum simultaneous positions |
| stop_loss_pct | 0.5% | Default stop-loss distance |
| take_profit_pct | 1.0% | Default take-profit (2:1 R/R ratio) |
| trailing_stop_pct | 0.3% | Trailing stop distance |
| min_capital_reserve | ₹10,000 | Never trade below this balance |

---

## Customizing the Watchlist

Edit the `watchlist` in `config/settings.py`:

```python
watchlist: list = field(default_factory=lambda: [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
])
```

Choose liquid, large-cap NSE stocks for best results with intraday trading.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "NorenRestApiPy not installed" | `pip install NorenRestApiPy` |
| "Ollama not running" | Run `ollama serve` in a separate terminal |
| "Model not found" | Run `ollama pull phi3:mini` |
| "Login failed" | Check credentials in `.env`, ensure TOTP secret is correct |
| "WebSocket disconnected" | Check internet connection, bot will auto-reconnect |
| Dashboard not loading | Ensure port 5000 is free, try `--port 8080` |
| High CPU usage | Reduce watchlist size or increase analysis interval |

---

## Disclaimer

This software is for **educational and personal use only**. Stock trading involves
substantial risk of financial loss. Past performance (including paper trading results)
does not guarantee future results. The developer is not responsible for any financial
losses incurred through the use of this software. Always trade responsibly and never
invest money you cannot afford to lose.
