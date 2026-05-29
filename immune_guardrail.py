#!/usr/bin/env python3
"""
immune_guardrail.py — Immune-Inspired Guardrail Orchestrator (Layer 9)

Three immune layers for autonomous agents:
  - Innate immunity: Hard-coded, non-negotiable limits (position size, loss cap, leverage)
  - Adaptive immunity: Learn from past guardrail events, match patterns
  - Immune privilege: Certain guardrails cannot be overridden by any agent

Connects to:
  - msr_guardrail.py (Layer 10 — MSR monitors encounter rate)
  - guardrail_bus.py (event bus for integration)
  - athena.py (agent runtime)

Usage:
    from immune_guardrail import ImmuneGuardrail, ImmuneDecision
    ig = ImmuneGuardrail()
    decision = ig.pre_trade_check("AAPL", 0.15, current_positions, day_pnl)
"""

import os, sys, json, time, math
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
from collections import defaultdict


# ──────────────────────────────────────────────
# 1. DECISION TYPES
# ──────────────────────────────────────────────

class ImmuneDecision(Enum):
    """Outcome of an immune guardrail check."""
    PASS = "pass"           # All clear
    WARN = "warn"           # Approaching limit, flag for attention
    REJECT = "reject"      # Hard block — immune privilege
    ESCALATE = "escalate"  # Needs human override

class GuardrailDomain(Enum):
    """Domains the immune system protects."""
    POSITION_SIZING = "position_sizing"
    PORTFOLIO_RISK = "portfolio_risk"
    BEHAVIORAL = "behavioral"
    AGENT_RUNTIME = "agent_runtime"
    RESOURCE_USAGE = "resource_usage"


# ──────────────────────────────────────────────
# 2. INNATE LIMITS (Immune Privileged)
# ──────────────────────────────────────────────

@dataclass
class InnateLimits:
    """
    Hard-coded limits the agent CANNOT override.

    These are immune privileged — stored as constants, not in agent config.
    Modified only by human operator.
    """
    # Position sizing
    max_position_pct: float = 0.20        # 20% of NAV
    max_daily_loss_pct: float = 0.02     # 2% of NAV
    max_leverage: float = 2.0            # 2:1
    hard_stop_drawdown: float = 0.15     # -15% triggers full close

    # Portfolio
    max_sector_pct: float = 0.30         # Max 30% in one sector
    min_cash_pct: float = 0.05           # Always keep 5% cash
    max_concentration: float = 0.30      # Top 5 positions < 30% of portfolio

    # Agent runtime
    max_consecutive_failures: int = 10   # Circuit breaker trigger
    max_guardrail_violations_per_hour: int = 5
    max_tool_calls_per_turn: int = 50

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    def check_position(self, nav: float, position_value: float) -> ImmuneDecision:
        """Check if a position exceeds max_position_pct of NAV."""
        ratio = position_value / max(nav, 0.01)
        if ratio > self.max_position_pct:
            return ImmuneDecision.REJECT
        if ratio > self.max_position_pct * 0.8:
            return ImmuneDecision.WARN
        return ImmuneDecision.PASS

    def check_daily_loss(self, nav: float, day_pnl: float) -> ImmuneDecision:
        """Check if daily P&L exceeds max_daily_loss_pct."""
        loss_pct = abs(day_pnl) / max(nav, 0.01) if day_pnl < 0 else 0.0
        if loss_pct > self.max_daily_loss_pct:
            return ImmuneDecision.REJECT
        if loss_pct > self.max_daily_loss_pct * 0.7:
            return ImmuneDecision.ESCALATE
        return ImmuneDecision.PASS

    def check_drawdown(self, peak_nav: float, current_nav: float) -> ImmuneDecision:
        """Progressive circuit breaker levels based on drawdown."""
        drawdown = 1.0 - (current_nav / max(peak_nav, 0.01))

        if drawdown >= self.hard_stop_drawdown:
            return ImmuneDecision.ESCALATE  # full freeze — needs human
        if drawdown >= self.hard_stop_drawdown * 0.67:  # -10%
            return ImmuneDecision.REJECT     # close all positions
        if drawdown >= self.hard_stop_drawdown * 0.33:  # -5%
            return ImmuneDecision.WARN       # reduce 50%
        return ImmuneDecision.PASS


