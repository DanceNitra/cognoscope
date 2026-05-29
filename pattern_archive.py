#!/usr/bin/env python3
"""
pattern_archive.py — Push-Based Cross-Session Pattern Memory

INSIGHT (from Figueira's Mnemos):
  Failures must be FIRST-CLASS objects. Most memory layers store
  the conversation and trust retrieval to surface the right slice.
  None treat failure as a structured, pushable lesson.

Upgrade over v1:
  - correct() / add_lesson() — stores structured {context, mistake, cause, lesson}
  - get_lessons_for_prewarm() — formats last N lessons for pre-warm injection
  - Auto-deduplicate by mistake text
  - Still v1-compatible (record/predict/integrate_with_athena work)

Usage:
    from pattern_archive import PatternArchive
    arch = PatternArchive()
    arch.add_lesson(context="building X", mistake="forgot Y", 
                    cause="assumed Z", lesson="always check Z first")
    lessons = arch.get_lessons_for_prewarm(limit=5)
"""

import json, os, uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────
# 1. PATTERN RECORD (v1 compatible)
# ──────────────────────────────────────────────

@dataclass
class DegradationPattern:
    pattern_id: str
    name: str
    stage: str
    trigger_signals: list[str]
    intervention: str
    outcome: str
    effective_changes: dict
    times_seen: int = 1
    avg_recovery_turns: float = 0.0
    last_seen: str = ""
    
    def update(self, outcome: str, recovery_turns: int, changes: dict):
        self.times_seen += 1
        self.last_seen = datetime.now().isoformat()
        self.avg_recovery_turns = (
            (self.avg_recovery_turns * (self.times_seen - 1)) + recovery_turns
        ) / self.times_seen
        if changes:
            self.effective_changes = changes


# ──────────────────────────────────────────────
# 2. LESSON RECORD (NEW — failures as first-class)
# ──────────────────────────────────────────────

@dataclass
class LessonRecord:
    """
    A structured lesson learned from a mistake.
    
    Fields (matching Mnemos.correct() convention):
      context:  what were you doing?
      mistake:  what went wrong?
      cause:    why did it happen?
      lesson:   what should you do differently?
    """
    lesson_id: str
    session_id: str
    timestamp: str
    context: str
    mistake: str
    cause: str
    lesson: str
    category: str = "general"  # code / reasoning / tool / social / safety
    applied_count: int = 0     # how many times this lesson prevented recurrence
    
    def to_text(self) -> str:
        """Short, pre-warm ready format (~100 tokens)."""
        return (
            f"• {self.lesson[:120]} "
            f"(Context: {self.context[:60]})"
        )
    
    def to_full(self) -> str:
        """Full detail for reference."""
        return (
            f"Lesson: {self.lesson}\n"
            f"  Context: {self.context}\n"
            f"  Mistake: {self.mistake}\n"
            f"  Cause:   {self.cause}\n"
            f"  Applied: {self.applied_count}x"
        )


# ──────────────────────────────────────────────
# 3. PATTERN ARCHIVE (+ Lesson Store)
# ──────────────────────────────────────────────

