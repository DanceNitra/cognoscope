#!/usr/bin/env python3
"""
monitor.py — Real-time cognoscope monitoring daemon (B4)

Tracks:
  - Polygraph: hypocrisy scores per category, trend direction
  - Guardrail bus: check frequency by decision type
  - Swarm: agent pool health, task completion rate

Usage:
  python monitor.py --live       # Continuous mode (every 30s, use with background=true)
  python monitor.py --snapshot   # One-shot report
"""

from __future__ import annotations
import os, sys, json, time, argparse
from datetime import datetime
from typing import Any

COGNOSCOPE_DIR = os.path.dirname(os.path.abspath(__file__))
POLYGRAPH_DIR = os.path.join(COGNOSCOPE_DIR, ".polygraph")
SWARM_DIR = os.path.join(COGNOSCOPE_DIR, ".swarm")
MONITOR_STATE = os.path.join(COGNOSCOPE_DIR, ".monitor_state.json")

sys.path.insert(0, COGNOSCOPE_DIR)


def fmt_time(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S")


def load_json(path: str) -> dict | list:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {} if path.endswith(".json") else []


def snapshot() -> dict:
    """Take a monitoring snapshot of all subsystems."""
    now = time.time()
    result = {
        "timestamp": now,
        "time_str": fmt_time(now),
    }

    # ── Polygraph ──
    alarm_path = os.path.join(POLYGRAPH_DIR, "alarms.json")
    alarms = load_json(alarm_path) if os.path.exists(alarm_path) else []
    if alarms:
        scores = [a.get("score", 0) for a in alarms]
        categories = [a.get("category", "?") for a in alarms]
        result["polygraph"] = {
            "total_alarms": len(alarms),
            "max_score": max(scores) if scores else 0,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "last_alarm": alarms[-1] if alarms else None,
            "categories": list(set(categories)),
        }
    else:
        result["polygraph"] = {
            "total_alarms": 0,
            "max_score": 0,
            "avg_score": 0,
            "last_alarm": None,
            "categories": [],
        }

    # ── Guardrail (from in-memory bus — best-effort) ──
    try:
        from guardrail_bus import GuardrailBus
        bus = GuardrailBus()
        hist = bus.guardrail_history or []
        if hist:
            by_decision: dict[str, int] = {}
            for h in hist:
                d = h.get("decision", "PASS")
                by_decision[d] = by_decision.get(d, 0) + 1
            result["guardrail"] = {
                "total_checks": len(hist),
                "by_decision": by_decision,
            }
        else:
            result["guardrail"] = {"total_checks": 0, "by_decision": {}}
    except Exception as e:
        result["guardrail"] = {"total_checks": 0, "by_decision": {}, "error": str(e)}

    # ── Swarm ──
    swarm_file = os.path.join(SWARM_DIR, "agents.json")
    if os.path.exists(swarm_file):
        agents = load_json(swarm_file)
        if agents:
            if isinstance(agents, dict):
                alive = sum(1 for a in agents.values() if a.get("status") == "alive")
            else:
                alive = sum(1 for a in agents if a.get("status") == "alive")
            result["swarm"] = {
                "total": len(agents),
                "alive": alive,
                "dead": len(agents) - alive,
            }
        else:
            result["swarm"] = {"total": 0, "alive": 0, "dead": 0}
    else:
        result["swarm"] = {"total": 0, "alive": 0, "dead": 0}

    return result


def format_snapshot(s: dict) -> str:
    """Format a snapshot for display."""
    lines = []
    lines.append(f"  [{s['time_str']}] Cognoscope Monitor")
    lines.append(f"  {'─' * 50}")

    # Polygraph
    p = s["polygraph"]
    if p["total_alarms"] > 0:
        icon = "🚨" if p["max_score"] >= 0.65 else "🔴" if p["max_score"] >= 0.35 else "🟡"
        lines.append(f"  {icon} Polygraph: {p['total_alarms']} alarms  |  "
                     f"max={p['max_score']:.2f}  avg={p['avg_score']:.2f}")
        if p["last_alarm"]:
            lines.append(f"     Last: {p['last_alarm'].get('category','?')} "
                         f"score={p['last_alarm'].get('score',0):.2f}")
    else:
        lines.append(f"  🟢 Polygraph: clean (0 alarms)")

    # Guardrail
    g = s["guardrail"]
    if g["total_checks"] > 0:
        lines.append(f"  🛡️  Guardrail: {g['total_checks']} checks")
        for dec, cnt in sorted(g["by_decision"].items(), key=lambda x: -x[1]):
            icon = {"PASS": "🟢", "WARN": "🟡", "BLOCK": "🔴", "REJECT": "🔴",
                    "FREEZE": "🚨", "ESCALATE": "🚨"}.get(dec, "⚪")
            lines.append(f"     {icon} {dec}: {cnt}")
    else:
        lines.append(f"  🛡️  Guardrail: no checks this session")

    # Swarm
    w = s["swarm"]
    if w["total"] > 0:
        icon = "🐝"
        lines.append(f"  {icon} Swarm: {w['alive']}/{w['total']} agents alive")
    else:
        lines.append(f"  🐝 Swarm: empty pool")

    return "\n".join(lines)


def save_state(snapshot: dict, history: list[dict]):
    """Append snapshot to persistent history."""
    state = {
        "last_snapshot": snapshot,
        "history": history[-100:],  # keep last 100
    }
    with open(MONITOR_STATE, "w") as f:
        json.dump(state, f, indent=2)


def live_loop(interval: float = 30.0):
    """Continuous monitoring loop."""
    history: list[dict] = []

    try:
        while True:
            s = snapshot()
            history.append(s)
            save_state(s, history)
            print(format_snapshot(s))
            print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n  Monitoring stopped. History saved ({len(history)} snapshots).")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Cognoscope real-time monitor")
    parser.add_argument("--live", action="store_true", help="Continuous mode (every 30s)")
    parser.add_argument("--interval", type=float, default=30.0, help="Poll interval (seconds)")
    parser.add_argument("--snapshot", action="store_true", help="One-shot report")
    args = parser.parse_args()

    if args.live:
        live_loop(args.interval)
    else:
        s = snapshot()
        print()
        print(format_snapshot(s))
        print()


if __name__ == "__main__":
    main()