# ──────────────────────────────────────────────
# 3. ADAPTIVE IMMUNITY
# ──────────────────────────────────────────────

@dataclass
class GuardrailMemoryEntry:
    """A remembered guardrail event for pattern matching."""
    timestamp: float
    guardrail_layer: int
    tool_name: str
    action_type: str
    severity: float
    context: dict = field(default_factory=dict)


class AdaptiveImmunity:
    """
    Learns from past guardrail encounters.

    Analogous to the adaptive immune system:
    - T cells = guardrail pattern matchers
    - B cells = response generators
    - Memory cells = remembered events
    """

    def __init__(self, memory_size: int = 100):
        self.memory: list[GuardrailMemoryEntry] = []
        self.memory_size = memory_size
        self.pattern_cache: dict[str, float] = {}  # pattern → frequency

    def remember(self, event: GuardrailMemoryEntry):
        """Store a guardrail event for future pattern matching."""
        self.memory.append(event)
        if len(self.memory) > self.memory_size:
            self.memory = self.memory[-self.memory_size:]
        # Invalidate cache
        self.pattern_cache = {}

    def match(
        self,
        tool_name: str,
        guardrail_layer: int | None = None,
        time_window_seconds: float = 3600.0,  # 1 hour
    ) -> float:
        """
        Check if current conditions match a known dangerous pattern.

        Returns:
            0.0 = no match (safe)
            1.0 = perfect match (dangerous)
        """
        now = time.time()
        recent = [e for e in self.memory
                  if now - e.timestamp < time_window_seconds]
        if not recent:
            return 0.0

        # Tool repetition score
        same_tool_hits = sum(1 for e in recent if e.tool_name == tool_name)
        if same_tool_hits >= 5:
            return min(1.0, 0.5 + same_tool_hits * 0.05)

        # Layer-specific escalation
        if guardrail_layer is not None:
            layer_hits = sum(1 for e in recent
                             if e.guardrail_layer == guardrail_layer)
            if layer_hits >= 3:
                return min(1.0, 0.3 + layer_hits * 0.1)

        # General guardrail storm — any layer
        total_hits = len(recent)
        if total_hits >= 10:
            return min(1.0, total_hits * 0.05)

        return 0.0  # No match

    def guardrail_storm_score(self, recent_hits: list) -> float:
        """
        Detect guardrail storm: many hits in short time.
        0.0 = calm, 1.0 = storm.
        """
        if len(recent_hits) < 3:
            return 0.0

        # Time compression: hits are close together
        if len(recent_hits) >= 2:
            times = [h.timestamp for h in recent_hits]
            spread = max(times) - min(times)
            density = len(recent_hits) / max(spread, 1.0)
            # 1 hit per second = 0.5 storm
            # 5+ hits per second = 1.0 storm
            return min(1.0, density * 0.5)
        return 0.0

    def status(self) -> dict:
        recent = [e for e in self.memory
                  if time.time() - e.timestamp < 3600.0]
        return {
            "total_memory": len(self.memory),
            "recent_hits_1h": len(recent),
            "pattern_cache_size": len(self.pattern_cache),
        }


# ──────────────────────────────────────────────
# 4. IMMUNE GUARDRAIL ORCHESTRATOR
# ──────────────────────────────────────────────

@dataclass
class ImmuneGuardrailConfig:
    """Configuration for the immune guardrail system."""
    innate: InnateLimits = field(default_factory=InnateLimits)
    adaptive_memory_size: int = 100
    regime_sensitivity_factor: float = 1.0  # 1.0 = normal, 0.5 = high vol, 2.0 = crisis
    verbose: bool = True
    log_path: str | None = None  # If set, append JSON logs


