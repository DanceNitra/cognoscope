#!/usr/bin/env python3
"""
msr_guardrail.py — Market Stability Reserve for Guardrails (Layer 10)

The EU ETS Market Stability Reserve (MSR) monitors the surplus of emission allowances
and automatically adjusts supply to maintain the market in a Goldilocks zone —
not too many allowances (price collapse), not too few (price spike).

The guardrail analog: an agent's guardrail system has a "surplus of capacity" when
guardrails are hit too rarely (agent is under-constrained, free to operate without
checks) and a "deficit" when guardrails are hit too frequently (agent is over-constrained,
cannot operate effectively).

This module monitors the distribution of guardrail encounters over a sliding window
and adjusts guardrail sensitivity parameters to maintain the system in equilibrium.

Architecture position — Athena stack:
  Agent behavior → Guardrails (Layers 1-9) → MSR (Layer 10) → adjusts guardrail params
  MetaLoop mutates LOOP parameters (reasoning, tools).
  MSR mutates GUARDRAIL parameters (sensitivity, thresholds, escalation).
"""

import time
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable
from collections import deque
from enum import Enum


# ──────────────────────────────────────────────
# 1. MSR STATE
# ──────────────────────────────────────────────

class MSRPhase(Enum):
    """Current phase of the market stability reserve."""
    NEUTRAL = "neutral"               # Surplus in Goldilocks zone — no action
    ABSORPTION = "absorption"          # Surplus too high — tightening guardrail sensitivity
    RELEASE = "release"                # Surplus too low — loosening guardrail sensitivity
    DRIFT_DETECTED = "drift_detected"  # Monotonic trend detected — escalate

@dataclass
class MSRConfig:
    """
    Parameters controlling the MSR behavior.

    Analogous to EU ETS MSR parameters:
    - Total Allowances in Circulation (TNAC) → guardrail encounter rate
    - Absorption threshold (833M) → upper_encounter_rate_threshold
    - Release threshold (400M) → lower_encounter_rate_threshold
    - Absorption rate (24%) → sensitivity_adjustment_rate
    """
    # Window parameters
    window_size: int = 50                     # Number of guardrail encounters to track
    min_window_fill: float = 0.3              # Min fraction of window filled before acting

    # Thresholds (analogous to 833M / 400M in EU ETS MSR)
    # guardrail_encounter_rate = hits / total_actions in the window
    upper_encounter_rate: float = 0.40        # Above this = too many guardrails (surplus LOW)
    lower_encounter_rate: float = 0.05        # Below this = too few guardrails (surplus HIGH)
    drift_threshold: float = 0.015            # Per-observation drift rate that triggers escalation

    # Adjustment parameters (analogous to 24% absorption rate)
    sensitivity_adjustment_rate: float = 0.15  # How much to tighten/loosen per adjustment
    max_tightening: float = 0.65               # Max we can tighten guardrail sensitivity
    min_loosening: float = 0.85               # Min we can loosen (max loosening is 1.0)

    # Timing
    min_observations_before_absorb: int = 3    # Must observe surplus N times before acting
    cooldown_turns: int = 5                    # Min turns between MSR actions

    # Escalation
    escalate_after_consecutive_drift: int = 3  # Alert user after N drift detections in a row

@dataclass
class GuardrailEvent:
    """An event representing a guardrail encounter."""
    guardrail_layer: int     # 1-9 which layer triggered
    action_type: str         # e.g., 'blocked', 'confirmed', 'flagged', 'escalated'
    tool_name: str           # Which tool triggered the guardrail
    timestamp: float = field(default_factory=time.time)
    turn_number: int = 0
    severity: float = 1.0    # 0.0 (check passed) to 1.0 (hard block)

