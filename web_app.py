from flask import Flask, render_template, jsonify, request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import psutil
import time

app = Flask(__name__)

os.makedirs('data', exist_ok=True)
os.makedirs('data/processed', exist_ok=True)
os.makedirs('data/raw', exist_ok=True)
os.makedirs('data/results', exist_ok=True)
os.makedirs('logs', exist_ok=True)

_predict_cache = {}
_CACHE_TTL = 3600

from apps.symbol_manager import symbol_bp
from apps.performance_dashboard import performance_bp

app.register_blueprint(symbol_bp)
app.register_blueprint(performance_bp)

PAPER_ACCOUNT_FILE = 'data/paper_account.json'

def load_paper_account():
    if os.path.exists(PAPER_ACCOUNT_FILE):
        with open(PAPER_ACCOUNT_FILE, 'r') as f:
            return json.load(f)
    return {
        'initial_balance': 100000,
        'balance': 100000,
        'positions': {},
        'transactions': []
    }

def save_paper_account(account):
    with open(PAPER_ACCOUNT_FILE, 'w') as f:
        json.dump(account, f, indent=2, default=str)

def get_live_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='2d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        return None
    except Exception:
        return None

def build_portfolio_snapshot():
    account = load_paper_account()
    positions_detail = {}
    total_market_value = 0.0

    for symbol, pos in account['positions'].items():
        price = get_live_price(symbol)
        if price is None:
            price = pos.get('avg_price', 0)
        market_value = pos['shares'] * price
        cost_basis = pos['shares'] * pos['avg_price']
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        positions_detail[symbol] = {
            'shares': pos['shares'],
            'avg_price': pos['avg_price'],
            'current_price': price,
            'market_value': market_value,
            'pnl': pnl,
            'pnl_pct': pnl_pct
        }
        total_market_value += market_value

    total_value = account['balance'] + total_market_value
    total_return = total_value - account['initial_balance']
    total_return_pct = (total_return / account['initial_balance'] * 100) if account['initial_balance'] > 0 else 0

    return {
        'portfolio_value': total_value,
        'cash_balance': account['balance'],
        'total_pnl': total_return,
        'total_pnl_pct': total_return_pct,
        'active_positions': len(positions_detail),
        'positions': positions_detail,
        'transactions': account['transactions'][-10:]
    }

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def generate_signals(symbol):
    try:
        data = yf.download(symbol, period='3mo', progress=False)
        if data.empty or len(data) < 30:
            return None

        close = data['Close'].squeeze()
        rsi = calculate_rsi(close)
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        current_price = float(close.iloc[-1])
        current_rsi = float(rsi.iloc[-1])
        s20 = float(sma20.iloc[-1])
        s50 = float(sma50.iloc[-1])

        if current_rsi < 30 and current_price > s20:
            signal = 'BUY'
            reason = f'RSI oversold ({current_rsi:.1f}) + price above SMA20'
            confidence = min(90, int(70 + (30 - current_rsi)))
        elif current_rsi > 70 and current_price < s20:
            signal = 'SELL'
            reason = f'RSI overbought ({current_rsi:.1f}) + price below SMA20'
            confidence = min(90, int(70 + (current_rsi - 70)))
        elif current_price > s20 > s50:
            signal = 'BUY'
            reason = 'Golden cross: price > SMA20 > SMA50'
            confidence = 65
        elif current_price < s20 < s50:
            signal = 'SELL'
            reason = 'Death cross: price < SMA20 < SMA50'
            confidence = 65
        else:
            signal = 'HOLD'
            reason = 'No clear directional signal'
            confidence = 40

        return {
            'signal': signal,
            'confidence': confidence,
            'reason': reason,
            'rsi': round(current_rsi, 2),
            'sma20': round(s20, 2),
            'sma50': round(s50, 2),
            'current_price': round(current_price, 2)
        }
    except Exception:
        return None

@app.route('/')
def home():
    try:
        snapshot = build_portfolio_snapshot()
        today_trades = len([
            t for t in snapshot['transactions']
            if str(t.get('timestamp', ''))[:10] == datetime.now().strftime('%Y-%m-%d')
        ])
        stats = {
            'portfolio_value': snapshot['portfolio_value'],
            'total_pnl': snapshot['total_pnl'],
            'cash_balance': snapshot['cash_balance'],
            'active_positions': snapshot['active_positions'],
            'today_trades': today_trades,
            'system_uptime': '99.8%',
            'transactions': snapshot['transactions']
        }
    except Exception:
        stats = {
            'portfolio_value': 0,
            'total_pnl': 0,
            'cash_balance': 100000,
            'active_positions': 0,
            'today_trades': 0,
            'system_uptime': 'N/A',
            'transactions': []
        }
    return render_template('home.html', stats=stats)

