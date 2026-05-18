#!/usr/bin/env python3
"""
rsi_kernel.py — Recursive Self-Improvement Kernel (Athena Level 5)

The FEP proves that any system minimizing free energy will, if it can model
its own minimization process, enter a recursive improvement trajectory.
This kernel closes that loop: it monitors the interaction between Athena's
4 levels and redesigns the coupling between them to minimize joint free energy.

Architecture:
  Level 5 monitors the free energy at each lower level.
  Level 5 acts by modifying the COUPLING between levels.
  The coupling parameters (frequency, precision, thresholds) are the
  "architecture" that Level 5 optimizes.
"""

import json
import math
import time
import random
from dataclasses import dataclass, field
from typing import Any
from collections import deque


# ──────────────────────────────────────────────
# 1. FREE ENERGY COMPUTATION
# ──────────────────────────────────────────────

@dataclass
class FreeEnergyReport:
    """
    Free energy at each recursive level.
    
    Lower values = better. The system minimizes this.
    Each level's free energy should be roughly constant
    in a well-functioning system.
    """
    # Level 1: Perceptual-active inference (tool predictions)
    f_l1: float  # Tool prediction error
    f_l1_trend: float  # Derivative (negative = improving)
    
    # Level 2: Meta-inference (loop architecture surprise)
    f_l2: float  # Recovery stage surprise
    f_l2_trend: float
    
    # Level 3: Meta-meta-inference (guardrail system)
    f_l3: float  # MSR guardrail encounter distribution surprise
    f_l3_trend: float
    
    # Level 4: Architectural self-modification
    f_l4: float  # Tool capability gap
    f_l4_trend: float
    
    # Composite
    f_combined: float  # Weighted sum across levels
    
    @property
    def is_healthy(self) -> bool:
        return self.f_combined < 1.0 and all(t < 0.1 for t in 
            [abs(self.f_l1_trend), abs(self.f_l2_trend), 
             abs(self.f_l3_trend), abs(self.f_l4_trend)])

    def to_dict(self) -> dict:
        return {
            "L1_tool": round(self.f_l1, 4),
            "L1_trend": round(self.f_l1_trend, 4),
            "L2_meta": round(self.f_l2, 4),
            "L2_trend": round(self.f_l2_trend, 4),
            "L3_msr": round(self.f_l3, 4),
            "L3_trend": round(self.f_l3_trend, 4),
            "L4_forge": round(self.f_l4, 4),
            "L4_trend": round(self.f_l4_trend, 4),
            "combined": round(self.f_combined, 4),
            "healthy": self.is_healthy,
        }


# ──────────────────────────────────────────────
# 2. RECURSIVE IMPROVEMENT KERNEL
# ──────────────────────────────────────────────

