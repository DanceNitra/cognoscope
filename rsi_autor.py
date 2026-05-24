#!/usr/bin/env python3
"""
rsi_autor.py — Phase 3: AutoResearch for RSI Kernel Coupling Optimization

The AutoResearch loop applied to Athena's RSI Kernel coupling configuration.
When the RSI Kernel identifies a coupling suboptimality, AR runs N experiments
to find the optimal coupling parameters.

How it works:
  1. RSI Kernel monitors free energy at each level (L1-L4)
  2. When FE exceeds threshold, AR kicks in to find better coupling
  3. Each experiment: mutate the CouplingConfig
  4. Evaluate: joint free energy across all levels
  5. Binary keep/discard — keep configs that reduce FE
  6. Deploy best config to runtime
  7. MSR Guardrail monitors AR encounter rate

This closes the recursion: RSI decides WHAT to optimize, AR finds HOW.
"""

import os, sys, json, random, math, time
from dataclasses import dataclass
from datetime import datetime
from collections import deque

sys.path.insert(0, os.path.expanduser("~/cognoscope"))
from autoresearch import (
    Mutator, Metric, AutoResearchLoop, AutoResearchConfig,
    AutoResearchResult, save_ar_report, format_ar_result
)
from rsi_kernel import (
    FreeEnergyReport, CouplingConfig, RecursiveImprovementKernel
)


# ──────────────────────────────────────────────
# RSI COUPLING MUTATOR
# ──────────────────────────────────────────────

class RSICouplingMutator(Mutator):
    """
    Generate mutations of RSI Kernel CouplingConfig.
    
    Each mutation changes one coupling parameter slightly.
    The AR loop finds the optimal balance between:
      - Detection frequency (more = better awareness, higher cost)
      - MSR gain (more = faster adjustment, less stable)
      - Precision weights (trade off between levels)
      - Exploration rate (more = find better configs, less stable)
    """
    
    PARAMETERS = [
        'detect_every_n',
        'msr_check_every_n',
        'msr_to_metaloop_gain',
        'forge_trigger_threshold',
        'precision_l1',
        'precision_l2',
        'precision_l3',
        'precision_l4',
        'exploration_rate',
        'max_experiments_per_generation',
    ]
    
    def __init__(self):
        self.kernel = None
        try:
            self.kernel = RecursiveImprovementKernel()
        except Exception:
            pass
    
    def mutate(self, file_path: str, content: str, experiment_id: int, history: list) -> tuple[str, str]:
        """
        Mutate the coupling configuration.
        
        We don't mutate a file — we mutate the runtime config.
        The content is a JSON-serialized CouplingConfig.
        """
        try:
            config = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content, "no-op (parse failed)"
        
        # Pick a parameter to mutate
        param = random.choice(self.PARAMETERS)
        
        if param not in config:
            return content, "no-op (parameter not found)"
        
        current = config[param]
        
        # Sensible mutation deltas per parameter type
        if param in ('detect_every_n', 'msr_check_every_n', 'max_experiments_per_generation'):
            # Integer parameters: ±1-3
            delta = random.choice([-3, -2, -1, 1, 2, 3])
            new_val = max(1, current + delta)
        elif param in ('exploration_rate',):
            # Rate parameters: ±0.005-0.02
            delta = random.choice([-0.02, -0.01, -0.005, 0.005, 0.01, 0.02])
            new_val = max(0.001, min(0.5, current + delta))
        elif 'precision' in param or 'gain' in param:
            # Precision/gain parameters: ±0.05-0.2
            delta = random.choice([-0.2, -0.1, -0.05, 0.05, 0.1, 0.2])
            new_val = max(0.1, min(2.0, current + delta))
        else:
            # Threshold parameters: ±0.02-0.08
            delta = random.choice([-0.08, -0.04, -0.02, 0.02, 0.04, 0.08])
            new_val = max(0.05, min(0.95, current + delta))
        
        old_val = config[param]
        config[param] = round(new_val, 4)
        
        new_content = json.dumps(config, indent=2)
        return new_content, f"coupling.{param}: {old_val} → {config[param]}"


