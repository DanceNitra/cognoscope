#!/usr/bin/env python3
"""
VRP (Volatility Risk Premium Harvesting) Fix Prototype
======================================================

Problem from Layer 3 validation: Sharpe 2.69 but max DD of -188%.
Root cause: simplified code sold naked puts without any max loss cap.

This prototype:
  1. Fetches SPY/VIX daily data via yfinance (2010–2025)
  2. Detects VIX contango periods (VIX futures curve slope > 5%)
  3. Implements two strategies side-by-side:
     a) UNPROTECTED: sells naked puts (no max loss cap) — replicates the bug
     b) PROTECTED: sells put spreads (long a lower-strike put) — caps loss at
        2x the premium collected
  4. Compares PnL, Sharpe, max drawdown for both

Usage:
    python vrp_fix.py
"""

import os
import sys
import warnings
from datetime import datetime, timedelta
from typing import Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Check dependencies ──────────────────────────────────────────────────────
_missing = []
try:
    import yfinance as yf
except ImportError:
    _missing.append("yfinance")

try:
    from scipy.stats import norm
except ImportError:
    _missing.append("scipy")

if _missing:
    print(f"[ERROR] Missing required packages: {', '.join(_missing)}")
    print("Install with: pip install yfinance scipy pandas numpy")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Data Fetch
# ══════════════════════════════════════════════════════════════════════════════

def fetch_data(
    start: str = "2010-01-01",
    end: str = "2025-05-01",
) -> pd.DataFrame:
    """
    Download SPY (ETF) and VIX (volatility index) daily data via yfinance.
    Returns a single DataFrame with columns:
        spy_close, spy_volume, vix_close
    Indexed by Date.
    """
    print(f"[INFO] Fetching SPY data ({start} to {end}) ...")
    spy = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)
    vix = yf.download("^VIX", start=start, end=end, progress=False)

    # yfinance returns MultiIndex columns (Price, Ticker)
    # Each column like spy["Close"] is a DataFrame of shape (n, 1) — squeeze to Series
    spy_close = spy["Close"].squeeze()
    spy_volume = spy["Volume"].squeeze()
    vix_close = vix["Close"].squeeze()

    df = pd.DataFrame(
        {
            "spy_close": spy_close,
            "spy_volume": spy_volume,
            "vix_close": vix_close,
        },
        index=spy.index,
    )
    df.dropna(inplace=True)
    print(f"[INFO] Fetched {len(df)} daily rows ({df.index[0].date()} → {df.index[-1].date()})")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 2. Contango Detection
# ══════════════════════════════════════════════════════════════════════════════

def detect_contango(df: pd.DataFrame, threshold: float = 0.05) -> pd.Series:
    """
    Simple contango proxy: flag days where VIX level is elevated and rolling
    median suggests the futures curve is in contango.

    Because historical VIX futures settlement data isn't freely available,
    we approximate contango using:
        contango ≈ (VIX_30d_rolling_high / VIX_current) - 1

    When VIX is elevated and the current VIX is lower than the recent
    rolling high, it suggests futures are pricing higher future vol
    (contango). This is a well-known approximation used in VRP research.

    Returns a boolean Series: True when contango > threshold.
    """
    # Rolling 30-day max of VIX (proxy for front-month future price)
    vix_high = df["vix_close"].rolling(window=30, min_periods=10).max()

    # Contango ratio: how much higher is the recent high vs current VIX
    contango_ratio = vix_high / df["vix_close"] - 1.0

    # Also require VIX to be above a minimum level (avoid noisy low-vol days)
    vix_min_level = 12.0

    signal = (contango_ratio > threshold) & (df["vix_close"] > vix_min_level)
    return signal.astype(bool)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Strategy Simulations
# ══════════════════════════════════════════════════════════════════════════════

