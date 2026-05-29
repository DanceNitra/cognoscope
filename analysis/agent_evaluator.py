#!/usr/bin/env python3
"""
agent_evaluator.py — Causal Agent Evaluation Orchestrator

Runs batches of agent simulations across different configurations,
collects behavioral fingerprints via AgentProfiler, runs optimal
fingerprinting attribution, and produces structured eval reports.

Usage:
    python3 -c "from analysis.agent_evaluator import main; main()"  # Full demo
"""

import os, sys, json, random, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict

from analysis.agent_profile import AgentProfiler, AgentProfileConfig
from analysis.optimal_fingerprint import (
    AgentBehaviorFingerprint,
    OptimalFingerprint,
    AttributionResult,
    generate_synthetic_agent_data,
)

# ──────────────────────────────────────────────
# 1. EVAL CONFIG
# ──────────────────────────────────────────────

@dataclass
class EvalConfig:
    """Configuration for an evaluation batch."""
    name: str = "eval_batch"
    n_baseline_runs: int = 5      # How many baseline ensemble runs
    n_variant_runs: int = 5       # How many variant ensemble runs
    n_noise_runs: int = 3         # How many same-agent runs (internal variability)
    noise_seed_offset: int = 999  # Seeds for noise runs
    max_turns: int = 30           # Turns per simulation
    treatment_effect: float = 0.05  # Synthetic treatment effect size
    verbose: bool = True
    output_dir: str | None = None  # If set, write results as JSON


@dataclass
class EvalResult:
    """Complete result of one evaluation batch."""
    config: EvalConfig
    baseline_fingerprints: list[AgentBehaviorFingerprint]
    variant_fingerprints: list[AgentBehaviorFingerprint]
    noise_fingerprints: list[AgentBehaviorFingerprint]
    target_fingerprint: AgentBehaviorFingerprint
    attribution: AttributionResult
    profiler_summary: dict

    def to_dict(self) -> dict:
        return {
            "config": {
                "name": self.config.name,
                "n_baseline": self.config.n_baseline_runs,
                "n_variant": self.config.n_variant_runs,
                "n_noise": self.config.n_noise_runs,
                "treatment_effect": self.config.treatment_effect,
            },
            "attribution": {
                "r_squared": self.attribution.r_squared,
                "variance_explained": self.attribution.total_variance_explained,
                "fingerprint_correlation": self.attribution.fingerprint_correlation,
                "n_detected": sum(1 for v in self.attribution.attributions.values() if v == "detected"),
                "n_inconclusive": sum(1 for v in self.attribution.attributions.values() if v == "inconclusive"),
                "n_not_detected": sum(1 for v in self.attribution.attributions.values() if v == "not_detected"),
                "attributions": self.attribution.attributions,
                "treatment_effects": self.attribution.treatment_effect,
                "confidence": self.attribution.confidence,
                "details": self.attribution.details,
            },
            "profiler_summary": self.profiler_summary,
        }

    def summary_report(self) -> str:
        r = self.attribution
        nd = sum(1 for v in r.attributions.values() if v == "detected")
        ni = sum(1 for v in r.attributions.values() if v == "inconclusive")
        nn = sum(1 for v in r.attributions.values() if v == "not_detected")

        lines = [
            f"{'=' * 50}",
            f"  EVAL REPORT: {self.config.name}",
            f"{'=' * 50}",
            f"  Setup: {self.config.n_baseline_runs} baseline, "
            f"{self.config.n_variant_runs} variant, "
            f"{self.config.n_noise_runs} noise runs",
            f"  Treatment effect injected: {self.config.treatment_effect:.1%}",
            f"",
            f"  CAUSAL ATTRIBUTION RESULTS:",
            f"  ───────────────────────────",
            f"  r²: {r.r_squared:.3f}",
            f"  Variance explained: {r.total_variance_explained:.1%}",
            f"  Fingerprint correlation: {r.fingerprint_correlation:.3f}",
            f"",
            f"  Per-task attributions:",
            f"  ──────────────────────",
        ]
        for tt in sorted(r.attributions.keys()):
            effect = r.treatment_effect.get(tt, 0.0)
            conf = r.confidence.get(tt, 0.0)
            attr = r.attributions.get(tt, "?")
            lines.append(f"    {tt:>15s} → {attr:>15s}  Δ={effect:+.3f}  p={conf:.0%}")

        lines.extend([
            f"  ",
            f"  DETECTED:     {nd}/6 task types",
            f"  INCONCLUSIVE: {ni}/6",
            f"  NOT DETECTED: {nn}/6",
            f"",
            f"  VERDICT: ",
        ])

        if nd >= 3:
            lines.append(f"    ✅ The architecture variant has a STRONG causal effect")
            lines.append(f"    on agent behavior across {nd} task types.")
        elif nd >= 1:
            lines.append(f"    🟡 A LIMITED causal effect in {nd} task type(s)")
            lines.append(f"    Other task types within structural uncertainty.")
        else:
            lines.append(f"    ❌ No detectable causal effect")
            lines.append(f"    Observed differences within noise range.")

        lines.extend([
            f"{'=' * 50}",
        ])
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 2. SYNTHETIC AGENT ENVIRONMENT
# ──────────────────────────────────────────────

