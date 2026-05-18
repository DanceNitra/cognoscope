#!/usr/bin/env python3
"""
optimal_fingerprint.py — Causal Attribution for Agent Behavior

Implements optimal fingerprinting, the standard causal attribution method from
climate science (Bridge #46), adapted for agent evaluation.

Climate attribution asks: "Is the observed climate change due to human forcing?"
Optimal fingerprinting answers: regress the observed pattern on model-simulated
response patterns, using a generalized linear model with structural uncertainty
from multi-model ensembles.

Agent attribution asks: "Is the observed behavior difference due to the
architecture change or to noise?"
Optimal fingerprinting for agents answers: regress agent behavior patterns
(task-type fingerprints) on architecture variants, using a multi-ensemble
framework with structural uncertainty quantification.

Usage:
    python3 optimal_fingerprint.py  # Run demo with synthetic agent data
"""

import numpy as np
import json
import sys
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────
# 1. DATA MODEL
# ──────────────────────────────────────────────

@dataclass
class AgentBehaviorFingerprint:
    """
    A fingerprint is a vector of behavior metrics across task types.
    Unlike a single summary metric (82% accuracy), the fingerprint preserves
    the *structure* of behavior — which tasks succeed and fail, where
    guardrails trigger, how reflection varies by domain.

    This is the analog of a climate model's spatiotemporal pattern:
    temperature change at every grid point, not just the global mean.
    """
    # Architecture identifier
    architecture_name: str
    run_id: str

    # Behavioral metrics — each is a dict mapping task_type → value
    # These are the "grid points" of the fingerprint
    accuracy: dict[str, float]            # success rate per task type
    guardrail_hit_rate: dict[str, float]  # guardrail encounters per task type
    reflection_ratio: dict[str, float]    # reflection turns / total turns
    tool_diversity: dict[str, float]      # unique tools used / total tools
    latency_seconds: dict[str, float]     # avg time per task type

    # Metadata
    total_turns: int
    total_tasks: int

    def to_vector(self, task_types: list[str] | None = None) -> np.ndarray:
        """
        Flatten the fingerprint into a single vector for regression.

        Each task type becomes features: accuracy, guardrail_rate, reflection,
        diversity, latency. Result is a vector of length (n_task_types * 5).
        """
        if task_types is None:
            # Union of all task types across all metrics
            all_types = set(self.accuracy.keys())
            all_types |= set(self.guardrail_hit_rate.keys())
            all_types |= set(self.reflection_ratio.keys())
            all_types |= set(self.tool_diversity.keys())
            task_types = sorted(all_types)

        features = []
        for tt in task_types:
            features.append(self.accuracy.get(tt, 0.0))
            features.append(self.guardrail_hit_rate.get(tt, 0.0))
            features.append(self.reflection_ratio.get(tt, 0.0))
            features.append(self.tool_diversity.get(tt, 0.0))
            features.append(self.latency_seconds.get(tt, 0.0))

        return np.array(features)

    @staticmethod
    def task_type_names(metrics: dict[str, float]) -> list[str]:
        return sorted(metrics.keys())

    @property
    def overall_accuracy(self) -> float:
        vals = list(self.accuracy.values())
        return sum(vals) / len(vals) if vals else 0.0


# ──────────────────────────────────────────────
# 2. OPTIMAL FINGERPRINTING
# ──────────────────────────────────────────────

