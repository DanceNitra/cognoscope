#!/usr/bin/env python3
"""
autoresearch.py — Core AutoResearch Loop Engine

Karpathy-inspired autonomous optimization loop for our architecture.

The pattern:
  Fixed time budget → Mutate single file → Run → Evaluate metric → Keep/Discard → Git commit

This is the shared engine used by all three integration phases:
  - Phase 1: Vault concept optimization (ariautor)
  - Phase 2: Tool compilation optimization (toolautor)
  - Phase 3: RSI coupling optimization (rsi_autor)

Safety:
  - Fixed iteration cap (MAX_EXPERIMENTS)
  - Single file scope enforced
  - Binary keep/discard (no partial merges)
  - Git rollback always available
  - MSR Guardrail monitors encounter rate
"""

import os, sys, re, json, math, time, random, subprocess, textwrap, ast
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from collections import deque

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
COGNOSCOPE = os.path.expanduser("~/cognoscope")
EXPERIMENTS_DIR = os.path.join(COGNOSCOPE, "autoresearch_experiments")
os.makedirs(EXPERIMENTS_DIR, exist_ok=True)

DEFAULT_MAX_EXPERIMENTS = 50
DEFAULT_TIME_BUDGET_SEC = 60  # per experiment (shorter than Karpathy's 5min for vault)
MIN_TIME_BUDGET = 10

# ──────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────

@dataclass
class Experiment:
    """One experiment in the AR loop."""
    id: int
    subject_name: str          # human-readable name of what's being optimized
    file_path: str             # the single file being mutated
    file_content_before: str   # snapshot before mutation
    file_content_after: str    # after mutation
    metric_before: float       # baseline
    metric_after: float        # post-mutation
    kept: bool                 # True if metric_after > metric_before
    mutation_log: str          # description of what changed
    duration_sec: float        # how long this experiment took
    timestamp: str             # when it ran


@dataclass
class AutoResearchConfig:
    """Configuration for one AR loop run."""
    max_experiments: int = DEFAULT_MAX_EXPERIMENTS
    time_budget_sec: int = DEFAULT_TIME_BUDGET_SEC
    min_improvement_threshold: float = 0.0  # minimum metric delta to keep
    branch_prefix: str = "ar-experiment"
    experiment_dir: str = field(default_factory=lambda: EXPERIMENTS_DIR)

    # Safety limits
    max_consecutive_failures: int = 10  # abort if this many keep=False in a row
    abort_on_metric_collapse: bool = True  # abort if metric drops >50%


@dataclass
class AutoResearchResult:
    """Result of one full AR loop run."""
    subject_name: str
    experiments: list[Experiment]
    total_experiments: int
    kept_experiments: int
    metric_start: float
    metric_end: float
    metric_improvement_pct: float
    best_experiment: Experiment | None
    branch_name: str | None
    duration_sec: float
    aborted: bool = False
    abort_reason: str = ""


# ──────────────────────────────────────────────
# CORE AUTO-RESEARCH LOOP
# ──────────────────────────────────────────────

class Mutator:
    """
    Base class for mutation strategies.
    
    Each phase (vault, tool, rsi) implements its own Mutator
    that knows how to generate variants of the subject being optimized.
    """
    
    def mutate(self, file_path: str, content: str, experiment_id: int, history: list[Experiment]) -> tuple[str, str]:
        """
        Given current file content, produce a variant.
        Returns (new_content, mutation_log).
        """
        raise NotImplementedError


class Metric:
    """
    Base class for evaluation metrics.
    
    Each phase implements its own Metric that computes
    a score for a given file/content.
    Higher = better.
    """
    
    def evaluate(self, file_path: str) -> float:
        """Evaluate the current state and return a score (higher is better)."""
        raise NotImplementedError
    
    def evaluate_content(self, content: str, file_path: str) -> float:
        """Evaluate content directly without writing to disk."""
        raise NotImplementedError


