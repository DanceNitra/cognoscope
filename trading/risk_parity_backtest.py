#!/usr/bin/env python3
"""
Risk Parity Backtest — 4 uncorrelated ETFs (SPY, TLT, GLD, GSG)
================================================================
Strategy:
  - Rebalance monthly to risk-parity weights (inverse of rolling 60-day vol)
  - Each asset weight ~ 1 / sigma_i, normalised to sum to 1

Metrics: CAGR, Sharpe ratio (RF=5%), max drawdown, Calmar ratio
Output : summary table + monthly equity curve (printed to stdout)

Dependencies: yfinance, numpy, pandas (all pip-installable)
"""

import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

# ── Config ──────────────────────────────────────────────────────────────
TICKERS = ["SPY", "TLT", "GLD", "GSG"]
START_DATE = "2008-01-01"  # GSG launched 2006-07; use 2008 to avoid early stub
END_DATE = datetime.today().strftime("%Y-%m-%d")
VOL_WINDOW = 60          # rolling window for daily volatility estimate
RF_ANNUAL = 0.05         # risk-free rate for Sharpe calculation
TRADING_DAYS = 252

# ── Data Fetch ──────────────────────────────────────────────────────────
print(f"Fetching {len(TICKERS)} tickers from {START_DATE} to {END_DATE}...")
data = yf.download(TICKERS, start=START_DATE, end=END_DATE, auto_adjust=True)

# yfinance multi-index columns → slice 'Close'
close = data["Close"][TICKERS].copy()
close.dropna(inplace=True)
print(f"Retrieved {len(close)} daily rows.\n")

# ── Daily returns ───────────────────────────────────────────────────────
returns = close.pct_change().dropna()

# ── Monthly rebalance dates (last trading day of each calendar month) ──
monthly_idx = returns.resample("M").apply(lambda s: s.index[-1] if len(s) else None).dropna()
monthly_dates = monthly_idx.index  # DatetimeIndex labelled at month-end

# ── Rolling volatility (annualised) ────────────────────────────────────
vol = returns.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std() * np.sqrt(TRADING_DAYS)

# ── Backtest Loop ──────────────────────────────────────────────────────
portfolio_value = [1.0]          # start at $1
weights_history = []             # record weights at each rebalance
equity_curve = [{"date": returns.index[0].strftime("%Y-%m-%d"), "value": 1.0}]

# Start with equal weight; stays equal until first valid vol reading
w_current = np.array([1.0 / len(TICKERS)] * len(TICKERS))
weights_history.append(w_current.copy())

first_valid_vol_idx = vol.dropna().index[0]
first_valid_vol_pos = returns.index.get_loc(first_valid_vol_idx)

for i in range(1, len(returns)):
    date = returns.index[i]
    daily_rets = returns.iloc[i].values

    # Rebalance check: monthly boundary AND we have valid vol data
    if date in monthly_dates and i >= first_valid_vol_pos:
        vol_t = vol.loc[date].values
        # Any NaN in vol means one asset hasn't warmed up yet — skip rebalance
        if not np.any(np.isnan(vol_t)):
            inv_vol = 1.0 / np.maximum(vol_t, 1e-6)
            w_current = inv_vol / inv_vol.sum()

    weights_history.append(w_current.copy())

    # Portfolio return = weighted sum of asset daily returns
    p_ret = np.dot(w_current, daily_rets)
    new_val = portfolio_value[-1] * (1.0 + p_ret)
    portfolio_value.append(new_val)

    if i % 63 == 0:  # record roughly quarterly points for equity curve
        equity_curve.append({"date": date.strftime("%Y-%m-%d"), "value": round(new_val, 6)})

# Also record final point
final_date = returns.index[-1]
equity_curve.append({"date": final_date.strftime("%Y-%m-%d"), "value": round(portfolio_value[-1], 6)})

# De-duplicate equity curve dates
seen = set()
equity_curve_dedup = []
for pt in equity_curve:
    if pt["date"] not in seen:
        seen.add(pt["date"])
        equity_curve_dedup.append(pt)
equity_curve = equity_curve_dedup

# ── Compute Metrics ─────────────────────────────────────────────────────
pvals = np.array(portfolio_value, dtype=float)
portfolio_returns = pvals[1:] / pvals[:-1] - 1.0
total_return = portfolio_value[-1] - 1.0
years = (returns.index[-1] - returns.index[0]).days / 365.25
cagr = (portfolio_value[-1] ** (1.0 / years)) - 1.0