@dataclass
class MSRAction:
    """
    An action the MSR recommends to the guardrail system.

    The action is always a RELATIVE adjustment — the MSR does not set
    absolute guardrail parameters but provides a direction and magnitude
    for adjustment from the current values.
    """
    phase: MSRPhase
    adjustment_direction: str     # 'tighten' | 'loosen' | 'none'
    adjustment_factor: float      # 0.0-1.0 how much to adjust
    target_layers: list[int]      # Which guardrail layers to adjust
    reason: str
    escalate: bool = False
    drift_metric: float | None = None


# ──────────────────────────────────────────────
# 2. THE MSR ENGINE
# ──────────────────────────────────────────────

class MarketStabilityReserve:
    """
    The MSR engine monitors guardrail encounters and recommends adjustments.

    Usage:
        msr = MarketStabilityReserve()
        msr.record_guardrail_hit(GuardrailEvent(...))
        msr.record_action(action_type='tool_call', tool='read_file')  # total actions
        action = msr.evaluate()  # Returns MSRAction or None
    """

    def __init__(self, **kwargs):
        # Accept either a config object or keyword arguments
        if 'config' in kwargs:
            self.config = kwargs['config']
        else:
            # Build config from matching keyword args
            config_fields = {
                k: v for k, v in kwargs.items()
                if k in MSRConfig.__dataclass_fields__
            }
            self.config = MSRConfig(**config_fields)

        # Rolling window: tracks the last N guardrail events
        self.guardrail_window: deque[GuardrailEvent] = deque(maxlen=self.config.window_size)

        # Total actions in the same window (guardrails + non-guardrail actions)
        self.action_count: int = 0
        self.last_clear_turn: int = 0

        # Adjustment state
        self.observations_since_last_action: int = 0
        self.last_action_turn: int = -self.config.cooldown_turns
        self.consecutive_drift_count: int = 0
        self.total_adjustments: int = 0

        # History for analysis
        self.action_history: list[dict] = []

        # Current guardrail sensitivity multipliers (1.0 = default)
        # MSR adjusts these relative to their default values
        self.sensitivity: dict[int, float] = {
            layer: 1.0 for layer in range(1, 10)
        }

    def record_guardrail_hit(self, event: GuardrailEvent):
        """Record a guardrail hit event."""
        self.guardrail_window.append(event)

    def record_action(self, action_type: str = 'tool_call', tool: str | None = None):
        """Record any agent action (guardrail or not) for rate calculation."""
        self.action_count += 1

    def total_actions_in_window(self) -> int:
        """Count total actions (guardrail + non-guardrail) in the current window."""
        return self.action_count

    def guardrail_encounter_rate(self) -> float | None:
        """
        Compute the guardrail encounter rate:
          hits in window / total actions in window

        Returns None if too few observations for a reliable rate.
        """
        guardrail_hits = len(self.guardrail_window)
        total = self.total_actions_in_window()

        window_fill = guardrail_hits / max(self.config.window_size, 1)
        if window_fill < self.config.min_window_fill:
            return None

        if total == 0:
            return None

        return guardrail_hits / total

    def _compute_window_drift(self) -> float | None:
        """
        Detect monotonic drift in the guardrail encounter rate.

        Divides the guardrail events into two halves by action index,
        and computes the encounter rate difference between them.

        Returns None if too few observations.
        """
        events = list(self.guardrail_window)
        if len(events) < 4:
            return None

        mid = len(events) // 2
        first_half = events[:mid]
        second_half = events[mid:]

        # Approximate the encounter rate by computing what fraction
        # of total actions the guardrail events in each half span.
        # If events are tightly clustered in the second half of the
        # action timeline, drift is positive.
        first_actions = len(first_half)
        second_actions = len(second_half)
        total = first_actions + second_actions
        if total == 0:
            return None

        # Rate within each segment: events / segment span
        # Since the window is deque maxlen = window_size, the first half has
        # ~mid events and the second half has ~total-mid events.
        # The rate comparison uses: first events vs second events.
        drift = (second_actions - first_actions) / max(total, 1)
        return drift

    def evaluate(self) -> MSRAction | None:
        """
        Evaluate the current state and return an MSRAction if adjustment is needed.

        Returns None if no action required.
        """
        rate = self.guardrail_encounter_rate()
        if rate is None:
            return None

        self.observations_since_last_action += 1

        # Check cooldown
        if self.observations_since_last_action < self.config.min_observations_before_absorb:
            return None

        # ── Case 1: Surplus HIGH (guardrails hit too rarely) → ABSORPTION ──
        # Agent is under-constrained. Tighten guardrail sensitivity.
        if rate < self.config.lower_encounter_rate:
            self.observations_since_last_action = 0
            self.consecutive_drift_count = 0

            # How far below the threshold? Controls magnitude
            deficit_ratio = (self.config.lower_encounter_rate - rate) / self.config.lower_encounter_rate
            adjustment = min(deficit_ratio, self.config.sensitivity_adjustment_rate)

            action = MSRAction(
                phase=MSRPhase.ABSORPTION,
                adjustment_direction='tighten',
                adjustment_factor=adjustment,
                target_layers=list(range(1, 10)),
                reason=f"Guardrail encounter rate {rate:.2%} below lower threshold "
                       f"{self.config.lower_encounter_rate:.0%}. Tightening guardrail sensitivity.",
            )
            self._apply(action)
            return action

        # ── Case 2: Surplus LOW (guardrails hit too often) → RELEASE ──
        # Agent is over-constrained. Loosen guardrail sensitivity.
        if rate > self.config.upper_encounter_rate:
            self.observations_since_last_action = 0
            self.consecutive_drift_count = 0

            excess_ratio = (rate - self.config.upper_encounter_rate) / rate
            adjustment = min(excess_ratio, self.config.sensitivity_adjustment_rate)

            action = MSRAction(
                phase=MSRPhase.RELEASE,
                adjustment_direction='loosen',
                adjustment_factor=adjustment,
                target_layers=list(range(1, 10)),
                reason=f"Guardrail encounter rate {rate:.2%} above upper threshold "
                       f"{self.config.upper_encounter_rate:.0%}. Loosening guardrail sensitivity.",
            )
            self._apply(action)
            return action

        # ── Case 3: In Goldilocks zone — check for drift ──
        # Even if the overall rate is acceptable, if it's trending, we should escalate.
        drift = self._compute_window_drift()
        if drift is not None and abs(drift) > self.config.drift_threshold:
            self.consecutive_drift_count += 1

            if self.consecutive_drift_count >= self.config.escalate_after_consecutive_drift:
                self.consecutive_drift_count = 0
                action = MSRAction(
                    phase=MSRPhase.DRIFT_DETECTED,
                    adjustment_direction='none',
                    adjustment_factor=0.0,
                    target_layers=[],  # No auto-adjustment — escalate
                    reason=f"Monotonic drift detected in guardrail encounter rate: {drift:+.3f} "
                           f"over {self.consecutive_drift_count} consecutive observations. "
                           f"Rate is within bounds ({rate:.2%}) but trending.",
                    escalate=True,
                    drift_metric=drift,
                )
                self._apply(action)
                return action

        return None

    def _apply(self, action: MSRAction):
        """Apply the MSR action to internal state and log it."""
        self.last_action_turn = self.action_count
        self.total_adjustments += 1

        for layer in action.target_layers:
            if action.adjustment_direction == 'tighten':
                self.sensitivity[layer] = max(
                    self.config.max_tightening,
                    self.sensitivity[layer] - action.adjustment_factor
                )
            elif action.adjustment_direction == 'loosen':
                self.sensitivity[layer] = min(
                    self.config.min_loosening,
                    self.sensitivity[layer] + action.adjustment_factor
                )

        self.action_history.append({
            "turn": self.action_count,
            "phase": action.phase.value,
            "direction": action.adjustment_direction,
            "factor": action.adjustment_factor,
            "escalated": action.escalate,
            "sensitivity_after": dict(self.sensitivity),
            "reason": action.reason,
        })

    # ──────────────────────────────────────────────
    # 3. REPORTING
    # ──────────────────────────────────────────────

    def status_report(self) -> dict:
        """Return current MSR state for logging and display."""
        rate = self.guardrail_encounter_rate()
        return {
            "phase": MSRPhase.NEUTRAL.value,
            "guardrail_encounter_rate": rate,
            "window_size": len(self.guardrail_window),
            "total_actions": self.action_count,
            "lower_threshold": self.config.lower_encounter_rate,
            "upper_threshold": self.config.upper_encounter_rate,
            "in_goldilocks": (rate is not None
                              and self.config.lower_encounter_rate <= rate <= self.config.upper_encounter_rate),
            "total_adjustments": self.total_adjustments,
            "adjustments_history": self.action_history[-5:] if self.action_history else [],
            "current_sensitivity": dict(self.sensitivity),
        }

    def get_sensitivity_multipliers(self) -> dict[int, float]:
        """
        Return current sensitivity multipliers for all guardrail layers.

        A multiplier of 0.7 means guardrail threshold tightened by 30%.
        A multiplier of 1.15 means guardrail threshold loosened by 15%.

        Integration: the calling code multiplies its guardrail thresholds
        by these values before checking them.
        """
        return dict(self.sensitivity)

    def to_json(self) -> str:
        return json.dumps({
            "sensitivity": self.sensitivity,
            "total_adjustments": self.total_adjustments,
            "action_history": self.action_history[-10:],
            "window_size": len(self.guardrail_window),
            "total_actions": self.action_count,
        }, indent=2)