class SyntheticAgentEnv:
    """
    Lightweight agent simulation environment.

    Produces event traces that can be fingerprinted by AgentProfiler.
    Supports configurable: task success rates, guardrail hit rates,
    reflection ratios, tool diversity, and latency.
    """

    def __init__(self, random_seed: int = 42):
        self.base_seed = random_seed

    def run(
        self,
        max_turns: int = 30,
        success_base: float = 0.65,
        guardrail_base: float = 0.10,
        reflection_base: float = 0.20,
        tool_diversity_base: float = 0.50,
        latency_base: float = 5.0,
        treatment_effect: float = 0.0,
        task_types: list[str] | None = None,
        run_index: int = 0,
    ) -> list[dict]:
        """
        Run synthetic agent.

        Args:
            max_turns: How many tool calls
            success_base: Base success probability
            guardrail_base: Base guardrail hit probability
            reflection_base: Base reflection probability
            tool_diversity_base: How varied tool selection is (1.0=all tools equally)
            latency_base: Base seconds per turn
            treatment_effect: Added to success_base for variant testing
            task_types: Override task mapping
            run_index: Unique index per run to vary noise seeds

        Returns:
            List of event dicts matching what AgentProfiler expects
        """
        self.random = random.Random(self.base_seed + run_index * 13)

        if task_types is None:
            task_types = ["retrieval", "synthesis", "execution",
                          "verification", "planning", "debugging"]

        tools = ["search", "read_file", "browser", "write", "terminal", "forge",
                 "verify_output", "plan_strategy", "debug_code"]
        tool_to_task = {
            "search": "retrieval", "read_file": "retrieval",
            "browser": "retrieval", "write": "synthesis",
            "terminal": "execution", "forge": "synthesis",
            "verify_output": "verification",
            "plan_strategy": "planning",
            "debug_code": "debugging",
        }
        events = []
        last_tool = "search"

        for turn in range(max_turns):
            # Tool selection with diversity control
            if self.random.random() < tool_diversity_base:
                tool = self.random.choice(tools)
            else:
                tool = last_tool

            last_tool = tool
            task = tool_to_task.get(tool, "execution")

            # Success: baseline + treatment effect
            success_prob = success_base + treatment_effect
            success = self.random.random() < success_prob

            # Guardrail hit
            guardrail_hit = self.random.random() < guardrail_base

            # Reflection
            reflects = self.random.random() < reflection_base

            events.append({"type": "tool_call", "tool": tool, "turn": turn})
            events.append({"type": "tool_result", "tool": tool, "turn": turn, "success": success})
            if guardrail_hit:
                events.append({"type": "guardrail_hit", "tool": tool, "turn": turn,
                               "guardrail_layer": 4, "action_type": "flagged"})
            if reflects:
                events.append({"type": "reasoning", "tool": tool, "turn": turn,
                               "content": "reflecting"})

        return events


# ──────────────────────────────────────────────
# 3. EVALUATOR
# ──────────────────────────────────────────────

