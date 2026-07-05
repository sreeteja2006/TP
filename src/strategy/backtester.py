import pandas as pd
import numpy as np


class Transaction:
    def __init__(self, date, type, price, shares, costs):
        self.date = date
        self.type = type
        self.price = price
        self.shares = shares
        self.costs = costs
        self.total = price * shares + costs


def calculate_slippage(price, shares, slippage_pct=0.001):
    return price * slippage_pct * (1 + np.log10(shares))


def position_size(capital, risk_per_trade, stop_loss_pct, price):
    risk_amount = capital * risk_per_trade
    stop_loss_amount = price * stop_loss_pct
    return int(risk_amount // stop_loss_amount)


def risk_metrics(portfolio_df):
    returns = portfolio_df['Portfolio Value'].pct_change().dropna()
    sharpe = (returns.mean() / returns.std() * (252 ** 0.5)) if len(returns) > 0 and returns.std() != 0 else 0
    cum_max = portfolio_df['Portfolio Value'].cummax()
    drawdown = (portfolio_df['Portfolio Value'] - cum_max) / cum_max
    return {
        'Sharpe Ratio': float(sharpe),
        'Max Drawdown': float(drawdown.min()),
        'Total Return': float(portfolio_df['Portfolio Value'].iloc[-1] / portfolio_df['Portfolio Value'].iloc[0] - 1)
    }


def simple_backtest_with_risk(data, signal_column='Signal', initial_capital=100000, risk_per_trade=0.01, stop_loss_pct=0.05, take_profit_pct=0.10):
    capital = initial_capital
    position = 0
    entry_price = 0
    history = []

    for idx, row in data.iterrows():
        price = row['Close']
        signal = row[signal_column]

        if signal == 'Buy' and position == 0:
            shares = position_size(capital, risk_per_trade, stop_loss_pct, price)
            position = shares
            entry_price = price
            capital -= shares * price
        elif signal == 'Sell' and position > 0:
            capital += position * price
            position = 0
            entry_price = 0

        if position > 0 and price <= entry_price * (1 - stop_loss_pct):
            capital += position * price
            position = 0
            entry_price = 0

        if position > 0 and price >= entry_price * (1 + take_profit_pct):
            capital += position * price
            position = 0
            entry_price = 0

        history.append({'Date': idx, 'Portfolio Value': capital + position * price})

    return pd.DataFrame(history)


def simple_backtest_with_costs(data, signal_column='Signal', initial_capital=100000, commission_pct=0.001, slippage_pct=0.001):
    portfolio = {'cash': initial_capital, 'position': 0}
    transactions = []
    history = []

    for idx, row in data.iterrows():
        current_value = portfolio['cash'] + portfolio['position'] * row['Close']
        history.append({'Date': idx, 'Portfolio Value': current_value, 'Cash': portfolio['cash'], 'Position': portfolio['position']})

        if row[signal_column] == 'Buy' and portfolio['cash'] > 0:
            shares = int(portfolio['cash'] * 0.95 / row['Close'])
            if shares > 0:
                slippage = calculate_slippage(row['Close'], shares, slippage_pct)
                commission = shares * row['Close'] * commission_pct
                total_cost = shares * (row['Close'] + slippage) + commission
                if total_cost <= portfolio['cash']:
                    portfolio['cash'] -= total_cost
                    portfolio['position'] += shares
                    transactions.append(Transaction(idx, 'Buy', row['Close'], shares, commission + slippage * shares))

        elif row[signal_column] == 'Sell' and portfolio['position'] > 0:
            shares = portfolio['position']
            slippage = calculate_slippage(row['Close'], shares, slippage_pct)
            commission = shares * row['Close'] * commission_pct
            portfolio['cash'] += shares * (row['Close'] - slippage) - commission
            portfolio['position'] = 0
            transactions.append(Transaction(idx, 'Sell', row['Close'], shares, commission + slippage * shares))

    return pd.DataFrame(history), transactions


def multi_asset_backtest(stock_data_dict, signal_column='Signal', initial_capital=100000):
    portfolio = {'cash': initial_capital, 'positions': {k: 0 for k in stock_data_dict}}
    history = []
    dates = stock_data_dict[list(stock_data_dict.keys())[0]].index

    for date in dates:
        daily_value = portfolio['cash']
        for ticker, data in stock_data_dict.items():
            price = data.loc[date, 'Close']
            signal = data.loc[date, signal_column]
            if signal == 'Buy' and portfolio['cash'] >= price:
                shares = int(portfolio['cash'] // price)
                portfolio['positions'][ticker] += shares
                portfolio['cash'] -= shares * price
            elif signal == 'Sell' and portfolio['positions'][ticker] > 0:
                portfolio['cash'] += portfolio['positions'][ticker] * price
                portfolio['positions'][ticker] = 0
            daily_value += portfolio['positions'][ticker] * price
        history.append({'Date': date, 'Portfolio Value': daily_value})

    return pd.DataFrame(history)