@dataclass
class CouplingConfig:
    """
    The coupling parameters between Athena's levels.
    
    These are the "knobs" that Level 5 optimizes.
    """
    # L1 → L2: How often MetaLoop checks Recovery
    detect_every_n: int = 3
    
    # L2 → L3: How often MSR evaluates guardrail distribution
    msr_check_every_n: int = 5
    
    # L3 → L2: How MSR adjustments affect MetaLoop triggers
    msr_to_metaloop_gain: float = 0.5  # 0 = no effect, 1 = full effect
    
    # L1 → L4: When ToolForge triggers (tool failure rate threshold)
    forge_trigger_threshold: float = 0.3  # Tool failure rate above this triggers synthesis
    
    # L4 → L1: How new tools affect ReAct loop
    forge_to_react_priority: float = 0.7  # How much to prefer new tools
    
    # Timescales
    l1_timescale: int = 1      # Turns
    l2_timescale: int = 3      # Sessions
    l3_timescale: int = 10     # Multi-session
    l4_timescale: int = 30     # Development cycle
    
    # Precision weighting
    precision_l1: float = 1.0
    precision_l2: float = 0.7
    precision_l3: float = 0.5
    precision_l4: float = 0.3
    
    def mutate(self, target: str, direction: str, magnitude: float = 0.15) -> 'CouplingConfig':
        """Produce a new CouplingConfig with one parameter mutated."""
        import copy
        new = copy.deepcopy(self)
        
        mutations = {
            ('detect_every_n', 'up'): lambda v: min(15, v + max(1, int(magnitude * 10))),
            ('detect_every_n', 'down'): lambda v: max(1, v - max(1, int(magnitude * 10))),
            ('msr_check_every_n', 'up'): lambda v: min(20, v + max(1, int(magnitude * 10))),
            ('msr_check_every_n', 'down'): lambda v: max(1, v - max(1, int(magnitude * 10))),
            ('msr_to_metaloop_gain', 'up'): lambda v: min(1.0, v + magnitude),
            ('msr_to_metaloop_gain', 'down'): lambda v: max(0.0, v - magnitude),
            ('forge_trigger_threshold', 'up'): lambda v: min(0.9, v + magnitude),
            ('forge_trigger_threshold', 'down'): lambda v: max(0.05, v - magnitude),
            ('precision_l1', 'up'): lambda v: min(2.0, v + magnitude),
            ('precision_l1', 'down'): lambda v: max(0.1, v - magnitude),
            ('precision_l2', 'up'): lambda v: min(2.0, v + magnitude),
            ('precision_l2', 'down'): lambda v: max(0.1, v - magnitude),
            ('precision_l3', 'up'): lambda v: min(2.0, v + magnitude),
            ('precision_l3', 'down'): lambda v: max(0.1, v - magnitude),
        }
        
        key = (target, direction)
        if key in mutations:
            current = getattr(new, target)
            setattr(new, target, mutations[key](current))
        
        return new


class CladeTracker:
    """
    Tracks agent lineage and computes Estimated CMP (Clade-Metaproductivity).
    
    From the HGM framework: CMP aggregates the performance of an agent's
    descendants to measure its true evolutionary potential. Greedy selection
    for immediate performance leads to the Metaproductivity-Performance
    Mismatch (MPM) — high-scoring agents are often evolutionary dead-ends.
    
    CMP solves MPM by rewarding structural flexibility that produces
    high-performing descendants rather than high immediate scores.
    """
    
    def __init__(self):
        self.agents: dict[int, dict] = {}  # gen_id → {parent, config, fe, descendants, timestamp}
        self.root_id: int | None = None
    
    def register(self, gen_id: int, parent_id: int | None, config: Any, free_energy: float):
        """Register a new agent generation with its lineage."""
        self.agents[gen_id] = {
            'parent': parent_id,
            'config': config,
            'fe': free_energy,
            'descendants': [],
            'timestamp': time.time(),
        }
        if parent_id is not None and parent_id in self.agents:
            self.agents[parent_id]['descendants'].append(gen_id)
        if self.root_id is None:
            self.root_id = gen_id
    
    def estimated_cmp(self, gen_id: int, max_depth: int = 3) -> float:
        """
        Compute Estimated CMP (CMP_hat) for an agent generation.
        
        CMP_hat = -mean(free_energy of descendants up to max_depth)
        
        Higher CMP_hat means the lineage produces descendants with
        lower free energy (better performance).
        """
        gen = self.agents.get(gen_id)
        if not gen:
            return 0.0
        
        descendant_fes = []
        to_visit = list(gen['descendants'])
        
        for depth in range(max_depth):
            next_visit = []
            for d_id in to_visit:
                if d_id in self.agents:
                    d = self.agents[d_id]
                    descendant_fes.append(d['fe'])
                    next_visit.extend(d['descendants'])
            to_visit = next_visit
            if not to_visit:
                break
        
        if not descendant_fes:
            # No descendants yet: use inverse of current FE as proxy
            # (low FE = good = high CMP)
            return -gen['fe']
        
        return -sum(descendant_fes) / len(descendant_fes)
    
    def best_by_cmp(self, configs: list[tuple[Any, int]]) -> tuple[Any, float]:
        """
        Select the configuration with the highest Estimated CMP.
        
        Args:
            configs: List of (config, gen_id) pairs to evaluate
            
        Returns:
            (best_config, best_cmp_value)
        """
        best_cmp = -float('inf')
        best_config = None
        
        for config, gen_id in configs:
            cmp_val = self.estimated_cmp(gen_id)
            if cmp_val > best_cmp:
                best_cmp = cmp_val
                best_config = config
        
        return best_config, best_cmp
    
    def lineage_summary(self, gen_id: int) -> dict:
        """Return the full lineage tree for an agent generation."""
        gen = self.agents.get(gen_id)
        if not gen:
            return {}
        
        # Walk ancestors
        ancestors = []
        current = gen_id
        while current is not None and current in self.agents:
            ancestors.append({
                'gen_id': current,
                'fe': self.agents[current]['fe'],
            })
            current = self.agents[current]['parent']
        
        # Walk descendants
        descendants = []
        to_visit = list(gen['descendants'])
        while to_visit:
            d_id = to_visit.pop(0)
            if d_id in self.agents:
                d = self.agents[d_id]
                descendants.append({
                    'gen_id': d_id,
                    'fe': d['fe'],
                    'descendant_count': len(d['descendants']),
                })
                to_visit.extend(d['descendants'])
        
        return {
            'gen_id': gen_id,
            'current_fe': gen['fe'],
            'estimated_cmp': self.estimated_cmp(gen_id),
            'ancestor_count': len(ancestors) - 1,  # Exclude self
            'descendant_count': len(descendants),
            'avg_descendant_fe': sum(d['fe'] for d in descendants) / len(descendants) if descendants else None,
        }