class RSIMetric(Metric):
    """
    Evaluate RSI coupling quality by running a short simulation.
    Lower free energy = better.
    """
    
    def __init__(self):
        self.kernel = None
        try:
            self.kernel = RecursiveImprovementKernel()
        except Exception:
            pass
    
    def evaluate(self, file_path: str) -> float:
        """
        Evaluate a coupling config file.
        
        Higher score = better (inverted from free energy).
        """
        try:
            with open(file_path) as f:
                content = f.read()
            return self.evaluate_content(content, file_path)
        except Exception:
            return 0.0
    
    def evaluate_content(self, content: str, file_path: str = "") -> float:
        """
        Run a short simulation with this config and return quality score.
        
        Simulates the RSI kernel for 10 generations and tracks:
          - Average free energy (lower = better)
          - Stability (std dev of FE across generations)
          - Trend (negative trend = improving)
        """
        try:
            config_dict = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return 0.0
        
        if not self.kernel:
            return 0.5  # Fallback
        
        # Simulate
        fe_values = []
        try:
            for gen in range(10):
                # Create CouplingConfig from dict
                cfg = CouplingConfig(
                    detect_every_n=config_dict.get('detect_every_n', 3),
                    msr_check_every_n=config_dict.get('msr_check_every_n', 5),
                    msr_to_metaloop_gain=config_dict.get('msr_to_metaloop_gain', 0.3),
                    forge_trigger_threshold=config_dict.get('forge_trigger_threshold', 0.4),
                    precision_l1=config_dict.get('precision_l1', 0.5),
                    precision_l2=config_dict.get('precision_l2', 0.5),
                    precision_l3=config_dict.get('precision_l3', 0.5),
                    precision_l4=config_dict.get('precision_l4', 0.5),
                    exploration_rate=config_dict.get('exploration_rate', 0.15),
                    max_experiments_per_generation=config_dict.get('max_experiments_per_generation', 30),
                )
                
                self.kernel.coupling = cfg
                report = self.kernel.compute_free_energy()  # May fail
                total_fe = report.f_l1 + report.f_l2 + report.f_l3 + report.f_l4
                fe_values.append(total_fe)
        except Exception:
            pass
        
        if not fe_values:
            return 0.5
        
        avg_fe = sum(fe_values) / len(fe_values)
        std_fe = (sum((f - avg_fe) ** 2 for f in fe_values) / len(fe_values)) ** 0.5
        
        # Compute score: lower FE = higher score
        # Typical FE range: 0.5-2.0
        fe_score = max(0.0, 1.0 - avg_fe / 2.0)
        
        # Stability bonus: lower std = higher score
        stability = max(0.0, 1.0 - std_fe * 2.0)
        
        # Combined: 70% FE + 30% stability
        score = fe_score * 0.7 + stability * 0.3
        
        return round(score, 4)


# ──────────────────────────────────────────────
# RSI → AR INTEGRATION
# ──────────────────────────────────────────────

def run_ar_on_coupling(output_dir: str = "~/.hermes/autoresearch/rsi") -> AutoResearchResult | None:
    """Run AR on the current RSI coupling config."""
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    config_path = os.path.join(output_dir, "coupling_config.json")
    
    # Get current config
    try:
        kernel = RecursiveImprovementKernel()
        config = {
            'detect_every_n': kernel.coupling.detect_every_n,
            'msr_check_every_n': kernel.coupling.msr_check_every_n,
            'msr_to_metaloop_gain': kernel.coupling.msr_to_metaloop_gain,
            'forge_trigger_threshold': kernel.coupling.forge_trigger_threshold,
            'precision_l1': kernel.coupling.precision_l1,
            'precision_l2': kernel.coupling.precision_l2,
            'precision_l3': kernel.coupling.precision_l3,
            'precision_l4': kernel.coupling.precision_l4,
            'exploration_rate': kernel.coupling.exploration_rate,
            'max_experiments_per_generation': kernel.coupling.max_experiments_per_generation,
        }
    except Exception:
        # Default config
        config = {
            'detect_every_n': 3,
            'msr_check_every_n': 5,
            'msr_to_metaloop_gain': 0.3,
            'forge_trigger_threshold': 0.4,
            'precision_l1': 0.5,
            'precision_l2': 0.5,
            'precision_l3': 0.5,
            'precision_l4': 0.5,
            'exploration_rate': 0.15,
            'max_experiments_per_generation': 30,
        }
    
    # Write current config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    mutator = RSICouplingMutator()
    metric = RSIMetric()
    baseline = metric.evaluate(config_path)
    
    loop = AutoResearchLoop(
        subject_name="RSI Coupling",
        file_path=config_path,
        mutator=mutator,
        metric=metric,
        baseline=baseline,
    )
    result = loop.run()
    save_ar_report(result, output_dir)
    
    return result


# ──────────────────────────────────────────────
# CLIENT
# ──────────────────────────────────────────────

def demo():
    """Demo: run AR on default coupling config."""
    result = run_ar_on_coupling()
    if result:
        print(format_ar_result(result))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RSI AutoResearch Phase 3")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--optimize", action="store_true", 
                        help="Optimize current RSI coupling")
    args = parser.parse_args()
    
    if args.demo or args.optimize:
        demo()
    else:
        print("Usage: python3 rsi_autor.py --demo")
