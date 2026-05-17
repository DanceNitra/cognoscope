"""
hermes_pattern_hook.py — Pattern Archive Integration for Hermes Agent

Called at Hermes session startup. Queries the Pattern Archive for
matching degradation patterns and pre-configures the agent's
LoopArchitecture before the first reasoning turn.

If no pattern matches, does nothing (graceful cold start).

Installation:
  Copy to ~/.hermes/scripts/ or call from cron or session init.
  Add to Hermes session startup sequence in config.

Usage:
  from hermes_pattern_hook import PatternSessionHook
  hook = PatternSessionHook()
  recommendation = hook.startup_check(session_id="ses_abc123")
  if recommendation:
      # Apply pre-configuration
      print(recommendation['message'])
"""

import json, os, sys

# Add cognoscope to path for PatternArchive import
sys.path.insert(0, os.path.expanduser("~/cognoscope"))

try:
    from pattern_archive import PatternArchive
    ARCHIVE_AVAILABLE = True
except ImportError:
    ARCHIVE_AVAILABLE = False

# Simple detection for signals from raw event data
# In production, this would use the actual Recovery classifier
def extract_signals_from_events(events: list[dict]) -> list[str]:
    """Extract Recovery signal names from agent events."""
    signals = []
    
    tool_names = []
    tool_calls = 0
    reflections = 0
    
    for e in events:
        if e.get('type') == 'tool_call' and e.get('tool'):
            tool_names.append(e['tool'])
            tool_calls += 1
        if e.get('type') == 'reasoning':
            reflections += 1
    
    if len(tool_names) < 3:
        return signals
    
    # Consecutive run
    max_run = 1
    cur = 1
    for i in range(1, len(tool_names)):
        if tool_names[i] == tool_names[i-1]:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 1
    
    if max_run >= 13: signals.append("MAX_RUN_13+")
    elif max_run >= 8: signals.append("MAX_RUN_8+")
    elif max_run >= 5: signals.append("MAX_RUN_5+")
    elif max_run >= 3: signals.append("MAX_RUN_3+")
    
    ratio = reflections / max(tool_calls, 1)
    if ratio < 0.1 and tool_calls >= 10: signals.append("FEEDBACK_DELAY")
    elif ratio < 0.2 and tool_calls >= 5: signals.append("LOW_REFLECTION")
    
    return signals


class PatternSessionHook:
    """
    Hermes session startup hook. Queries the Pattern Archive
    and returns a pre-configuration recommendation.
    """
    
    def __init__(self, archive_path: str | None = None):
        self.archive = PatternArchive() if ARCHIVE_AVAILABLE else None
        self.history_file = os.path.expanduser(
            archive_path or "~/.hermes/pattern_archive.json")
    
    def startup_check(self, session_id: str = "",
                       recent_events: list[dict] | None = None,
                       session_type: str = "cli") -> dict | None:
        """
        Called when a Hermes session starts.
        
        Args:
            session_id: Current Hermes session ID
            recent_events: Events from the last few turns (or empty for new sessions)
            session_type: 'cli', 'cron', 'gateway', etc.
        
        Returns:
            dict with pre-configuration recommendation, or None
        """
        if not self.archive:
            return {
                'status': 'unavailable',
                'message': 'Pattern archive not available',
            }
        
        # For brand-new sessions, use session type as weak signal
        if not recent_events or len(recent_events) < 3:
            return self._cold_start_check(session_type)
        
        # Extract signals from recent events
        signals = extract_signals_from_events(recent_events)
        if not signals:
            return {
                'status': 'no_signals',
                'message': 'Not enough signal data yet — will check again soon',
            }
        
        # Query the archive
        prediction = self.archive.predict(signals)
        if not prediction:
            return {
                'status': 'no_match',
                'signals': signals,
                'message': f'Signals detected: {signals}. No matching pattern in archive.',
            }
        
        # Return pre-configuration recommendation
        return {
            'status': 'prediction',
            'pattern_id': prediction['pattern_id'],
            'pattern_name': prediction['pattern_name'],
            'similarity': prediction['similarity'],
            'expected_stage': prediction['predicted_stage'],
            'recommended_intervention': prediction['recommended_intervention'],
            'preferred_changes': prediction.get('preferred_changes', {}),
            'expected_recovery_turns': prediction.get('avg_recovery_turns', 0),
            'message': (
                f"Pattern archive matched '{prediction['pattern_name']}' "
                f"({prediction['similarity']:.0%} similarity). "
                f"Pre-configuring: {prediction['recommended_intervention']}"
            ),
        }
    
    def _cold_start_check(self, session_type: str) -> dict:
        """
        Cold start check: no prior events to analyze.
        For cron jobs and known repetitive tasks, seed a weak check.
        """
        # Cron patterns are often repetitive — seed weak check
        if session_type == 'cron':
            return {
                'status': 'cold_start_cron',
                'message': 'Cron session started. No prior events yet — monitoring.',
            }
        
        return {
            'status': 'cold_start',
            'message': 'New session, no events to analyze yet.',
        }
    
    def record_outcome(self, session_id: str, events: list[dict],
                        outcome: str, recovery_turns: int = 0):
        """
        Called at session end to record the outcome.
        Updates the Pattern Archive with what happened.
        """
        if not self.archive:
            return
        
        signals = extract_signals_from_events(events)
        if not signals:
            return
        
        # In production, this would extract intervention from session config
        self.archive.record(
            name=f"Auto-recorded pattern from {session_id}",
            stage="stage_2",  # Inferred from signals
            signals=signals,
            intervention="auto (pattern archive recommendation)",
            outcome=outcome,
            changes={},
            recovery_turns=recovery_turns,
        )


# ──────────────────────────────────────────────
# CLI DEMO
# ──────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  PATTERN ARCHIVE — Hermes Integration Hook")
    print("=" * 60)
    print()
    
    hook = PatternSessionHook()
    
    # Simulate cold start
    print("  [1] Cold start (new session, no events)")
    result = hook.startup_check(session_id="ses_new_001", session_type="cli")
    print(f"      {result['message']}")
    print()
    
    # Simulate session with early signals
    print("  [2] Session with early signals (MAX_RUN_3+, LOW_REFLECTION)")
    events = [
        {"type": "tool_call", "tool": "search"}, {"type": "tool_result", "tool": "search"},
        {"type": "tool_call", "tool": "search"}, {"type": "tool_result", "tool": "search"},
        {"type": "tool_call", "tool": "search"}, {"type": "tool_result", "tool": "search"},
        {"type": "tool_call", "tool": "search"}, {"type": "tool_result", "tool": "search"},
        {"type": "tool_call", "tool": "search"}, {"type": "tool_result", "tool": "search"},
    ]
    result = hook.startup_check(session_id="ses_existing_002", recent_events=events)
    
    if result['status'] == 'prediction':
        print(f"      MATCH: {result['pattern_name']} ({result['similarity']:.0%})")
        print(f"      Pre-configure: {result['recommended_intervention']}")
        for k, v in result.get('preferred_changes', {}).items():
            print(f"        {k}: {v}")
    else:
        print(f"      {result['message']}")
    print()
    
    print("=" * 60)
    print("  Integration with Hermes session lifecycle:")
    print()
    print("  1. Session starts → hook.startup_check()")
    print("  2. If match → pre-configure LoopArchitecture")
    print("  3. Session runs (with Athena layers 1-3)")
    print("  4. Session ends → hook.record_outcome()")
    print("  5. Archive updated → next session gets better predictions")
    print("=" * 60)