@dataclass
class AttributionResult:
    """
    The result of an optimal fingerprinting analysis.

    Analogous to the IPCC's attribution statement:
    "Human forcing is the dominant driver of observed warming (virtual certainty)."
    """
    treatment_effect: dict[str, float]  # Effect per task type
    structural_uncertainty: dict[str, float]  # Spread per task type
    confidence: dict[str, float]  # Statistical confidence per task type
    r_squared: float  # How well the model fits
    total_variance_explained: float
    fingerprint_correlation: float  # Correlation between observed and predicted
    attributions: dict[str, str]  # Per metric: "detected" | "not_detected" | "inconclusive"
    details: dict[str, Any]

    def summary(self) -> str:
        lines = [
            "═" * 56,
            "  OPTIMAL FINGERPRINTING — Causal Attribution Results",
            "═" * 56,
            f"  Total variance explained: {self.total_variance_explained:.1%}",
            f"  Fingerprint correlation: {self.fingerprint_correlation:.3f}",
            f"  R²: {self.r_squared:.3f}",
            "",
            "  Attributions:",
        ]
        for metric, attribution in self.attributions.items():
            effect = self.treatment_effect.get(metric, 0.0)
            uncert = self.structural_uncertainty.get(metric, 0.0)
            conf = self.confidence.get(metric, 0.0)
            lines.append(
                f"    {metric:>20s}: {attribution:>14s}  "
                f"Δ={effect:+.3f}  σ={uncert:.3f}  p={conf:.0%}"
            )
        lines.append("═" * 56)
        return "\n".join(lines)


