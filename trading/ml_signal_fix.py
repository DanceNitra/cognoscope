#!/usr/bin/env python3
"""
ML Signal (Triple-Barrier) Fix Prototype
=========================================

Problem from Layer 3 validation:
  - Original used 2x ATR barriers → too few trades generated
  - Fix: reduce barriers to 1.5x ATR

This prototype:
  1. Fetches SPY daily data via yfinance (2000–2025)
  2. Implements triple-barrier labeling:
     - Upper barrier (take-profit): entry_price + n * ATR
     - Lower barrier (stop-loss):  entry_price - n * ATR
     - Max holding period (time barrier): 5 days
     - n = 2.0 (original) vs n = 1.5 (fixed)
  3. Counts how many trades each version generates
  4. Compares hit rates, avg returns, trade durations

Usage:
    python ml_signal_fix.py
"""

import os
import sys
import warnings
from typing import Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_missing = []
try:
    import yfinance as yf
except ImportError:
    _missing.append("yfinance")
if _missing:
    print(f"[ERROR] Missing required packages: {', '.join(_missing)}")
    print("Install with: pip install yfinance pandas numpy")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Data Fetch
# ══════════════════════════════════════════════════════════════════════════════

def fetch_data(
    start: str = "2000-01-01",
    end: str = "2025-05-01",
) -> pd.DataFrame:
    """
    Download SPY daily OHLCV data. Returns DataFrame with columns:
        open, high, low, close, volume
    """
    print(f"[INFO] Fetching SPY data ({start} to {end}) ...")
    spy = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)

    # yfinance returns MultiIndex columns (Price, Ticker) since v0.2.44
    # Each column like spy["Close"] is (n, 1) DataFrame — squeeze to Series
    df = pd.DataFrame({
        "open": spy["Open"].squeeze(),
        "high": spy["High"].squeeze(),
        "low": spy["Low"].squeeze(),
        "close": spy["Close"].squeeze(),
        "volume": spy["Volume"].squeeze(),
    }, index=spy.index)

    df.dropna(inplace=True)
    print(f"[INFO] Fetched {len(df)} daily rows ({df.index[0].date()} → {df.index[-1].date()})")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 2. ATR Calculation
