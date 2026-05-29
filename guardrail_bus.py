#!/usr/bin/env python3
"""
guardrail_bus.py — Guardrail Integration Event Bus

Connects:
  - MSR (Layer 10 — Market Stability Reserve monitoring)
  - Immune (Layer 9 — Immune guardrail response)
  - Athena (agent runtime — executes guardrail decisions)

Event flow:
  Agent action → ImmuneGuardrail (fast check) → MSR (monitor encounter rate)
  → MSR adjusts sensitivity → Immune applies adjustment → Athena applies decision

Usage:
    from guardrail_bus import GuardrailBus
    bus = GuardrailBus()
    result = bus.check_action("terminal", {"consecutive": 5})
    # Returns: GuardrailDecision with PASS/WARN/REJECT/ESCALATE
"""

import os, sys, json, time
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


# Regime detection constants
REGIMES = {
    "low_vol": {"factor": 1.0, "description": "Normal market conditions"},
    "high_vol": {"factor": 0.5, "description": "VIX > 25 — tighten all limits"},
    "crisis": {"factor": 0.3, "description": "VIX > 35 — widest tolerance for drawdowns"},
}
DEFAULT_REGIME = "low_vol"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from msr_guardrail import (
    MarketStabilityReserve, MSRConfig, GuardrailEvent as MSREvent,
    MSRAction, create_msr_integration
)
from immune_guardrail import (
    ImmuneGuardrail, ImmuneDecision, GuardrailCheckResult,
    ImmuneGuardrailConfig, AdaptiveImmunity, GuardrailDomain
)


# ──────────────────────────────────────────────
# 1. SHARED DECISION MODEL
# ──────────────────────────────────────────────

class GuardrailAction(Enum):
    """Final action after all guardrail layers."""
    PASS = "pass"            # All clear
    WARN = "warn"            # Proceed with caution
    REDUCE = "reduce"        # Reduce activity (e.g., 50% position)
    BLOCK = "block"          # Block this specific action
    FREEZE = "freeze"        # Stop all actions, human review
    ESCALATE = "escalate"    # Alert human operator


@dataclass
class GuardrailDecision:
    """The combined decision from all guardrail layers."""
    action: GuardrailAction
    confidence: float          # 0.0-1.0 how certain the system is
    reason: str                # Human-readable explanation
    source_layer: int = 9      # Which layer triggered (9=immune, 10=MSR)
    turn_number: int = 0
    tool_name: str = ""
    immune_result: GuardrailCheckResult | None = None
    msr_action: MSRAction | None = None
    msr_multipliers: dict[int, float] | None = None

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "source_layer": self.source_layer,
            "turn": self.turn_number,
            "tool": self.tool_name,
            "immune": self.immune_result.to_dict() if self.immune_result else None,
            "msr": {
                "phase": self.msr_action.phase.value if self.msr_action else None,
                "direction": self.msr_action.adjustment_direction if self.msr_action else None,
                "factor": self.msr_action.adjustment_factor if self.msr_action else None,
                "multipliers": self.msr_multipliers,
            } if self.msr_action or self.msr_multipliers else None,
        }


# ──────────────────────────────────────────────
# 2. GUARDRAIL BUS
# ──────────────────────────────────────────────

@dataclass
class GuardrailBusConfig:
    """Configuration for the integration bus."""
    msr_window_size: int = 50
    msr_upper_rate: float = 0.40
    msr_lower_rate: float = 0.05
    immune_memory_size: int = 100
    verbose: bool = True
    log_path: str | None = None


