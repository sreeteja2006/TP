import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import json
import os
from datetime import datetime


class RiskManager:
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_portfolio_risk = 0.02
        self.max_position_risk = 0.01
        self.max_sector_exposure = 0.3
        self.max_single_stock = 0.1
        self.default_stop_loss = 0.05
        self.default_take_profit = 0.15
        self.trailing_stop = 0.03
        self.positions = {}
        self.sector_exposure = {}
        self.daily_pnl = []
        self.risk_metrics = {}
        self._load()

    def _load(self):
        if os.path.exists('risk_data.json'):
            with open('risk_data.json', 'r') as f:
                data = json.load(f)
                self.daily_pnl = data.get('daily_pnl', [])
                self.sector_exposure = data.get('sector_exposure', {})
                self.risk_metrics = data.get('risk_metrics', {})

    def _save(self):
        with open('risk_data.json', 'w') as f:
            json.dump({
                'daily_pnl': self.daily_pnl,
                'sector_exposure': self.sector_exposure,
                'risk_metrics': self.risk_metrics,
                'last_updated': datetime.now().isoformat()
            }, f, indent=2)

    def calculate_position_size(self, symbol: str, entry_price: float, stop_loss_price: float) -> int:
        risk_per_share = abs(entry_price - stop_loss_price)
        max_risk_amount = self.current_capital * self.max_position_risk
        max_by_risk = int(max_risk_amount / risk_per_share) if risk_per_share > 0 else 0
        max_by_concentration = int(self.current_capital * self.max_single_stock / entry_price)
        return min(max_by_risk, max_by_concentration)

    def validate_trade(self, symbol: str, action: str, quantity: int, price: float, sector: str = None) -> Tuple[bool, str]:
        now = datetime.now()
        if now.weekday() >= 5:
            return False, 'Market is closed (weekend)'
        if not (9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30)):
            return False, 'Market is closed (outside trading hours)'
        trade_value = quantity * price
        if action.upper() == 'BUY':
            if trade_value > self.current_capital * 0.9:
                return False, f'Insufficient capital. Need ₹{trade_value:,.2f}'
            cur_exp = self.positions.get(symbol, {}).get('market_value', 0)
            if (cur_exp + trade_value) / self.current_capital > self.max_single_stock:
                return False, f'Single stock limit exceeded (max {self.max_single_stock:.1%})'
            if sector:
                cur_sec = self.sector_exposure.get(sector, 0)
                if (cur_sec + trade_value) / self.current_capital > self.max_sector_exposure:
                    return False, f'Sector limit exceeded (max {self.max_sector_exposure:.1%})'
        elif action.upper() == 'SELL':
            cur_qty = self.positions.get(symbol, {}).get('quantity', 0)
            if quantity > cur_qty:
                return False, f'Insufficient shares. Have {cur_qty}'
        return True, 'Trade validated'

    def update_position(self, symbol: str, action: str, quantity: int, price: float, sector: str = None):
        if symbol not in self.positions:
            self.positions[symbol] = {'quantity': 0, 'avg_price': 0, 'market_value': 0, 'unrealized_pnl': 0, 'sector': sector}
        pos = self.positions[symbol]
        if action.upper() == 'BUY':
            total_cost = pos['quantity'] * pos['avg_price'] + quantity * price
            total_qty = pos['quantity'] + quantity
            pos['avg_price'] = total_cost / total_qty if total_qty > 0 else 0
            pos['quantity'] = total_qty
            pos['market_value'] = total_qty * price
            if sector:
                self.sector_exposure[sector] = self.sector_exposure.get(sector, 0) + quantity * price
        elif action.upper() == 'SELL':
            pos['quantity'] -= quantity
            pos['market_value'] = pos['quantity'] * price
            if sector:
                self.sector_exposure[sector] = max(0, self.sector_exposure.get(sector, 0) - quantity * price)
            if pos['quantity'] <= 0:
                del self.positions[symbol]

    def calculate_stop_loss(self, entry_price: float, action: str = 'BUY') -> float:
        return entry_price * (1 - self.default_stop_loss) if action.upper() == 'BUY' else entry_price * (1 + self.default_stop_loss)

    def calculate_take_profit(self, entry_price: float, action: str = 'BUY') -> float:
        return entry_price * (1 + self.default_take_profit) if action.upper() == 'BUY' else entry_price * (1 - self.default_take_profit)

    def check_stop_loss_take_profit(self, current_prices: Dict[str, float]) -> List[Dict]:
        alerts = []
        for symbol, pos in self.positions.items():
            if symbol not in current_prices:
                continue
            cp = current_prices[symbol]
            ep = pos['avg_price']
            pnl_pct = (cp - ep) / ep
            if pnl_pct <= -self.default_stop_loss:
                alerts.append({'type': 'STOP_LOSS', 'symbol': symbol, 'current_price': cp, 'entry_price': ep, 'pnl_pct': pnl_pct, 'action': 'SELL', 'quantity': pos['quantity']})
            elif pnl_pct >= self.default_take_profit:
                alerts.append({'type': 'TAKE_PROFIT', 'symbol': symbol, 'current_price': cp, 'entry_price': ep, 'pnl_pct': pnl_pct, 'action': 'SELL', 'quantity': pos['quantity']})
        return alerts

    def calculate_portfolio_metrics(self) -> Dict:
        if not self.daily_pnl:
            return {}
        returns = np.array(self.daily_pnl)
        vol = np.std(returns)
        rfr = 0.06 / 252
        sharpe = (np.mean(returns) - rfr) / vol if vol > 0 else 0
        cum = np.cumsum(returns)
        max_dd = np.min(cum - np.maximum.accumulate(cum))
        win_rate = len([r for r in returns if r > 0]) / len(returns)
        return {
            'total_return': float(np.sum(returns)),
            'avg_daily_return': float(np.mean(returns)),
            'volatility': float(vol),
            'sharpe_ratio': float(sharpe),
            'max_drawdown': float(max_dd),
            'win_rate': float(win_rate),
            'var_95': float(np.percentile(returns, 5)),
            'total_trades': len(returns)
        }

    def add_daily_pnl(self, pnl: float):
        self.daily_pnl.append(pnl)
        if len(self.daily_pnl) > 252:
            self.daily_pnl = self.daily_pnl[-252:]
        self._save()