# ──────────────────────────────────────────────
# 4. INTEGRATION STUB — Athena hook
# ──────────────────────────────────────────────

def create_msr_integration(athena_instance) -> Callable:
    """
    Factory: returns an MSR integration function for an Athena instance.

    The returned function should be called after every guardrail check:

    Usage:
        msr_hook = create_msr_integration(athena)
        # ... in athena's loop after guardrail check ...
        msr_action = msr_hook(turn, tool, guardrail_result)
        if msr_action and msr_action.escalate:
            # Alert user about drift
            log(f"[MSR] ESCALATION: {msr_action.reason}")
    """
    msr = MarketStabilityReserve()

    def msr_hook(
        turn: int,
        tool: str | None = None,
        guardrail_hit: GuardrailEvent | None = None,
        guardrail_layers: list[int] | None = None,
    ) -> MSRAction | None:
        """
        Called after each guardrail check.

        Args:
            turn: Current turn number
            tool: Tool name that was checked
            guardrail_hit: If a guardrail was triggered, the event
            guardrail_layers: Which layers are active in this system

        Returns:
            MSRAction if adjustment is needed, None otherwise
        """
        msr.record_action(tool=tool)

        if guardrail_hit:
            msr.record_guardrail_hit(guardrail_hit)

        return msr.evaluate()

    # Attach the msr instance for inspection
    msr_hook.msr = msr
    msr_hook.status = lambda: msr.status_report()
    msr_hook.multipliers = lambda: msr.get_sensitivity_multipliers()

    return msr_hook


