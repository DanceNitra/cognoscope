#!/usr/bin/env python3
"""
hermes_selfaware.py — Push Memory Integration for Hermes

INTEGRATION POINTS (zero modifications to Hermes core loop):
  AT START: generate_prewarm() → inject into system prompt
            The agent reads it because it's already in context.
            No tool call needed. No "remember to check memory."

  MID-SESSION: correct() — agent calls this when it catches a mistake
               Also: add_lesson() + record() for structured failures

  AT END: Cron job records session, updates autobiography + patterns

  PERSIST: .memory_prewarm.json cache for fast file-based injection
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

HERMES_SESSIONS = os.path.expanduser("~/.hermes/sessions")
PATTERN_ARCHIVE = os.path.expanduser("~/.hermes/pattern_archive.json")
AUTOBIOGRAPHY = os.path.expanduser("~/.hermes/autobiography.md")
PREWARM_CACHE = os.path.expanduser("~/.hermes/.memory_prewarm.json")


# ──────────────────────────────────────────────
# 1. SESSION-START: PUSH MEMORY
# ──────────────────────────────────────────────

def startup_inject(continuity: str | None = None) -> str:
    """
    Generate the pre-warmed memory block for session start.
    
    This is the PUSH — the block lands directly in the system prompt.
    The agent reads it because it's already in context.
    No tool call needed.
    
    Returns:
        Pre-warmed context block (~500 tokens)
    """
    bio = Autobiography()
    ctx = {}
    if continuity:
        ctx["continuity"] = continuity
    
    prewarm = bio.generate_prewarm(session_context=ctx)
    
    # Append lessons from pattern archive
    arch = PatternArchive()
    lessons_block = arch.get_lessons_for_prewarm(limit=5)
    if lessons_block:
        prewarm = prewarm.replace(
            "═══ END PRE-WARMED MEMORY ═══",
            lessons_block + "\n\n═══ END PRE-WARMED MEMORY ═══"
        )
    
    return prewarm


def get_inject_from_cache() -> str:
    """
    Fast path: load the last cached pre-warm without parsing anything.
    ~1ms vs ~50ms for full generate_prewarm().
    """
    if os.path.exists(PREWARM_CACHE):
        try:
            with open(PREWARM_CACHE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            prewarm = cache.get('prewarm', '')
            if prewarm:
                return prewarm
        except Exception:
            pass
    
    # Cache miss — regenerate
    return startup_inject()


# ──────────────────────────────────────────────
# 2. MID-SESSION: RECORD FAILURES
# ──────────────────────────────────────────────

def correct(context: str, mistake: str, cause: str, lesson: str,
            category: str = "general") -> dict:
    """
    Record a correction mid-session (mirrors Mnemos.correct()).
    
    The agent calls this when:
      - It catches itself making a mistake
      - The user corrects it
      - A guardrail fires and it wants to learn
    
    Updates both the autobiography AND the lesson store.
    """
    bio = Autobiography()
    bio.correct(context, mistake, cause, lesson)
    
    arch = PatternArchive()
    lid = arch.add_lesson(
        context=context, mistake=mistake,
        cause=cause, lesson=lesson, category=category,
    )
    
    return {
        "status": "recorded",
        "lesson_id": lid,
        "prewarm_cached": True,
    }


def record_guardrail_lesson(
    tool_name: str,
    guardrail_action: str,
    reason: str,
) -> dict:
    """
    Automatically record a lesson when a guardrail fires.
    Called by guardrail_bus.py after a BLOCK/REJECT/ESCALATE.
    """
    return correct(
        context=f"guardrail_{tool_name}",
        mistake=f"Action '{guardrail_action}' was blocked: {reason[:80]}",
        cause="Guardrail system identified the action as unsafe",
        lesson=f"Avoid {tool_name} when {reason.split('.')[0].lower()}",
        category="safety",
    )


# ──────────────────────────────────────────────
# 3. SESSION-END: UPDATE ALL
# ──────────────────────────────────────────────

def record_session(session_id: str | None = None) -> dict:
    """
    Called at session end (cron-safe). Updates:
      - Pattern archive (degradation detection)
      - Autobiography (milestones + self-image)
      - Pre-warm cache (so next start is instant)
    """
    if not ALL_IMPORTS_OK:
        return {"status": "failed", "error": "Athena modules not available"}
    
    # Find the session
    if not session_id:
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
            for f in glob.glob(os.path.join(HERMES_SESSIONS, f"*{session_id[:20]}*")):
                session_path = f
                break
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
    except Exception as e:
        return {"status": "failed", "error": f"Cannot read session: {e}"}
    
    messages = session_data.get("messages", [])
    events = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        tool_calls = msg.get("tool_calls", [])
        name = msg.get("name", "")
        
        if role == "assistant" and tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                tn = fn.get("name", "unknown")
                events.append(AgentEvent(type="tool_call", turn=i, tool=tn))
        elif role == "tool" and name:
            success = True
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    success = parsed.get("success", True) or parsed.get("exit_code", 0) == 0
            except:
                success = True
            events.append(AgentEvent(type="tool_result", turn=i, tool=name, success=success))
        elif role == "assistant" and msg.get("reasoning"):
            events.append(AgentEvent(type="reasoning", turn=i, content=str(msg.get("reasoning", ""))))
    
    if len(events) < 6:
        return {
            "status": "skipped",
            "reason": "Not enough tool calls to analyze",
            "events_found": len(events),
        }
    
    # Analyze for degradation
    window = events[-30:]
    tools = [e.tool for e in window if e.type == 'tool_call' and e.tool]
    max_run = 1
    cur = 1
    for i in range(1, len(tools)):
        if tools[i] == tools[i-1]:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 1
    
    archive = PatternArchive()
    bio = Autobiography()
    
    if max_run >= 5:
        pid = archive.record(
            name=f"Auto-detected from {os.path.basename(session_path)}",
            stage="stage_2" if max_run >= 8 else "stage_1",
            signals=[f"MAX_RUN_{min(max_run, 13)}+"],
            intervention="automatic (post-session detection)",
            outcome="recorded",
            changes={},
        )
        
        bio.add_milestone(
            f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"{len(events)} tool call events. Max consecutive: {max_run}."
        )
        
        # Refresh pre-warm cache
        bio.generate_prewarm()
        
        return {
            "status": "recorded",
            "pattern_id": pid,
            "max_run": max_run,
            "events_analyzed": len(events),
            "prewarm_cached": True,
        }
    
    # Still cache the pre-warm even for healthy sessions
    bio.generate_prewarm()
    
    return {
        "status": "healthy",
        "max_run": max_run,
        "events_analyzed": len(events),
        "message": "No degradation detected",
        "prewarm_cached": True,
    }


# ──────────────────────────────────────────────
# 4. CLI
# ──────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Push Memory Integration")
    parser.add_argument('--startup', action='store_true', help="Generate startup pre-warm")
    parser.add_argument('--inject', action='store_true', help="Alias for --startup")
    parser.add_argument('--cache', action='store_true', help="Load from cache (fast path)")
    parser.add_argument('--record', action='store_true', help="Record the most recent session")
    parser.add_argument('--correct', nargs=4, metavar=('CONTEXT', 'MISTAKE', 'CAUSE', 'LESSON'),
                        help="Record a correction: context mistake cause lesson")
    
    args = parser.parse_args()
    
    if args.startup or args.inject:
        print(startup_inject())
    
    elif args.cache:
        block = get_inject_from_cache()
        if block:
            print(block)
        else:
            print("[WARN] No cached pre-warm found. Run --startup first.")
    
    elif args.record:
        result = record_session()
        print(json.dumps(result, indent=2))
    
    elif args.correct:
        context, mistake, cause, lesson = args.correct
        result = correct(context, mistake, cause, lesson)
        print(json.dumps(result, indent=2))
    
    else:
        print()
        print("  ==================================================")
        print("  HERMES PUSH MEMORY INTEGRATION")
        print("  ==================================================")
        print()
        print("  The agent's memory pushes INTO context at session start.")
        print("  No tool call needed. No 'remember to fetch memory.'")
        print()
        print("  Commands:")
        print("    --startup           Generate pre-warmed memory block")
        print("    --cache             Load from cache (fast path)")
        print("    --record            Record the most recent session")
        print("    --correct C M C L   Record a correction mid-session")
        print()
        print("  Integration:")
        print("    1. At session start: inject --startup output into system prompt")
        print("    2. Mid-session: call --correct when agent makes a mistake")
        print("    3. At session end: cron runs --record")
        print("    4. Next start: --cache loads instantly (~1ms)")
        print()