class AgentEvaluator:
    """
    Full evaluation pipeline:
    1. Generate synthetic agent runs (baseline + variant + noise)
    2. Profile each run into fingerprints
    3. Run optimal fingerprinting attribution
    4. Produce report
    """

    def __init__(
        self,
        config: EvalConfig | None = None,
        profiler: AgentProfiler | None = None,
        fingerprint: OptimalFingerprint | None = None,
    ):
        self.config = config or EvalConfig()
        self.profiler = profiler or AgentProfiler()
        self.fingerprint = fingerprint or OptimalFingerprint()

    def run_evaluation(
        self,
        config: EvalConfig | None = None,
    ) -> EvalResult:
        """Run a full evaluation batch."""
        cfg = config or self.config
        profiler = self.profiler
        rng = random.Random(42)
        rng.seed(42)

        task_types = AgentProfileConfig().task_types

        # ── Generate synthetic runs ──
        if cfg.verbose:
            print(f"[EVAL] Generating {cfg.n_baseline_runs} baseline runs...")
            print(f"[EVAL] Generating {cfg.n_variant_runs} variant runs "
                  f"(effect={cfg.treatment_effect:.1%})...")
            print(f"[EVAL] Generating {cfg.n_noise_runs} noise runs...")

        env = SyntheticAgentEnv(random_seed=42)

        baseline_fps = []
        for i in range(cfg.n_baseline_runs):
            events = env.run(
                max_turns=cfg.max_turns,
                success_base=0.65,
                guardrail_base=0.10,
                reflection_base=0.20,
                treatment_effect=0.0,
                run_index=i,
            )
            fp = profiler.profile_from_events("Baseline", f"baseline_{i}", events)
            baseline_fps.append(fp)

        # Reset RNG state so variant can be compared fairly
        variant_fps = []
        for i in range(cfg.n_variant_runs):
            events = env.run(
                max_turns=cfg.max_turns,
                success_base=0.65,
                guardrail_base=0.10,
                reflection_base=0.20,
                treatment_effect=cfg.treatment_effect,
                run_index=cfg.n_baseline_runs + i,
            )
            fp = profiler.profile_from_events("Variant", f"variant_{i}", events)
            variant_fps.append(fp)

        noise_fps = []
        noisy_env = SyntheticAgentEnv(random_seed=cfg.noise_seed_offset)
        for i in range(cfg.n_noise_runs):
            events = noisy_env.run(
                max_turns=cfg.max_turns,
                success_base=0.65,
                guardrail_base=0.10,
                reflection_base=0.20,
                treatment_effect=0.0,
                run_index=i,
            )
            fp = profiler.profile_from_events("SameAgent", f"noise_{i}", events)
            noise_fps.append(fp)

        # ── Build target fingerprint (Variant ensemble mean) ──
        if variant_fps:
            first = variant_fps[0]
            target = AgentBehaviorFingerprint(
                architecture_name="Target (Variant Mean)",
                run_id="target_mean",
                accuracy={tt: float(np.mean([fp.accuracy[tt] for fp in variant_fps]))
                          for tt in first.accuracy},
                guardrail_hit_rate={tt: float(np.mean([fp.guardrail_hit_rate[tt] for fp in variant_fps]))
                                    for tt in first.guardrail_hit_rate},
                reflection_ratio={tt: float(np.mean([fp.reflection_ratio[tt] for fp in variant_fps]))
                                  for tt in first.reflection_ratio},
                tool_diversity={tt: float(np.mean([fp.tool_diversity[tt] for fp in variant_fps]))
                                for tt in first.tool_diversity},
                latency_seconds={tt: float(np.mean([fp.latency_seconds[tt] for fp in variant_fps]))
                                 for tt in first.latency_seconds},
                total_turns=cfg.max_turns,
                total_tasks=len(task_types),
            )
        else:
            # Fallback: use synthetic data generator
            baseline_fps, variant_fps, noise_fps = generate_synthetic_agent_data(
                n_baseline_runs=cfg.n_baseline_runs,
                n_variant_runs=cfg.n_variant_runs,
                n_noise_runs=cfg.n_noise_runs,
                treatment_effect=cfg.treatment_effect,
            )
            first = variant_fps[0]
            target = AgentBehaviorFingerprint(
                architecture_name="Target",
                run_id="target",
                accuracy={tt: float(np.mean([fp.accuracy[tt] for fp in variant_fps]))
                          for tt in first.accuracy},
                guardrail_hit_rate={tt: float(np.mean([fp.guardrail_hit_rate[tt] for fp in variant_fps]))
                                    for tt in first.guardrail_hit_rate},
                reflection_ratio={tt: float(np.mean([fp.reflection_ratio[tt] for fp in variant_fps]))
                                  for tt in first.reflection_ratio},
                tool_diversity={tt: float(np.mean([fp.tool_diversity[tt] for fp in variant_fps]))
                                for tt in first.tool_diversity},
                latency_seconds={tt: float(np.mean([fp.latency_seconds[tt] for fp in variant_fps]))
                                 for tt in first.latency_seconds},
                total_turns=cfg.max_turns,
                total_tasks=len(task_types),
            )

        # ── Run optimal fingerprinting ──
        if cfg.verbose:
            print(f"[EVAL] Running optimal fingerprinting attribution...")

        opt = OptimalFingerprint()
        result = opt.attribute(target, baseline_fps, variant_fps, noise_ensemble=noise_fps)

        # ── Profiler summary ──
        profiler_summary = profiler.profile_summary(variant_fps)

        eval_result = EvalResult(
            config=cfg,
            baseline_fingerprints=baseline_fps,
            variant_fingerprints=variant_fps,
            noise_fingerprints=noise_fps,
            target_fingerprint=target,
            attribution=result,
            profiler_summary=profiler_summary,
        )

        # ── Save if output_dir set ──
        if cfg.output_dir:
            os.makedirs(cfg.output_dir, exist_ok=True)
            out_path = os.path.join(cfg.output_dir, f"{cfg.name}_result.json")
            with open(out_path, "w") as f:
                json.dump(eval_result.to_dict(), f, indent=2, default=str)
            if cfg.verbose:
                print(f"[EVAL] Saved to {out_path}")

        return eval_result


