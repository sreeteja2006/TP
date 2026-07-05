import yfinance as yf
from datetime import datetime
import json
import os
import logging

logger = logging.getLogger(__name__)


class PaperTradingAccount:
    def __init__(self, initial_balance=100000, account_file='data/paper_account.json'):
        self.account_file = account_file
        self._load_or_init(initial_balance)

    def _load_or_init(self, initial_balance):
        if os.path.exists(self.account_file):
            with open(self.account_file, 'r') as f:
                data = json.load(f)
            self.initial_balance = data['initial_balance']
            self.balance = data['balance']
            self.positions = data['positions']
            self.transactions = data['transactions']
        else:
            self.initial_balance = initial_balance
            self.balance = initial_balance
            self.positions = {}
            self.transactions = []

    def _save(self):
        os.makedirs(os.path.dirname(self.account_file), exist_ok=True)
        with open(self.account_file, 'w') as f:
            json.dump({
                'initial_balance': self.initial_balance,
                'balance': self.balance,
                'positions': self.positions,
                'transactions': self.transactions
            }, f, indent=2, default=str)

    def get_current_price(self, symbol):
        try:
            hist = yf.Ticker(symbol).history(period='2d')
            return float(hist['Close'].iloc[-1]) if not hist.empty else None
        except Exception:
            return None

    def buy_stock(self, symbol, shares, price=None):
        if price is None:
            price = self.get_current_price(symbol)
        if price is None:
            return False, 'Could not get current price'
        total_cost = shares * price
        if total_cost > self.balance:
            return False, f'Insufficient funds. Need ₹{total_cost:.2f}, have ₹{self.balance:.2f}'
        self.balance -= total_cost
        if symbol in self.positions:
            cur = self.positions[symbol]
            new_avg = (cur['shares'] * cur['avg_price'] + shares * price) / (cur['shares'] + shares)
            self.positions[symbol]['shares'] += shares
            self.positions[symbol]['avg_price'] = new_avg
        else:
            self.positions[symbol] = {'shares': shares, 'avg_price': price}
        self.transactions.append({'timestamp': datetime.now().isoformat(), 'action': 'BUY', 'symbol': symbol, 'shares': shares, 'price': price, 'total': total_cost, 'balance_after': self.balance})
        self._save()
        return True, f'Bought {shares} shares of {symbol} at ₹{price:.2f}'

    def sell_stock(self, symbol, shares, price=None):
        if symbol not in self.positions:
            return False, f'No position in {symbol}'
        if self.positions[symbol]['shares'] < shares:
            return False, f'Only have {self.positions[symbol]["shares"]} shares'
        if price is None:
            price = self.get_current_price(symbol)
        if price is None:
            return False, 'Could not get current price'
        proceeds = shares * price
        self.balance += proceeds
        self.positions[symbol]['shares'] -= shares
        if self.positions[symbol]['shares'] == 0:
            del self.positions[symbol]
        self.transactions.append({'timestamp': datetime.now().isoformat(), 'action': 'SELL', 'symbol': symbol, 'shares': shares, 'price': price, 'total': proceeds, 'balance_after': self.balance})
        self._save()
        return True, f'Sold {shares} shares of {symbol} at ₹{price:.2f}'

    def get_portfolio_summary(self):
        summary = {'cash_balance': self.balance, 'positions': {}, 'total_portfolio_value': 0, 'total_return': 0, 'total_return_pct': 0}
        position_value = 0.0
        for symbol, pos in self.positions.items():
            price = self.get_current_price(symbol) or pos['avg_price']
            mv = pos['shares'] * price
            cb = pos['shares'] * pos['avg_price']
            pnl = mv - cb
            summary['positions'][symbol] = {'shares': pos['shares'], 'avg_price': pos['avg_price'], 'current_price': price, 'market_value': mv, 'cost_basis': cb, 'pnl': pnl, 'pnl_pct': (pnl / cb * 100) if cb > 0 else 0}
            position_value += mv
        summary['total_portfolio_value'] = self.balance + position_value
        summary['total_return'] = summary['total_portfolio_value'] - self.initial_balance
        summary['total_return_pct'] = summary['total_return'] / self.initial_balance * 100
        return summary