#!/usr/bin/env python3
"""
hermes_selfaware.py — Safe integration of self-awareness into Hermes.

Reads the Pattern Archive and Autobiography at session start.
Writes session-end updates via a cron job.

Zero modifications to Hermes core loop.
Zero risk of breaking the agent runtime.

Integration points:
  AT START: Agent reads autobiography.md and pattern_archive.json
            via read_file at session init. No code changes.
  AT END:   Cron job runs record_session.py to archive this session's
            degradation signals and update the autobiography.
  PERSIST:  memory() tool stores key facts in Hermes' own memory.
"""

import json, os, sys, glob, re
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.expanduser("~/cognoscope"))
try:
    from pattern_archive import PatternArchive
    from autobiography import Autobiography
    from metaloop import classify_stage, AgentEvent
    ALL_IMPORTS_OK = True
except ImportError as e:
    ALL_IMPORTS_OK = False
    print(f"[WARN] Could not import Athena modules: {e}")


HERMES_SESSIONS = os.path.expanduser("~/.hermes/sessions")
PATTERN_ARCHIVE = os.path.expanduser("~/.hermes/pattern_archive.json")
AUTOBIOGRAPHY = os.path.expanduser("~/.hermes/autobiography.md")


# ──────────────────────────────────────────────
# 1. SESSION-START CHECK
# ──────────────────────────────────────────────