# ══════════════════════════════════════════════════════════════════════════════

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (ATR) using Wilder's smoothed method.

    True Range = max(
        high - low,
        |high - prev_close|,
        |low - prev_close|
    )

    ATR = EMA(TR, period) using Wilder's α = 1/period
    """
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    tr = np.zeros(len(df))
    tr[0] = high[0] - low[0]
    for i in range(1, len(df)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    # Wilder's smoothed ATR
    atr = np.zeros(len(df))
    atr[0] = tr[0]
    for i in range(1, len(df)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return pd.Series(atr, index=df.index)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Triple-Barrier Labeling
# ══════════════════════════════════════════════════════════════════════════════

def triple_barrier_labels(
    df: pd.DataFrame,
    atr_multiple: float = 2.0,
    max_hold_days: int = 5,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Apply triple-barrier method to label every day.

    For each day t (entry):
      - Entry price = close[t]
      - Upper barrier = entry_price + atr_multiple * ATR[t]
      - Lower barrier = entry_price - atr_multiple * ATR[t]
      - Time barrier  = t + max_hold_days

    Scan forward and record:
      - Which barrier was hit first
      - Return at exit
      - Number of bars held
      - Exit price

    Returns DataFrame with columns:
        barrier_hit: 1 = upper (win), -1 = lower (loss), 0 = time-out
        exit_return: percentage return from entry to exit
        exit_bar: number of days held
        exit_price: price at exit
    """
    n = len(df)
    barrier_hit = np.zeros(n, dtype=np.int8)
    exit_return = np.zeros(n, dtype=np.float64)
    exit_bar = np.zeros(n, dtype=np.int32)
    exit_price = np.zeros(n, dtype=np.float64)

    atr = compute_atr(df, period=atr_period).values
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    for i in range(n):
        entry = closes[i]
        atr_val = atr[i]
        if atr_val <= 0 or np.isnan(atr_val):
            barrier_hit[i] = 0
            exit_return[i] = 0.0
            exit_bar[i] = 0
            exit_price[i] = entry
            continue

        upper = entry + atr_multiple * atr_val
        lower = entry - atr_multiple * atr_val
        limit = min(i + max_hold_days + 1, n)

        hit = 0
        hit_price = entry
        bars_held = 0

        for j in range(i + 1, limit):
            bars_held = j - i
            # Check if upper barrier was touched during this bar
            if highs[j] >= upper:
                hit = 1
                hit_price = upper
                break
            # Check if lower barrier was touched during this bar
            if lows[j] <= lower:
                hit = -1
                hit_price = lower
                break

        if hit == 0 and bars_held > 0:
            # Time barrier hit — exit at close of last bar
            hit = 0
            hit_price = closes[min(i + max_hold_days, n - 1)]
            bars_held = max_hold_days

        if bars_held == 0:
            # No forward bars (shouldn't happen for i < n-1)
            hit = 0
            hit_price = entry

        barrier_hit[i] = hit
        exit_return[i] = (hit_price - entry) / entry * 100.0
        exit_bar[i] = bars_held
        exit_price[i] = hit_price

    return pd.DataFrame(
        {
            "barrier_hit": barrier_hit,
            "exit_return": exit_return,
            "exit_bar": exit_bar,
            "exit_price": exit_price,
        },
        index=df.index,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Reporting
# ══════════════════════════════════════════════════════════════════════════════

def print_results(
    labels: pd.DataFrame,
    atr_multiple: float,
    label: str,
):
    """Print summary statistics for a given ATR multiple run."""
    # Filter out the last N days where the label might be incomplete
    # (we can't label the last 5 days because no forward data)
    valid = labels.iloc[:-6]  # exclude last 5+ days
    total = len(valid)
    wins = int((valid["barrier_hit"] == 1).sum())
    losses = int((valid["barrier_hit"] == -1).sum())
    timeouts = int((valid["barrier_hit"] == 0).sum())
    hit_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0
    avg_return = valid["exit_return"].mean()
    avg_bars = valid["exit_bar"].mean()

    # Trades count = days where barriers were hit (win + loss)
    trades = wins + losses
    timeout_trades = timeouts  # these also generate labels but are "no trade"

    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(f"  ATR Multiple:             {atr_multiple}x")
    print(f"  Max Hold Days:            5 (fixed)")
    print(f"  Total Days Labeled:       {total}")
    print(f"  ────────────────────────────────────────")
    print(f"  Trades Generated (win+loss):  {trades}")
    print(f"    Wins (upper barrier hit):   {wins:>5}")
    print(f"    Losses (lower barrier hit): {losses:>5}")
    print(f"    Time-outs (neither hit):    {timeouts:>5}")
    print(f"  Hit Rate (wins / trades):     {hit_rate:.1f}%")
    print(f"  Avg Return per Trade:         {avg_return:.3f}%")
    print(f"  Avg Bars Held:                {avg_bars:.1f}")
    print(f"  Trades as % of total days:    {trades / total * 100:.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("  ML SIGNAL FIX PROTOTYPE — Triple-Barrier Labeling")
    print("=" * 72)
    print()
    print("  Problem: Original 2x ATR barriers produced too few trades.")
    print("  Fix:     Reduce to 1.5x ATR to generate more trade signals.")
    print()

    # 1. Data
    df = fetch_data(start="2000-01-01", end="2025-05-01")

    # 2. Compute ATR stats
    atr = compute_atr(df, period=14)
    print(f"\n[INFO] ATR(14) stats: mean={atr.mean():.2f}, "
          f"median={atr.median():.2f}, "
          f"as % of SPY price: {atr.mean() / df['close'].mean() * 100:.2f}%")
    print(f"[INFO] SPY price range: ${df['close'].min():.2f} – ${df['close'].max():.2f}")

    # 3. Run both versions
    print("\n[RUN] Labeling with 2.0x ATR (ORIGINAL) ...")
    labels_2x = triple_barrier_labels(df, atr_multiple=2.0, max_hold_days=5)
    print_results(labels_2x, atr_multiple=2.0, label="ORIGINAL: 2.0x ATR Barriers")

    print("\n[RUN] Labeling with 1.5x ATR (FIXED) ...")
    labels_1_5x = triple_barrier_labels(df, atr_multiple=1.5, max_hold_days=5)
    print_results(labels_1_5x, atr_multiple=1.5, label="FIXED: 1.5x ATR Barriers")

    # 4. Side-by-side comparison
    valid_2x = labels_2x.iloc[:-6]
    valid_1_5x = labels_1_5x.iloc[:-6]

    trades_2x = int((valid_2x["barrier_hit"] != 0).sum())
    trades_1_5x = int((valid_1_5x["barrier_hit"] != 0).sum())

    wins_2x = int((valid_2x["barrier_hit"] == 1).sum())
    wins_1_5x = int((valid_1_5x["barrier_hit"] == 1).sum())

    losses_2x = int((valid_2x["barrier_hit"] == -1).sum())
    losses_1_5x = int((valid_1_5x["barrier_hit"] == -1).sum())

    hit_rate_2x = wins_2x / trades_2x * 100 if trades_2x else 0
    hit_rate_1_5x = wins_1_5x / trades_1_5x * 100 if trades_1_5x else 0

    avg_ret_2x = valid_2x["exit_return"].mean()
    avg_ret_1_5x = valid_1_5x["exit_return"].mean()

    print(f"\n{'=' * 72}")
    print(f"  COMPARISON SUMMARY")
    print(f"{'=' * 72}")
    print(f"  {'Metric':<35} {'2.0x ATR':<16} {'1.5x ATR':<16}")
    print(f"  {'─' * 67}")
    print(f"  {'Trades Generated':<35} {trades_2x:<16} {trades_1_5x:<16}")
    print(f"  {'Wins (upper hit)':<35} {wins_2x:<16} {wins_1_5x:<16}")
    print(f"  {'Losses (lower hit)':<35} {losses_2x:<16} {losses_1_5x:<16}")
    print(f"  {'Time-outs':<35} {int((valid_2x['barrier_hit'] == 0).sum()):<16} "
          f"{int((valid_1_5x['barrier_hit'] == 0).sum()):<16}")
    print(f"  {'Hit Rate (win/trade)':<35} {hit_rate_2x:<15.1f}% {hit_rate_1_5x:<15.1f}%")
    print(f"  {'Avg Return per Trade':<35} {avg_ret_2x:<15.3f}% {avg_ret_1_5x:<15.3f}%")
    print(f"{'=' * 72}")

    # 5. Trade count increase
    trade_increase = trades_1_5x - trades_2x
    trade_increase_pct = (trade_increase / trades_2x * 100) if trades_2x else 0
    print(f"\n[RESULT] Trade count increased by {trade_increase} "
          f"({trade_increase_pct:+.1f}%)")
    if trade_increase > 0:
        print("[RESULT] Fix confirmed: 1.5x ATR generates significantly more trades.")
    else:
        print("[WARN] Trade count did not increase — check barrier logic or data range.")

    # 6. Optional: show some example trades
    print(f"\n{'─' * 72}")
    print(f"  EXAMPLE TRADES (1.5x ATR, first 10 trade days)")
    print(f"{'─' * 72}")
    trade_days_1_5x = valid_1_5x[valid_1_5x["barrier_hit"] != 0].head(10)
    for idx, row in trade_days_1_5x.iterrows():
        direction = "WIN" if row["barrier_hit"] == 1 else "LOSS"
        print(f"  {idx.date()} | {direction:4s} | "
              f"return={row['exit_return']:+.2f}% | "
              f"held={int(row['exit_bar'])}d")

    print(f"\n{'=' * 72}")
    print(f"  SUMMARY")
    print(f"{'=' * 72}")
    print(f"  Original (2.0x ATR): {trades_2x} trades over {len(valid_2x)} days "
          f"≈ {trades_2x / (len(valid_2x) / 252):.0f} trades/yr")
    print(f"  Fixed   (1.5x ATR): {trades_1_5x} trades over {len(valid_1_5x)} days "
          f"≈ {trades_1_5x / (len(valid_1_5x) / 252):.0f} trades/yr")
    print(f"  → {trade_increase_pct:+.0f}% more trading opportunities")
    print(f"  Trade-off: tighter barriers mean slightly lower hit rate "
          f"({hit_rate_1_5x:.1f}% vs {hit_rate_2x:.1f}%)")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    main()
