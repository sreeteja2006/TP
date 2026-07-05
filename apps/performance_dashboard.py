from flask import Blueprint, render_template, jsonify, request
import pandas as pd
import json
import os
import sqlite3
import yfinance as yf
from datetime import datetime, timedelta

performance_bp = Blueprint('performance', __name__, url_prefix='/performance')

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'trading.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        shares INTEGER NOT NULL,
        avg_price REAL NOT NULL,
        current_price REAL NOT NULL,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        action TEXT NOT NULL,
        symbol TEXT NOT NULL,
        shares INTEGER NOT NULL,
        price REAL NOT NULL,
        total REAL NOT NULL,
        balance_after REAL NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS portfolio_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        portfolio_value REAL NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

init_db()

PAPER_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'paper_account.json')

def load_paper_account():
    if os.path.exists(PAPER_ACCOUNT_FILE):
        with open(PAPER_ACCOUNT_FILE, 'r') as f:
            return json.load(f)
    return {'initial_balance': 100000, 'balance': 100000, 'positions': {}, 'transactions': []}

def get_live_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='2d')
        return float(hist['Close'].iloc[-1]) if not hist.empty else None
    except Exception:
        return None

def get_portfolio_summary():
    account = load_paper_account()
    positions = {}
    total_market_value = 0.0

    for symbol, pos in account['positions'].items():
        price = get_live_price(symbol) or pos.get('avg_price', 0)
        market_value = pos['shares'] * price
        cost_basis = pos['shares'] * pos['avg_price']
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        positions[symbol] = {
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
        'total_portfolio_value': total_value,
        'total_return': total_return,
        'total_return_pct': total_return_pct,
        'cash_balance': account['balance'],
        'positions': positions
    }

def get_transactions():
    account = load_paper_account()
    txns = []
    for t in reversed(account['transactions'][-10:]):
        txns.append({
            'Date': str(t.get('timestamp', ''))[:10],
            'Time': str(t.get('timestamp', ''))[11:19],
            'Action': t.get('action', ''),
            'Symbol': t.get('symbol', ''),
            'Shares': t.get('shares', 0),
            'Price': f"₹{t.get('price', 0):,.2f}",
            'Total': f"₹{t.get('total', 0):,.2f}",
            'Balance After': f"₹{t.get('balance_after', 0):,.2f}"
        })
    return txns

def get_performance_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM portfolio_history ORDER BY date ASC')
    rows = cursor.fetchall()
    dates = [r['date'] for r in rows]
    values = [r['portfolio_value'] for r in rows]
    conn.close()

    if not dates:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(31)]
        account = load_paper_account()
        initial = account['initial_balance']
        import numpy as np
        values = list(initial + np.cumsum(np.random.normal(0, initial * 0.005, 31)))

    return {'dates': dates, 'values': values}

@performance_bp.route('/')
def performance_dashboard():
    summary = get_portfolio_summary()
    transactions = get_transactions()
    performance_data = get_performance_history()

    wins = [t for t in transactions if t['Action'] == 'SELL']

    return render_template(
        'performance.html',
        summary=summary,
        transactions=transactions,
        performance_data=json.dumps(performance_data),
        stats={
            'win_rate': 'N/A',
            'avg_return': f"{summary['total_return_pct']:+.2f}%",
            'best_trade': 'N/A',
            'worst_trade': 'N/A',
            'sharpe_ratio': 'N/A',
            'max_drawdown': 'N/A'
        },
        is_demo=False
    )

@performance_bp.route('/api/data')
def get_performance_data():
    summary = get_portfolio_summary()
    summary['transactions'] = get_transactions()
    return jsonify(summary)

@performance_bp.route('/api/add_transaction', methods=['POST'])
def add_transaction():
    try:
        data = request.get_json()
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now()
        price = float(data.get('price', 0))
        shares = int(data.get('shares', 0))
        cursor.execute(
            'INSERT INTO transactions (date, time, action, symbol, shares, price, total, balance_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (data.get('date', now.strftime('%Y-%m-%d')),
             data.get('time', now.strftime('%H:%M:%S')),
             data.get('action'), data.get('symbol'), shares, price,
             price * shares, float(data.get('balance_after', 0)))
        )
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Transaction added'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500