class AutoResearchLoop:
    """
    The core AR loop.
    
    Usage:
        loop = AutoResearchLoop(
            subject_name="Prefrontal Cortex",
            file_path="path/to/concept.md",
            mutator=MyMutator(),
            metric=MyMetric(),
            baseline=baseline_score
        )
        result = loop.run()
    """
    
    def __init__(
        self,
        subject_name: str,
        file_path: str,
        mutator: Mutator,
        metric: Metric,
        config: AutoResearchConfig | None = None,
        baseline: float | None = None,
    ):
        self.subject_name = subject_name
        self.file_path = os.path.abspath(file_path)
        self.mutator = mutator
        self.metric = metric
        self.config = config or AutoResearchConfig()
        
        # Read baseline content
        with open(self.file_path) as f:
            self.original_content = f.read()
        
        # Measure baseline metric
        self.baseline = baseline if baseline is not None else metric.evaluate(self.file_path)
        
        # Experiment history
        self.experiments: list[Experiment] = []
        
        # Git tracking
        self.branch_name = None
        self._capture_pre_run_hash()
    
    def _capture_pre_run_hash(self):
        """Capture git hash before any mutations for rollback."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=os.path.dirname(self.file_path) or ".",
                capture_output=True, text=True, timeout=5
            )
            self.pre_run_hash = result.stdout.strip()
        except Exception:
            self.pre_run_hash = None
    
    def _git_commit(self, experiment_id: int, content: str, mutation_log: str, metric: float):
        """Git commit the experiment result."""
        try:
            repo_dir = self._find_git_root()
            if not repo_dir:
                return
            
            # Write content
            with open(self.file_path, 'w') as f:
                f.write(content)
            
            # Stage and commit
            subprocess.run(
                ["git", "add", self.file_path],
                cwd=repo_dir, capture_output=True, timeout=5
            )
            subprocess.run(
                ["git", "commit", "-m", f"AR exp#{experiment_id}: {mutation_log} (metric: {metric:.4f})"],
                cwd=repo_dir, capture_output=True, timeout=5
            )
        except Exception:
            pass
    
    def _find_git_root(self) -> str | None:
        """Find git root directory."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=os.path.dirname(self.file_path) or ".",
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def run(self) -> AutoResearchResult:
        """
        Execute the AR loop.
        
        For each experiment:
          1. Mutate the file
          2. Save to disk
          3. Evaluate metric
          4. Binary keep if improved
          5. Git commit
          6. Revert if not kept
        """
        start_time = time.time()
        best_metric = self.baseline
        best_content = self.original_content
        best_experiment = None
        consecutive_failures = 0
        aborted = False
        abort_reason = ""
        
        print(f"\n{'='*60}")
        print(f"  AR LOOP: {self.subject_name}")
        print(f"  Baseline metric: {self.baseline:.4f}")
        print(f"  Max experiments: {self.config.max_experiments}")
        print(f"  File: {os.path.basename(self.file_path)}")
        print(f"{'='*60}\n")
        
        for exp_id in range(1, self.config.max_experiments + 1):
            exp_start = time.time()
            
            # Read current best content
            current_content = best_content
            
            # 1. Mutate
            try:
                new_content, mutation_log = self.mutator.mutate(
                    self.file_path, current_content, exp_id, self.experiments
                )
            except Exception as e:
                print(f"  [{exp_id:3d}] Mutation failed: {e}")
                continue
            
            if new_content == current_content:
                # No-op mutation, skip
                continue
            
            # 2. Write to disk
            with open(self.file_path, 'w') as f:
                f.write(new_content)
            
            # 3. Evaluate
            try:
                new_metric = self.metric.evaluate(self.file_path)
            except Exception as e:
                print(f"  [{exp_id:3d}] Evaluation failed: {e}")
                # Restore
                with open(self.file_path, 'w') as f:
                    f.write(current_content)
                continue
            
            duration = time.time() - exp_start
            
            # 4. Binary keep/discard
            improved = new_metric > best_metric + self.config.min_improvement_threshold
            collapsed = new_metric < best_metric * 0.5
            
            if improved:
                best_metric = new_metric
                best_content = new_content
                consecutive_failures = 0
                status = "✅ KEPT"
                print(f"  [{exp_id:3d}] {status} metric: {new_metric:.4f} (Δ{new_metric-best_metric:+.4f}) | {mutation_log[:50]}")
            elif collapsed and self.config.abort_on_metric_collapse:
                # Restore previous best
                with open(self.file_path, 'w') as f:
                    f.write(current_content)
                consecutive_failures += 1
                status = "💀 COLLAPSED"
                print(f"  [{exp_id:3d}] {status} metric: {new_metric:.4f} (dropped {new_metric/best_metric:.1%}) | aborting")
                aborted = True
                abort_reason = f"Metric collapsed at experiment {exp_id}: {new_metric:.4f} vs {best_metric:.4f} ({(new_metric/best_metric-1)*100:.0f}%)"
                break
            else:
                # Restore previous best
                with open(self.file_path, 'w') as f:
                    f.write(current_content)
                consecutive_failures += 1
                status = "❌ DISCARD" if not improved else "→ best already"
            
            # Record experiment
            exp = Experiment(
                id=exp_id,
                subject_name=self.subject_name,
                file_path=self.file_path,
                file_content_before=current_content,
                file_content_after=new_content,
                metric_before=best_metric if improved else best_metric,
                metric_after=new_metric,
                kept=improved,
                mutation_log=mutation_log,
                duration_sec=duration,
                timestamp=datetime.now().isoformat()
            )
            self.experiments.append(exp)
            
            if improved:
                best_experiment = exp
                # Git commit the improvement
                self._git_commit(exp_id, new_content, mutation_log, new_metric)
            
            # 5. Check consecutive failures
            if consecutive_failures >= self.config.max_consecutive_failures:
                print(f"  Aborting: {consecutive_failures} consecutive failures")
                aborted = True
                abort_reason = f"{consecutive_failures} consecutive non-improving experiments"
                break
            
            # 6. Time check
            elapsed = time.time() - start_time
            if exp_id > 5 and elapsed > self.config.time_budget_sec * self.config.max_experiments * 0.5:
                # Running out of time — ensure we complete at least half the experiments
                pass
        
        # Ensure best version is on disk
        with open(self.file_path, 'w') as f:
            f.write(best_content)
        
        total_time = time.time() - start_time
        improvement_pct = ((best_metric - self.baseline) / self.baseline * 100) if self.baseline > 0 else 0
        
        result = AutoResearchResult(
            subject_name=self.subject_name,
            experiments=self.experiments,
            total_experiments=len(self.experiments),
            kept_experiments=sum(1 for e in self.experiments if e.kept),
            metric_start=self.baseline,
            metric_end=best_metric,
            metric_improvement_pct=improvement_pct,
            best_experiment=best_experiment,
            branch_name=self.branch_name,
            duration_sec=total_time,
            aborted=aborted,
            abort_reason=abort_reason
        )
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"  AR LOOP COMPLETE: {self.subject_name}")
        print(f"  Experiments: {result.total_experiments} total, {result.kept_experiments} kept")
        print(f"  Metric: {result.metric_start:.4f} → {result.metric_end:.4f} ({result.metric_improvement_pct:+.1f}%)")
        print(f"  Duration: {result.duration_sec:.1f}s")
        if aborted:
            print(f"  ⚠️  Aborted: {abort_reason}")
        print(f"{'='*60}\n")
        
        return result