class GuardrailBus:
    """
    Integration bus connecting all guardrail layers.

    Pipeline:
      1. ImmuneGuardrail.pre_trade_check() or check_tool_call()
         → fast pattern match + innate limits
      2. MSR records the guardrail event and monitors encounter rate
         → drift detection, surplus/deficit analysis
      3. Immune applies MSR sensitivity multipliers
         → tightens or loosens guardrail thresholds
      4. Combined decision returned to caller (Athena)

    The bus is the SINGLE entry point for all guardrail checks.
    No layer is accessed directly.
    """

    def __init__(
        self,
        config: GuardrailBusConfig | None = None,
        immune: ImmuneGuardrail | None = None,
        msr: MarketStabilityReserve | None = None,
    ):
        self.config = config or GuardrailBusConfig()

        # Layer 9 — Immune
        if immune is None:
            icfg = ImmuneGuardrailConfig(
                adaptive_memory_size=self.config.immune_memory_size,
                verbose=self.config.verbose,
            )
            self.immune = ImmuneGuardrail(config=icfg)
        else:
            self.immune = immune

        # Layer 10 — MSR
        if msr is None:
            self.msr = MarketStabilityReserve(
                window_size=self.config.msr_window_size,
                upper_encounter_rate=self.config.msr_upper_rate,
                lower_encounter_rate=self.config.msr_lower_rate,
            )
        else:
            self.msr = msr

        self.turn = 0
        self.decisions: list[GuardrailDecision] = []
        self._log: list[dict] = []
        self._current_regime: str = DEFAULT_REGIME

    # ── REGIME MANAGEMENT ──

    def set_regime(self, regime_name: str):
        """
        Set market regime and adjust all guardrail thresholds.

        Regime names: 'low_vol', 'high_vol', 'crisis'
        """
        if regime_name not in REGIMES:
            return
        self._current_regime = regime_name
        factor = REGIMES[regime_name]["factor"]
        self.immune.set_regime_factor(factor)
        if self.config.verbose:
            print(f"[GUARDRAIL] Regime: {regime_name} (factor={factor:.1f}) — "
                  f"{REGIMES[regime_name]['description']}")

    def get_regime(self) -> dict:
        """Return current regime info."""
        info = dict(REGIMES[self._current_regime])
        info["name"] = self._current_regime
        return info

    # ── MAIN ENTRY POINTS ──

    def check_trade(
        self,
        ticker: str,
        size_pct: float,
        nav: float,
        current_positions: dict[str, float],
        day_pnl: float = 0.0,
        peak_nav: float | None = None,
    ) -> GuardrailDecision:
        """
        Full guardrail check before a trade.
        Returns a GuardrailDecision after immune + MSR layers.
        """
        self.turn += 1

        # Step 1: Immune pre-trade check
        immune_result = self.immune.pre_trade_check(
            ticker, size_pct, nav, current_positions, day_pnl, peak_nav
        )

        # Step 2: Record to MSR
        if immune_result.decision in (ImmuneDecision.REJECT, ImmuneDecision.ESCALATE, ImmuneDecision.WARN):
            msr_event = MSREvent(
                guardrail_layer=immune_result.level,
                action_type=immune_result.decision.value,
                tool_name=ticker,
                turn_number=self.turn,
                severity=1.0 if immune_result.decision == ImmuneDecision.REJECT else 0.5,
            )
            self.msr.record_guardrail_hit(msr_event)
        self.msr.record_action(tool=ticker)

        # Step 3: Check MSR for guardrail system health
        msr_action = self.msr.evaluate()

        # Step 4: Get MSR sensitivity multipliers
        multipliers = self.msr.get_sensitivity_multipliers()

        # Step 5: Apply MSR adjustments to Immune
        if msr_action and msr_action.adjustment_direction == "tighten":
            # MSR says too few guardrails → tighten
            self.immune.set_regime_factor(
                max(0.5, 1.0 - msr_action.adjustment_factor)
            )
        elif msr_action and msr_action.adjustment_direction == "loosen":
            # MSR says too many guardrails → loosen
            self.immune.set_regime_factor(
                min(1.5, 1.0 + msr_action.adjustment_factor)
            )

        # Step 6: Combine into final decision
        decision = self._combine_decisions(
            immune_result, msr_action, multipliers
        )

        self.decisions.append(decision)
        if self.config.verbose and decision.action != GuardrailAction.PASS:
            print(f"[GUARDRAIL] t={self.turn} {decision.action.value.upper()}: "
                  f"{decision.reason[:60]}")

        return decision

    def check_tool(
        self,
        tool_name: str,
        consecutive_calls: int = 0,
        failures_in_window: int = 0,
    ) -> GuardrailDecision:
        """
        Check an agent tool call through all guardrail layers.
        """
        self.turn += 1

        # Step 1: Immune tool check
        immune_result = self.immune.check_tool_call(
            tool_name, consecutive_calls, failures_in_window
        )

        # Step 2: Record to MSR
        if immune_result.decision != ImmuneDecision.PASS:
            msr_event = MSREvent(
                guardrail_layer=immune_result.level,
                action_type=immune_result.decision.value,
                tool_name=tool_name,
                turn_number=self.turn,
                severity=1.0 if immune_result.decision == ImmuneDecision.REJECT else 0.5,
            )
            self.msr.record_guardrail_hit(msr_event)
        self.msr.record_action(tool=tool_name)

        # Step 3: MSR evaluation
        msr_action = self.msr.evaluate()
        multipliers = self.msr.get_sensitivity_multipliers()

        # Step 4: Combine
        decision = self._combine_decisions(
            immune_result, msr_action, multipliers
        )

        self.decisions.append(decision)
        return decision

    def record_guardrail_hit(
        self,
        tool_name: str,
        guardrail_layer: int,
        action_type: str,
        severity: float = 1.0,
    ):
        """Record an external guardrail hit into both immune and MSR."""
        self.immune.record_guardrail_hit(tool_name, guardrail_layer, action_type, severity)

        msr_event = MSREvent(
            guardrail_layer=guardrail_layer,
            action_type=action_type,
            tool_name=tool_name,
            turn_number=self.turn,
            severity=severity,
        )
        self.msr.record_guardrail_hit(msr_event)
        self.msr.record_action(tool=tool_name)

    # ── COMBINATION LOGIC ──

    def _combine_decisions(
        self,
        immune_result: GuardrailCheckResult,
        msr_action: MSRAction | None,
        multipliers: dict[int, float],
    ) -> GuardrailDecision:
        """Merge immune + MSR into a single GuardrailDecision."""

        # Map ImmuneDecision → GuardrailAction
        decision_map = {
            ImmuneDecision.PASS: GuardrailAction.PASS,
            ImmuneDecision.WARN: GuardrailAction.WARN,
            ImmuneDecision.REJECT: GuardrailAction.BLOCK,
            ImmuneDecision.ESCALATE: GuardrailAction.FREEZE,
        }
        base_action = decision_map.get(immune_result.decision, GuardrailAction.PASS)

        # MSR escalation overrides
        if msr_action and msr_action.escalate:
            base_action = GuardrailAction.ESCALATE

        # Reason
        reason = immune_result.message
        if msr_action:
            reason += f" | MSR: {msr_action.reason}"

        return GuardrailDecision(
            action=base_action,
            confidence=1.0 - immune_result.match_score if immune_result.match_score else 0.95,
            reason=reason,
            source_layer=10 if (msr_action and msr_action.escalate) else 9,
            turn_number=self.turn,
            tool_name=immune_result.tool_name,
            immune_result=immune_result,
            msr_action=msr_action,
            msr_multipliers=multipliers,
        )

    # ── STATUS ──

    def status_report(self) -> dict:
        """Combined status of the entire guardrail system."""
        immune_status = self.immune.status_report()
        msr_status = self.msr.status_report()

        action_counts = {}
        for d in self.decisions:
            action_counts[d.action.value] = action_counts.get(d.action.value, 0) + 1

        return {
            "total_checks": len(self.decisions),
            "action_counts": action_counts,
            "guardrail_encounter_rate": msr_status.get("guardrail_encounter_rate"),
            "msr_phase": msr_status.get("phase"),
            "immune_reject_rate": immune_status["reject_rate"],
            "regime_factor": immune_status["regime_factor"],
            "regime": self._current_regime,
            "adaptive_memory": immune_status["adaptive"]["total_memory"],
            "msr_adjustments": msr_status.get("total_adjustments"),
        }