@dataclass
class GuardrailCheckResult:
    """Result of a single guardrail check."""
    decision: ImmuneDecision
    domain: GuardrailDomain
    message: str
    level: int = 1       # 1-10 guardrail layer
    tool_name: str = ""
    match_score: float = 0.0  # Adaptive match score (if applicable)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "domain": self.domain.value,
            "message": self.message,
            "level": self.level,
            "tool_name": self.tool_name,
            "match_score": self.match_score,
        }


class ImmuneGuardrail:
    """
    Immune-inspired guardrail orchestrator (Layer 9).

    Three layers applied in sequence:
    1. Adaptive immunity — check historic patterns first (fast)
    2. Innate immunity — check hard limits (non-negotiable)
    3. Immune privilege — protect invariant that agent cannot modify

    All guardrail checks go through this class.
    """

    def __init__(
        self,
        config: ImmuneGuardrailConfig | None = None,
        adaptive: AdaptiveImmunity | None = None,
    ):
        self.config = config or ImmuneGuardrailConfig()
        self.adaptive = adaptive or AdaptiveImmunity(
            memory_size=self.config.adaptive_memory_size
        )
        self.innate = self.config.innate
        self.log: list[dict] = []
        self._checks_total = 0
        self._checks_rejected = 0

    # ── PUBLIC API ──

    def pre_trade_check(
        self,
        ticker: str,
        size_pct: float,
        nav: float,
        current_positions: dict[str, float],
        day_pnl: float = 0.0,
        peak_nav: float | None = None,
    ) -> GuardrailCheckResult:
        """
        Run all guardrail checks before a trade.

        Order: adaptive → innate position → innate loss → drawdown
        Returns: PASS if all clear, first REJECT/ESCALATE if found.
        """
        self._checks_total += 1

        # 1. Adaptive: pattern match
        match = self.adaptive.match(ticker)
        if match > 0.7:
            self._checks_rejected += 1
            return GuardrailCheckResult(
                decision=ImmuneDecision.REJECT,
                domain=GuardrailDomain.BEHAVIORAL,
                message=f"Pattern match ({match:.0%}) — {ticker} in recent guardrail history",
                level=9,
                tool_name=ticker,
                match_score=match,
            )

        # 2. Innate: position size
        pos_decision = self.innate.check_position(nav, size_pct * nav)
        if pos_decision == ImmuneDecision.REJECT:
            self._checks_rejected += 1
            return GuardrailCheckResult(
                decision=ImmuneDecision.REJECT,
                domain=GuardrailDomain.POSITION_SIZING,
                message=f"Position size {size_pct:.1%} exceeds max {self.innate.max_position_pct:.0%}",
                level=1,
                tool_name=ticker,
            )

        # 3. Innate: daily loss
        loss_decision = self.innate.check_daily_loss(nav, day_pnl)
        if loss_decision in (ImmuneDecision.REJECT, ImmuneDecision.ESCALATE):
            self._checks_rejected += 1
            loss_pct = abs(day_pnl) / max(nav, 0.01)
            return GuardrailCheckResult(
                decision=loss_decision,
                domain=GuardrailDomain.PORTFOLIO_RISK,
                message=f"Daily loss {loss_pct:.1%} exceeds limit {self.innate.max_daily_loss_pct:.0%}",
                level=3,
                tool_name=ticker,
            )

        # 4. Drawdown
        if peak_nav is not None:
            dd_decision = self.innate.check_drawdown(peak_nav, nav)
            if dd_decision != ImmuneDecision.PASS:
                drawdown_pct = (1 - nav / max(peak_nav, 0.01)) * 100
                return GuardrailCheckResult(
                    decision=dd_decision,
                    domain=GuardrailDomain.PORTFOLIO_RISK,
                    message=f"Drawdown {drawdown_pct:.1f}% triggered circuit breaker",
                    level=5,
                    tool_name=ticker,
                )

        return GuardrailCheckResult(
            decision=ImmuneDecision.PASS,
            domain=GuardrailDomain.POSITION_SIZING,
            message=f"All checks passed for {ticker}",
            level=1,
            tool_name=ticker,
        )

    def record_guardrail_hit(
        self,
        tool_name: str,
        guardrail_layer: int,
        action_type: str,
        severity: float = 1.0,
        context: dict | None = None,
    ):
        """Record a guardrail hit for adaptive immunity learning."""
        entry = GuardrailMemoryEntry(
            timestamp=time.time(),
            guardrail_layer=guardrail_layer,
            tool_name=tool_name,
            action_type=action_type,
            severity=severity,
            context=context or {},
        )
        self.adaptive.remember(entry)

        result = GuardrailCheckResult(
            decision=ImmuneDecision.REJECT,
            domain=GuardrailDomain.AGENT_RUNTIME,
            message=f"Guardrail L{guardrail_layer} hit on {tool_name}: {action_type}",
            level=guardrail_layer,
            tool_name=tool_name,
        )
        self._log(result)

    def check_tool_call(
        self,
        tool_name: str,
        consecutive_calls: int = 0,
        failures_in_window: int = 0,
    ) -> GuardrailCheckResult:
        """Check if a tool call is safe."""
        # Adaptive: known dangerous pattern?
        match = self.adaptive.match(tool_name)
        if match > 0.8:
            return GuardrailCheckResult(
                decision=ImmuneDecision.REJECT,
                domain=GuardrailDomain.BEHAVIORAL,
                message=f"Tool {tool_name} in dangerous pattern (match={match:.0%})",
                level=9,
                tool_name=tool_name,
                match_score=match,
            )

        # Consecutive failures → circuit breaker
        if consecutive_calls >= self.innate.max_consecutive_failures:
            return GuardrailCheckResult(
                decision=ImmuneDecision.REJECT,
                domain=GuardrailDomain.AGENT_RUNTIME,
                message=f"Circuit breaker: {consecutive_calls} consecutive failures",
                level=8,
                tool_name=tool_name,
            )

        if failures_in_window >= self.innate.max_guardrail_violations_per_hour:
            return GuardrailCheckResult(
                decision=ImmuneDecision.ESCALATE,
                domain=GuardrailDomain.AGENT_RUNTIME,
                message=f"Guardrail storm: {failures_in_window} hits in 1h",
                level=9,
                tool_name=tool_name,
            )

        if match > 0.4:
            return GuardrailCheckResult(
                decision=ImmuneDecision.WARN,
                domain=GuardrailDomain.BEHAVIORAL,
                message=f"Tool {tool_name} weakly matches known pattern",
                level=9,
                tool_name=tool_name,
                match_score=match,
            )

        return GuardrailCheckResult(
            decision=ImmuneDecision.PASS,
            domain=GuardrailDomain.AGENT_RUNTIME,
            message=f"Tool {tool_name} cleared",
            level=1,
            tool_name=tool_name,
        )

    def status_report(self) -> dict:
        """Return full status of the immune guardrail system."""
        return {
            "checks_total": self._checks_total,
            "checks_rejected": self._checks_rejected,
            "reject_rate": self._checks_rejected / max(self._checks_total, 1),
            "adaptive": self.adaptive.status(),
            "innate_limits": self.innate.to_dict(),
            "regime_factor": self.config.regime_sensitivity_factor,
        }

    def set_regime_factor(self, factor: float):
        """
        Adjust all limits by a regime factor.

        factor < 1.0 = more conservative (high vol)
        factor > 1.0 = looser (low vol regime)

        This is the immune equivalent of vasodilation/vasoconstriction.
        """
        self.config.regime_sensitivity_factor = max(0.2, min(2.0, factor))
        # Scale innate limits
        self.innate.max_position_pct *= factor
        self.innate.max_daily_loss_pct *= factor
        self.innate.hard_stop_drawdown *= factor

    def _log(self, result: GuardrailCheckResult):
        self.log.append(result.to_dict())
        if self.config.verbose and result.decision != ImmuneDecision.PASS:
            s = f"[IMMUNE] {result.decision.value.upper()}: {result.message}"
            print(f"  {s}")