class OptimalFingerprint:
    """
    Optimal fingerprinting for agent behavior comparison.

    Climate optimal fingerprinting (Ribes & Terray, 2013):
        y = Σ β_i x_i + ν

    Where:
        y = observed climate response (the fingerprint)
        x_i = model-simulated response to forcing i
        β_i = scaling factor (the causal parameter)
        ν = internal variability (noise)

    Agent optimal fingerprinting:
        y = performance of the TARGET agent (the one we're evaluating)
        x_1 = performance of the BASELINE agent
        x_2 = performance of the VARIANT agent(s)
        x_3 = expected noise (random variation from random seeds)
        β_i = how much each contribution matters
        ν = irreducible stochasticity

    The key question: Is β_variant significantly different from zero?
    If yes: the architecture change has a detectable causal effect.
    If no: the observed difference could be noise.
    """

    def __init__(
        self,
        task_types: list[str] | None = None,
        noise_threshold: float = 0.05,
        detection_threshold: float = 0.10,
    ):
        self.task_types = task_types
        self.noise_threshold = noise_threshold
        self.detection_threshold = detection_threshold

    def attribute(
        self,
        target_fingerprint: AgentBehaviorFingerprint,
        baseline_fingerprints: list[AgentBehaviorFingerprint],
        variant_fingerprints: list[AgentBehaviorFingerprint],
        noise_ensemble: list[AgentBehaviorFingerprint] | None = None,
    ) -> AttributionResult:
        """
        Run optimal fingerprinting attribution.

        Args:
            target_fingerprint: The agent whose behavior we want to attribute
            baseline_fingerprints: Multiple runs of the baseline architecture
            variant_fingerprints: Multiple runs of the variant architecture
            noise_ensemble: Multiple runs of the SAME agent with different seeds
                            (internal variability estimate)

        Returns:
            AttributionResult with treatment effects and confidence
        """
        # Determine task types from data if not specified
        if self.task_types is None:
            all_types = set(target_fingerprint.accuracy.keys())
            for fp in baseline_fingerprints + variant_fingerprints:
                all_types |= set(fp.accuracy.keys())
            if noise_ensemble:
                for fp in noise_ensemble:
                    all_types |= set(fp.accuracy.keys())
            self.task_types = sorted(all_types)

        tt = self.task_types
        n_features = len(tt)

        # Build the target vector
        y = target_fingerprint.to_vector(tt)

        # Build baseline ensemble (multi-model mean and spread)
        baseline_vectors = np.array([fp.to_vector(tt) for fp in baseline_fingerprints])
        baseline_mean = np.mean(baseline_vectors, axis=0)
        baseline_spread = np.std(baseline_vectors, axis=0)

        # Build variant ensemble
        variant_vectors = np.array([fp.to_vector(tt) for fp in variant_fingerprints])
        variant_mean = np.mean(variant_vectors, axis=0)
        variant_spread = np.std(variant_vectors, axis=0)

        # Build noise ensemble (internal variability)
        if noise_ensemble and len(noise_ensemble) >= 3:
            noise_vectors = np.array([fp.to_vector(tt) for fp in noise_ensemble])
            noise_std = np.std(noise_vectors, axis=0)
        else:
            # Use baseline spread as noise proxy
            noise_std = baseline_spread.copy()
            noise_std[noise_std < 0.01] = 0.01  # Floor

        # ── Fingerprinting regression ──
        # y = β_0 * baseline + β_1 * (variant - baseline) + ν
        # The treatment effect is captured by β_1

        # Design matrix
        X = np.column_stack([
            baseline_mean,
            variant_mean - baseline_mean,
        ])

        # Ridge regression to handle collinearity and noise
        n, p = X.shape
        lambda_ = 1.0  # Ridge regularization

        try:
            XtX = X.T @ X + lambda_ * np.eye(p)
            Xty = X.T @ y
            beta = np.linalg.solve(XtX, Xty)
        except np.linalg.LinAlgError:
            beta = np.array([0.0, 0.0])

        beta_baseline = beta[0]
        beta_variant = beta[1]

        # ── Predict and compute residuals ──
        y_pred = X @ beta
        residuals = y - y_pred
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / max(ss_tot, 1e-10)

        # ── Structural uncertainty (variability across models) ──
        # In climate attribution, structural uncertainty comes from different
        # models giving different scaling factors. Here, we compute the
        # spread of β_variant across bootstrap resamples of the ensemble.
        structural_uncertainty = {}
        treatment_effect = {}
        confidence = {}
        attributions = {}

        for idx, task_type in enumerate(tt):
            # Extract the 5 features for this task type
            # accuracy, guardrail_rate, reflection, diversity, latency
            feature_start = idx * 5
            feature_end = feature_start + 5

            # Bootstrapped structural uncertainty
            n_bootstrap = 100
            bootstrap_effects = []

            for _ in range(n_bootstrap):
                # Resample baseline and variant with replacement
                bs_indices = np.random.choice(
                    len(baseline_vectors), len(baseline_vectors), replace=True
                )
                vs_indices = np.random.choice(
                    len(variant_vectors), len(variant_vectors), replace=True
                )

                X_bs = np.column_stack([
                    np.mean(baseline_vectors[bs_indices], axis=0)[feature_start:feature_end],
                    (np.mean(variant_vectors[vs_indices], axis=0)
                     - np.mean(baseline_vectors[bs_indices], axis=0))[feature_start:feature_end],
                ])
                y_bs = target_fingerprint.to_vector(tt)[feature_start:feature_end]

                try:
                    # Simple OLS for each bootstrap
                    XtX_bs = X_bs.T @ X_bs + lambda_ * np.eye(2)
                    Xty_bs = X_bs.T @ y_bs
                    beta_bs = np.linalg.solve(XtX_bs, Xty_bs)
                    bootstrap_effects.append(beta_bs[1])
                except np.linalg.LinAlgError:
                    bootstrap_effects.append(0.0)

            if bootstrap_effects:
                boot_effects = np.array(bootstrap_effects)
                structural_uncertainty_ = np.std(boot_effects)
                treatment_effect_ = np.mean(boot_effects)

                # Confidence: is the treatment effect reliably non-zero?
                # Count how often the bootstrap effect has the same sign
                sign_fraction = max(
                    np.sum(boot_effects > 0) / len(boot_effects),
                    np.sum(boot_effects < 0) / len(boot_effects),
                )
                # Signal-to-noise ratio
                snr = abs(treatment_effect_) / max(structural_uncertainty_, 0.01)

                # Detection criteria (parallel to climate attribution)
                if snr >= self.detection_threshold / max(noise_std[0], 0.01):
                    attrib = "detected"
                    conf = min(1.0, sign_fraction * (1 + snr * 0.5))
                elif snr >= self.noise_threshold / max(noise_std[0], 0.01):
                    attrib = "inconclusive"
                    conf = sign_fraction
                else:
                    attrib = "not_detected"
                    conf = 1.0 - sign_fraction
            else:
                structural_uncertainty_ = 0.0
                treatment_effect_ = 0.0
                attrib = "insufficient_data"
                conf = 0.0

            treatment_effect[task_type] = treatment_effect_
            structural_uncertainty[task_type] = structural_uncertainty_
            confidence[task_type] = conf
            attributions[task_type] = attrib

        # ── Overall metrics ──
        # Fingerprint correlation: correlation between observed and predicted
        fp_corr = np.corrcoef(y, y_pred)[0, 1] if len(y) > 1 and np.std(y) > 0 else 0.0

        # Variance explained
        var_explained = 1 - np.var(residuals) / max(np.var(y), 1e-10)

        return AttributionResult(
            treatment_effect=treatment_effect,
            structural_uncertainty=structural_uncertainty,
            confidence=confidence,
            r_squared=r_squared,
            total_variance_explained=var_explained,
            fingerprint_correlation=fp_corr,
            attributions=attributions,
            details={
                "beta_baseline": float(beta_baseline),
                "beta_variant": float(beta_variant),
                "n_baseline": len(baseline_fingerprints),
                "n_variant": len(variant_fingerprints),
                "n_noise": len(noise_ensemble) if noise_ensemble else 0,
                "task_types": tt,
                "target_architecture": target_fingerprint.architecture_name,
            },
        )