# ──────────────────────────────────────────────
# 3. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║ Guardrail Bus — Integration Demo                       ║")
    print("  ║ Immune Guardrail (L9) + MSR (L10) + Athena             ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    bus = GuardrailBus(config=GuardrailBusConfig(verbose=False))
    nav = 100_000.0
    peak_nav = 105_000.0
    positions = {"AAPL": 0.08, "MSFT": 0.06, "NVDA": 0.05}

    # ── Scenario 1: Normal trades — all pass ──
    print("─" * 50)
    print("  [1] Normal trading — 5% position, no issues")
    print("─" * 50)
    for ticker in ["MSFT", "GOOGL", "AMZN"]:
        r = bus.check_trade(ticker, 0.05, nav, positions)
        print(f"  {ticker}: {r.action.value.upper():>7s} | {r.reason[:50]}")
    print()

    # ── Scenario 2: Position too large ──
    print("─" * 50)
    print("  [2] Oversized position — 25% of NAV")
    print("─" * 50)
    r = bus.check_trade("AAPL", 0.25, nav, positions)
    print(f"  Result: {r.action.value.upper()} | {r.reason}")
    print()

    # ── Scenario 3: Tool call storm (guardrail over-constrained) ──
    print("─" * 50)
    print("  [3] Tool call storm — 10 rapid guardrail hits on terminal")
    print("─" * 50)
    for i in range(10):
        bus.record_guardrail_hit("terminal", 4, "blocked", severity=1.0)
    r = bus.check_tool("terminal", failures_in_window=10)
    print(f"  After storm: {r.action.value.upper()} | {r.reason[:60]}")
    if r.msr_multipliers:
        print(f"  MSR multipliers: L4={r.msr_multipliers.get(4, 1.0):.2f}")
    print()

    # ── Scenario 4: Drawdown ──
    print("─" * 50)
    print("  [4] Drawdown — -19% from peak")
    print("─" * 50)
    r = bus.check_trade("TSLA", 0.05, 85000.0, positions, peak_nav=105000.0)
    print(f"  Result: {r.action.value.upper()} | {r.reason}")
    print()

    # ── Scenario 5: MSR drift detection ──
    print("─" * 50)
    print("  [5] MSR drift — consistently low guardrail hits")
    print("─" * 50)
    # Simulate many passes with no guardrails (under-constrained)
    for i in range(60):
        bus.check_trade(f"TICK{i}", 0.05, nav, positions)
    print()

    # ── Status ──
    print("─" * 50)
    print("  GUARDRAIL SYSTEM STATUS")
    print("─" * 50)
    s = bus.status_report()
    print(f"  Total checks:    {s['total_checks']}")
    print(f"  Action counts:   {s['action_counts']}")
    print(f"  Encounter rate:  {s['guardrail_encounter_rate']:.2%}" if s['guardrail_encounter_rate'] is not None else "  Encounter rate:  N/A")
    print(f"  MSR phase:       {s['msr_phase']}" if s['msr_phase'] else "")
    print(f"  Immune reg. fac: {s['regime_factor']:.2f}")
    print(f"  Immune mem:      {s['adaptive_memory']}")
    print(f"  MSR adj:         {s['msr_adjustments']}")
    print()


if __name__ == "__main__":
    main()