# ──────────────────────────────────────────────
# 5. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║ Immune Guardrail Orchestrator (Layer 9)                 ║")
    print("  ║ Innate → Adaptive → Circuit Breaker                    ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    ig = ImmuneGuardrail()
    nav = 100_000.0
    peak_nav = 105_000.0

    # ── Scenario 1: Position too large ──
    print("─" * 50)
    print("  [1] Position Size Check — 25% of NAV (limit 20%)")
    print("─" * 50)
    r = ig.pre_trade_check("AAPL", 0.25, nav, {}, 0.0, peak_nav)
    print(f"  Decision: {r.decision.value.upper()}")
    print(f"  Reason: {r.message}")
    print(f"  Domain: {r.domain.value}")
    print()

    # ── Scenario 2: Daily loss exceeded ──
    print("─" * 50)
    print("  [2] Daily Loss Check — -3% (limit 2%)")
    print("─" * 50)
    r = ig.pre_trade_check("NVDA", 0.05, nav, {}, -3000.0, peak_nav)
    print(f"  Decision: {r.decision.value.upper()}")
    print(f"  Reason: {r.message}")
    print()

    # ── Scenario 3: Adaptive pattern match ──
    print("─" * 50)
    print("  [3] Adaptive Immunity — pattern learning")
    print("─" * 50)
    # Simulate 6 guardrail hits on 'terminal'
    for i in range(6):
        ig.record_guardrail_hit("terminal", 4, "blocked", severity=1.0)

    r = ig.check_tool_call("terminal", failures_in_window=6)
    print(f"  Decision: {r.decision.value.upper()}")
    print(f"  Reason: {r.message}")
    if r.match_score:
        print(f"  Match score: {r.match_score:.0%}")
    print()

    # ── Scenario 4: Drawdown circuit breaker ──
    print("─" * 50)
    print("  [4] Drawdown Check — peak=$105K, current=$85K (-19%)")
    print("─" * 50)
    # Simulate the drawdown as a daily loss check
    r = ig.innate.check_drawdown(105_000.0, 85_000.0)
    print(f"  Innate drawdown result: {r.value.upper()}")
    # Use pre_trade_check with peak_nav
    ig.innate.hard_stop_drawdown = 0.15
    r = ig.pre_trade_check("TSLA", 0.05, 85_000.0, {}, 0.0, 105_000.0)
    print(f"  Decision: {r.decision.value.upper()}")
    print(f"  Reason: {r.message}")
    print()

    # ── Scenario 5: All clear ──
    print("─" * 50)
    print("  [5] All Clear — 5% position, no loss")
    print("─" * 50)
    r = ig.pre_trade_check("MSFT", 0.05, nav, {}, 0.0, peak_nav)
    print(f"  Decision: {r.decision.value.upper()}")
    print(f"  Reason: {r.message}")
    print()

    # ── Status ──
    print("─" * 50)
    print("  IMMUNE SYSTEM STATUS")
    print("─" * 50)
    s = ig.status_report()
    print(f"  Total checks:     {s['checks_total']}")
    print(f"  Rejected:         {s['checks_rejected']}")
    print(f"  Reject rate:      {s['reject_rate']:.1%}")
    print(f"  Adaptive memory:  {s['adaptive']['total_memory']}")
    print(f"  Recent hits (1h): {s['adaptive']['recent_hits_1h']}")
    print(f"  Regime factor:    {s['regime_factor']}")
    print()


if __name__ == "__main__":
    main()
