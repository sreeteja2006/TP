# TradePro

**FOR LEARNING ONLY. NOT FOR REAL TRADING.**

A paper trading web application built with Python and Flask. It pulls live market data, runs ML price predictions, and lets you execute simulated trades.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-trading--strategy--nttz.onrender.com-brightgreen?style=for-the-badge&logo=render)](https://trading-strategy-nttz.onrender.com)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3.3-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Render%20Managed-336791?logo=postgresql)
![Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?logo=render)

## Live Demo

[https://trading-strategy-nttz.onrender.com](https://trading-strategy-nttz.onrender.com)

The app runs on Render's free tier and may take around 30 seconds to wake up on the first visit.

| Page | URL |
|---|---|
| Home | `/` |
| Trading Dashboard | `/dashboard` |
| Paper Trading | `/trading` |
| Performance | `/performance/` |
| Symbol Manager | `/symbols/` |
| System Status | `/system` |

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask 2.3.3 |
| Server | Gunicorn (2 workers) |
| Database | PostgreSQL (Render Managed) |
| Market Data | yfinance |
| ML Models | scikit-learn (Random Forest), statsmodels (ARIMA) |
| Charts | Plotly.js |
| Frontend | HTML, CSS, JavaScript |
| Hosting | Render |

## Features

**Trading Dashboard**
Real-time candlestick charts with RSI, SMA20, and SMA50 overlays. Generates BUY / SELL / HOLD signals based on RSI thresholds and moving average crossovers.

**Paper Trading**
Execute BUY and SELL orders at live market prices against a simulated account starting at 1,00,000 INR. Positions and transaction history persist in PostgreSQL.

**ML Price Predictions**
5-day ahead price forecast using an ARIMA + Random Forest ensemble. Results are cached per symbol for 1 hour.

**Symbol Manager**
Search any stock across NSE, NYSE, NASDAQ, ETFs, and Forex. Watchlist is stored in PostgreSQL and persists across restarts.

**Performance Dashboard**
Portfolio value over time, position breakdown, P&L per position, and full transaction history.

**System Status**
Live CPU, memory, and disk usage. Service health indicators and log viewer.

## ML Models

### ARIMA (40% weight)

Order: ARIMA(5, 1, 0). Uses the last 5 days of closing prices, differences once to remove trend, and forecasts the next 5 trading days. Handles short-term momentum well.

### Random Forest (60% weight)

100 decision trees trained on 10 engineered features: 1/3/5-day price returns, 5/10/20-day SMAs, 5/10-day rolling volatility, volume change, and 5-day volume SMA.

### Ensemble

```
Final Prediction = 0.4 x ARIMA + 0.6 x Random Forest
```

## Database Schema

All tables are created automatically on first boot using `CREATE TABLE IF NOT EXISTS`.

| Table | Purpose |
|---|---|
| `paper_account` | Cash balance, positions, and transaction history (JSONB) |
| `watchlist` | Saved symbols |
| `positions` | Open position tracker |
| `transactions` | Full trade log |
| `portfolio_history` | Portfolio value over time |

## Project Structure

```
TP/
    web_app.py                      Main Flask app and paper trading routes
    db.py                           Shared PostgreSQL connection helper
    apps/
        symbol_manager.py           Watchlist CRUD and symbol search
        performance_dashboard.py    Portfolio analytics
    templates/                      Jinja2 HTML templates
        base.html
        home.html
        dashboard.html
        trading.html
        performance.html
        manage_symbols.html
        system.html
    static/
        css/
        js/
    src/
        models/                     ML model implementations
    config/                         JSON config files
    Dockerfile
    docker-compose.yml
    render.yaml
    requirements.txt
```

## Local Setup

Requirements: Python 3.11+ and a PostgreSQL instance (local or remote).

```bash
git clone https://github.com/sreeteja2006/TP.git
cd TP

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

export DATABASE_URL="postgresql://postgres:yourpassword@localhost:5432/tradepro"

python web_app.py
```

The app will be available at `http://localhost:5000`. All database tables are created on startup.

### Docker

```bash
docker-compose up -d
```

## Render Deployment

The app runs as a Render web service backed by a Render managed PostgreSQL database.

1. Create a PostgreSQL database on Render (free plan).
2. Create a web service and connect your GitHub repository.
3. Add an environment variable `DATABASE_URL` using the Internal Connection String from the database.
4. Set the build command to `pip install -r requirements.txt`.
5. Set the start command to `gunicorn --workers 2 --timeout 120 web_app:app`.

The included `render.yaml` can auto-provision both services if you use Render's Blueprint feature.

## Configuration

`config/trading_config.json`

```json
{
  "max_positions": 8,
  "position_size_pct": 0.1,
  "stop_loss_pct": 0.05,
  "take_profit_pct": 0.15,
  "daily_loss_limit": 0.02,
  "max_trades_per_day": 10
}
```

## Disclaimer

This is a paper trading simulator. No real money is involved. The signals and predictions are not financial advice. Market data is sourced from Yahoo Finance via the yfinance library.

## Contact

GitHub: [sreeteja2006](https://github.com/sreeteja2006)
Email: gsreeteja25@gmail.com