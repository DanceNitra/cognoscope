#!/usr/bin/env python3
"""
e2e_pipeline.py — End-to-End Pipeline: Eval → Guardrail Feedback Loop

Connects:
  - Agent Evaluation (Session 1): baseline/variant/noise → fingerprint → attribution
  - Immune Guardrail (Session 2): check_trade + check_tool + regime adaptation
  - MSR (Layer 10): guardrail encounter rate monitoring
  - Feedback loop: eval results tune guardrail sensitivity

Usage:
    python3 e2e_pipeline.py   # Full demo
"""

import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

# Session 1 — Evaluation
from analysis.agent_evaluator import (
    AgentEvaluator, EvalConfig, SyntheticAgentEnv, EvalResult
)
from analysis.agent_profile import AgentProfiler, AgentProfileConfig
from analysis.optimal_fingerprint import AgentBehaviorFingerprint

# Session 2 — Guardrails
from guardrail_bus import GuardrailBus, GuardrailBusConfig, GuardrailAction
from immune_guardrail import ImmuneGuardrail, ImmuneDecision


# ──────────────────────────────────────────────
# 1. FEEDBACK LOOP
# ──────────────────────────────────────────────

def eval_to_guardrail_feedback(
    eval_result: EvalResult,
    guardrail_bus: GuardrailBus,
) -> dict:
    """
    Feed evaluation results back into the guardrail system.

    Logic:
    - If agent eval shows STRONG signal (3+ detected → variant arch matters):
      → CRISIS regime — agent behavior is meaningfully different
    - If eval shows LIMITED signal (1-2 detected):
      → HIGH_VOL regime — be cautious but not frozen
    - If eval shows NO signal (0 detected):
      → LOW_VOL — guardrails stay normal, eval noise was expected

    Returns dict with regime change decision.
    """
    r = eval_result.attribution
    n_detected = sum(1 for v in r.attributions.values() if v == "detected")
    n_inconclusive = sum(1 for v in r.attributions.values() if v == "inconclusive")
    treatment_size = abs(eval_result.config.treatment_effect)

    feedback = {
        "n_detected": n_detected,
        "n_inconclusive": n_inconclusive,
        "treatment_effect": treatment_size,
        "r_squared": r.r_squared,
        "variance_explained": r.total_variance_explained,
        "old_regime": guardrail_bus.get_regime()["name"],
    }

    if n_detected >= 3:
        # Strong signal — something real changed
        guardrail_bus.set_regime("crisis")
        feedback["new_regime"] = "crisis"
        feedback["reason"] = (
            f"Eval detected {n_detected}/6 task types with causal effect "
            f"(treatment={treatment_size:.1%}). Architecture change is REAL. "
            f"Freezing all non-essential actions."
        )
    elif n_detected >= 1 or n_inconclusive >= 3:
        guardrail_bus.set_regime("high_vol")
        feedback["new_regime"] = "high_vol"
        feedback["reason"] = (
            f"Eval detected {n_detected}/6 + {n_inconclusive} inconclusive. "
            f"Possible architecture effect. Tightening all guardrails."
        )
    else:
        guardrail_bus.set_regime("low_vol")
        feedback["new_regime"] = "low_vol"
        feedback["reason"] = (
            f"Eval detected 0/6. No architecture effect found. "
            f"Guardrails at normal sensitivity."
        )

    return feedback


# ──────────────────────────────────────────────
# 2. FULL PIPELINE DEMO
# ──────────────────────────────────────────────