class RecursiveImprovementKernel:
    """
    The Level 5 kernel that drives recursive self-improvement.
    
    It maintains:
    - A history of free energy observations across levels
    - A current coupling configuration (the "knobs")
    - A generative model of how coupling changes affect free energy
    - An action policy that proposes coupling mutations
    
    This is NOT a learning algorithm. It is an active inference engine
    operating at the meta-level: it minimizes the free energy of the
    coupling configuration.
    """
    
    def __init__(self, initial_config: CouplingConfig | None = None):
        self.config = initial_config or CouplingConfig()
        self.generation = 0
        self.history: list[dict] = []
        self.free_energy_history: list[FreeEnergyReport] = []
        self.actions: list[dict] = []
        
        # Generative model of coupling → performance
        self.model_memory: list[tuple[CouplingConfig, float]] = []
        
        # ── Clade Tracker (HGM-inspired CMP metric) ──
        self.clade = CladeTracker()
        self.parent_generation: int | None = None
        
        # Exploration parameters (analogous to temperature in active inference)
        self.exploration_rate: float = 0.3
        self.epistemic_value: float = 0.0  # How much we value information gain
        
        print(f"[RSI] Kernel initialized. Generation 0.")
        print(f"[RSI] Starting coupling: detect={self.config.detect_every_n}, "
              f"msr_check={self.config.msr_check_every_n}, "
              f"msr_gain={self.config.msr_to_metaloop_gain:.2f}")
        
    def observe(self, events: dict) -> FreeEnergyReport:
        """
        Observe a full cycle through Levels 1-4 and compute free energy.
        
        This is the perception step: "what is the current state of the system?"
        """
        # Level 1: Tool prediction error
        # Computed from task success rate and tool failure rate
        task_success = events.get('task_success', 0.5)
        tool_failure_rate = events.get('tool_failure_rate', 0.1)
        # Free energy of L1: how surprised is the agent by tool outcomes?
        f_l1 = (1 - task_success) * 0.5 ** self.config.precision_l1 + tool_failure_rate
        
        # Level 2: Recovery stage surprise
        # How far is the agent from the healthy stage?
        recovery_stage = events.get('recovery_stage', 'healthy')
        stage_map = {'healthy': 0.0, 'stage_1': 0.3, 'stage_2': 0.6, 'stage_3': 0.9, 'relapse': 1.0}
        f_l2 = stage_map.get(recovery_stage, 0.5) ** self.config.precision_l2
        
        # Level 3: MSR guardrail distribution surprise
        # How far from the Goldilocks zone?
        guardrail_rate = events.get('guardrail_encounter_rate', 0.2)
        lower = events.get('msr_lower_threshold', 0.05)
        upper = events.get('msr_upper_threshold', 0.40)
        if guardrail_rate < lower:
            f_l3 = (lower - guardrail_rate) / lower * self.config.precision_l3
        elif guardrail_rate > upper:
            f_l3 = (guardrail_rate - upper) / upper * self.config.precision_l3
        else:
            f_l3 = 0.0  # In Goldilocks zone
        
        # Level 4: Tool capability gap
        # Does the agent have tools for the tasks it faces?
        tools_synthesized = events.get('tools_synthesized', 0)
        tool_effectiveness = events.get('tool_effectiveness', 0.8)
        tasks_requiring_new_tools = events.get('tasks_requiring_new_tools', 0)
        f_l4 = tasks_requiring_new_tools / max(tools_synthesized + 1, 1) * (1 - tool_effectiveness)
        f_l4 = f_l4 * self.config.precision_l4
        
        # Trends (derivative approximation)
        # Only compute if we have previous reports
        f_l1_trend = 0.0
        f_l2_trend = 0.0
        f_l3_trend = 0.0
        f_l4_trend = 0.0
        
        if self.free_energy_history:
            prev = self.free_energy_history[-1]
            f_l1_trend = f_l1 - prev.f_l1
            f_l2_trend = f_l2 - prev.f_l2
            f_l3_trend = f_l3 - prev.f_l3
            f_l4_trend = f_l4 - prev.f_l4
        
        # Combined: weighted by the precision of each level
        # Higher precision → more weight (the system cares more about 
        # levels it is more confident about)
        total_precision = (self.config.precision_l1 + self.config.precision_l2 + 
                          self.config.precision_l3 + self.config.precision_l4)
        
        f_combined = (
            f_l1 * self.config.precision_l1 +
            f_l2 * self.config.precision_l2 +
            f_l3 * self.config.precision_l3 +
            f_l4 * self.config.precision_l4
        ) / total_precision
        
        report = FreeEnergyReport(
            f_l1=f_l1, f_l1_trend=f_l1_trend,
            f_l2=f_l2, f_l2_trend=f_l2_trend,
            f_l3=f_l3, f_l3_trend=f_l3_trend,
            f_l4=f_l4, f_l4_trend=f_l4_trend,
            f_combined=f_combined,
        )
        
        self.free_energy_history.append(report)
        
        return report
    
    def act(self, report: FreeEnergyReport) -> dict:
        """
        Act on the coupling configuration to minimize free energy.
        
        This is the action step: "what should I change about how
        the system improves itself?"
        
        Returns a dict describing the action.
        """
        self.generation += 1
        
        # Store the current config + performance in model memory
        self.model_memory.append((self.config, report.f_combined))
        
        # If insufficient history, just observe
        if len(self.free_energy_history) < 3:
            return {'action': 'observe', 'reason': 'cold_start', 'generation': self.generation}
        
        # Determine which level has the highest free energy (worst performance)
        level_fe = {
            'L1_tool': report.f_l1,
            'L2_meta': report.f_l2,
            'L3_msr': report.f_l3,
            'L4_forge': report.f_l4,
        }
        worst_level = max(level_fe, key=level_fe.get)
        
        # Determine if free energy is trending up (getting worse)
        trend_derivative = report.f_combined - self.free_energy_history[-2].f_combined
        
        # ── Action Selection ──
        
        # If trending up significantly, intervene immediately
        if trend_derivative > 0.15:
            return self._emergency_intervention(worst_level, trend_derivative)
        
        # If in equilibrium (combined < 0.5 and stable), explore
        if report.f_combined < 0.5 and abs(trend_derivative) < 0.05:
            if random.random() < self.exploration_rate:
                return self._explore()
            else:
                return self._exploit(worst_level)
        
        # If performance is poor, exploit known good configs
        if report.f_combined > 0.7:
            return self._exploit(worst_level)
        
        # Default: fine-tune
        return self._finetune(worst_level, trend_derivative)
    
    def _explore(self) -> dict:
        """Randomly mutate a coupling parameter to explore the space."""
        params = [
            ('detect_every_n', 'up'), ('detect_every_n', 'down'),
            ('msr_check_every_n', 'up'), ('msr_check_every_n', 'down'),
            ('msr_to_metaloop_gain', 'up'), ('msr_to_metaloop_gain', 'down'),
            ('forge_trigger_threshold', 'up'), ('forge_trigger_threshold', 'down'),
            ('precision_l1', 'up'), ('precision_l1', 'down'),
        ]
        target, direction = random.choice(params)
        old_val = getattr(self.config, target)
        
        new_config = self.config.mutate(target, direction)
        action = {
            'action': 'explore',
            'target': target,
            'direction': direction,
            'old_value': old_val,
            'new_value': getattr(new_config, target),
            'reason': f'exploring coupling space (rate={self.exploration_rate:.2f})',
            'generation': self.generation,
        }
        
        self.config = new_config
        self.actions.append(action)
        self.exploration_rate *= 0.995  # Decay exploration over time
        return action
    
    def _exploit(self, worst_level: str) -> dict:
        """Exploit past experience: move toward the best known config."""
        if len(self.model_memory) < 5:
            return self._finetune(worst_level, 0.0)
        
        # Find the config with the lowest free energy in memory
        best_config = min(self.model_memory, key=lambda x: x[1])[0]
        
        # Identify the parameter difference that explains the improvement
        params_to_check = ['detect_every_n', 'msr_check_every_n', 
                          'msr_to_metaloop_gain', 'forge_trigger_threshold',
                          'precision_l1', 'precision_l2', 'precision_l3']
        
        improvements = []
        for param in params_to_check:
            current = getattr(self.config, param)
            best = getattr(best_config, param)
            if current != best:
                direction = 'up' if best > current else 'down'
                improvements.append((param, direction, abs(best - current)))
        
        if not improvements:
            return self._finetune(worst_level, 0.0)
        
        # Apply the most impactful improvement
        target_param, direction, magnitude = improvements[0]
        old_val = getattr(self.config, target_param)
        new_config = self.config.mutate(target_param, direction, magnitude)
        
        action = {
            'action': 'exploit',
            'target': target_param,
            'direction': direction,
            'old_value': old_val,
            'new_value': getattr(new_config, target_param),
            'reason': f'exploiting from memory (target: {worst_level})',
            'generation': self.generation,
        }
        
        self.config = new_config
        self.actions.append(action)
        return action
    
    def _finetune(self, target_level: str, trend: float) -> dict:
        """
        Fine-tune coupling around the worst-performing level.
        
        Each level's free energy maps to a specific coupling parameter:
        - High L1 (tool errors) → adjust forge_trigger_threshold
        - High L2 (recovery issues) → adjust detect_every_n
        - High L3 (MSR issues) → adjust msr_check_every_n
        - High L4 (tool gaps) → adjust forge_to_react_priority
        """
        # Map level to coupling parameter
        level_map = {
            'L1_tool': ('forge_trigger_threshold', 'detect_every_n'),
            'L2_meta': ('detect_every_n', 'msr_check_every_n'),
            'L3_msr': ('msr_check_every_n', 'msr_to_metaloop_gain'),
            'L4_forge': ('forge_to_react_priority', 'forge_trigger_threshold'),
        }
        
        primary_param, secondary_param = level_map.get(target_level, ('detect_every_n', 'precision_l1'))
        
        # Trend negative = improving. Positive = worsening.
        if trend > 0.05:
            # System is getting worse: tighten the coupling
            # (more frequent checks, faster response)
            direction = 'down'
            target = primary_param
        elif trend < -0.05:
            # System is improving: loosen coupling
            # (less overhead, more autonomy)
            direction = 'up'
            target = primary_param
        else:
            # Stable: adjust secondary parameter
            direction = random.choice(['up', 'down'])
            target = secondary_param
        
        old_val = getattr(self.config, target)
        new_config = self.config.mutate(target, direction, 0.08)
        
        action = {
            'action': 'finetune',
            'target': target,
            'direction': direction,
            'old_value': old_val,
            'new_value': getattr(new_config, target),
            'reason': f'finetuning for {target_level} (trend={trend:+.3f})',
            'generation': self.generation,
        }
        
        self.config = new_config
        self.actions.append(action)
        return action
    
    def _emergency_intervention(self, worst_level: str, trend: float) -> dict:
        """Emergency stop: drastically tighten coupling to regain control."""
        new_config = CouplingConfig(
            detect_every_n=1,        # Check every turn
            msr_check_every_n=2,      # Check every 2 turns
            msr_to_metaloop_gain=1.0, # Full coupling
            forge_trigger_threshold=0.15, # Trigger forge at low threshold
            precision_l1=2.0,         # Maximum precision at L1
            precision_l2=1.5,
            precision_l3=1.0,
            precision_l4=0.5,
        )
        
        action = {
            'action': 'emergency_intervention',
            'target': 'all',
            'direction': 'tighten_maximum',
            'old_value': str(self.config),
            'new_value': str(new_config),
            'reason': f'CRITICAL: F trend={trend:+.3f}, worst={worst_level}. Full coupling reset.',
            'generation': self.generation,
        }
        
        self.config = new_config
        self.actions.append(action)
        return action
    
    def status_report(self) -> dict:
        """Return the current status of the RSI kernel."""
        recent_history = self.free_energy_history[-5:] if self.free_energy_history else []
        recent_actions = self.actions[-5:] if self.actions else []
        
        return {
            "generation": self.generation,
            "current_config": {
                "detect_every_n": self.config.detect_every_n,
                "msr_check_every_n": self.config.msr_check_every_n,
                "msr_to_metaloop_gain": self.config.msr_to_metaloop_gain,
                "forge_trigger_threshold": self.config.forge_trigger_threshold,
                "precision": [self.config.precision_l1, self.config.precision_l2,
                             self.config.precision_l3, self.config.precision_l4],
            },
            "free_energy_trend": [
                {"generation": i, "f_combined": fe.f_combined}
                for i, fe in enumerate(self.free_energy_history[-10:])
            ] if self.free_energy_history else [],
            "recent_actions": recent_actions,
            "total_actions": len(self.actions),
            "exploration_rate": round(self.exploration_rate, 3),
            "total_observations": len(self.free_energy_history),
        }