# Sharpe (annualised)
excess = np.mean(portfolio_returns) - (RF_ANNUAL / TRADING_DAYS)
sharpe = (excess / np.std(portfolio_returns, ddof=1)) * np.sqrt(TRADING_DAYS)

# Max drawdown
peak = np.maximum.accumulate(portfolio_value)
dd = (np.array(portfolio_value) - peak) / peak
max_dd = np.min(dd)

# Calmar ratio
calmar = cagr / abs(max_dd) if max_dd != 0 else np.nan

# Last weights
last_weights = dict(zip(TICKERS, w_current))

# ── Summary Table ───────────────────────────────────────────────────────
print("=" * 70)
print("  RISK PARITY BACKTEST — RESULTS")
print("=" * 70)
print(f"  Period          : {returns.index[0].strftime('%Y-%m-%d')} → {returns.index[-1].strftime('%Y-%m-%d')}  ({years:.1f} yr)")
print(f"  Rebalance       : Monthly (last trading day)")
print(f"  Volatility lookback: {VOL_WINDOW} trading days")
print(f"  Risk-free rate  : {RF_ANNUAL*100:.1f}%")
print(f"  Tickers         : {', '.join(TICKERS)}")
print("-" * 70)
print(f"  {'Metric':<25} {'Value':>12}")
print("-" * 70)
print(f"  {'CAGR':<25} {cagr*100:>10.2f} %")
print(f"  {'Sharpe Ratio':<25} {sharpe:>10.2f}")
print(f"  {'Max Drawdown':<25} {max_dd*100:>10.2f} %")
print(f"  {'Calmar Ratio':<25} {calmar:>10.2f}")
print(f"  {'Total Return':<25} {total_return*100:>10.2f} %")
print(f"  {'Final Portfolio Value ($1)':<25} {portfolio_value[-1]:>10.4f}")
print("-" * 70)
print(f"  Last Weights (as of {final_date.strftime('%Y-%m-%d')}):")
for ticker, w in sorted(last_weights.items(), key=lambda x: -x[1]):
    print(f"    {ticker:<6}  {w*100:>6.2f} %")
print("=" * 70)

# ── Equity Curve Data Points ───────────────────────────────────────────
print("\n\nEquity Curve (date, value):")
print("-" * 50)
print(f"  {'Date':<14} {'Portfolio Value':>16}")
print("-" * 50)
for pt in equity_curve:
    print(f"  {pt['date']:<14} {pt['value']:>16.6f}")
print("-" * 50)

# ── Summary stats per asset ─────────────────────────────────────────────
print("\n\nPer-Asset Statistics (annualised):")
print("-" * 70)
print(f"  {'Ticker':<8} {'CAGR':>8} {'Vol':>8} {'Sharpe':>8} {'Avg Wt':>8}")
print("-" * 70)

asset_metrics = {}
for ticker in TICKERS:
    r = returns[ticker].values
    asset_cagr = (close[ticker].iloc[-1] / close[ticker].iloc[0]) ** (1.0 / years) - 1.0
    asset_vol = np.std(r, ddof=1) * np.sqrt(TRADING_DAYS)
    asset_sharpe = ((np.mean(r) - RF_ANNUAL / TRADING_DAYS) / np.std(r, ddof=1)) * np.sqrt(TRADING_DAYS)
    asset_metrics[ticker] = {"cagr": asset_cagr, "vol": asset_vol, "sharpe": asset_sharpe}
    # Average weight across all rebalance periods
    avg_w = np.mean([w[TICKERS.index(ticker)] for w in weights_history])
    print(f"  {ticker:<8} {asset_cagr*100:>7.2f}% {asset_vol*100:>7.2f}% {asset_sharpe:>7.2f}  {avg_w*100:>7.2f}%")

print("-" * 70)
print(f"\nCorrelation Matrix (daily returns):")
print("-" * 40)
corr = returns.corr()
for t in TICKERS:
    row = "  ".join(f"{corr.loc[t, c]:>6.3f}" for c in TICKERS)
    print(f"  {t:<6} {row}")
print("-" * 40)

print("\n✅ Backtest complete.")