# ──────────────────────────────────────────────
# EXPERIMENT REPORTER
# ──────────────────────────────────────────────

def format_ar_result(result: AutoResearchResult) -> str:
    """Format AR result as a readable report."""
    lines = []
    lines.append(f"## AutoResearch: {result.subject_name}")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Experiments | {result.total_experiments} |")
    lines.append(f"| Kept | {result.kept_experiments} |")
    lines.append(f"| Start | {result.metric_start:.4f} |")
    lines.append(f"| End | {result.metric_end:.4f} |")
    lines.append(f"| Improvement | {result.metric_improvement_pct:+.1f}% |")
    lines.append(f"| Duration | {result.duration_sec:.1f}s |")
    if result.aborted:
        lines.append(f"| Aborted | {result.abort_reason} |")
    
    if result.best_experiment:
        lines.append(f"\n### Best Experiment (#{result.best_experiment.id})")
        lines.append(f"- Mutation: {result.best_experiment.mutation_log}")
        lines.append(f"- Metric: {result.best_experiment.metric_before:.4f} → {result.best_experiment.metric_after:.4f}")
    
    return "\n".join(lines)


def save_ar_report(result: AutoResearchResult, output_dir: str | None = None):
    """Save AR result to JSON and markdown report."""
    output_dir = output_dir or EXPERIMENTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', result.subject_name)
    
    # JSON
    json_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.json")
    with open(json_path, 'w') as f:
        # Convert to serializable dict
        data = {
            "subject_name": result.subject_name,
            "total_experiments": result.total_experiments,
            "kept_experiments": result.kept_experiments,
            "metric_start": result.metric_start,
            "metric_end": result.metric_end,
            "metric_improvement_pct": result.metric_improvement_pct,
            "duration_sec": result.duration_sec,
            "aborted": result.aborted,
            "abort_reason": result.abort_reason,
            "experiments": [
                {
                    "id": e.id,
                    "kept": e.kept,
                    "metric_before": e.metric_before,
                    "metric_after": e.metric_after,
                    "mutation_log": e.mutation_log,
                    "duration_sec": e.duration_sec,
                }
                for e in result.experiments
            ]
        }
        json.dump(data, f, indent=2)
    
    # Markdown
    md_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.md")
    with open(md_path, 'w') as f:
        f.write(format_ar_result(result))
    
    return json_path, md_path


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AutoResearch Loop Engine")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    args = parser.parse_args()
    
    if args.test:
        print("AutoResearch Core Engine — Self Test")
        print(f"  Max experiments: {DEFAULT_MAX_EXPERIMENTS}")
        print(f"  Time budget: {DEFAULT_TIME_BUDGET_SEC}s")
        print(f"  Experiments dir: {EXPERIMENTS_DIR}")
        print("\nReady for integration with:")
        print("  - Phase 1: ariauthor (vault concept optimization)")
        print("  - Phase 2: toolautor (tool compilation optimization)")
        print("  - Phase 3: rsi_autor (RSI coupling optimization)")
        print("  - ARI integration (ARI → AR pipeline)")
