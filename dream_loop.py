#!/usr/bin/env python3
"""
dream_loop.py — Background Session Analysis Engine (The Dreaming Agent)

Inspired by Claude Code's "dream about your codebase while you sleep"
(HN #5, 2026-05-29). The agent analyzes its own sessions overnight:

  1. Scans all new sessions since last dream run
  2. Extracts patterns: tool churn, tool loops, guardrail hits, topic shifts
  3. Consolidates lessons: merges similar mistakes, archives stale ones
  4. Refreshes pre-warm cache for morning
  5. Generates dream report (morning briefing)

Usage:
    python3 dream_loop.py                   # Run full dream loop
    python3 dream_loop.py --report          # Show last dream report
    python3 dream_loop.py --status          # Check when dream last ran
"""

import json, os, sys, glob, re
from datetime import datetime, timedelta, timezone
from typing import Any
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from pattern_archive import PatternArchive, LessonRecord
    from autobiography import Autobiography
    ALL_IMPORTS_OK = True
except ImportError:
    ALL_IMPORTS_OK = False

HERMES_SESSIONS_DIR = os.path.expanduser("~/.hermes/sessions")
SESSIONS_JSON = os.path.join(HERMES_SESSIONS_DIR, "sessions.json")
DREAM_STATE_PATH = os.path.expanduser("~/.hermes/.dream_state.json")
PREWARM_CACHE = os.path.expanduser("~/.hermes/.memory_prewarm.json")


# ──────────────────────────────────────────────
# 1. SESSION SCANNER
# ──────────────────────────────────────────────

def get_recent_sessions(min_new_since: str | None = None) -> list[dict]:
    """
    Scan sessions.json and .jsonl files for all sessions since last dream run.
    
    Some sessions are stored ONLY as .jsonl files (not indexed in sessions.json).
    We scan both.
    
    Returns list of {session_id, platform, source, jsonl_path}
    """
    result = []
    seen_ids = set()
    
    # 1. Check sessions.json (current active sessions)
    if os.path.exists(SESSIONS_JSON):
        with open(SESSIONS_JSON) as f:
            data = json.load(f)
        
        for key, meta in data.items():
            sid = meta.get("session_id", "")
            if not sid:
                continue
            
            updated = meta.get("updated_at", "")
            if min_new_since and updated and updated < min_new_since:
                continue
            
            # Find corresponding .jsonl file
            jsonl_path = _find_jsonl_for_session(sid)
            if jsonl_path is None:
                # Session is active/live, no .jsonl yet
                continue
            
            seen_ids.add(sid)
            result.append({
                "session_id": sid,
                "platform": meta.get("platform", "?"),
                "source": meta.get("source", "?"),
                "created_at": meta.get("created_at", ""),
                "updated_at": updated,
                "jsonl_path": jsonl_path,
                "size_kb": os.path.getsize(jsonl_path) / 1024,
            })
    
    # 2. Also scan .jsonl files directly (older sessions not in sessions.json)
    for fname in os.listdir(HERMES_SESSIONS_DIR):
        if not fname.endswith('.jsonl'):
            continue
        jsonl_path = os.path.join(HERMES_SESSIONS_DIR, fname)
        
        # Extract session_id from filename
        sid = fname.replace('.jsonl', '')
        
        if sid in seen_ids:
            continue
        
        # Get creation time from file mtime
        mtime = os.path.getmtime(jsonl_path)
        created_dt = datetime.fromtimestamp(mtime)
        created_iso = created_dt.isoformat()
        
        if min_new_since and created_iso < min_new_since:
            continue
        
        seen_ids.add(sid)
        result.append({
            "session_id": sid,
            "platform": "file",
            "source": "jsonl",
            "created_at": created_iso,
            "updated_at": created_iso,
            "jsonl_path": jsonl_path,
            "size_kb": os.path.getsize(jsonl_path) / 1024,
        })
    
    # Sort by updated_at descending
    result.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return result


def _find_jsonl_for_session(session_id: str) -> str | None:
    """Find a .jsonl file matching a session_id."""
    for fname in os.listdir(HERMES_SESSIONS_DIR):
        if fname.endswith('.jsonl') and session_id in fname:
            return os.path.join(HERMES_SESSIONS_DIR, fname)
    return None