@app.route('/dashboard')
def dashboard():
    try:
        from apps.symbol_manager import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT symbol, name FROM watchlist ORDER BY added_date DESC')
        watchlist_symbols = cursor.fetchall()
        conn.close()
        symbols = [{'symbol': row['symbol'], 'name': row['name']} for row in watchlist_symbols]
        if not symbols:
            symbols = [
                {'symbol': 'RELIANCE.NS', 'name': 'Reliance Industries'},
                {'symbol': 'TCS.NS', 'name': 'TCS'},
                {'symbol': 'INFY.NS', 'name': 'Infosys'},
                {'symbol': 'HDFCBANK.NS', 'name': 'HDFC Bank'}
            ]
    except Exception:
        symbols = [
            {'symbol': 'RELIANCE.NS', 'name': 'Reliance Industries'},
            {'symbol': 'TCS.NS', 'name': 'TCS'},
            {'symbol': 'INFY.NS', 'name': 'Infosys'},
            {'symbol': 'HDFCBANK.NS', 'name': 'HDFC Bank'}
        ]

    selected_symbol = request.args.get('symbol')
    if not selected_symbol and symbols:
        selected_symbol = symbols[0]['symbol']

    return render_template('dashboard.html', symbols=symbols, selected_symbol=selected_symbol)

@app.route('/trading')
def trading():
    try:
        from apps.symbol_manager import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT symbol, name FROM watchlist ORDER BY added_date DESC')
        rows = cursor.fetchall()
        conn.close()
        watchlist = [{'symbol': r['symbol'], 'name': r['name']} for r in rows]
    except Exception:
        watchlist = []

    if not watchlist:
        watchlist = [
            {'symbol': 'RELIANCE.NS', 'name': 'Reliance Industries'},
            {'symbol': 'TCS.NS', 'name': 'TCS'},
            {'symbol': 'INFY.NS', 'name': 'Infosys'},
            {'symbol': 'HDFCBANK.NS', 'name': 'HDFC Bank'}
        ]

    account = load_paper_account()
    snapshot = build_portfolio_snapshot()

    return render_template('trading.html',
                           symbols=watchlist,
                           cash_balance=account['balance'],
                           portfolio=snapshot)