# ──────────────────────────────────────────────
# 3. GENERATE SYNTHETIC DATA (for demo)
# ──────────────────────────────────────────────

def generate_synthetic_agent_data(
    n_baseline_runs: int = 20,
    n_variant_runs: int = 20,
    n_noise_runs: int = 10,
    treatment_effect: float = 0.05,
    random_seed: int = 42,
) -> tuple[list[AgentBehaviorFingerprint], list[AgentBehaviorFingerprint], list[AgentBehaviorFingerprint]]:
    """
    Generate synthetic agent fingerprints for demo purposes.

    The baseline agent has a certain performance profile.
    The variant agent has the same profile PLUS a treatment effect
    (which can be positive = improvement, negative = regression).
    The noise runs are the SAME agent with different seeds.

    Task types simulate 6 common agent tasks.
    """
    np.random.seed(random_seed)

    task_types = [
        "retrieval",
        "synthesis",
        "execution",
        "verification",
        "planning",
        "debugging",
    ]

    # Baseline performance profile (per task type)
    base_accuracy = {
        "retrieval": 0.88, "synthesis": 0.72, "execution": 0.65,
        "verification": 0.91, "planning": 0.78, "debugging": 0.58,
    }
    base_guardrail = {
        "retrieval": 0.02, "synthesis": 0.08, "execution": 0.15,
        "verification": 0.01, "planning": 0.05, "debugging": 0.12,
    }
    base_reflection = {
        "retrieval": 0.10, "synthesis": 0.25, "execution": 0.08,
        "verification": 0.30, "planning": 0.35, "debugging": 0.15,
    }
    base_diversity = {
        "retrieval": 0.40, "synthesis": 0.60, "execution": 0.50,
        "verification": 0.30, "planning": 0.70, "debugging": 0.45,
    }
    base_latency = {
        "retrieval": 2.0, "synthesis": 8.0, "execution": 5.0,
        "verification": 3.0, "planning": 4.0, "debugging": 10.0,
    }

    def make_fingerprint(
        name: str,
        run_id: str,
        noise_std: float = 0.03,
        effect: float = 0.0,
        effect_by_task: dict[str, float] | None = None,
    ) -> AgentBehaviorFingerprint:
        """Create a fingerprint with gaussian noise and optional treatment effect."""
        if effect_by_task is None:
            effect_by_task = {tt: effect for tt in task_types}

        acc = {}
        gr = {}
        ref = {}
        div = {}
        lat = {}
        for tt in task_types:
            e = effect_by_task.get(tt, 0.0)
            acc[tt] = np.clip(base_accuracy[tt] + e + np.random.normal(0, noise_std), 0, 1)
            gr[tt] = np.clip(base_guardrail[tt] - e * 0.5 + np.random.normal(0, noise_std * 0.5), 0, 1)
            ref[tt] = np.clip(base_reflection[tt] + np.random.normal(0, noise_std * 1.5), 0, 1)
            div[tt] = np.clip(base_diversity[tt] + np.random.normal(0, noise_std), 0, 1)
            lat[tt] = max(0.5, base_latency[tt] - e * 10 + np.random.normal(0, noise_std * 2))

        return AgentBehaviorFingerprint(
            architecture_name=name,
            run_id=run_id,
            accuracy=acc,
            guardrail_hit_rate=gr,
            reflection_ratio=ref,
            tool_diversity=div,
            latency_seconds=lat,
            total_turns=np.random.randint(50, 200),
            total_tasks=len(task_types),
        )

    # Baseline runs
    baseline = []
    for i in range(n_baseline_runs):
        fp = make_fingerprint("Baseline", f"baseline_{i}", noise_std=0.03, effect=0.0)
        baseline.append(fp)

    # Variant runs — treatment effect varies by task type
    # The treatment targets synthesis and debugging (the hard tasks)
    effect_by_task = {
        "retrieval": treatment_effect * 0.5,
        "synthesis": treatment_effect * 2.0,    # Strong effect
        "execution": treatment_effect * 1.0,
        "verification": treatment_effect * 0.3,
        "planning": treatment_effect * 0.8,
        "debugging": treatment_effect * 2.5,    # Strongest effect
    }

    variant = []
    for i in range(n_variant_runs):
        fp = make_fingerprint("Variant", f"variant_{i}", noise_std=0.03, effect_by_task=effect_by_task)
        variant.append(fp)

    # Noise ensemble — same as baseline but with extra stochasticity
    noise = []
    for i in range(n_noise_runs):
        fp = make_fingerprint("SameAgent", f"noise_{i}", noise_std=0.06, effect=0.0)
        noise.append(fp)

    return baseline, variant, noise