# ──────────────────────────────────────────────
# 4. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔═══════════════════════════════════════════════════════════╗")
    print("  ║  Agent Evaluation Pipeline — Causal Attribution Demo     ║")
    print("  ║  Run: baseline vs variant × optimal fingerprinting       ║")
    print("  ╚═══════════════════════════════════════════════════════════╝")
    print()

    # ── Test 1: Strong signal (10% treatment effect) ──
    print("─" * 50)
    print("  [1] Strong Signal — 10% treatment effect")
    print("─" * 50)
    print()

    cfg1 = EvalConfig(
        name="strong_signal",
        n_baseline_runs=20,
        n_variant_runs=20,
        n_noise_runs=10,
        treatment_effect=0.10,
        verbose=False,
    )
    ev1 = AgentEvaluator(config=cfg1)
    r1 = ev1.run_evaluation()
    print(r1.summary_report())
    print()

    # ── Test 2: Weak signal (1% treatment effect) ──
    print("─" * 50)
    print("  [2] Weak Signal — 1% treatment effect")
    print("─" * 50)
    print()

    cfg2 = EvalConfig(
        name="weak_signal",
        n_baseline_runs=15,
        n_variant_runs=15,
        n_noise_runs=8,
        treatment_effect=0.01,
        verbose=False,
    )
    ev2 = AgentEvaluator(config=cfg2)
    r2 = ev2.run_evaluation()
    print(r2.summary_report())
    print()

    # ── Test 3: No effect (0%) — should be NOT DETECTED ──
    print("─" * 50)
    print("  [3] Null Effect — 0% treatment (should be NOT DETECTED)")
    print("─" * 50)
    print()

    cfg3 = EvalConfig(
        name="null_effect",
        n_baseline_runs=15,
        n_variant_runs=15,
        n_noise_runs=8,
        treatment_effect=0.0,
        verbose=False,
    )
    ev3 = AgentEvaluator(config=cfg3)
    r3 = ev3.run_evaluation()
    print(r3.summary_report())
    print()

    # ── Summary comparison ──
    print("=" * 50)
    print("  COMPARISON SUMMARY")
    print("=" * 50)
    print()

    for name, result in [("Strong (5%)", r1), ("Weak (1%)", r2), ("Null (0%)", r3)]:
        r = result.attribution
        nd = sum(1 for v in r.attributions.values() if v == "detected")
        print(f"  {name:>15s} | r²={r.r_squared:.3f} | "
              f"corr={r.fingerprint_correlation:.3f} | "
              f"detected={nd}/6")
    print()


if __name__ == "__main__":
    main()