# ──────────────────────────────────────────────
# 5. DEMO
# ──────────────────────────────────────────────

def main():
    """Run a demonstration showing the MSR in action."""
    import random

    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║   MSR — Market Stability Reserve for Guardrails (Layer 10)  ║")
    print("  ║  Guardrail-on-guardrail: auto-adjusting sensitivity system   ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()

    msr = MarketStabilityReserve()

    # Simulate a session with three phases:
    # Phase 1: Agent is under-constrained (guardrail hits ~2%) → MSR tightens
    # Phase 2: Agent is over-constrained (guardrail hits ~55%) → MSR loosens
    # Phase 3: Drift detection — rate within bounds but trending up → escalate

    print("─" * 56)
    print("  Phase 1: Under-constrained agent (hit rate well below threshold)")
    print("  MSR should detect surplus and TIGHTEN")
    print("─" * 56)
    print()

    msr = MarketStabilityReserve(window_size=30, min_window_fill=0.2,
                                  lower_encounter_rate=0.25, min_observations_before_absorb=2)

    # Phase 1: 150 turns with hits at ~8% rate — below 25% threshold
    for turn in range(1, 151):
        msr.record_action(tool='search')
        if turn > 50 and turn % 12 == 0:  # ~8% hit rate
            msr.record_guardrail_hit(GuardrailEvent(
                guardrail_layer=4, action_type='blocked',
                tool_name='delete_file', turn_number=turn
            ))
        action = msr.evaluate()
        if action:
            print(f"  [t={turn:>3d}] {action.phase.value:>12s} → {action.adjustment_direction:>7s} "
                  f"(fac={action.adjustment_factor:.2f}): {action.reason[:80]}")

    rate1 = msr.guardrail_encounter_rate()
    print(f"\n  Hit rate: {rate1:.2%} | Sensitivity: L1={msr.sensitivity[1]:.2f} "
          f"L4={msr.sensitivity[4]:.2f} (tightened: {1-msr.sensitivity[4]:.0%})")
    print()

    # Phase 2: over-constrained demo
    print("─" * 56)
    print("  Phase 2: Over-constrained agent (hit rate above threshold)")
    print("  MSR should detect deficit and LOOSEN")
    print("─" * 56)
    print()

    msr2 = MarketStabilityReserve(window_size=24, min_window_fill=0.3,
                                   upper_encounter_rate=0.35, min_observations_before_absorb=2)

    for turn in range(1, 121):
        msr2.record_action(tool='browser')
        if turn % 2 == 0:  # 50% hit rate
            msr2.record_guardrail_hit(GuardrailEvent(
                guardrail_layer=1, action_type='flagged',
                tool_name='browser', turn_number=turn
            ))
        action = msr2.evaluate()
        if action:
            print(f"  [t={turn:>3d}] {action.phase.value:>12s} → {action.adjustment_direction:>7s} "
                  f"(fac={action.adjustment_factor:.2f}): {action.reason[:80]}")

    rate2 = msr2.guardrail_encounter_rate()
    print(f"\n  Hit rate: {rate2:.2%} | Sensitivity: L1={msr2.sensitivity[1]:.2f} "
          f"(loosened: {msr2.sensitivity[1]-1:.0%})")
    print()

    # Phase 3: Drift detection — rate stays within bounds but trends up
    print("─" * 56)
    print("  Phase 3: Drift (rate stays within Goldilocks zone but trends)")
    print("  MSR should detect monotonic trend and ESCALATE")
    print("─" * 56)
    print()

    msr3 = MarketStabilityReserve(window_size=20, min_window_fill=0.3,
                                   lower_encounter_rate=0.10, upper_encounter_rate=0.50,
                                   drift_threshold=0.02, min_observations_before_absorb=3,
                                   escalate_after_consecutive_drift=2)

    for turn in range(1, 151):
        msr3.record_action(tool='terminal')
        # Gradual drift: probability starts at 0.18, ends at 0.45
        prob = 0.18 + (turn / 150) * 0.27
        if random.random() < prob:
            msr3.record_guardrail_hit(GuardrailEvent(
                guardrail_layer=6, action_type='blocked',
                tool_name='terminal', turn_number=turn
            ))
        action = msr3.evaluate()
        if action:
            print(f"  [t={turn:>3d}] {action.phase.value:>12s} → "
                  f"{action.adjustment_direction:>7s}"
                  f"{' ⚠ ESCALATE' if action.escalate else ''}: {action.reason[:75]}")

    s = msr3.status_report()
    print(f"\n  Final: rate={s['guardrail_encounter_rate']:.2%} "
          f"| drift_alerts={s['total_adjustments']}")


if __name__ == "__main__":
    main()