def run_full_pipeline():
    print()
    print("  ╔═══════════════════════════════════════════════════════════╗")
    print("  ║  E2E Pipeline: Eval → Guardrail Feedback Loop           ║")
    print("  ║  Session 1 (Eval) + Session 2 (Guardrail) = Session 3   ║")
    print("  ╚═══════════════════════════════════════════════════════════╝")
    print()

    bus = GuardrailBus(config=GuardrailBusConfig(verbose=False))

    # ── SCENARIO 1: Strong signal (10% treatment) → CRISIS regime ──
    print("─" * 50)
    print("  [1] Strong Signal — 10% treatment effect")
    print("      10 baseline, 10 variant, 5 noise runs")
    print("─" * 50)
    print()

    cfg1 = EvalConfig(
        name="scenario_1_strong",
        n_baseline_runs=10,
        n_variant_runs=10,
        n_noise_runs=5,
        treatment_effect=0.10,
        verbose=False,
    )
    ev1 = AgentEvaluator(config=cfg1)
    r1 = ev1.run_evaluation()

    fb1 = eval_to_guardrail_feedback(r1, bus)
    print(f"  Eval result: {fb1['n_detected']}/6 detected, "
          f"r²={r1.attribution.r_squared:.3f}")
    print(f"  Regime: {fb1['old_regime']} → {fb1['new_regime']}")
    print(f"  Reason: {fb1['reason']}")
    print()

    # Simulate trades under CRISIS regime
    nav = 100000.0
    peak = 105000.0
    r = bus.check_trade("AAPL", 0.05, nav, {}, 0.0, peak)
    print(f"  Trade check (5% pos, crisis): {r.action.value.upper()} — {r.reason[:40]}")
    r = bus.check_trade("NVDA", 0.12, nav, {}, 0.0, peak)
    print(f"  Trade check (12% pos, crisis): {r.action.value.upper()} — {r.reason[:40]}")

    # Check guardrail status
    s = bus.status_report()
    print(f"  Guardrail status: regime={s['regime']}, "
          f"immune_factor={s['regime_factor']:.2f}, "
          f"reject_rate={s['immune_reject_rate']:.0%}")
    print()

    # ── SCENARIO 2: Weak/no signal → LOW_VOL ──
    print("─" * 50)
    print("  [2] Weak/No Signal — 0% treatment (null effect)")
    print("      15 baseline, 15 variant, 8 noise runs")
    print("─" * 50)
    print()

    cfg2 = EvalConfig(
        name="scenario_2_null",
        n_baseline_runs=15,
        n_variant_runs=15,
        n_noise_runs=8,
        treatment_effect=0.0,
        verbose=False,
    )
    ev2 = AgentEvaluator(config=cfg2)
    r2 = ev2.run_evaluation()

    fb2 = eval_to_guardrail_feedback(r2, bus)
    print(f"  Eval result: {fb2['n_detected']}/6 detected, "
          f"r²={r2.attribution.r_squared:.3f}")
    print(f"  Regime: {fb2['old_regime']} → {fb2['new_regime']}")
    print(f"  Reason: {fb2['reason']}")
    print()

    # Now trades should be normal
    r = bus.check_trade("MSFT", 0.08, nav, {}, 0.0, peak)
    print(f"  Trade check (8% pos, low_vol): {r.action.value.upper()} — {r.reason[:40]}")
    print()

    # ── SCENARIO 3: Tool storm under eval feedback ──
    print("─" * 50)
    print("  [3] Tool Storm — guardrail hits under eval regime")
    print("      8 rapid hits on 'terminal'")
    print("─" * 50)
    print()

    for i in range(8):
        bus.record_guardrail_hit("terminal", 4, "blocked", severity=1.0)
    r = bus.check_tool("terminal", failures_in_window=8)
    print(f"  Tool check: {r.action.value.upper()} — {r.reason[:60]}")
    if r.msr_multipliers:
        print(f"  MSR multipliers: {r.msr_multipliers}")
    print()

    # ── SCENARIO 4: Adaptive regime switch mid-session ──
    print("─" * 50)
    print("  [4] Regime switch mid-session")
    print("      low_vol → high_vol → crisis → back")
    print("─" * 50)
    print()

    for regime in ["low_vol", "high_vol", "crisis", "low_vol"]:
        bus.set_regime(regime)
        r = bus.check_trade("AMZN", 0.10, nav, {}, 0.0, peak)
        print(f"  {regime:>10s} | pos=10% → {r.action.value.upper():>7s} | "
              f"factor={bus.get_regime()['factor']:.1f} | {r.reason[:30]}")
    print()

    # ── FINAL STATUS ──
    print("=" * 50)
    print("  PIPELINE STATUS")
    print("=" * 50)
    s = bus.status_report()
    print(f"  Total guardrail checks: {s['total_checks']}")
    print(f"  Action distribution:    {s['action_counts']}")
    print(f"  Current regime:         {s['regime']} (factor={s['regime_factor']})")
    print(f"  Guardrail encounter:    {s['guardrail_encounter_rate']:.2%}" if s['guardrail_encounter_rate'] is not None else "  Guardrail encounter:    N/A")
    print(f"  MSR phase:              {s['msr_phase']}")
    print(f"  Adaptive memory:        {s['adaptive_memory']} events")
    print(f"  MSR adjustments:        {s['msr_adjustments']}")
    print()
    print("  ✅ E2E Pipeline complete: Eval → Guardrail → Regime → Feedback")
    print()


if __name__ == "__main__":
    run_full_pipeline()