def simulate_naked_put(
    df: pd.DataFrame,
    signal: pd.Series,
    portfolio_value: float = 100_000.0,
    premium_pct: float = 0.03,       # 3% of SPY price as premium per share
    contracts_per_trade: int = 10,    # 10 option contracts (= 1,000 shares equiv)
    strike_atm_pct: float = 1.0,      # sell at-the-money (strike = 100% of price)
    days_to_expiry: int = 30,
) -> pd.Series:
    """
    Simulate selling naked puts when contango signal is True.
    Uses realistic contract count for portfolio-sized exposure.

    Mechanics:
      - When signal fires: collect premium = contracts * 100 * premium_pct * SPY price
      - If SPY drops below strike before expiry, loss = contracts * 100 * (strike - SPY_low)
      - Net trade PnL = premium collected - max(0, strike - SPY_low) * contracts * 100
      - If SPY stays above strike, keep full premium

    Returns a Series of daily PnL contributions.
    """
    pnl = pd.Series(0.0, index=df.index)
    trade_open = False
    entry_idx = None
    entry_price = 0.0
    collected_premium = 0.0
    strike_price = 0.0
    expiry_date = None

    for i in range(len(df)):
        dt = df.index[i]
        price = df["spy_close"].iloc[i]

        # ── Open trade ──
        if not trade_open and signal.iloc[i]:
            trade_open = True
            entry_idx = i
            entry_price = price
            strike_price = price * strike_atm_pct
            # Premium collected = contracts * 100 shares * premium_pct * price
            collected_premium = contracts_per_trade * 100 * price * premium_pct
            expiry_date = dt + timedelta(days=days_to_expiry)
            pnl.iloc[i] = collected_premium  # credit received today
            continue

        # ── Manage open trade ──
        if trade_open:
            # Check if expired
            if dt >= expiry_date:
                # At expiry: if SPY < strike, we take the loss
                if price < strike_price:
                    loss = contracts_per_trade * 100 * (strike_price - price)
                    pnl.iloc[i] = -loss
                # If SPY >= strike, option expires worthless, premium already counted
                trade_open = False
            else:
                pnl.iloc[i] = 0.0

    return pnl


def simulate_put_spread(
    df: pd.DataFrame,
    signal: pd.Series,
    portfolio_value: float = 100_000.0,
    premium_pct: float = 0.03,        # 3% of SPY price as credit per share
    contracts_per_trade: int = 10,    # 10 option contracts
    spread_width_pct: float = 0.06,   # 6% wide spread → max loss = spread - credit
    strike_atm_pct: float = 1.0,
    days_to_expiry: int = 30,
) -> pd.Series:
    """
    Simulate selling a put spread (bear put spread / credit put spread).

    Structure:
      - Sell 1 ATM put at strike K1 (≈ SPY price)
      - Buy 1 OTM put at strike K2 = K1 * (1 - spread_width)
      - Net credit = contracts * 100 * premium_pct * SPY price
      - Max loss = contracts * 100 * ((K1 - K2) - net_credit_per_share)
      - Max loss is capped at ~2x the premium collected

    With premium_pct=0.03 and spread_width_pct=0.06:
        Max loss per share = 6% - 3% = 3% of SPY price
        Total risk = 2x premium collected (3% credit + 3% additional loss)
        If SPY crashes -20%, loss still capped at 3% per share.

    Returns a Series of daily PnL contributions.
    """
    pnl = pd.Series(0.0, index=df.index)
    trade_open = False
    entry_price = 0.0
    net_credit = 0.0
    k1 = 0.0  # short put strike (ATM)
    k2 = 0.0  # long put strike (OTM, lower)
    expiry_date = None

    for i in range(len(df)):
        dt = df.index[i]
        price = df["spy_close"].iloc[i]

        if not trade_open and signal.iloc[i]:
            trade_open = True
            entry_price = price
            k1 = price * strike_atm_pct
            k2 = k1 * (1.0 - spread_width_pct)
            net_credit = contracts_per_trade * 100 * price * premium_pct
            expiry_date = dt + timedelta(days=days_to_expiry)
            pnl.iloc[i] = net_credit  # credit received today
            continue

        if trade_open:
            if dt >= expiry_date:
                # At expiry: payoff = max(0, K1 - S) - max(0, K2 - S)
                short_put_payoff = max(0.0, k1 - price)
                long_put_payoff = max(0.0, k2 - price)
                # Total PnL = net_credit (already booked) - short_payoff + long_payoff
                trade_pnl = contracts_per_trade * 100 * (-short_put_payoff + long_put_payoff)
                pnl.iloc[i] = trade_pnl
                trade_open = False
            else:
                pnl.iloc[i] = 0.0

    return pnl