# ──────────────────────────────────────────────
# 4. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║  Optimal Fingerprinting — Causal Attribution for Agents     ║")
    print("  ║  Climate attribution method adapted for agent evaluation     ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Generate synthetic agent data ──
    print("  Generating synthetic agent fingerprints...")
    print("  Task types: retrieval, synthesis, execution, verification, planning, debugging")
    print()

    baseline, variant, noise = generate_synthetic_agent_data(
        n_baseline_runs=20,
        n_variant_runs=20,
        n_noise_runs=10,
        treatment_effect=0.05,  # 5% average improvement
    )

    # Target: the mean of the variant ensemble (treated as "observed" agent)
    target = AgentBehaviorFingerprint(
        architecture_name="Target (Variant Ensemble Mean)",
        run_id="target_mean",
        accuracy={tt: np.mean([fp.accuracy[tt] for fp in variant]) for tt in variant[0].accuracy},
        guardrail_hit_rate={tt: np.mean([fp.guardrail_hit_rate[tt] for fp in variant]) for tt in variant[0].guardrail_hit_rate},
        reflection_ratio={tt: np.mean([fp.reflection_ratio[tt] for fp in variant]) for tt in variant[0].reflection_ratio},
        tool_diversity={tt: np.mean([fp.tool_diversity[tt] for fp in variant]) for tt in variant[0].tool_diversity},
        latency_seconds={tt: np.mean([fp.latency_seconds[tt] for fp in variant]) for tt in variant[0].latency_seconds},
        total_turns=100,
        total_tasks=6,
    )

    # Baseline ensemble mean (for comparison)
    baseline_mean_fp = AgentBehaviorFingerprint(
        architecture_name="Baseline Ensemble Mean",
        run_id="baseline_mean",
        accuracy={tt: np.mean([fp.accuracy[tt] for fp in baseline]) for tt in baseline[0].accuracy},
        guardrail_hit_rate={tt: np.mean([fp.guardrail_hit_rate[tt] for fp in baseline]) for tt in baseline[0].guardrail_hit_rate},
        reflection_ratio={tt: np.mean([fp.reflection_ratio[tt] for fp in baseline]) for tt in baseline[0].reflection_ratio},
        tool_diversity={tt: np.mean([fp.tool_diversity[tt] for fp in baseline]) for tt in baseline[0].tool_diversity},
        latency_seconds={tt: np.mean([fp.latency_seconds[tt] for fp in baseline]) for tt in baseline[0].latency_seconds},
        total_turns=100,
        total_tasks=6,
    )

    # ── Run attribution ──
    print("─" * 56)
    print("  Running optimal fingerprinting attribution...")
    print("─" * 56)
    print()

    fp = OptimalFingerprint(detection_threshold=0.10, noise_threshold=0.03)

    # Use the actual ensemble means as target to get cleaner attribution
    # (In real use, the target would be the actual observed agent behavior)
    result = fp.attribute(target, baseline, variant, noise_ensemble=noise)

    # ── Side-by-side comparison ──
    print("─" * 56)
    print("  Baseline vs Variant — Accuracy by Task Type")
    print("─" * 56)
    print()
    print(f"  {'Task':>15s}  {'Baseline':>10s}  {'Variant':>10s}  {'Δ':>8s}  {'Attribution':>15s}")
    print(f"  {'─'*15}  {'─'*10}  {'─'*10}  {'─'*8}  {'─'*15}")
    for tt in sorted(target.accuracy.keys()):
        base_val = baseline_mean_fp.accuracy[tt]
        var_val = target.accuracy[tt]
        delta = var_val - base_val
        attr = result.attributions[tt]
        attr_sym = "✓" if attr == "detected" else "∼" if attr == "inconclusive" else "✗"
        print(f"  {tt:>15s}  {base_val:>7.1%}  {var_val:>7.1%}  {delta:>+7.1%}  {attr_sym:>3s} {attr:>12s}")
    print()


    # ── Multi-Model Ensemble Summary ──
    print("─" * 56)
    print("  Multi-Model Ensemble Analysis")
    print("─" * 56)
    print()

    n_detected = sum(1 for v in result.attributions.values() if v == "detected")
    n_inconclusive = sum(1 for v in result.attributions.values() if v == "inconclusive")
    n_not = sum(1 for v in result.attributions.values() if v == "not_detected")

    print(f"  Task types with DETECTED effect:      {n_detected}")
    print(f"  Task types with INCONCLUSIVE effect:  {n_inconclusive}")
    print(f"  Task types with NOT DETECTED effect:  {n_not}")
    print()

    # Climate-style attribution statement
    print(f"  ATTRIBUTION STATEMENT:")
    print(f"  {'=' * 40}")
    if n_detected >= 3:
        print("  The variant architecture has a DETECTABLE causal effect")
        print(f"  on agent behavior across {n_detected} of 6 task types.")
        print(f"  This is the agent equivalent of 'human forcing detected'")
        print(f"  in climate attribution.")
    elif n_detected >= 1:
        print("  A LIMITED causal effect is detectable in")
        print(f"  {n_detected} task type(s). Other task types show no")
        print("  reliable difference beyond structural uncertainty.")
        print("  Equivalent to 'regional attribution' in climate science.")
    else:
        print("  No DETECTABLE causal effect. The observed behavior")
        print("  differences are within the range of structural")
        print("  uncertainty (stochastic variation). More data needed.")
        print("  Equivalent to 'no detectable human signal' in climate analysis.")
    print()

    # ── Summary metrics ──
    print("─" * 56)
    print("  Attribution Summary Metrics")
    print("─" * 56)
    print(f"  Fingerprint correlation: {result.fingerprint_correlation:.3f}")
    print(f"  Variance explained:      {result.total_variance_explained:.1%}")
    print(f"  R²:                      {result.r_squared:.3f}")
    print(f"  Models in baseline:      {result.details['n_baseline']}")
    print(f"  Models in variant:       {result.details['n_variant']}")
    print(f"  Noise ensemble size:     {result.details['n_noise']}")
    print()

    print("═" * 56)
    print("  Interpretation (climate → agent):")
    print("═" * 56)
    print("  Climate detection:   Observed change exceeds internal variability")
    print("  Agent detection:     Behavior difference exceeds structural noise")
    print()
    print("  Climate attribution: Model-simulated response fits observed pattern")
    print("  Agent attribution:   Architecture-variant fingerprints fit target")
    print()
    print("  Climate uncertainty: Multi-model ensemble spread")
    print("  Agent uncertainty:   Multi-architecture run spread")
    print()


if __name__ == "__main__":
    main()
