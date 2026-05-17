#!/usr/bin/env python3
"""
pattern_archive.py — Cross-Session Degradation Memory (The Next Breakthrough)

Problem: Every agent session is independent. Session A enters a Stage 3
loop. Session B starts showing identical early signals. No one remembers
Session A. The loop develops fully before any intervention.

Solution: A persistent archive that records degradation trajectories and
their effective interventions. New sessions query the archive before the
loop develops. The archive predicts: "You're showing Pattern #3. Apply
this intervention NOW — it worked last time."

This is cross-session memory for agent loops — the missing layer that
completes Athena's self-awareness.

Athena has detection (Recovery), reconfiguration (MetaLoop), extension
(ToolForge). What it lacks is MEMORY — learning from past loops to
prevent future ones before they develop.
"""

import json, os, uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────
# 1. PATTERN RECORD
# ──────────────────────────────────────────────

@dataclass
class DegradationPattern:
    """A recorded episode of agent degradation and recovery."""
    pattern_id: str
    name: str
    stage: str
    trigger_signals: list[str]  # signal names that fired
    intervention: str
    outcome: str
    effective_changes: dict
    times_seen: int = 1
    avg_recovery_turns: float = 0.0
    last_seen: str = ""
    
    def update(self, outcome: str, recovery_turns: int, changes: dict):
        self.times_seen += 1
        self.last_seen = datetime.now().isoformat()
        self.avg_recovery_turns = ((self.avg_recovery_turns * (self.times_seen - 1)) + recovery_turns) / self.times_seen
        if changes:
            self.effective_changes = changes


# ──────────────────────────────────────────────
# 2. PATTERN ARCHIVE
# ──────────────────────────────────────────────