def startup_message() -> dict:
    """
    Called at session start. Returns a dict that the agent
    reads as self-knowledge. No runtime effect.
    
    Can be called from a skill or from the agent's
    own initialization routine.
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "has_autobiography": os.path.exists(AUTOBIOGRAPHY),
        "has_pattern_archive": os.path.exists(PATTERN_ARCHIVE),
        "past_session_count": len(glob.glob(os.path.join(HERMES_SESSIONS, "*.json"))),
    }
    
    # Read autobiography
    if result["has_autobiography"]:
        try:
            with open(AUTOBIOGRAPHY, 'r', encoding='utf-8') as f:
                result["autobiography_preview"] = []
                for section in ['## Self-Image', '## Values', '## Aspirations']:
                    content = f.read()
                    if section in content:
                        start = content.index(section)
                        end = content.find('\n## ', start + 1)
                        if end == -1:
                            end = len(content)
                        snippet = content[start:end].strip()[:200]
                        result["autobiography_preview"].append(snippet)
                    f.seek(0)
        except Exception as e:
            result["autobiography_error"] = str(e)
    
    # Read pattern archive
    if result["has_pattern_archive"]:
        try:
            with open(PATTERN_ARCHIVE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            result["pattern_count"] = len(raw)
            result["patterns"] = []
            for pid, p in raw.items():
                result["patterns"].append({
                    "id": pid,
                    "name": p.get("name", "unknown"),
                    "stage": p.get("stage", "unknown"),
                    "times_seen": p.get("times_seen", 0),
                    "signals": p.get("trigger_signals", [])[:3],
                })
        except Exception as e:
            result["archive_error"] = str(e)
    
    return result


def memory_injection() -> str:
    """
    Generates a short prompt injection block that tells the agent
    who it is, what patterns it has fallen into before, and what
    it aspires to. Safe — this is just text in the system prompt.
    """
    info = startup_message()
    lines = ["---", "SELF-KNOWLEDGE (from persistent identity)", ""]
    
    if info["has_autobiography"] and info.get("autobiography_preview"):
        lines.append("My autobiography says:")
        for s in info["autobiography_preview"][:2]:
            lines.append(f"  {s[:100]}")
        lines.append("")
    
    if info["has_pattern_archive"] and info.get("patterns"):
        lines.append(f"I have experienced {info['past_session_count']} sessions.")
        lines.append(f"My pattern archive contains {info['pattern_count']} known patterns.")
        for p in info["patterns"][:3]:
            sigs = ", ".join(p["signals"])
            lines.append(f"  - {p['name']} (seen {p['times_seen']}x): {sigs}")
        lines.append("")
        lines.append("If I notice these signals, I can pre-configure my")
        lines.append("architecture to avoid repeating past mistakes.")
    
    lines.append("---")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 2. SESSION-END RECORDING (cron-safe)
# ──────────────────────────────────────────────

def record_session(session_id: str | None = None) -> dict:
    """
    Called at session end. Reads the most recent Hermes session,
    extracts degradation signals, updates the Pattern Archive
    and the Autobiography.
    
    Safe for cron: pure file I/O, no network, no agent loop.
    """
    if not ALL_IMPORTS_OK:
        return {"status": "failed", "error": "Athena modules not available"}
    
    # Find the session
    if not session_id:
        # Use the most recent session
        files = sorted(
            glob.glob(os.path.join(HERMES_SESSIONS, "*.json")),
            key=os.path.getmtime, reverse=True
        )
        if not files:
            return {"status": "skipped", "reason": "No session files found"}
        session_path = files[0]
    else:
        session_path = os.path.join(HERMES_SESSIONS, f"{session_id}.json")
        if not os.path.exists(session_path):
            # Try to find it by prefix
            for f in glob.glob(os.path.join(HERMES_SESSIONS, f"*{session_id[:20]}*")):
                session_path = f
                break
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
    except Exception as e:
        return {"status": "failed", "error": f"Cannot read session: {e}"}
    
    messages = session_data.get("messages", [])
    
    # Extract tool calls from messages
    events = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        tool_calls = msg.get("tool_calls", [])
        name = msg.get("name", "")
        
        # Assistant messages with tool_calls in extra fields
        if role == "assistant" and tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                tn = fn.get("name", "unknown")
                events.append(AgentEvent(type="tool_call", turn=i, tool=tn))
        
        # Tool result messages (role="tool")
        elif role == "tool" and name:
            success = True
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    success = parsed.get("success", True) or parsed.get("exit_code", 0) == 0
            except:
                success = True
            events.append(AgentEvent(type="tool_result", turn=i, tool=name, success=success))
        
        # Reasoning content from assistant
        elif role == "assistant" and msg.get("reasoning"):
            events.append(AgentEvent(type="reasoning", turn=i, content=str(msg.get("reasoning", ""))))
    
    if len(events) < 6:
        return {
            "status": "skipped",
            "reason": "Not enough tool calls to analyze",
            "events_found": len(events),
        }
    
    # Run recovery classification
    recovery = None
    try:
        window = events[-30:]
        # Simple classifier without importing metaloop (avoid deps)
        tools = [e.tool for e in window if e.type == 'tool_call' and e.tool]
        reflections = [e for e in window if e.type == 'reasoning']
        tool_calls_count = len([e for e in window if e.type == 'tool_call'])
        
        max_run = 1
        cur = 1
        for i in range(1, len(tools)):
            if tools[i] == tools[i-1]:
                cur += 1
                max_run = max(max_run, cur)
            else:
                cur = 1
        
        if max_run >= 5:
            # Update pattern archive
            archive = PatternArchive()
            pid = archive.record(
                name=f"Auto-detected from {os.path.basename(session_path)}",
                stage="stage_2" if max_run >= 8 else "stage_1",
                signals=[f"MAX_RUN_{min(max_run, 13)}+"],
                intervention="automatic (post-session detection)",
                outcome="recorded",
                changes={},
            )
            
            # Update autobiography
            bio = Autobiography()
            bio.append_to('capabilities', f"- Session {os.path.basename(session_path)[:20]}: {len(events)} tool calls, max run {max_run}")
            bio.add_milestone(
                f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"{len(events)} tool call events recorded. Max consecutive: {max_run}."
            )
            
            result = {
                "status": "recorded",
                "pattern_id": pid,
                "max_run": max_run,
                "events_analyzed": len(events),
                "message": f"Recorded pattern with max run {max_run}"
            }
            return result
        
        return {
            "status": "healthy",
            "max_run": max_run,
            "events_analyzed": len(events),
            "message": "No degradation detected — session was healthy"
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ──────────────────────────────────────────────
# 3. SETUP CRON
# ──────────────────────────────────────────────

def setup_cron() -> str:
    """
    Instructions for setting up a cron job that records
    session outcomes automatically.
    
    To be run once. The cron job fires 5 minutes after
    every session end (conservative estimate).
    """
    lines = [
        "To enable automatic session-end recording:",
        "",
        "1. Create a session-end cron job:",
        "   hermes cron create \\",
        "     --name 'session-end-record' \\",
        "     --schedule '*/15 * * * *' \\",
        "     --script '~/cognoscope/hermes_selfaware.py' \\",
        "     --no-agent",
        "",
        "2. Or run it manually after any session:",
        "   python3 ~/cognoscope/hermes_selfaware.py --record",
        "",
        "3. At session start, the agent reads:",
        "   - ~/.hermes/autobiography.md (self-image)",
        "   - ~/.hermes/pattern_archive.json (past patterns)",
        "",
        "4. To inject self-knowledge into the prompt:",
        "   Run: python3 ~/cognoscope/hermes_selfaware.py --inject",
        "   This prints a block you can add to the system prompt.",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 4. CLI
# ──────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Self-Awareness Integration")
    parser.add_argument('--startup', action='store_true', help="Check startup state")
    parser.add_argument('--inject', action='store_true', help="Generate memory injection block")
    parser.add_argument('--record', action='store_true', help="Record the most recent session")
    parser.add_argument('--setup', action='store_true', help="Show setup instructions")
    
    args = parser.parse_args()
    
    if args.startup:
        info = startup_message()
        print(json.dumps(info, indent=2))
    
    elif args.inject:
        print(memory_injection())
    
    elif args.record:
        result = record_session()
        print(json.dumps(result, indent=2))
    
    elif args.setup:
        print(setup_cron())
    
    else:
        print()
        print("  ==================================================")
        print("  HERMES SELF-AWARENESS INTEGRATION")
        print("  ==================================================")
        print()
        print("  Safe integration — zero modifications to Hermes.")
        print()

        info = startup_message()
        print(f"  Sessions recorded:     {info['past_session_count']}")
        print(f"  Autobiography exists:  {info['has_autobiography']}")
        print(f"  Pattern archive exists: {info['has_pattern_archive']}")
        archive_count = info.get('pattern_count', 0)
        print(f"  Known patterns:         {archive_count}")
        print()
        
        if info['has_autobiography']:
            print("  The agent knows itself. Your Autobiography is ready.")
        else:
            print("  No Autobiography yet. It will be created after")
            print("  the first session-end recording.")
        print()
        
        print("  Commands:")
        print("    --startup   Check session state")
        print("    --inject    Generate memory injection block")
        print("    --record    Record the most recent session")
        print("    --setup     Show cron setup instructions")
        print()