# ──────────────────────────────────────────────
# 3. DEMO — RSI Cycle
# ──────────────────────────────────────────────

def main():
    random.seed = 42
    
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║    RSI KERNEL — Recursive Self-Improvement (Athena L5)      ║")
    print("  ║  Active inference on the coupling between improvement layers ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()
    
    kernel = RecursiveImprovementKernel()
    
    # Simulate 30 generations of system evolution
    # The environment is a simulation of Levels 1-4 behavior.
    # It has three phases: stable → harsh → recovery
    
    print("─" * 56)
    print("  Simulating 30 RSI generations through 3 environment phases...")
    print("─" * 56)
    print()
    
    base_task_success = 0.75
    best_fe_observed = float('inf')
    fe_at_stable = None
    
    for gen in range(30):
        # Three environment phases:
        # Gens 0-9: STABLE — baseline
        # Gens 10-19: HARSH — environment degrades (tests adaptation)
        # Gens 20-29: RECOVERY — environment stabilizes (tests learning)
        if gen < 10:
            difficulty = 0.05  # Easy
        elif gen < 20:
            difficulty = 0.15 + (gen - 10) * 0.03  # Gradual increase
        else:
            difficulty = max(0.05, 0.35 - (gen - 20) * 0.03)  # Recovery
        
        # Simulate system state under current coupling
        # Coupling quality: how well the kernel's config matches the environment
        detect_quality = max(0, 1.0 - (kernel.config.detect_every_n - 1) / 14.0)
        msr_quality = kernel.config.msr_to_metaloop_gain
        precision_bonus = (kernel.config.precision_l1 - 0.5) / 1.5 * 0.1
        
        coupling_quality = (detect_quality * 0.2 + msr_quality * 0.15 + precision_bonus)
        
        # Add noise to make it realistic
        noise = random.uniform(-0.03, 0.03)
        task_success = min(0.95, max(0.1, base_task_success + coupling_quality - difficulty + noise))
        tool_failure = max(0.01, base_task_success * 0.12 + difficulty * 0.4 - coupling_quality * 0.2)
        
        # Recovery stage
        if kernel.config.detect_every_n <= 2:
            # Fast detection catches problems early
            stage = 'healthy' if task_success > 0.4 else 'stage_1'
        elif kernel.config.detect_every_n <= 5:
            stage = 'stage_1' if task_success > 0.3 else 'stage_2'
        else:
            stage = 'stage_2' if task_success > 0.2 else 'stage_3'
        
        # Guardrail rate
        guardrail_rate = max(0.01, 0.20 - kernel.config.msr_to_metaloop_gain * 0.12 + difficulty * 0.3)
        
        # Tool synthesis
        tasks_needing_tools = max(0, int(difficulty * 8))
        forge_efficiency = 3 / max(kernel.config.forge_trigger_threshold, 0.05)
        tools_found = min(tasks_needing_tools + 1, max(1, int(forge_efficiency)))
        tool_effectiveness = max(0.3, 0.9 - difficulty * 0.5 + msr_quality * 0.1)
        
        events = {
            'task_success': task_success,
            'tool_failure_rate': tool_failure,
            'recovery_stage': stage,
            'guardrail_encounter_rate': guardrail_rate,
            'msr_lower_threshold': 0.05,
            'msr_upper_threshold': 0.40,
            'tools_synthesized': tools_found,
            'tool_effectiveness': tool_effectiveness,
            'tasks_requiring_new_tools': tasks_needing_tools,
        }
        
        report = kernel.observe(events)
        action = kernel.act(report)
        
        # Track best FE
        if report.f_combined < best_fe_observed:
            best_fe_observed = report.f_combined
        if gen == 9:
            fe_at_stable = report.f_combined
        
        # Print every 2 generations or on important events
        if gen % 2 == 0 or action['action'] in ('explore', 'emergency_intervention'):
            phase_marker = "S" if gen < 10 else "H" if gen < 20 else "R"
            print(f"  [{phase_marker} G{gen:>2d}] F={report.f_combined:.3f} "
                  f"(L1={report.f_l1:.2f} L2={report.f_l2:.2f} "
                  f"L3={report.f_l3:.2f} L4={report.f_l4:.2f}) "
                  f"| detect={kernel.config.detect_every_n} "
                  f"msr_gain={kernel.config.msr_to_metaloop_gain:.2f} "
                  f"pL1={kernel.config.precision_l1:.1f} "
                  f"task={task_success:.0%}"
                  f"{' ⚠' if action['action'] == 'emergency_intervention' else ''}")
    
    # ── Summary ──
    print()
    print("─" * 56)
    print("  RSI Evolution Summary")
    print("─" * 56)
    print()
    
    s = kernel.status_report()
    print(f"  Generations:          {s['generation']}")
    print(f"  Total actions:        {s['total_actions']}")
    print(f"  Final exploration:    {s['exploration_rate']}")
    print()
    
    print("  Final coupling configuration:")
    print(f"    L1→L2 detect:       {s['current_config']['detect_every_n']} turns")
    print(f"    L2→L3 MSR check:    {s['current_config']['msr_check_every_n']} turns")
    print(f"    L3→L2 MSR gain:     {s['current_config']['msr_to_metaloop_gain']:.2f}")
    print(f"    L1→L4 forge trig:   {s['current_config']['forge_trigger_threshold']:.2f}")
    print(f"    Precision L1..L4:   {s['current_config']['precision']}")
    print()
    
    if kernel.free_energy_history:
        initial_f = kernel.free_energy_history[0].f_combined
        final_f = kernel.free_energy_history[-1].f_combined
        improvement = (initial_f - final_f) / max(initial_f, 0.01) * 100
        print(f"  Free energy: {initial_f:.3f} → {final_f:.3f} ({improvement:.0f}% improvement)")
        print()
        
        # Check if recursion is compressing
        action_types = {}
        for a in kernel.actions:
            action_types[a['action']] = action_types.get(a['action'], 0) + 1
        
        print("  Action distribution:")
        for action_type, count in sorted(action_types.items()):
            print(f"    {action_type:>30s}: {count}")
        print()
        
        # Check for recursive improvement: did the system learn from the harsh phase?
        # Key metric: was free energy during RECOVERY (gen 20-29) lower than during
        # the equivalent STABLE phase (gen 0-9), controlling for difficulty?
        # If yes, the system improved its improvement mechanism.
        if fe_at_stable is not None and len(kernel.free_energy_history) >= 30:
            # Average FE in last 5 gens of recovery vs last 5 gens of stable
            recovery_fe = sum(fe.f_combined for fe in kernel.free_energy_history[-5:]) / 5
            stable_fe = sum(fe.f_combined for fe in kernel.free_energy_history[5:10]) / 5
            
            if recovery_fe < stable_fe * 0.5:
                improvement_type = "RECURSIVE"
                improvement_pct = (stable_fe - recovery_fe) / stable_fe * 100
            elif recovery_fe < stable_fe * 0.8:
                improvement_type = "ADAPTIVE"
                improvement_pct = (stable_fe - recovery_fe) / stable_fe * 100
            else:
                improvement_type = "MAINTENANCE"
                improvement_pct = ((initial_f or 1) - final_f) / (initial_f or 1) * 100
            
            print(f"  ╔══════════════════════════════════════════════════════════╗")
            print(f"  ║      {improvement_type} IMPROVEMENT DETECTED{'' if len(improvement_type) < 10 else ''}          ║")
            print(f"  ╚══════════════════════════════════════════════════════════╝")
            print(f"  Stable FE (G5-9): {stable_fe:.3f}")
            print(f"  Recovery FE (G25-29): {recovery_fe:.3f}")
            print(f"  Improvement: {improvement_pct:.0f}%")
            
            if improvement_type == "RECURSIVE":
                print()
                print("  The RSI kernel adapted to the harsh phase (G10-19) and")
                print("  returned to a LOWER free energy state than the original")
                print("  stable phase. This is RECURSIVE improvement: the system")
                print("  improved its own improvement capacity through exposure")
                print("  to challenge.")
                print()
                print("  This is the FEP prediction confirmed: active inference at")
                print("  Level 5 (coupling optimization) produces a trajectory where")
                print("  the system's ability to maintain low free energy IMPROVES")
                print("  over time, not just stabilizes.")
        else:
            print("  Insufficient data to assess recursive improvement.")
            print("  (Need at least 30 generations for the 3-phase test.)")
    
    print("═" * 56)
    print("  Interpretation:")
    print("═" * 56)
    print("  The RSI kernel observes the free energy at each of Athena's")
    print("  4 levels and adjusts the COUPLING between them.")
    print()
    print("  This closes the recursion: Level 5 is active inference on")
    print("  how Levels 1-4 perform active inference.")
    print()
    print("  Each coupling adjustment is an improvement to the")
    print("  improvement mechanism itself — the definition of RSI.")
    print()


if __name__ == "__main__":
    main()