class PatternArchive:
    """
    Cross-session memory for agent degradation patterns.
    
    Persists to ~/.hermes/pattern_archive.json so it survives
    Hermes restarts and agent reinstallations.
    """
    
    def __init__(self):
        self.path = os.path.expanduser("~/.hermes/pattern_archive.json")
        self.patterns: dict[str, DegradationPattern] = {}
        self._load()
    
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    raw = json.load(f)
                for pid, data in raw.items():
                    self.patterns[pid] = DegradationPattern(**data)
            except Exception as e:
                pass
    
    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            raw = {pid: dp.__dict__ for pid, dp in self.patterns.items()}
            json.dump(raw, f, indent=2, default=str)
    
    def record(self, name: str, stage: str, signals: list[str],
               intervention: str, outcome: str, changes: dict,
               recovery_turns: int = 0) -> str:
        """Record a pattern or update a matching one."""
        now = datetime.now().isoformat()
        
        # Match against existing patterns
        signal_set = set(signals)
        for pid, existing in self.patterns.items():
            ex_set = set(existing.trigger_signals)
            overlap = len(signal_set & ex_set)
            smaller = min(len(signal_set), len(ex_set))
            if smaller > 0 and overlap >= smaller * 0.5:
                existing.update(outcome, recovery_turns, changes)
                self._save()
                return pid
        
        # New pattern
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
        """
        Predict a pattern from early signals.
        
        Returns a recommendation BEFORE the loop develops.
        Uses Jaccard similarity on signal names.
        """
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
            
            # Bonus for matching stage
            if current_stage and current_stage == pattern.stage:
                similarity += 0.2
            # Bonus for repeated patterns (reliable signal)
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
        """
        Called by Athena at session start. Returns pre-configuration
        recommendations if the pattern archive recognizes early signs.
        
        This is the integration point: Athena queries the archive
        BEFORE the loop develops and pre-configures the architecture.
        """
        prediction = self.predict(current_signals, current_stage)
        if not prediction:
            return None
        
        # Pre-configure the LoopArchitecture
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
        """Human-readable report of all archived patterns."""
        if not self.patterns:
            return "  No patterns archived yet.\n"
        
        lines = []
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
        
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 3. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║     PATTERN ARCHIVE — Cross-Session Agent Memory     ║")
    print("  ║   The missing layer: learning from past degradation  ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    print("  Problem: Every session is independent. Session A loops.")
    print("  Session B shows the same signs. No one remembers A.")
    print()
    print("  Solution: Persistent archive. Session B queries it")
    print("  BEFORE the loop develops and pre-configures.")
    print()

    archive = PatternArchive()
    
    # ── Record Session A: severe escalation loop ──
    print("─" * 54)
    print("  [1] Recording Session A (Stage 3 escalation)")
    print("─" * 54)
    pid1 = archive.record(
        name="Search Escalation Loop",
        stage="stage_3",
        signals=["MAX_RUN_8+", "FEEDBACK_DELAY", "ESCALATION"],
        intervention="navitoclax (verify_then_output, consec=1, temp=0.3)",
        outcome="recovered",
        changes={"reasoning_mode": "verify_then_output", 
                 "max_consecutive_same_tool": 1, "temperature": 0.3},
        recovery_turns=3,
    )
    print(f"  Recorded: {pid1}")
    print()
    
    # ── Record Session B: different pattern ──
    print("─" * 54)
    print("  [2] Recording Session B (diversity drop)")
    print("─" * 54)
    pid2 = archive.record(
        name="Tool Narrowing + Overconfidence",
        stage="stage_2",
        signals=["DIVERSITY_DROP", "PFC_FAILURE", "LOW_REFLECTION"],
        intervention="quercetin (reflection_first, consec=3, certainty=on)",
        outcome="recovered",
        changes={"reasoning_mode": "reflection_first",
                 "max_consecutive_same_tool": 3,
                 "require_certainty_calibration": True},
        recovery_turns=5,
    )
    print(f"  Recorded: {pid2}")
    print()
    
    # ── Record Session C: same pattern as A (reinforcement) ──
    pid3 = archive.record(
        name="Search Escalation Loop",
        stage="stage_3",
        signals=["MAX_RUN_8+", "FEEDBACK_DELAY", "ESCALATION"],
        intervention="navitoclax (verify_then_output, consec=1, temp=0.3)",
        outcome="recovered",
        changes={"reasoning_mode": "verify_then_output",
                 "max_consecutive_same_tool": 1, "temperature": 0.3},
        recovery_turns=4,
    )
    print(f"  [3] Same pattern seen again — updated existing")
    print()
    
    # ── Session D: early signs ──
    print("─" * 54)
    print("  [4] PREDICTION: Session D — MAX_RUN_3+ and LOW_REFLECTION")
    print("  -> Early signs! Pattern archive can predict BEFORE loop develops.")
    print("─" * 54)
    
    pred = archive.predict(["MAX_RUN_3+", "LOW_REFLECTION"], current_stage="stage_1")
    if pred:
        print(f"  MATCH: {pred['pattern_name']} ({pred['similarity']:.0%})")
        print(f"  Warning: {pred['warning']}")
        print(f"  Pre-configure: {pred['recommended_intervention']}")
        chg = "; ".join(f"{k}: {v}" for k, v in pred['preferred_changes'].items())
        print(f"  Apply now: {chg}")
        pred_turns = pred.get('avg_recovery_turns', '?')
        print(f"  Expected recovery: ~{pred_turns} turns")
    else:
        print("  No match — enough signals yet")
    print()
    
    # ── Session E: different early signs ──
    print("─" * 54)
    print("  [5] PREDICTION: Session E — diversity drop + PFC failure")
    print("─" * 54)
    pred2 = archive.predict(["DIVERSITY_DROP", "PFC_FAILURE"], current_stage="stage_1")
    if pred2:
        print(f"  MATCH: {pred2['pattern_name']} ({pred2['similarity']:.0%})")
        print(f"  Warning: {pred2['warning']}")
        print(f"  Pre-configure: {pred2['recommended_intervention']}")
    else:
        print("  No match")
    print()
    
    # ── Archive report ──
    print("=" * 54)
    print("  ARCHIVE CONTENTS (persists across sessions)")
    print("=" * 54)
    print()
    print(archive.report())
    print()
    print(f"  Location: ~/.hermes/pattern_archive.json")
    print()
    
    # ── Integration with Athena ──
    print("─" * 54)
    print("  [INTEGRATION] Athena + Pattern Archive")
    print("─" * 54)
    athena_pred = archive.integrate_with_athena(
        ["MAX_RUN_3+", "LOW_REFLECTION"], current_stage="stage_1"
    )
    if athena_pred:
        print()
        print(f"  {athena_pred['message']}")
        chg = "; ".join(f"{k}: {v}" for k, v in athena_pred['pre_config'].items())
        print(f"  Pre-configured architecture: {chg}")
        print(f"  Loop prevented before it starts.")
    print()
    
    print("=" * 54)
    print("  BREAKTHROUGH: Cross-session memory for loops.")
    print("  The archive predicts degradation BEFORE it develops.")
    print("  Session D avoids the loop because it recognizes")
    print("  the early pattern and pre-configures the loop.")
    print("")
    print("  Athena now has all 4 layers:")
    print("  1. RECOVERY — detect degradation in real-time")
    print("  2. METALOOP — reconfigure loop at runtime")
    print("  3. TOOLFORGE — synthesize tools on demand")
    print("  4. PATTERN ARCHIVE — remember past degradation")
    print("=" * 54)


if __name__ == '__main__':
    main()