# ══════════════════════════════════════════════════════════════════════════════
# 4. Metrics & Reporting
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics(pnl_series: pd.Series) -> dict:
    """
    Compute key performance metrics from a daily PnL series.

    Returns:
        total_return, annual_return, volatility, sharpe, max_drawdown, num_trades
    """
    cumulative = pnl_series.cumsum()
    total_return = cumulative.iloc[-1]

    # Equity curve starting at $100k
    equity = 100_000.0 + cumulative
    rets = equity.pct_change().dropna()

    ann_return = rets.mean() * 252
    ann_vol = rets.std() * np.sqrt(252)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

    # Max drawdown
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = drawdown.min()

    # Count trades: number of days where we opened a position (positive PnL entry)
    num_trades = (pnl_series > 0).sum()

    return {
        "total_return": total_return,
        "total_return_pct": total_return / 100_000.0 * 100,
        "annual_return_pct": ann_return * 100,
        "annual_vol_pct": ann_vol * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd * 100,
        "num_trades": num_trades,
    }


def print_comparison(metrics_a: dict, metrics_b: dict, label_a: str, label_b: str):
    """Print a side-by-side comparison table."""
    print(f"\n{'=' * 80}")
    print(f"  METRICS COMPARISON")
    print(f"{'=' * 80}")
    print(f"  {'Metric':<30} {label_a:<22} {label_b:<22}")
    print(f"  {'─' * 76}")
    rows = [
        ("Total Return ($)", "total_return", ".2f"),
        ("Total Return (%)", "total_return_pct", ".2f"),
        ("Annual Return (%)", "annual_return_pct", ".2f"),
        ("Annual Vol (%)", "annual_vol_pct", ".2f"),
        ("Sharpe Ratio", "sharpe", ".2f"),
        ("Max Drawdown (%)", "max_drawdown_pct", ".2f"),
        ("Num Trades", "num_trades", ".0f"),
    ]
    for label, key, fmt in rows:
        va = metrics_a[key]
        vb = metrics_b[key]
        print(f"  {label:<30} {va:{fmt}}{'':>10} {vb:{fmt}}{'':>10}")
    print(f"{'=' * 80}\n")


