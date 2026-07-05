from flask import Blueprint, render_template, jsonify, request
import yfinance as yf
import json
import os
import sqlite3
from datetime import datetime
import requests
import pandas as pd

symbol_bp = Blueprint('symbols', __name__, url_prefix='/symbols')

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'watchlist.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        market TEXT NOT NULL,
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

init_db()

@symbol_bp.route('/')
def manage_symbols():
    return render_template('manage_symbols.html')

@symbol_bp.route('/api/search_symbols')
def search_symbols():
    query = request.args.get('query', '')
    market = request.args.get('market', 'all')

    if not query:
        return jsonify({'status': 'error', 'message': 'Query is required'}), 400

    try:
        results = []

        try:
            url = f'https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=20&newsCount=0'
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if 'quotes' in data and data['quotes']:
                    for quote in data['quotes']:
                        if 'symbol' not in quote:
                            continue
                        market_type = _market_type_from_quote(quote)
                        if market != 'all' and market.lower() != market_type.lower():
                            continue
                        price, change = _get_quick_price(quote['symbol'])
                        results.append({
                            'symbol': quote['symbol'],
                            'name': quote.get('shortname', quote.get('longname', 'Unknown')),
                            'market': market_type,
                            'price': price,
                            'change': change
                        })
        except Exception:
            pass

        if not results:
            try:
                ticker = yf.Ticker(query)
                info = ticker.info
                if info and 'symbol' in info:
                    market_type = _market_type_from_info(info)
                    if market == 'all' or market.lower() == market_type.lower():
                        results.append({
                            'symbol': info['symbol'],
                            'name': info.get('longName', info.get('shortName', 'Unknown')),
                            'market': market_type,
                            'price': info.get('regularMarketPrice'),
                            'change': info.get('regularMarketChangePercent')
                        })
            except Exception:
                pass

        return jsonify({'status': 'success', 'data': results})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def _get_quick_price(symbol):
    try:
        hist = yf.Ticker(symbol).history(period='2d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            change = ((price - float(hist['Close'].iloc[-2])) / float(hist['Close'].iloc[-2]) * 100) if len(hist) > 1 else None
            return price, change
    except Exception:
        pass
    return None, None

def _market_type_from_quote(quote):
    qt = quote.get('quoteType', '')
    if qt == 'EQUITY': return 'Stocks'
    if qt == 'ETF': return 'ETFs'
    if qt == 'INDEX': return 'Indices'
    if qt in ('CURRENCY', 'CRYPTOCURRENCY'): return 'Forex'
    if qt == 'FUTURE': return 'Commodities'
    ex = quote.get('exchange', '').upper()
    if ex in ('MCX', 'NYMEX', 'COMEX'): return 'Commodities'
    return 'Stocks'

def _market_type_from_info(info):
    qt = info.get('quoteType', '')
    if qt == 'EQUITY': return 'Stocks'
    if qt == 'ETF': return 'ETFs'
    if qt == 'INDEX': return 'Indices'
    if qt in ('CURRENCY', 'CRYPTOCURRENCY'): return 'Forex'
    return 'Stocks'

@symbol_bp.route('/api/watchlist')
def get_watchlist():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM watchlist ORDER BY added_date DESC')
        rows = cursor.fetchall()
        conn.close()
        watchlist = []
        for row in rows:
            price, change = _get_quick_price(row['symbol'])
            watchlist.append({
                'symbol': row['symbol'],
                'name': row['name'],
                'market': row['market'],
                'price': price,
                'change': change
            })
        return jsonify({'status': 'success', 'data': watchlist})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@symbol_bp.route('/api/watchlist/add', methods=['POST'])
def add_to_watchlist():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ('symbol', 'name', 'market')):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM watchlist WHERE symbol = ?', (data['symbol'],))
        if cursor.fetchone():
            conn.close()
            return jsonify({'status': 'error', 'message': 'Symbol already in watchlist'}), 400

        cursor.execute('INSERT INTO watchlist (symbol, name, market) VALUES (?, ?, ?)',
                       (data['symbol'], data['name'], data['market']))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': f'{data["symbol"]} added to watchlist'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@symbol_bp.route('/api/watchlist/remove', methods=['POST'])
def remove_from_watchlist():
    try:
        data = request.get_json()
        if not data or 'symbol' not in data:
            return jsonify({'status': 'error', 'message': 'Symbol is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM watchlist WHERE symbol = ?', (data['symbol'],))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': f'{data["symbol"]} removed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@symbol_bp.route('/api/watchlist/save', methods=['POST'])
def save_watchlist():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT symbol FROM watchlist')
        symbols = [r['symbol'] for r in cursor.fetchall()]
        conn.close()

        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'trading_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = {'max_positions': 8, 'position_size_pct': 0.1, 'stop_loss_pct': 0.05, 'take_profit_pct': 0.15, 'daily_loss_limit': 0.02, 'max_trades_per_day': 10}

        config['symbols'] = symbols
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return jsonify({'status': 'success', 'message': 'Watchlist saved to config'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@symbol_bp.route('/api/download_stock_lists', methods=['POST'])
def download_stock_lists():
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(data_dir, exist_ok=True)

        try:
            nse_df = pd.read_csv('https://archives.nseindia.com/content/equities/EQUITY_L.csv')
            nse_df = nse_df[['SYMBOL', 'NAME OF COMPANY']]
            nse_df.columns = ['Symbol', 'Company Name']
            nse_df.to_csv(os.path.join(data_dir, 'nse_stocks.csv'), index=False)
        except Exception:
            pass

        try:
            tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
            sp500 = tables[0][['Symbol', 'Security']]
            sp500.columns = ['Symbol', 'Name']
            sp500.to_csv(os.path.join(data_dir, 'us_stocks.csv'), index=False)
        except Exception:
            pass

        return jsonify({'status': 'success', 'message': 'Stock lists downloaded'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500