def analyze_session(jsonl_path: str) -> dict:
    """
    Analyze a single session's .jsonl file.
    
    Returns:
      tool_calls: list of tool names used
      tool_frequencies: Counter of tool use
      max_consecutive_same_tool: int
      guardrail_hits: list of tools that hit guardrails
      topic_shifts: int (approximate by content topic changes)
      total_turns: int
      user_messages: int
      assistant_messages: int
      key_actions: list of notable action descriptions
    """
    if not os.path.exists(jsonl_path):
        return {"error": "File not found"}
    
    tool_calls = []
    messages = []
    
    try:
        with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        return {"error": str(e)}
    
    # Track tool calls
    tool_details = []  # (turn, tool)
    guardrail_references = []
    assistant_contents = []
    user_contents = []
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        tool_calls_list = msg.get("tool_calls", [])
        name = msg.get("name", "")
        
        if role == "assistant" and tool_calls_list:
            for tc in tool_calls_list:
                fn = tc.get("function", {})
                tn = fn.get("name", "unknown")
                tool_details.append((i, tn))
                tool_calls.append(tn)
        
        elif role == "assistant":
            assistant_contents.append(content)
        
        elif role == "user":
            user_contents.append(content)
        
        # Check for guardrail-related content
        content_lower = content.lower()
        for guardrail_word in ["guardrail", "blocked", "rejected", "freeze", "escalate"]:
            if guardrail_word in content_lower:
                guardrail_references.append((i, content[:100]))
                break
    
    # Max consecutive same tool
    max_run = 1
    current_run = 1
    for i in range(1, len(tool_details)):
        if tool_details[i][1] == tool_details[i-1][1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    
    # Tool frequencies
    freq = Counter(tool_calls)
    
    # Topic estimation by word frequency shifts
    all_text = " ".join(assistant_contents)
    words = all_text.lower().split()
    topic_words = [w for w in words if len(w) > 5]
    topic_shifts = len(set(topic_words)) // 20  # rough approximation
    
    # Extract key actions from assistant content
    key_actions = []
    import re as _re
    # Look for pattern: "Built X" / "Created Y" / "Fixed Z"
    action_re = r'\b([Bb]uilt|[Cc]reated|[Ff]ixed|[Ii]mplemented|[Aa]dded|[Ww]rote)\b\s+([^.!]+)'
    for content in assistant_contents[-10:]:  # last 10 assistant messages
        for m in _re.finditer(action_re, content):
            key_actions.append(f"{m.group(1)} {m.group(2)}")
            if len(key_actions) >= 5:
                break
        if len(key_actions) >= 5:
            break
    
    return {
        "tool_calls": tool_calls,
        "tool_frequencies": dict(freq.most_common(10)),
        "unique_tools": len(set(tool_calls)),
        "max_consecutive_same_tool": max_run,
        "guardrail_hits": len(guardrail_references),
        "guardrail_details": guardrail_references[:3],
        "topic_shifts": min(topic_shifts, 20),
        "total_messages": len(messages),
        "user_messages": sum(1 for m in messages if m.get("role") == "user"),
        "assistant_messages": sum(1 for m in messages if m.get("role") == "assistant"),
        "tool_messages": sum(1 for m in messages if m.get("role") == "tool"),
        "key_actions": key_actions[:5],
        "session_length_chars": sum(len(m.get("content", "")) for m in messages),
    }


# ──────────────────────────────────────────────
# 2. PATTERN DETECTOR
# ──────────────────────────────────────────────

def detect_patterns(all_sessions_analysis: list[tuple[str, dict]]) -> list[dict]:
    """
    Detect cross-session patterns from analyzed sessions.
    
    Returns list of detected patterns with name, severity, sessions_affected
    """
    patterns = []
    
    if not all_sessions_analysis:
        return patterns
    
    # Pattern 1: Tool churn (same tool used > 8 consecutive times across sessions)
    churn_sessions = []
    for sid, analysis in all_sessions_analysis:
        if isinstance(analysis, dict) and "error" not in analysis:
            if analysis.get("max_consecutive_same_tool", 0) >= 8:
                churn_sessions.append(sid)
    if churn_sessions:
        patterns.append({
            "name": "tool_churn",
            "severity": "high",
            "description": f"Tool churn detected in {len(churn_sessions)} sessions",
            "sessions_affected": churn_sessions,
            "recommendation": "Consider tightening max_consecutive_same_tool or adding reflection checkpoints",
        })
    
    # Pattern 2: Guardrail spike
    guardrail_sessions = []
    for sid, analysis in all_sessions_analysis:
        if isinstance(analysis, dict) and "error" not in analysis:
            if analysis.get("guardrail_hits", 0) >= 3:
                guardrail_sessions.append(sid)
    if guardrail_sessions:
        patterns.append({
            "name": "guardrail_spike",
            "severity": "medium",
            "description": f"Guardrail spikes in {len(guardrail_sessions)} sessions",
            "sessions_affected": guardrail_sessions,
            "recommendation": "Review what triggered guardrails — possible overcaution or actual risk",
        })
    
    # Pattern 3: Low diversity (only 1-2 unique tools used across session)
    low_div_sessions = []
    for sid, analysis in all_sessions_analysis:
        if isinstance(analysis, dict) and "error" not in analysis:
            if analysis.get("unique_tools", 0) <= 2 and analysis.get("total_messages", 0) > 20:
                low_div_sessions.append(sid)
    if low_div_sessions:
        patterns.append({
            "name": "low_tool_diversity",
            "severity": "medium",
            "description": f"Low tool diversity in {len(low_div_sessions)} sessions",
            "sessions_affected": low_div_sessions,
            "recommendation": "Agent may be stuck in one mode — consider forcing tool rotation",
        })
    
    # Pattern 4: Topic saturation (many sessions on same topic)
    tool_freqs = Counter()
    for sid, analysis in all_sessions_analysis:
        if isinstance(analysis, dict) and "error" not in analysis:
            tf = analysis.get("tool_frequencies", {})
            for tool, count in tf.items():
                tool_freqs[tool] += count
    
    if tool_freqs:
        dominant = tool_freqs.most_common(1)[0]
        total = sum(tool_freqs.values())
        if total > 0 and dominant[1] / total > 0.6:
            patterns.append({
                "name": "tool_dominance",
                "severity": "low",
                "description": f"'{dominant[0]}' dominates {dominant[1]/total:.0%} of all tool calls",
                "sessions_affected": [sid for sid, _ in all_sessions_analysis],
                "recommendation": "Consider distributing work across more tools",
            })
    
    return patterns


# ──────────────────────────────────────────────
# 3. LESSONS CONSOLIDATOR
# ──────────────────────────────────────────────

def consolidate_lessons(archive: PatternArchive) -> dict:
    """
    Consolidate similar lessons. Merge duplicates, archive stale ones.
    
    Returns report of what was consolidated.
    """
    if not archive or not archive.lessons:
        return {"merged": 0, "archived": 0, "remaining": 0}
    
    merged = 0
    # Group by similarity in lesson text
    to_remove = set()
    lessons = list(archive.lessons)  # copy
    
    for i in range(len(lessons)):
        if lessons[i].lesson_id in to_remove:
            continue
        for j in range(i + 1, len(lessons)):
            if lessons[j].lesson_id in to_remove:
                continue
            
            # Jaccard on lesson words
            wi = set(lessons[i].lesson.lower().split()[:10])
            wj = set(lessons[j].lesson.lower().split()[:10])
            if wi and wj:
                overlap = len(wi & wj)
                smaller = min(len(wi), len(wj))
                if smaller > 0 and overlap / smaller >= 0.4:
                    # Merge: keep the one with more applied_count, or the newer one
                    if lessons[i].applied_count >= lessons[j].applied_count:
                        lessons[i].applied_count += lessons[j].applied_count + 1
                        to_remove.add(lessons[j].lesson_id)
                    else:
                        lessons[j].applied_count += lessons[i].applied_count + 1
                        to_remove.add(lessons[i].lesson_id)
                    merged += 1
    
    # Archive stale lessons (> 72h with 0 applied_count)
    archived = 0
    now = datetime.now()
    for l in lessons:
        if l.lesson_id in to_remove:
            continue
        if l.applied_count == 0:
            try:
                ts = datetime.fromisoformat(l.timestamp) if l.timestamp else now
                if (now - ts) > timedelta(hours=72):
                    to_remove.add(l.lesson_id)
                    archived += 1
            except:
                pass
    
    # Apply changes
    if to_remove:
        archive.lessons = [l for l in archive.lessons if l.lesson_id not in to_remove]
        archive._save_lessons()
    
    return {
        "merged": merged,
        "archived": archived,
        "remaining": len(archive.lessons),
    }


# ──────────────────────────────────────────────
# 4. DREAM LOOP ENGINE
# ──────────────────────────────────────────────

class DreamLoop:
    """
    Nightly session analysis engine.
    
    Pipeline:
      1. Load dream state (when was last run, which sessions processed)
      2. Scan new sessions since last run
      3. Analyze each session
      4. Detect cross-session patterns
      5. Consolidate lessons
      6. Update pattern archive
      7. Refresh pre-warm cache
      8. Generate dream report
      9. Save dream state
    """
    
    def __init__(self):
        self.state = self._load_state()
        self.archive = PatternArchive()
        self.bio = Autobiography()
    
    def _load_state(self) -> dict:
        default = {
            "last_run": None,
            "processed_session_ids": [],
            "total_runs": 0,
            "last_report": "",
        }
        if os.path.exists(DREAM_STATE_PATH):
            try:
                with open(DREAM_STATE_PATH) as f:
                    state = json.load(f)
                return {**default, **state}
            except:
                pass
        return default
    
    def _save_state(self):
        os.makedirs(os.path.dirname(DREAM_STATE_PATH), exist_ok=True)
        with open(DREAM_STATE_PATH, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)
    
    def run(self) -> dict:
        """Execute one dream loop cycle."""
        now = datetime.now()
        now_iso = now.isoformat()
        
        # 1. Find new sessions
        last_run = self.state.get("last_run")
        sessions = get_recent_sessions(min_new_since=last_run)
        
        # Filter out already processed
        processed_set = set(self.state.get("processed_session_ids", []))
        new_sessions = [s for s in sessions if s["session_id"] not in processed_set]
        
        # If none, refresh cache anyway but produce a lighter report
        if not new_sessions:
            self.state["last_run"] = now_iso
            self.state["total_runs"] += 1
            self._save_state()
            
            # Still refresh pre-warm cache
            self.bio.generate_prewarm()
            
            return {
                "status": "no_new_sessions",
                "total_known_sessions": len(sessions),
                "message": "No new sessions since last dream run. Pre-warm refreshed.",
            }
        
        # 2. Analyze each new session
        analysis_results = []
        session_summaries = []
        total_tool_calls = 0
        
        for s in new_sessions:
            analysis = analyze_session(s["jsonl_path"])
            
            if "error" in analysis:
                continue
            
            analysis_results.append((s["session_id"], analysis))
            
            total_tool_calls += len(analysis.get("tool_calls", []))
            
            # Build summary
            tools = analysis.get("tool_frequencies", {})
            top_tools = ", ".join([f"{t}({c})" for t, c in list(tools.items())[:3]])
            
            session_summaries.append({
                "session_id": s["session_id"],
                "platform": s.get("platform", "?"),
                "created_at": s.get("created_at", "?"),
                "total_messages": analysis.get("total_messages", 0),
                "max_consecutive": analysis.get("max_consecutive_same_tool", 0),
                "unique_tools": analysis.get("unique_tools", 0),
                "guardrail_hits": analysis.get("guardrail_hits", 0),
                "top_tools": top_tools,
                "key_actions": analysis.get("key_actions", []),
            })
        
        # 3. Detect cross-session patterns
        patterns = detect_patterns(analysis_results)
        
        # 4. Record patterns to archive
        new_pattern_ids = []
        for p in patterns:
            signals = [p["name"]]
            if p["severity"] == "high":
                signals.append("HIGH_SEVERITY")
            pid = self.archive.record(
                name=p["name"],
                stage="dream_detected",
                signals=signals,
                intervention=f"Automatic: {p['recommendation']}",
                outcome="detected",
                changes={},
            )
            new_pattern_ids.append(pid)
        
        # 5. Consolidate lessons
        consolidation = consolidate_lessons(self.archive)
        
        # 6. Record milestones for key achievements
        all_actions = []
        for sid, analysis in analysis_results:
            all_actions.extend(analysis.get("key_actions", []))
        
        notable_actions = []
        for action in all_actions:
            if any(word in action.lower() for word in ["built", "created", "implemented", "wrote"]):
                if len(action) < 100 and action not in [a["action"] for a in notable_actions]:
                    notable_actions.append({"action": action, "session_id": sid})
        
        # 7. Refresh pre-warm cache
        # Build continuity from the most interesting session
        continuity_parts = []
        for p in patterns[:2]:
            continuity_parts.append(f"Dream detected: {p['name']} ({p['severity']})")
        if notable_actions:
            continuity_parts.append(f"Built: {notable_actions[-1]['action'][:60]}")
        
        continuity = " | ".join(continuity_parts) if continuity_parts else "Dream loop completed overnight"
        
        self.bio.generate_prewarm(session_context={
            "continuity": continuity,
        })
        
        # 8. Generate dream report
        report = self._generate_report(
            new_sessions, session_summaries, patterns,
            consolidation, total_tool_calls, notable_actions
        )
        
        # 9. Update state
        new_processed = [s["session_id"] for s in new_sessions]
        self.state["processed_session_ids"] = new_processed + list(processed_set)
        self.state["last_run"] = now_iso
        self.state["total_runs"] += 1
        self.state["last_report"] = report
        self._save_state()
        
        return {
            "status": "completed",
            "sessions_analyzed": len(new_sessions),
            "total_tool_calls": total_tool_calls,
            "patterns_found": len(patterns),
            "lessons_consolidated": consolidation["merged"] + consolidation["archived"],
            "lessons_remaining": consolidation["remaining"],
            "prewarm_refreshed": True,
            "new_pattern_ids": new_pattern_ids,
            "report": report,
        }
    
    def _generate_report(
        self,
        sessions, summaries, patterns,
        consolidation, total_calls, notable_actions,
    ) -> str:
        """Generate the formatted dream report."""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        n_sessions = len(sessions)
        
        lines = [
            f"🌙 Dream Loop — {now_str}",
            "",
            f"📊 Analyzoval som {n_sessions} session" + ("í" if n_sessions > 1 else "u") + ",",
            f"   {total_calls} tool callov cez všetky sessiony.",
            "",
        ]
        
        # Session summaries
        lines.append("📋 Sessiony:")
        for s in summaries:
            sid_short = s["session_id"][:25] + "..."
            guardrail_str = f"⚠️ {s['guardrail_hits']} guardrail" if s['guardrail_hits'] else "✅ clean"
            lines.append(
                f"  • {sid_short} | "
                f"{s['total_messages']} msgs | "
                f"max_run={s['max_consecutive']} | "
                f"tools={s['unique_tools']} | "
                f"{guardrail_str}"
            )
        lines.append("")
        
        # Patterns
        if patterns:
            lines.append("🧠 Nové vzory:")
            for p in patterns:
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                icon = severity_icon.get(p['severity'], "⚪")
                lines.append(f"  {icon} {p['name']} ({p['severity']})")
                lines.append(f"     {p['description']}")
            lines.append("")
        
        # Consolidation
        if consolidation["merged"] > 0 or consolidation["archived"] > 0:
            lines.append("📚 Lessons:")
            if consolidation["merged"] > 0:
                lines.append(f"  • Zlúčené: {consolidation['merged']} podobných lekcií")
            if consolidation["archived"] > 0:
                lines.append(f"  • Archivované: {consolidation['archived']} starých (0x použitých >72h)")
            lines.append(f"  • Zostáva: {consolidation['remaining']} aktívnych lekcií")
            lines.append("")
        
        # Notable achievements
        if notable_actions:
            lines.append("🏆 Key achievements:")
            for a in notable_actions[-3:]:
                lines.append(f"  • {a['action'][:80]}")
            lines.append("")
        
        # Morning recommendation
        if patterns:
            worst = max(patterns, key=lambda p: {"high": 3, "medium": 2, "low": 1}.get(p['severity'], 0))
            lines.append(f"⚡ Dnes dávaj pozor na: {worst['name']} — {worst['recommendation'][:80]}")
            lines.append("")
        
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 5. CLI
# ──────────────────────────────────────────────

def main():
    loop = DreamLoop()
    
    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║  DREAM LOOP — Background Session Analysis Engine     ║")
    print("  ║  The agent dreams about its own sessions overnight   ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()
    
    result = loop.run()
    
    if result["status"] == "no_new_sessions":
        print("  📭 No new sessions since last dream run.")
        print("  🔄 Pre-warm cache refreshed.")
        print()
        return
    
    print(f"  📊 Analyzed: {result['sessions_analyzed']} sessions")
    print(f"  🔧 Tool calls: {result['total_tool_calls']}")
    print(f"  🧠 Patterns found: {result['patterns_found']}")
    print(f"  📚 Lessons consolidated: {result['lessons_consolidated']}")
    print(f"  🔄 Pre-warm cache: {'refreshed' if result['prewarm_refreshed'] else 'unchanged'}")
    print()
    
    if result.get("report"):
        print("  ── DREAM REPORT ──")
        print()
        for line in result["report"].split("\n"):
            print(f"  {line}")
        print()
    
    print(f"  ✅ Dream loop complete. State saved to ~/.hermes/.dream_state.json")
    print()


if __name__ == "__main__":
    main()