def plot_comparison(df: pd.DataFrame, pnl_a: pd.Series, pnl_b: pd.Series,
                    label_a: str, label_b: str):
    """Generate a terminal-friendly ASCII plot of cumulative PnL."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

        # Panel 1: SPY price
        axes[0].plot(df.index, df["spy_close"], color="gray", linewidth=0.8)
        axes[0].set_ylabel("SPY Close ($)")
        axes[0].set_title("S&P 500 ETF (SPY) — Daily Close")
        axes[0].grid(alpha=0.3)

        # Panel 2: VIX and contango signals
        axes[1].plot(df.index, df["vix_close"], color="orange", linewidth=0.8, label="VIX")
        # Highlight contango periods
        signal = detect_contango(df, threshold=0.05)
        contango_dates = df.index[signal]
        axes[1].fill_between(
            contango_dates,
            df.loc[contango_dates, "vix_close"].values,
            0,
            color="green",
            alpha=0.15,
            label="Contango > 5%",
        )
        axes[1].set_ylabel("VIX Level")
        axes[1].set_title("VIX Volatility Index with Contango Zones")
        axes[1].legend(fontsize=8)
        axes[1].grid(alpha=0.3)

        # Panel 3: Cumulative PnL comparison
        cum_a = pnl_a.cumsum()
        cum_b = pnl_b.cumsum()
        axes[2].plot(df.index, cum_a, color="red", linewidth=0.9, label=label_a)
        axes[2].plot(df.index, cum_b, color="blue", linewidth=0.9, label=label_b)
        axes[2].axhline(y=0, color="black", linewidth=0.5, linestyle="--")
        axes[2].set_ylabel("Cumulative PnL ($)")
        axes[2].set_title("Strategy Cumulative PnL Comparison")
        axes[2].legend(fontsize=9)
        axes[2].grid(alpha=0.3)

        plt.tight_layout()
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "vrp_comparison.png")
        plt.savefig(out_path, dpi=120)
        plt.close()
        print(f"[INFO] Plot saved to: {out_path}")
    except ImportError:
        print("[WARN] matplotlib not installed — skipping plot generation.")
    except Exception as e:
        print(f"[WARN] Could not generate plot: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  VRP FIX PROTOTYPE — Volatility Risk Premium with Max Loss Cap")
    print("=" * 80)

    # 1. Data
    df = fetch_data(start="2010-01-01", end="2025-05-01")

    # 2. Contango signal
    signal = detect_contango(df, threshold=0.05)
    n_trade_days = signal.sum()
    print(f"[INFO] Contango > 5% detected on {n_trade_days} / {len(df)} days "
          f"({100 * n_trade_days / len(df):.1f}%)")

    # 3. Run both strategies
    print("\n[RUN] Simulating NAKED PUT strategy (UNPROTECTED — max loss = unlimited) ...")
    pnl_naked = simulate_naked_put(df, signal, premium_pct=0.03)

    print("[RUN] Simulating PUT SPREAD strategy (PROTECTED — max loss = 2x premium) ...")
    pnl_spread = simulate_put_spread(df, signal, premium_pct=0.03, spread_width_pct=0.06)

    # 4. Metrics
    metrics_naked = compute_metrics(pnl_naked)
    metrics_spread = compute_metrics(pnl_spread)

    # 5. Side-by-side table
    print_comparison(
        metrics_naked, metrics_spread,
        label_a="Naked Put (Unprotected)",
        label_b="Put Spread (Capped 2x)",
    )

    # 6. Highlight the max drawdown fix
    dd_naked = metrics_naked["max_drawdown_pct"]
    dd_spread = metrics_spread["max_drawdown_pct"]
    print(f"[RESULT] Max Drawdown: Naked Put = {dd_naked:.2f}%  →  "
          f"Put Spread = {dd_spread:.2f}%")
    if dd_spread > dd_naked:
        print(f"[RESULT] Drawdown improved by {abs(dd_spread - dd_naked):.2f} percentage points.")
    else:
        print(f"[WARN] Drawdown did NOT improve — check parameters.")

    # 7. Plot
    plot_comparison(df, pnl_naked, pnl_spread,
                    label_a="Naked Put (Unprotected)",
                    label_b="Put Spread (Capped 2x)")

    # 8. Summary
    print(f"\n{'=' * 80}")
    print("  SUMMARY")
    print(f"{'=' * 80}")
    print("  Problem: VRP with naked puts has unlimited tail risk.")
    print("  Fix: Replace naked puts with put spreads.")
    print(f"  With premium_pct=3% and spread_width_pct=6%:")
    print("    - Max loss capped at (6% - 3%) = 3% of SPY per trade")
    print("    - That is exactly 2x the premium collected (3% credit, 3% additional loss)")
    print("    - SPY crash of -20% only causes -3% loss on this trade")
    print(f"  Original max DD: {dd_naked:.2f}%")
    print(f"  Capped max DD:   {dd_spread:.2f}%")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
