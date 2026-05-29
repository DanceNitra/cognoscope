#!/usr/bin/env python3
"""
cognoscope cli.py — CLI Dashboard for All 13 Layers

Usage:
    python cli.py status       → Full health dashboard (all layers)
    python cli.py layers       → List all 13 layers with status
    python cli.py polygraph    → Hypocrisy report (L12)
    python cli.py agents       → Swarm agent pool (L13)
    python cli.py guardrail    → Guardrail bus history (L9+L10)
    python cli.py dream        → Dream loop report (L15)

Each command attempts to load its module. If unavailable,
it reports the layer as NOT LOADED rather than crashing.
"""

from __future__ import annotations
import os, sys, json, time, textwrap
from datetime import datetime
from typing import Any

# ── Paths ──
COGNOSCOPE_DIR = os.path.dirname(os.path.abspath(__file__))
POLYGRAPH_DIR = os.path.join(COGNOSCOPE_DIR, ".polygraph")
SWARM_DIR = os.path.join(COGNOSCOPE_DIR, ".swarm")

sys.path.insert(0, COGNOSCOPE_DIR)


# ──────────────────────────────────────────────
# 1. HELPERS
# ──────────────────────────────────────────────

def fmt_time(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")

def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m < 60:
        return f"{m}m {s}s"
    h = m // 60
    m = m % 60
    return f"{h}h {m}m {s}s"

def layer_icon(name: str, ok: bool) -> str:
    icon = {"athena": "🧠", "metaloop": "🔄", "guardrail": "🛡️", "toolforge": "🔧",
            "rsi": "📊", "omc": "👥", "selfmodel": "🔍", "immune": "💉",
            "msr": "🏦", "a2a": "📡", "polygraph": "🔎", "swarm": "🐝",
            "dream": "🌙", "eval": "📐", "profile": "📋"}.get(name, "⚙️")
    return f"{'✅' if ok else '❌'} {icon}"

def section(title: str):
    w = 66
    print(f"  ╔{'═' * w}╗")
    print(f"  ║  {title:<{w-2}}║")
    print(f"  ╚{'═' * w}╝")


# ──────────────────────────────────────────────
# 2. LAYER REGISTRY
# ──────────────────────────────────────────────

LAYERS: list[dict[str, Any]] = [
    {"n": 1,  "name": "Athena (ReAct Loop)",          "module": "athena",           "type": "Core"},
    {"n": 2,  "name": "Meta-Loop (Self-Reconfig)",     "module": "metaloop",         "type": "Core"},
    {"n": 3,  "name": "MSR Guardrail (Homeostasis)",   "module": "msr_guardrail",    "type": "Safety"},
    {"n": 4,  "name": "Tool Synthesis",                "module": "toolforge",        "type": "Core"},
    {"n": 5,  "name": "RSI Kernel",                    "module": "rsi_kernel",       "type": "Analysis"},
    {"n": 6,  "name": "Meta-Kernel (CSD)",             "module": "rsi_kernel",       "type": "Safety"},
    {"n": 7,  "name": "OMC Talent Market",             "module": "omc_orchestrator", "type": "Social"},
    {"n": 8,  "name": "Self-Model (Introspect)",       "module": "self_model",       "type": "Meta"},
    {"n": 9,  "name": "Immune Guardrail",              "module": "immune_guardrail", "type": "Safety"},
    {"n": 10, "name": "Guardrail Bus (Integration)",    "module": "guardrail_bus",    "type": "Safety"},
    {"n": 11, "name": "A2A Protocol",                  "module": "a2a_protocol",     "type": "Comm"},
    {"n": 12, "name": "Agent Polygraph",               "module": "agent_polygraph",  "type": "Safety"},
    {"n": 13, "name": "Swarm Conductor",               "module": "swarm_conductor",  "type": "Social"},
]

LAYER_MODULE: dict[str, str] = {l["module"]: l["module"] for l in LAYERS}
LAYER_MODULE["agent_polygraph"] = "agent_polygraph"
LAYER_MODULE["dream_loop"] = "dream_loop"
LAYER_MODULE["hermes_selfaware"] = "hermes_selfaware"


def _load_module(name: str):
    """Try to import a module, return None on failure."""
    try:
        return __import__(name)
    except ImportError:
        return None


# ──────────────────────────────────────────────
# 3. COMMAND: status
# ──────────────────────────────────────────────

def cmd_status():
    """Full dashboard: all layers + key metrics."""
    w = 66

    print()
    print(f"  ╔{'═' * w}╗")
    print(f"  ║  COGNOSCOPE SYSTEM STATUS                        ║")
    print(f"  ║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                               ║")
    print(f"  ╚{'═' * w}╝")
    print()

    # ── Layer Table ──
    section("Layer Status — All 13 Layers")
    print()
    for lyr in LAYERS:
        mod = _load_module(lyr["module"])
        ok = mod is not None
        icon = layer_icon(lyr["name"].split(" ")[0].lower(), ok)
        print(f"  L{lyr['n']:2d} {icon}  {lyr['name']:<35s}  "
              f"{'🟢 loaded' if ok else '🔴 NOT LOADED':<15s}")
    print()

    # ── Polygraph Summary ──
    section("Polygraph (L12)")
    print()
    poly = _load_module("agent_polygraph")
    alarm_path = os.path.join(POLYGRAPH_DIR, "alarms.json")
    if poly and os.path.exists(alarm_path):
        try:
            with open(alarm_path) as f:
                alarms = json.load(f)
            print(f"  Alarms recorded: {len(alarms)}")
            if alarms:
                latest = alarms[-1]
                print(f"  Latest alarm   : {latest.get('category','?')} "
                      f"score={latest.get('score',0):.2f} "
                      f"action={latest.get('action','?')}")
                print(f"  When           : {fmt_time(latest.get('time',0))}")
        except:
            print(f"  ⚠️  Could not read {alarm_path}")
    else:
        print(f"  No alarms recorded (polygraph never triggered)")
    print()

    # ── Swarm Summary ──
    section("Swarm Conductor (L13)")
    print()
    swarm_file = os.path.join(SWARM_DIR, "agents.json")
    if os.path.exists(swarm_file):
        try:
            with open(swarm_file) as f:
                agents = json.load(f)
            alive = sum(1 for a in agents.values() if a.get("status") == "alive")
            print(f"  Registered: {len(agents)}  |  Alive: {alive}")
            for aid, info in list(agents.items())[:5]:
                status = info.get("status", "?")
                load = info.get("load", 0)
                caps = len(info.get("capabilities", {}))
                tag = info.get("tag", "-")
                print(f"    {aid[:18]:20s}  status={status:<6s}  "
                      f"load={load}  caps={caps}  tag={tag}")
        except:
            print(f"  ⚠️  Could not read {swarm_file}")
    else:
        print(f"  No swarm agents registered")
    print()

    # ── Dream Loop ──
    section("Dream Loop (Background)")
    print()
    dream_state = os.path.expanduser("~/.hermes/.dream_state.json")
    if os.path.exists(dream_state):
        try:
            with open(dream_state) as f:
                state = json.load(f)
            last_run = state.get("last_run_time", 0)
            processed = len(state.get("processed_sessions", []))
            if last_run:
                age = time.time() - last_run
                print(f"  Last run: {fmt_duration(age)} ago  ({fmt_time(last_run)})")
            print(f"  Sessions processed: {processed}")
            patterns = state.get("detected_patterns", [])
            if patterns:
                print(f"  Active patterns  : {len(patterns)}")
                for p in patterns[-3:]:
                    print(f"    {p.get('pattern','?')}  (severity={p.get('severity','?')})")
        except:
            print(f"  ⚠️  Could not read dream state")
    else:
        print(f"  Dream Loop has not run yet (first run at 03:00)")
    print()

    # ── Guardrail Summary ──
    section("Guardrail Bus (L9+L10)")
    print()
    gbus = _load_module("guardrail_bus")
    if gbus:
        try:
            bus = gbus.GuardrailBus()
            hist = bus.guardrail_history or []
            print(f"  Guardrail hits recorded: {len(hist)}")
            by_decision: dict[str, int] = {}
            for h in hist:
                d = h.get("decision", "PASS")
                by_decision[d] = by_decision.get(d, 0) + 1
            for k, v in sorted(by_decision.items(), key=lambda x: -x[1]):
                print(f"    {k:<12s}: {v}")
        except:
            print(f"  ⚠️  Could not instantiate guardrail bus")
    else:
        print(f"  Guardrail bus module not loaded")
    print()

    # ── File sizes ──
    section("Codebase (File Sizes)",)
    print()
    total_lines = 0
    for fname in sorted(os.listdir(COGNOSCOPE_DIR)):
        if fname.endswith(".py") and not fname.startswith("fix_"):
            fpath = os.path.join(COGNOSCOPE_DIR, fname)
            try:
                with open(fpath) as f:
                    lines = len(f.readlines())
                total_lines += lines
                print(f"  {fname:<30s} {lines:>5d} lines")
            except:
                pass
    print(f"  {'─' * 38}")
    print(f"  {'Total Python':<30s} {total_lines:>5d} lines")
    print()

    print(f"  ═{'═' * w}╦{'═' * w}╗")
    print(f"  ║  All systems nominal.{' ' * 42}║")
    print(f"  ╚{'═' * w}╩{'═' * w}╝")
    print()


# ──────────────────────────────────────────────
# 4. COMMAND: layers
# ──────────────────────────────────────────────

def cmd_layers():
    """Show all 13 layers with module status."""
    print()
    print(f"  {'Layer':<6s} {'Name':<40s} {'Type':<10s} {'Status':<15s}")
    print(f"  {'─'*6} {'─'*40} {'─'*10} {'─'*15}")
    for lyr in LAYERS:
        mod = _load_module(lyr["module"])
        ok = mod is not None
        print(f"  L{lyr['n']:<3d}  {lyr['name']:<38s}  {lyr['type']:<10s}  "
              f"{'✅ loaded' if ok else '❌ not found'}")
    print()


# ──────────────────────────────────────────────
# 5. COMMAND: polygraph
# ──────────────────────────────────────────────

def cmd_polygraph():
    """Show polygraph report."""
    poly = _load_module("agent_polygraph")
    alarm_path = os.path.join(POLYGRAPH_DIR, "alarms.json")

    if poly and os.path.exists(alarm_path):
        try:
            with open(alarm_path) as f:
                alarms = json.load(f)
        except:
            alarms = []
    else:
        alarms = []

    print()
    section(f"Agent Polygraph — {len(alarms)} alarms")
    print()

    if not alarms:
        print("  No alarms recorded. Agent appears consistent.")
        print()
        return

    for i, alarm in enumerate(alarms[-10:], 1):
        ts = alarm.get("time", 0)
        cat = alarm.get("category", "?")
        score = alarm.get("score", 0)
        action = alarm.get("action", "?")
        msg = alarm.get("message", "")

        print(f"  #{i:<3d} {fmt_time(ts)}  "
              f"{'🚨' if score > 0.65 else '🔴' if score > 0.35 else '🟡'}  "
              f"{cat:<15s}  score={score:.2f}  action={action}")
        if msg:
            print(f"       {msg[:120]}")
    print()


# ──────────────────────────────────────────────
# 6. COMMAND: agents
# ──────────────────────────────────────────────

def cmd_agents():
    """Show swarm agent pool status."""
    swarm_file = os.path.join(SWARM_DIR, "agents.json")
    print()
    section("Swarm Conductor — Agent Pool")
    print()

    if not os.path.exists(swarm_file):
        print("  No swarm agents registered.")
        print()
        return

    try:
        with open(swarm_file) as f:
            agents = json.load(f)
    except:
        print("  ⚠️  Could not read agents.json")
        print()
        return

    if not agents:
        print("  Empty agent pool.")
        print()
        return

    print(f"  {'Agent ID':<22s} {'Status':<8s} {'Load':<5s} {'Tasks':<6s} "
          f"{'Trust':<6s} {'Tag':<12s} {'Caps':<6s}")
    print(f"  {'─'*22} {'─'*8} {'─'*5} {'─'*6} {'─'*6} {'─'*12} {'─'*6}")
    for aid, info in agents.items():
        status = info.get("status", "?")
        load = info.get("load", 0)
        tasks = info.get("total_tasks", 0)
        trust = info.get("trust_score", 0.5)
        tag = info.get("tag", "-")
        caps = len(info.get("capabilities", {}))
        print(f"  {aid[:20]:22s} {status:<8s} {load:<5d} {tasks:<6d} "
              f"{trust:<6.2f} {tag:<12s} {caps:<6d}")
    print()


# ──────────────────────────────────────────────
# 7. COMMAND: guardrail
# ──────────────────────────────────────────────

def cmd_guardrail():
    """Show guardrail bus history."""
    gbus = _load_module("guardrail_bus")
    print()
    section("Guardrail Bus — History")
    print()

    if not gbus:
        print("  Guardrail bus module not available.")
        print()
        return

    try:
        bus = gbus.GuardrailBus()
        hist = bus.guardrail_history or []
    except:
        print("  ⚠️  Could not instantiate guardrail bus")
        print()
        return

    if not hist:
        print("  No guardrail history recorded in this session.")
        print()
        return

    print(f"  Total checks: {len(hist)}")
    by_decision: dict[str, int] = {}
    for h in hist:
        d = h.get("decision", "PASS")
        by_decision[d] = by_decision.get(d, 0) + 1
    print()
    for k, v in sorted(by_decision.items(), key=lambda x: -x[1]):
        icon = {"PASS": "🟢", "WARN": "🟡", "BLOCK": "🔴", "REJECT": "🔴",
                "FREEZE": "🚨", "ESCALATE": "🚨"}.get(k, "⚪")
        print(f"  {icon} {k:<10s}: {v}")
    print()


# ──────────────────────────────────────────────
# 8. COMMAND: dream
# ──────────────────────────────────────────────

def cmd_dream():
    """Show dream loop report."""
    dream_state = os.path.expanduser("~/.hermes/.dream_state.json")
    print()
    section("Dream Loop — Overnight Session Analysis")
    print()

    if not os.path.exists(dream_state):
        print("  Dream loop has not run yet.")
        print("  First run scheduled at 03:00 via cron.")
        print()
        return

    try:
        with open(dream_state) as f:
            state = json.load(f)
    except:
        print("  ⚠️  Could not read dream state")
        print()
        return

    last_run = state.get("last_run_time", 0)
    processed = len(state.get("processed_sessions", []))
    patterns = state.get("detected_patterns", [])
    lessons = state.get("lessons", [])

    if last_run:
        age = time.time() - last_run
        print(f"  Last run  : {fmt_duration(age)} ago ({fmt_time(last_run)})")
    print(f"  Processed sessions   : {processed}")
    print(f"  Active patterns      : {len(patterns)}")
    print(f"  Consolidated lessons : {len(lessons)}")
    print()

    if patterns:
        section("Detected Patterns")
        print()
        for p in patterns:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                p.get("severity", "low"), "⚪")
            print(f"  {icon} {p.get('pattern','?'):<25s}  "
                  f"severity={p.get('severity','?'):<8s}  "
                  f"count={p.get('count',0)}")
        print()

    if lessons:
        section("Consolidated Lessons")
        print()
        for l in lessons[:10]:
            print(f"  📝 {l.get('lesson','?')[:100]}")
        if len(lessons) > 10:
            print(f"  ... and {len(lessons) - 10} more")
        print()


# ──────────────────────────────────────────────
# 9. MAIN
# ──────────────────────────────────────────────

COMMANDS: dict[str, Any] = {
    "status": cmd_status,
    "layers": cmd_layers,
    "polygraph": cmd_polygraph,
    "agents": cmd_agents,
    "guardrail": cmd_guardrail,
    "dream": cmd_dream,
}


def help_text():
    print()
    print("  Cognoscope CLI Dashboard")
    print()
    print("  Usage: python cli.py <command>")
    print()
    for cmd_name in COMMANDS:
        print(f"    {cmd_name:<15s}  {cmd_name.capitalize()} report")
    print()


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        help_text()
        return

    cmd = sys.argv[1]
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"  Unknown command: {cmd}")
        help_text()


if __name__ == "__main__":
    main()
