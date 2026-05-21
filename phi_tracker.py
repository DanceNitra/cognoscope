#!/usr/bin/env python3
"""
phi_tracker.py — Track vault integration metrics over time.

Runs phi_audit and stores results in a JSON history file.
Outputs trend: "Your vault integration (Φ) is 0.231. Last week: 0.228 (+0.003)."

Usage:
    python3 phi_tracker.py                # Run and append to history
    python3 phi_tracker.py --report       # Show trend
    python3 phi_tracker.py --json         # JSON output
"""

import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from athena_core import VaultGraph, VAULT_PATHS, readiness_check

HISTORY_FILE = os.path.join(os.path.dirname(__file__), ".phi_history.json")


def load_history() -> list[dict]:
    if os.path.isfile(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_history(entry: dict):
    history = load_history()
    history.append(entry)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)
    # Keep only last 52 entries (~1 year of weekly runs)
    if len(history) > 52:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history[-52:], f, indent=2)


def run() -> dict:
    g = VaultGraph()
    summary = g.summary()
    
    entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "nodes": summary["nodes"],
        "domain_count": summary["domain_count"],
        "mean_phi": round(summary["mean_phi"], 4),
        "domains_list": summary["domains_list"],
    }
    save_history(entry)
    return entry


def report() -> str:
    history = load_history()
    if not history:
        return "No Φ history yet. Run `python3 phi_tracker.py` first."
    
    current = history[-1]
    lines = []
    lines.append(f"Vault integration (Φ): {current['mean_phi']}")
    lines.append(f"Notes: {current['nodes']} | Domains: {current['domain_count']}")
    
    if len(history) >= 2:
        prev = history[-2]
        delta = current['mean_phi'] - prev['mean_phi']
        trend = "+" if delta >= 0 else ""
        lines.append(f"Trend: {trend}{delta:.4f} ({len(history)} samples)")
        # Weekly rate
        if len(history) >= 3:
            oldest = history[0]
            total_delta = current['mean_phi'] - oldest['mean_phi']
            weeks = len(history)
            lines.append(f"Weekly growth: {total_delta / max(weeks, 1):.4f}/week")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phi Tracker")
    parser.add_argument("--report", action="store_true", help="Show trend report")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.report:
        if args.json:
            print(json.dumps(load_history(), indent=2))
        else:
            print(report())
        return
    
    entry = run()
    print(report())


if __name__ == "__main__":
    main()
