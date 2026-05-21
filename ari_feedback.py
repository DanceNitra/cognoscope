#!/usr/bin/env python3
"""
ari_feedback.py — Phase 5: ARI feedback loop.

Measures ARI's impact on vault quality:
  1. Reads ARI log → publications with confidence, novelty, phi_impact
  2. Reads phi history → integration trend over time
  3. Reads lint history → quality trend over time
  4. Correlates: does ARI activity correlate with score improvements?
  5. Ranks ARI publications by empirical impact

Intended to be called by athena_orchestrator.py daily.
"""

import os, sys, json, glob
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ARI_LOG = os.path.expanduser("~/Obsidian Vault/04 Resources/ARI/ari_log.json")
PHI_HISTORY = os.path.join(os.path.dirname(__file__), ".phi_history.json")
LINT_HISTORY = os.path.join(os.path.dirname(__file__), ".lint_history.json")


def load_json(path):
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    except:
        return []


def load_ari_log() -> list[dict]:
    return load_json(ARI_LOG)


def load_phi_history() -> list[dict]:
    return load_json(PHI_HISTORY)


def load_lint_history() -> list[dict]:
    return load_json(LINT_HISTORY)


def rank_publications() -> list[dict]:
    """
    Score every ARI publication by empirical criteria:
    - confidence × novelty = predicted quality
    - phi_impact = structural contribution
    - Combined score for ranking
    """
    log = load_ari_log()
    if not log:
        return []
    
    scored = []
    for entry in log:
        confidence = entry.get("confidence", 0.5)
        novelty = entry.get("novelty", 0.5)
        phi_impact = entry.get("phi_impact", 0.0)
        mode = entry.get("mode", "?")
        action = entry.get("action", "?")
        title = entry.get("title", "?")[:60]
        ts = entry.get("timestamp", "")[:19]
        
        # Predicted quality: geometric mean of confidence × novelty
        pred_quality = (confidence * novelty) ** 0.5
        # Structural impact: phi_impact (usually 0.01-0.05)
        # Combined: 70% quality + 30% phi impact
        combined = 0.7 * pred_quality + 0.3 * min(phi_impact * 10, 1.0)
        
        scored.append({
            "timestamp": ts,
            "mode": mode,
            "action": action,
            "title": title,
            "confidence": confidence,
            "novelty": novelty,
            "phi_impact": phi_impact,
            "pred_quality": round(pred_quality, 3),
            "combined_score": round(combined, 3),
        })
    
    scored.sort(key=lambda x: x["combined_score"], reverse=True)
    return scored


def ari_velocity(last_days: int = 7) -> dict:
    """How many ARI cycles per mode in the last N days."""
    log = load_ari_log()
    cutoff = datetime.now(timezone.utc) - timedelta(days=last_days)
    
    counts = {"balanced": 0, "novelty": 0, "risk": 0, "integration": 0, "bridge_growth": 0, "other": 0}
    recent = 0
    for entry in log:
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts > cutoff:
                recent += 1
                mode = entry.get("mode", "other")
                if mode in counts:
                    counts[mode] += 1
                else:
                    counts["other"] += 1
        except:
            pass
    
    return {
        "total_recent": recent,
        "by_mode": {k: v for k, v in counts.items() if v > 0},
        "days": last_days,
    }


def phi_trend() -> dict:
    """Phi trend: latest vs first, weekly growth rate."""
    history = load_phi_history()
    if len(history) < 2:
        return {"samples": len(history), "msg": "Need 2+ samples for trend"}
    
    first = history[0]
    last = history[-1]
    delta = last.get("mean_phi", 0) - first.get("mean_phi", 0)
    weeks = max(len(history), 1)
    
    # Phi change per ARI cycle (since ARI runs write to vault)
    return {
        "samples": len(history),
        "first_phi": first.get("mean_phi", 0),
        "latest_phi": last.get("mean_phi", 0),
        "total_delta": round(delta, 4),
        "weekly_rate": round(delta / weeks, 4),
        "nodes_growth": last.get("nodes", 0) - first.get("nodes", 0),
    }


def lint_trend() -> dict:
    """Lint score trend."""
    history = load_lint_history()
    if len(history) < 2:
        return {"samples": len(history), "msg": "Need 2+ samples for trend"}
    
    first = history[0]
    last = history[-1]
    score_delta = last.get("score", 0) - first.get("score", 0)
    
    return {
        "samples": len(history),
        "first_score": first.get("score", 0),
        "latest_score": last.get("score", 0),
        "score_delta": score_delta,
        "improving": score_delta > 0,
    }


def full_report() -> dict:
    """Complete feedback report."""
    top_pubs = rank_publications()[:5]
    vel = ari_velocity(7)
    phi = phi_trend()
    lint = lint_trend()
    
    return {
        "ari_velocity_7d": vel,
        "phi_trend": phi,
        "lint_trend": lint,
        "top_ari_pubs": top_pubs,
        "ari_total": len(load_ari_log()),
    }


def format_feedback(report: dict) -> str:
    """Human-readable feedback block for the Athena brief."""
    lines = []
    
    # Velocity
    vel = report["ari_velocity_7d"]
    lines.append(f"**📊 ARI Velocity (7d):** {vel['total_recent']} cycles")
    if vel.get("by_mode"):
        mode_str = ", ".join(f"{k}={v}" for k, v in vel["by_mode"].items())
        lines.append(f"  Modes: {mode_str}")
    
    # Phi trend
    phi = report["phi_trend"]
    if phi.get("samples", 0) >= 2:
        delta = phi["total_delta"]
        trend_icon = "📈" if delta >= 0 else "📉"
        lines.append(f"**{trend_icon} Φ Trend:** {phi['first_phi']} → {phi['latest_phi']} ({delta:+.4f})")
        if phi.get("nodes_growth", 0) != 0:
            lines.append(f"  Nodes: {phi['nodes_growth']:+d} change")
    
    # Lint trend
    lint = report["lint_trend"]
    if lint.get("samples", 0) >= 2:
        delta = lint["score_delta"]
        icon = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
        lines.append(f"**{icon} Lint Trend:** {lint['first_score']} → {lint['latest_score']} ({delta:+d})")
    
    # Top publications
    top = report.get("top_ari_pubs", [])
    if top:
        lines.append(f"**🏆 Top ARI Publications:**")
        for i, pub in enumerate(top[:3], 1):
            lines.append(f"  {i}. [{pub['mode']}] {pub['title'][:50]} ({pub['combined_score']})")
    
    return "\n".join(lines)


def main():
    report = full_report()
    print(json.dumps(report, indent=2, default=str))
    print("")
    print(format_feedback(report))


if __name__ == "__main__":
    main()