class PatternArchive:
    """
    Cross-session memory for both degradation patterns AND lessons.
    
    Persists two stores:
      ~/.hermes/pattern_archive.json  — degradation patterns (v1)
      ~/.hermes/pattern_lessons.json  — structured lessons (NEW)
    """
    
    def __init__(self):
        self.path = os.path.expanduser("~/.hermes/pattern_archive.json")
        self.lessons_path = os.path.expanduser("~/.hermes/pattern_lessons.json")
        self.patterns: dict[str, DegradationPattern] = {}
        self.lessons: list[LessonRecord] = []
        self._load()
        self._load_lessons()
    
    # ── Patterns (v1) ──
    
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    raw = json.load(f)
                for pid, data in raw.items():
                    self.patterns[pid] = DegradationPattern(**data)
            except Exception:
                pass
    
    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            raw = {pid: dp.__dict__ for pid, dp in self.patterns.items()}
            json.dump(raw, f, indent=2, default=str)
    
    # ── Lessons (NEW) ──
    
    def _load_lessons(self):
        if os.path.exists(self.lessons_path):
            try:
                with open(self.lessons_path) as f:
                    raw = json.load(f)
                self.lessons = [LessonRecord(**r) for r in raw]
            except Exception:
                pass
    
    def _save_lessons(self):
        os.makedirs(os.path.dirname(self.lessons_path), exist_ok=True)
        with open(self.lessons_path, 'w') as f:
            raw = [l.__dict__ for l in self.lessons]
            json.dump(raw, f, indent=2, default=str)
    
    # ── PUSH MEMORY: LESSONS FOR PRE-WARM ──
    
    def add_lesson(
        self,
        context: str,
        mistake: str,
        cause: str,
        lesson: str,
        session_id: str = "current",
        category: str = "general",
    ) -> str:
        """
        Record a structured lesson (failure as first-class object).
        
        Auto-deduplicates: if same mistake text already exists,
        increments applied_count instead of creating a duplicate.
        
        Returns: lesson_id
        """
        now = datetime.now().isoformat()
        
        # Dedup: check for similar mistake
        for existing in self.lessons:
            # Jaccard-ish match on mistake text
            words_mistake = set(mistake.lower().split()[:10])
            words_existing = set(existing.mistake.lower().split()[:10])
            if words_mistake and words_existing:
                overlap = len(words_mistake & words_existing)
                smaller = min(len(words_mistake), len(words_existing))
                if smaller > 0 and overlap / smaller >= 0.5:
                    # Same lesson — just increment and update
                    existing.applied_count += 1
                    existing.lesson = lesson  # update with latest formulation
                    self._save_lessons()
                    return existing.lesson_id
        
        # New lesson
        lesson_id = f"LESSON_{len(self.lessons) + 1:04d}"
        record = LessonRecord(
            lesson_id=lesson_id,
            session_id=session_id,
            timestamp=now,
            context=context,
            mistake=mistake,
            cause=cause,
            lesson=lesson,
            category=category,
        )
        self.lessons.append(record)
        self._save_lessons()
        return lesson_id
    
    def get_lessons_for_prewarm(self, limit: int = 5, time_window_hours: int = 72) -> str:
        """
        Format recent lessons for pre-warm injection.
        
        Filter: only lessons from the last `time_window_hours`,
        sorted by applied_count descending (most relevant first).
        
        Returns: plain text block ready for system prompt injection.
        """
        now = datetime.now()
        cutoff = now - timedelta(hours=time_window_hours)
        
        # Filter & sort
        recent = []
        for l in self.lessons:
            try:
                ts = datetime.fromisoformat(l.timestamp)
                if ts >= cutoff:
                    recent.append(l)
            except Exception:
                recent.append(l)  # include if timestamp unparseable
        
        # Sort by most applied, then most recent
        recent.sort(key=lambda l: (-l.applied_count, l.timestamp or ""), reverse=False)
        recent = recent[:limit]
        
        if not recent:
            return ""
        
        lines = ["📚 Things I learned from mistakes (auto-pushed):"]
        for l in recent:
            lines.append(f"  {l.to_text()}")
        return "\n".join(lines)
    
    def mark_applied(self, lesson_id: str):
        """Manually increment a lesson's applied_count."""
        for l in self.lessons:
            if l.lesson_id == lesson_id:
                l.applied_count += 1
                self._save_lessons()
                return True
        return False
    
    # ── LEGACY: v1-compatible methods ──
    
    def record(self, name: str, stage: str, signals: list[str],
               intervention: str, outcome: str, changes: dict,
               recovery_turns: int = 0) -> str:
        now = datetime.now().isoformat()
        signal_set = set(signals)
        for pid, existing in self.patterns.items():
            ex_set = set(existing.trigger_signals)
            overlap = len(signal_set & ex_set)
            smaller = min(len(signal_set), len(ex_set))
            if smaller > 0 and overlap >= smaller * 0.5:
                existing.update(outcome, recovery_turns, changes)
                self._save()
                return pid
        pid = f"PAT_{len(self.patterns) + 1:04d}"
        self.patterns[pid] = DegradationPattern(
            pattern_id=pid, name=name, stage=stage,
            trigger_signals=signals, intervention=intervention,
            outcome=outcome, effective_changes=changes,
            avg_recovery_turns=recovery_turns, last_seen=now,
        )
        self._save()
        return pid
    
    def predict(self, current_signals: list[str],
                current_stage: str = None) -> dict | None:
        if not self.patterns:
            return None
        current_set = set(current_signals)
        best_match = None
        best_score = 0.0
        for pid, pattern in self.patterns.items():
            pattern_set = set(pattern.trigger_signals)
            intersection = len(current_set & pattern_set)
            union = len(current_set | pattern_set)
            if union == 0:
                continue
            similarity = intersection / union
            if current_stage and current_stage == pattern.stage:
                similarity += 0.2
            if pattern.times_seen >= 2:
                similarity += 0.1
            if similarity > best_score:
                best_score = similarity
                best_match = pattern
        if best_score >= 0.3:
            p = best_match
            return {
                'pattern_id': p.pattern_id,
                'pattern_name': p.name,
                'similarity': best_score,
                'predicted_stage': p.stage,
                'recommended_intervention': p.intervention,
                'preferred_changes': p.effective_changes,
                'times_seen': p.times_seen,
                'avg_recovery_turns': round(p.avg_recovery_turns, 1),
                'warning': f"Early signs match '{p.name}' (seen {p.times_seen}x, {p.outcome})"
            }
        return None
    
    def integrate_with_athena(self, current_signals: list[str],
                               current_stage: str = None) -> dict | None:
        prediction = self.predict(current_signals, current_stage)
        if not prediction:
            return None
        changes = prediction.get('preferred_changes', {})
        return {
            'prediction': prediction,
            'pre_config': changes,
            'action': 'pre_configure',
            'message': (
                f"Pattern archive matched '{prediction['pattern_name']}' "
                f"({prediction['similarity']:.0%} similarity). "
                f"Pre-configuring architecture to prevent recurrence."
            )
        }
    
    def report(self) -> str:
        lines = []
        if not self.patterns:
            lines.append("  No patterns archived yet.")
        else:
            lines.append("=== DEGRADATION PATTERNS ===")
            for pid in sorted(self.patterns.keys()):
                p = self.patterns[pid]
                sigs = ", ".join(p.trigger_signals[:3])
                chg = "; ".join(f"{k}: {v}" for k, v in p.effective_changes.items())
                lines.append(f"  {pid}: {p.name}")
                lines.append(f"    Stage: {p.stage} | Seen: {p.times_seen}x | "
                            f"Recovery: {p.avg_recovery_turns:.1f}t | {p.outcome}")
                lines.append(f"    Signals: {sigs}")
                lines.append(f"    Intervention: {p.intervention[:50]}")
                if chg:
                    lines.append(f"    Changes: {chg}")
        
        if self.lessons:
            lines.append("")
            lines.append("=== STRUCTURED LESSONS (failures as first-class) ===")
            for l in reversed(self.lessons[-5:]):
                lines.append(f"  {l.to_full()}")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 4. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║ PATTERN ARCHIVE — Push Lessons + Pre-Warm Engine    ║")
    print("  ║  Failures as first-class, pushable at session start ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    print("  INSIGHT (Figueira): 'Most memory layers store the")
    print("  conversation. None treat failure as a structured,")
    print("  pushable lesson.'")
    print()
    
    arch = PatternArchive()
    
    # ── Degradation patterns (v1 demo) ──
    print("─" * 50)
    print("  [1] Recording degradation patterns (v1)")
    print("─" * 50)
    pid1 = arch.record(
        name="Search Escalation Loop", stage="stage_3",
        signals=["MAX_RUN_8+", "FEEDBACK_DELAY", "ESCALATION"],
        intervention="navitoclax (verify_then_output, consec=1, temp=0.3)",
        outcome="recovered",
        changes={"reasoning_mode": "verify_then_output",
                 "max_consecutive_same_tool": 1, "temperature": 0.3},
        recovery_turns=3,
    )
    pid2 = arch.record(
        name="Tool Narrowing + Overconfidence", stage="stage_2",
        signals=["DIVERSITY_DROP", "PFC_FAILURE", "LOW_REFLECTION"],
        intervention="quercetin (reflection_first, consec=3, certainty=on)",
        outcome="recovered",
        changes={"reasoning_mode": "reflection_first",
                 "max_consecutive_same_tool": 3, "require_certainty_calibration": True},
        recovery_turns=5,
    )
    print(f"  Recorded: {pid1}, {pid2}")
    print()
    
    # ── Structured lessons (NEW) ──
    print("─" * 50)
    print("  [2] Structured lessons — failures as first-class")
    print("─" * 50)
    lid1 = arch.add_lesson(
        context="guardrail_bus.set_regime()",
        mistake="Called set_regime_factor() twice compounding the scaling",
        cause="Forgot factor multiplies CURRENT limits not defaults",
        lesson="Always call set_regime('low_vol') first to reset then set desired regime",
        category="code",
    )
    lid2 = arch.add_lesson(
        context="agent_evaluator.py synthetic env",
        mistake="Only 3 of 6 task types had tool mappings (verification/planning/debugging = 0)",
        cause="tools list didn't include verify_output, plan_strategy, debug_code",
        lesson="All 6 task types must have at least one matching tool for accurate fingerprints",
        category="code",
    )
    lid3 = arch.add_lesson(
        context="optimal_fingerprint.py detection",
        mistake="Used noise_std[0] for threshold comparison instead of SNR",
        cause="Copied threshold formula from climate attribution literally",
        lesson="Detection should use pure SNR (≥2.0 = detected, ≥1.0 = inconclusive)",
        category="reasoning",
    )
    print(f"  Recorded: {lid1}, {lid2}, {lid3}")
    print()
    
    # ── Apply a lesson (simulate "this prevented recurrence") ──
    print("─" * 50)
    print("  [3] Lesson applied (prevented recurrence)")
    print("─" * 50)
    arch.mark_applied(lid1)
    arch.mark_applied(lid1)  # Twice!
    print(f"  {lid1}: applied_count → 2 (prevented recurrence 2x)")
    print()
    
    # ── Push: lessons for pre-warm ──
    print("─" * 50)
    print("  [4] get_lessons_for_prewarm() — pushable block")
    print("─" * 50)
    print()
    block = arch.get_lessons_for_prewarm(limit=5)
    print(block if block else "  (no recent lessons)")
    print()
    
    # ── Integration with pre-warm ──
    print("─" * 50)
    print("  [5] Combined pre-warm (autobiography + lessons)")
    print("─" * 50)
    print()
    from autobiography import Autobiography
    bio = Autobiography(path="/tmp/test_autobiography_combined.md")
    bio.add_milestone("Push Memory Upgrade", "Autobiography now pushes into context")
    
    # Inject lessons into the session context
    prewarm = bio.generate_prewarm(session_context={
        "continuity": "Implement pattern_archive push upgrade",
    })
    # Append lessons block after the prewarm footer
    lessons_block = arch.get_lessons_for_prewarm(limit=3)
    if lessons_block:
        combined = prewarm.replace("═══ END PRE-WARMED MEMORY ═══",
                                    lessons_block + "\n\n═══ END PRE-WARMED MEMORY ═══")
        tokens = len(combined.split())
        print(combined)
        print(f"\n  Total tokens: ~{tokens}")
    else:
        print(prewarm)
    
    # Cleanup
    if os.path.exists("/tmp/test_autobiography_combined.md"):
        os.remove("/tmp/test_autobiography_combined.md")
    print()


if __name__ == '__main__':
    main()
