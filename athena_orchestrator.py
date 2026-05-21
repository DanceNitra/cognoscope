#!/usr/bin/env python3
"""
athena_orchestrator.py — Phase 4 Metacognitive Orchestrator.

Daily brief that aggregates:
  1. Alert log — recent cron failure signals
  2. Vault lint — quality score + top issues
  3. Φ tracker — integration trend
  4. ARI log — recent discoveries & publication count
  5. System status — enabled crons, healthy vs broken

Output: structured report sent to /tmp/athena-brief.json + stdout.
"""

import os, sys, json, glob, re
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from athena_core import VaultGraph, VAULT_PATHS, Logger
from vault_linter import lint
from phi_tracker import report as phi_report, run as phi_run

# ── Paths ──
ALERT_LOG = "/tmp/athena-alert.log"
CRON_OUTPUT = os.path.expanduser("~/.hermes/cron/output")
ARI_LOG = os.path.expanduser("~/Obsidian Vault/04 Resources/ARI/ari_log.json")
VAULT_ARI = os.path.expanduser("~/Obsidian Vault/04 Resources/ARI")


def check_alerts() -> dict:
    """Read the alert log — how many errors in last 24h."""
    if not os.path.isfile(ALERT_LOG):
        return {"count": 0, "recent": [], "file_exists": False}
    try:
        with open(ALERT_LOG) as f:
            lines = [l.strip() for l in f if l.strip()]
    except:
        return {"count": 0, "recent": [], "file_exists": True, "error": "unreadable"}
    
    # Count ERROR lines
    error_lines = [l for l in lines if "ERROR" in l]
    recent = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for l in error_lines:
        # Extract timestamp if present
        ts_match = re.search(r'\[(.*?)\]', l)
        if ts_match:
            try:
                ts = datetime.fromisoformat(ts_match.group(1))
                if ts > cutoff:
                    recent.append(l)
            except:
                recent.append(l)
        else:
            recent.append(l)
    
    return {
        "count": len(error_lines),
        "recent_24h": len(recent),
        "recent": recent[:5],
        "file_exists": True,
    }


def check_ari_recent(hours: int = 24) -> dict:
    """Check ARI log for recent activity."""
    if not os.path.isfile(ARI_LOG):
        # Fall back to file listing
        files = sorted(glob.glob(os.path.join(VAULT_ARI, "*.md")), reverse=True)
        return {"log_found": False, "recent_files": len(files), "latest": files[:3] if files else []}
    
    try:
        with open(ARI_LOG) as f:
            log = json.load(f)
    except:
        return {"log_found": True, "error": "unparseable", "total_cycles": 0, "recent": []}
    
    if not isinstance(log, list):
        log = [log]
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = []
    for entry in reversed(log):
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts > cutoff:
                recent.append(entry)
        except:
            pass
    
    return {
        "log_found": True,
        "total_cycles": len(log),
        "recent_24h": len(recent),
        "recent": recent[:5],
        "latest_mode": recent[-1].get("mode", "?") if recent else "none",
        "latest_title": recent[-1].get("title", "?")[:80] if recent else "none",
    }


def check_system_health() -> dict:
    """Read hermes cron API — would need to parse output. Simplified: check alert log."""
    return {
        "alert_log_size": os.path.getsize(ALERT_LOG) if os.path.isfile(ALERT_LOG) else 0,
    }


def format_brief() -> str:
    """Build the daily brief text."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append(f"## 🏛️ ATHENA BRIEF — {now}")
    lines.append("")
    
    # ── 1. Alerts ──
    alerts = check_alerts()
    if alerts["count"] > 0:
        lines.append(f"**⚠️ Alerts:** {alerts['count']} pending ({alerts['recent_24h']} in last 24h)")
        for a in alerts["recent"]:
            lines.append(f"  `{a[:100]}`")
    else:
        lines.append("**✅ Alerts:** None")
    lines.append("")
    
    # ── 2. Vault lint ──
    try:
        result = lint(verbose=False)
        score = result.get("score", 0)
        broken = result.get("broken_links", 0)
        orphans = result.get("orphans", 0)
        stale = result.get("stale", 0)
        idx_gaps = result.get("index_gaps", 0)
        total = result.get("total_issues", 0)
        # Emoji rating
        if score >= 80: rating = "🟢"
        elif score >= 50: rating = "🟡"
        else: rating = "🔴"
        lines.append(f"**{rating} Lint:** {score}/100 | {broken} broken | {orphans} orphans | {stale} stale | {idx_gaps} index | {total} issues")
    except Exception as e:
        lines.append(f"**❌ Lint:** Error: {e}")
    lines.append("")
    
    # ── 3. Phi trend ──
    try:
        phi_run()  # Record latest
        phi_text = phi_report()
        lines.append(f"**🧠 Phi:** {phi_text}")
    except Exception as e:
        lines.append(f"**❌ Phi:** Error: {e}")
    lines.append("")
    
    # ── 4. ARI activity ──
    ari = check_ari_recent()
    if ari.get("log_found"):
        lines.append(f"**🤖 ARI:** {ari['total_cycles']} total cycles | {ari['recent_24h']} in 24h")
        if ari["recent"]:
            latest = ari["recent"][-1]
            lines.append(f"  Latest: [{latest.get('mode','?')}] {latest.get('title','?')[:60]}")
    else:
        lines.append(f"**🤖 ARI:** {ari['recent_files']} blog posts written, no log file")
        if ari.get("latest"):
            lines.append(f"  Latest: {ari['latest'][0].split('/')[-1]}")
    lines.append("")
    
    # ── 5. Summary ──
    all_ok = alerts["count"] == 0
    status = "✅ ALL SYSTEMS NOMINAL" if all_ok else "⚠️ ISSUES DETECTED — check alerts"
    lines.append(f"**{status}**")
    lines.append("")
    lines.append("---")
    lines.append("_Generated by Athena Orchestrator (Phase 4)_")
    
    return "\n".join(lines)


def save_brief(text: str):
    """Save the brief to /tmp/athena-brief.txt for delivery."""
    path = "/tmp/athena-brief.txt"
    with open(path, "w") as f:
        f.write(text)
    # Also save JSON structured version
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alerts": check_alerts(),
        "ari": check_ari_recent(),
    }
    with open("/tmp/athena-brief.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path


def main():
    text = format_brief()
    print(text)
    save_brief(text)


if __name__ == "__main__":
    main()