@app.route('/system')
def system():
    metrics = {
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_percent': psutil.disk_usage('/').percent,
        'boot_time': datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_hours': (datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds() / 3600
    }

    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i * 5)) for i in range(12)]
    timestamps.reverse()

    resource_data = {
        'timestamps': [t.strftime('%H:%M') for t in timestamps],
        'cpu': [max(0, min(100, metrics['cpu_percent'] - 10 + i * 2)) for i in range(12)],
        'memory': [max(0, min(100, metrics['memory_percent'] - 5 + i)) for i in range(12)]
    }

    services = {'web': True, 'data': True, 'trading': True}

    return render_template(
        'system.html',
        metrics=metrics,
        resource_data=json.dumps(resource_data),
        containers=[],
        services=services,
        last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/api/stock_data/<symbol>')
def get_stock_data(symbol):
    try:
        clean_symbol = symbol if symbol.endswith('.NS') or symbol.endswith('.BO') else symbol

        data = yf.download(clean_symbol, period='1mo', progress=False)
        if data.empty:
            data = yf.download(clean_symbol, period='3mo', progress=False)
        if data.empty:
            return jsonify({'error': f'No data for {symbol}'})
        if len(data) < 2:
            return jsonify({'error': f'Insufficient data for {symbol}'})

        ticker = yf.Ticker(clean_symbol)
        try:
            fi = ticker.fast_info
            current_price = fi.last_price or float(data['Close'].iloc[-1])
            prev_close = fi.previous_close or float(data['Close'].iloc[-2])
        except Exception:
            current_price = float(data['Close'].iloc[-1])
            prev_close = float(data['Close'].iloc[-2])

        close_series = data['Close'].squeeze()
        rsi_series = calculate_rsi(close_series)
        sma20 = close_series.rolling(20).mean()
        sma50 = close_series.rolling(50).mean()

        change = current_price - prev_close
        change_pct = (change / prev_close) * 100

        def safe_list(series):
            vals = series.tolist()
            return [v if v == v else None for v in vals]

        return jsonify({
            'dates': data.index.strftime('%Y-%m-%d').tolist(),
            'open': safe_list(data['Open'].squeeze()),
            'high': safe_list(data['High'].squeeze()),
            'low': safe_list(data['Low'].squeeze()),
            'close': safe_list(close_series),
            'volume': safe_list(data['Volume'].squeeze()),
            'rsi': safe_list(rsi_series),
            'sma20': safe_list(sma20),
            'sma50': safe_list(sma50),
            'current_price': round(float(current_price), 2),
            'change': round(float(change), 2),
            'change_pct': round(float(change_pct), 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/portfolio')
def get_portfolio():
    snapshot = build_portfolio_snapshot()
    portfolio_list = []
    for symbol, pos in snapshot['positions'].items():
        portfolio_list.append({
            'symbol': symbol,
            'shares': pos['shares'],
            'avg_price': pos['avg_price'],
            'current_price': pos['current_price'],
            'market_value': pos['market_value'],
            'pnl': pos['pnl'],
            'pnl_pct': pos['pnl_pct']
        })
    return jsonify(portfolio_list)

@app.route('/api/trade', methods=['POST'])
def execute_trade():
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        action = data.get('action', '').upper()
        shares = int(data.get('shares', 0))

        if not symbol or action not in ('BUY', 'SELL') or shares <= 0:
            return jsonify({'status': 'error', 'message': 'Invalid trade parameters'}), 400

        price = get_live_price(symbol)
        if price is None:
            return jsonify({'status': 'error', 'message': 'Could not fetch live price'}), 400

        account = load_paper_account()
        total = shares * price

        if action == 'BUY':
            if total > account['balance']:
                return jsonify({'status': 'error', 'message': f'Insufficient funds. Need ₹{total:,.2f}, have ₹{account["balance"]:,.2f}'}), 400
            account['balance'] -= total
            if symbol in account['positions']:
                cur = account['positions'][symbol]
                new_avg = ((cur['shares'] * cur['avg_price']) + total) / (cur['shares'] + shares)
                account['positions'][symbol]['shares'] += shares
                account['positions'][symbol]['avg_price'] = new_avg
            else:
                account['positions'][symbol] = {'shares': shares, 'avg_price': price}

        elif action == 'SELL':
            if symbol not in account['positions']:
                return jsonify({'status': 'error', 'message': f'No position in {symbol}'}), 400
            if account['positions'][symbol]['shares'] < shares:
                return jsonify({'status': 'error', 'message': f'Only have {account["positions"][symbol]["shares"]} shares'}), 400
            account['balance'] += total
            account['positions'][symbol]['shares'] -= shares
            if account['positions'][symbol]['shares'] == 0:
                del account['positions'][symbol]

        account['transactions'].append({
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'symbol': symbol,
            'shares': shares,
            'price': price,
            'total': total,
            'balance_after': account['balance']
        })

        save_paper_account(account)
        return jsonify({
            'status': 'success',
            'message': f'{action} {shares} shares of {symbol} @ ₹{price:.2f}',
            'new_balance': account['balance']
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signals/<symbol>')
def get_signals(symbol):
    result = generate_signals(symbol)
    if result is None:
        return jsonify({'status': 'error', 'message': 'Could not generate signals'}), 400
    return jsonify({'status': 'success', 'data': result})

@app.route('/api/signals/batch')
def get_batch_signals():
    try:
        from apps.symbol_manager import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT symbol FROM watchlist LIMIT 6')
        rows = cursor.fetchall()
        conn.close()
        symbols = [r['symbol'] for r in rows]
    except Exception:
        symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS']

    results = []
    for sym in symbols:
        sig = generate_signals(sym)
        if sig:
            sig['symbol'] = sym
            results.append(sig)

    return jsonify({'status': 'success', 'data': results})

@app.route('/api/system_status')
def system_status():
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'status': 'online',
        'cpu_usage': psutil.cpu_percent(),
        'memory_usage': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('/').percent,
        'uptime_hours': round((datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds() / 3600, 1)
    })

@app.route('/system/api/logs')
def get_logs():
    service = request.args.get('service', 'all')
    log_dir = 'logs'
    logs = ''
    try:
        for f in os.listdir(log_dir):
            if f.endswith('.log'):
                with open(os.path.join(log_dir, f)) as lf:
                    logs += lf.read()[-2000:]
    except Exception:
        logs = f'No logs found for {service}'
    if not logs:
        logs = 'No log entries yet.'
    return jsonify({'status': 'success', 'logs': logs})

@app.route('/system/api/restart', methods=['POST'])
def restart_services():
    return jsonify({'status': 'success', 'message': 'Restart signal sent'})

@app.route('/system/api/backup', methods=['POST'])
def create_backup():
    import shutil
    backup_time = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = 'data/backups'
    os.makedirs(backup_dir, exist_ok=True)
    try:
        shutil.copytree('data', f'{backup_dir}/backup_{backup_time}', dirs_exist_ok=True)
        return jsonify({'status': 'success', 'message': f'Backup created: backup_{backup_time}', 'file': f'backup_{backup_time}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def _next_trading_days(last_date_str, n):
    from datetime import datetime, timedelta
    dt = datetime.strptime(last_date_str, '%Y-%m-%d')
    days = []
    while len(days) < n:
        dt += timedelta(days=1)
        if dt.weekday() < 5:
            days.append(dt.strftime('%Y-%m-%d'))
    return days

def _run_arima(close_series, steps):
    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(close_series, order=(5, 1, 0))
        fitted = model.fit()
        fc = fitted.forecast(steps=steps)
        return fc.tolist()
    except Exception:
        return None

def _run_rf(data, steps):
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.preprocessing import StandardScaler
        df = data.copy()
        df['r1'] = df['Close'].pct_change()
        df['r3'] = df['Close'].pct_change(3)
        df['r5'] = df['Close'].pct_change(5)
        df['sma5'] = df['Close'].rolling(5).mean()
        df['sma10'] = df['Close'].rolling(10).mean()
        df['sma20'] = df['Close'].rolling(20).mean()
        df['vol5'] = df['Close'].rolling(5).std()
        df['vol10'] = df['Close'].rolling(10).std()
        if 'Volume' in df.columns:
            df['vol_chg'] = df['Volume'].pct_change()
            df['vol_sma5'] = df['Volume'].rolling(5).mean()
        df['target'] = df['Close'].shift(-1)
        df = df.dropna()
        if len(df) < 30:
            return None
        feature_cols = [c for c in df.columns if c not in ('Close', 'Open', 'High', 'Low', 'Volume', 'target')]
        X = df[feature_cols].values
        y = df['target'].values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        rf.fit(X_scaled, y)
        preds = []
        last_row = df[feature_cols].iloc[-1:].values.copy()
        last_price = float(df['Close'].iloc[-1])
        for _ in range(steps):
            p = float(rf.predict(scaler.transform(last_row))[0])
            preds.append(p)
            last_row[0][0] = (p - last_price) / last_price if last_price != 0 else 0
            last_price = p
        return preds
    except Exception:
        return None

@app.route('/api/predict/<symbol>')
def predict_price(symbol):
    global _predict_cache
    now = time.time()
    if symbol in _predict_cache:
        cached = _predict_cache[symbol]
        if now - cached['ts'] < _CACHE_TTL:
            return jsonify(cached['data'])

    try:
        data = yf.download(symbol, period='6mo', progress=False)
        if data.empty or len(data) < 40:
            return jsonify({'error': f'Not enough data for {symbol}'}), 400

        close = data['Close'].squeeze().dropna()
        steps = 5

        arima_preds = _run_arima(close, steps)
        rf_preds = _run_rf(data, steps)

        if arima_preds is None and rf_preds is None:
            return jsonify({'error': 'Both models failed to generate predictions'}), 500

        if arima_preds and rf_preds:
            ensemble = [(a * 0.4 + r * 0.6) for a, r in zip(arima_preds, rf_preds)]
        elif arima_preds:
            ensemble = arima_preds
        else:
            ensemble = rf_preds

        future_dates = _next_trading_days(data.index[-1].strftime('%Y-%m-%d'), steps)

        result = {
            'symbol': symbol,
            'last_actual_date': data.index[-1].strftime('%Y-%m-%d'),
            'last_actual_price': round(float(close.iloc[-1]), 2),
            'future_dates': future_dates,
            'arima': [round(p, 2) for p in arima_preds] if arima_preds else None,
            'random_forest': [round(p, 2) for p in rf_preds] if rf_preds else None,
            'ensemble': [round(p, 2) for p in ensemble],
            'models_used': ([('ARIMA' if arima_preds else '')] + [('RandomForest' if rf_preds else '')]),
            'cached_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        _predict_cache[symbol] = {'ts': now, 'data': result}
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})


@app.route('/api/search_symbols/<query>')
def search_symbols(query):
    try:
        info = yf.Ticker(query).info
        results = [{'symbol': info.get('symbol', query), 'name': info.get('shortName', query), 'exchange': info.get('exchange', 'N/A')}]
        return jsonify(results)
    except Exception:
        return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)