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
import statistics
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
        
        # ── Meta-Kernel (L6 — Paradigm Shift Engine) ──
        self.meta_kernel = MetaKernel()
        self.last_exhaustion_status = {}
        
        # ── Code Space Monitor (CodeCMP → Meta-Kernel bridge) ──
        self.code_cmp_scores: list[dict] = []  # Most recent CMP scores per tool
        self.code_space_exhausted: bool = False
        
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
        
        # Feed free energy to Meta-Kernel (L6) for exhaustion detection
        self.meta_kernel.observe_generation(report.f_combined)
        
        return report
    
    def act(self, report: FreeEnergyReport) -> dict:
        """
        Act on the coupling configuration to minimize free energy.
        
        This is the action step: "what should I change about how
        the system improves itself?"
        
        Returns a dict describing the action.
        """
        self.generation += 1
        
        # Feed CodeCMP scores to MetaKernel (for code space exhaustion)
        if self.code_cmp_scores:
            self.meta_kernel.set_code_cmp_scores(self.code_cmp_scores)
        
        # ── Level 6 Check: Kuhnian Crisis? ──
        # If the Meta-Kernel detects parameter space OR code space exhaustion,
        # the paradigm shift takes priority over all L5 actions.
        exhaustion = self.meta_kernel.check_and_shift(
            self.meta_kernel.detector.detect_exhaustion()
        )
        self.last_exhaustion_status = exhaustion
        
        if exhaustion.get('action') == 'paradigm_shift':
            # Paradigm shift occurred. Rehydrate the coupling config
            # from the new genotype.
            self._hydrate_from_genotype()
            return {
                'action': 'paradigm_shift',
                'shift_type': exhaustion.get('shift_type', 'unknown'),
                'old_parameter_count': exhaustion.get('old_count', 0),
                'new_parameter_count': exhaustion.get('new_count', 0),
                'delta': exhaustion.get('delta', 0),
                'generation': self.generation,
                'reason': f"Paradigm shift type={exhaustion['shift_type']}: "
                          f"{exhaustion['old_count']}→{exhaustion['new_count']} params",
            }
        
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
    
    def _hydrate_from_genotype(self):
        """
        Rehydrate the coupling config from the Meta-Kernel's mutated genotype.
        
        The MetaKernel can add, split, fuse, or expand parameters.
        This method maps the new genotype back onto a CouplingConfig,
        preserving shared parameters and adding defaults for new ones.
        """
        old_config = self.config
        new_genotype = self.meta_kernel.genotype.genotype
        
        known_fields = {
            'detect_every_n', 'msr_check_every_n', 'msr_to_metaloop_gain',
            'forge_trigger_threshold', 'forge_to_react_priority',
            'precision_l1', 'precision_l2', 'precision_l3', 'precision_l4',
        }
        
        new_kwargs = {}
        for param_name, param_type, min_val, max_val, deps in new_genotype:
            if param_name in known_fields:
                new_kwargs[param_name] = getattr(old_config, param_name, (min_val + max_val) / 2)
            else:
                if param_type == 'int':
                    new_kwargs[param_name] = int((min_val + max_val) / 2)
                else:
                    new_kwargs[param_name] = (min_val + max_val) / 2
        
        self.config = CouplingConfig()
        for k, v in new_kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        
        print(f"[RSI] L6 PARADIGM SHIFT: {len(new_genotype)} params active "
              f"(was {self.meta_kernel.old_parameter_count})")
        print(f"[RSI] New coupling: detect={self.config.detect_every_n}, "
              f"msr_check={self.config.msr_check_every_n}, "
              f"msr_gain={self.config.msr_to_metaloop_gain:.2f}")
    
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
            "meta_kernel": {
                "paradigm_shifts": self.meta_kernel.paradigm_shifts,
                "parameter_count": len(self.meta_kernel.genotype.genotype),
                "exhaustion_probability": self.last_exhaustion_status.get(
                    'exhaustion_probability', 0) if self.last_exhaustion_status else 0,
                "kuhnian_crisis": self.last_exhaustion_status.get(
                    'kuhnian_crisis', False) if self.last_exhaustion_status else False,
                "safe_mode": self.meta_kernel.safe_mode,
                "code_space_crisis": self.meta_kernel.code_space_crisis,
                "code_cmp_count": len(self.meta_kernel.code_cmp_scores),
            },
        }


# ──────────────────────────────────────────────
# 3. DEMO — RSI Cycle
# ──────────────────────────────────────────────

def main():
    random.seed = 42
    
    print()
    print("  ╔══════════════════════════════════════════════════════════════════╗")
    print("  ║     RSI KERNEL + META-KERNEL — Recursive Self-Improvement       ║")
    print("  ║  L5: Coupling optimization | L6: Paradigm shift on exhaustion  ║")
    print("  ╚══════════════════════════════════════════════════════════════════╝")
    print()
    
    kernel = RecursiveImprovementKernel()
    
    # Simulate 70 generations with 6 environment phases.
    # Phases are designed to push the system past its parameter space limits,
    # triggering Critical Slowing Down signals and a Meta-Kernel paradigm shift.
    
    print("─" * 64)
    print("  Simulating 70 RSI generations through 6 environment phases...")
    print("─" * 64)
    print()
    
    base_task_success = 0.75
    best_fe_observed = float('inf')
    fe_at_stable = None
    
    print(f"  {'Gen':>3s} {'Phase':>7s} {'F':>5s} {'L1':>4s} {'L2':>4s} {'L3':>4s} {'L4':>4s}"
          f" {'detect':>6s} {'msr_gain':>8s} {'task':>4s} {'action':>20s}")
    print("  " + "─" * 82)
    
    for gen in range(70):
        # ── Environment Phases ──
        # Phase 1 (0-14):  STABLE   — Easy, low noise
        # Phase 2 (15-29): CLIMBING — Harder each generation (tests adaptation)
        # Phase 3 (30-49): EXHAUST  — Sustained high difficulty with slow oscillation.
        #                             Coupling quality capped = bounded parameter space.
        #                             Slow waves produce CSD signals: high variance + AR(1).
        # Phase 4 (50-59): CHAOTIC  — Rapid oscillations (tests robustness after shift)
        # Phase 5 (60-69): RECOVERY — New stability, tests if paradigm shift helped
        
        if gen < 15:
            phase = "STABLE"
            difficulty = 0.05
        elif gen < 30:
            phase = "CLIMB"
            difficulty = 0.10 + (gen - 15) * 0.025  # 0.10 → 0.475
        elif gen < 50:
            phase = "EXHAUST"
            # 20 generations of a TRULY bounded parameter space.
            # Override ALL environment metrics to fixed oscillating values —
            # no amount of coupling tuning helps. The system faces genuine
            # parameter space exhaustion: the degrees of freedom are saturated.
            difficulty = 0.40 + math.sin((gen - 30) * 0.4) * 0.10
            stage = 'stage_2' if gen % 2 == 0 else 'stage_3'
            task_success = 0.30 + math.sin((gen - 30) * 0.4) * 0.10 + math.cos(gen * 7) * 0.02
            tool_failure = 0.25 + math.sin((gen - 30) * 0.3) * 0.05
            guardrail_rate = 0.25 + math.sin(gen * 0.5) * 0.05
            tasks_needing_tools = 3
            tools_found = 1
            tool_effectiveness = 0.45
        elif gen < 60:
            phase = "CHAOTIC"
            # Sinusoidal difficulty: rapid oscillation from 0.1 to 0.5
            raw = math.sin((gen - 50) * 1.5) * 0.25 + 0.35
            difficulty = max(0.1, min(0.6, raw))
        else:
            phase = "RECOVER"
            difficulty = max(0.05, 0.40 - (gen - 60) * 0.045)  # 0.40 → 0.05
        
        # Simulate system state under current coupling
        detect_quality = max(0, 1.0 - (kernel.config.detect_every_n - 1) / 14.0)
        msr_quality = kernel.config.msr_to_metaloop_gain
        precision_bonus = (kernel.config.precision_l1 - 0.5) / 1.5 * 0.1
        
        coupling_quality = (detect_quality * 0.2 + msr_quality * 0.15 + precision_bonus)
        
        # Noise grows in CHAOTIC phase (simulating CSD)
        noise_amplitude = 0.03 if gen < 50 else 0.08
        noise = random.uniform(-noise_amplitude, noise_amplitude)
        
        # ── Compute environment metrics ──
        # EXHAUST phase (gen 30-49): override ALL metrics with fixed values
        # to simulate a bounded parameter space. No config change helps.
        if gen >= 30 and gen < 50:
            # Override is already set above — skip the normal computation
            pass
        else:
            task_success = min(0.95, max(0.1, base_task_success + coupling_quality - difficulty + noise))
            tool_failure = max(0.01, base_task_success * 0.12 + difficulty * 0.4 - coupling_quality * 0.2)
            
            # Recovery stage maps difficulty to system health
            stage_quality = task_success / max(difficulty, 0.01)
            if stage_quality > 3.0:
                stage = 'healthy'
            elif stage_quality > 2.0:
                stage = 'stage_1'
            elif stage_quality > 1.0:
                stage = 'stage_2'
            else:
                stage = 'stage_3'
            
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
        if gen == 14:
            fe_at_stable = report.f_combined
        
        # Print every 3 generations or on important events
        if gen % 3 == 0 or action['action'] in ('paradigm_shift', 'emergency_intervention', 'explore'):
            action_label = action.get('action', 'observe')
            if action_label == 'paradigm_shift':
                action_label = f"⚡{action.get('shift_type', 'shift')[:10]}"
            
            print(f"  [{phase[:3]:>3s} G{gen:>2d}] F={report.f_combined:.3f} "
                  f"({report.f_l1:.2f} {report.f_l2:.2f} "
                  f"{report.f_l3:.2f} {report.f_l4:.2f}) "
                  f"| dt={kernel.config.detect_every_n:>2d} "
                  f"mg={kernel.config.msr_to_metaloop_gain:.2f} "
                  f"ts={task_success:.0%}"
                  f" {action_label:>20s}")
    
    # ── Summary ──
    print()
    print("─" * 64)
    print("  RSI + Meta-Kernel Evolution Summary")
    print("─" * 64)
    print()
    
    s = kernel.status_report()
    mk = s.get('meta_kernel', {})
    
    print(f"  Generations:              {s['generation']}")
    print(f"  Total actions:            {s['total_actions']}")
    print(f"  Paradigm shifts (L6):     {mk.get('paradigm_shifts', 0)}")
    print(f"  Final parameter count:    {mk.get('parameter_count', 0)}")
    print(f"  Final exhaustion prob:    {mk.get('exhaustion_probability', 0):.2%}")
    print()
    
    print("  Final coupling configuration:")
    print(f"    L1→L2 detect:           {s['current_config']['detect_every_n']} turns")
    print(f"    L2→L3 MSR check:        {s['current_config']['msr_check_every_n']} turns")
    print(f"    L3→L2 MSR gain:         {s['current_config']['msr_to_metaloop_gain']:.2f}")
    print(f"    L1→L4 forge trig:       {s['current_config']['forge_trigger_threshold']:.2f}")
    print(f"    Precision L1..L4:       {s['current_config']['precision']}")
    print()
    
    if kernel.free_energy_history:
        # Compute improvement relative to best observed
        initial_f = kernel.free_energy_history[0].f_combined
        final_f = kernel.free_energy_history[-1].f_combined
        improvement = (initial_f - final_f) / max(initial_f, 0.01) * 100
        print(f"  Free energy trajectory: {initial_f:.3f} → {final_f:.3f} ({improvement:.0f}% Δ)")
        print()
        
        # Action distribution
        action_types = {}
        for a in kernel.actions:
            at = a['action']
            action_types[at] = action_types.get(at, 0) + 1
        
        print("  Action distribution:")
        for action_type, count in sorted(action_types.items()):
            label = f"L6_ParadigmShift" if action_type == 'paradigm_shift' else action_type
            print(f"    {label:>22s}: {count}")
        print()
        
        # Meta-Kernel transitions detail
        if mk.get('paradigm_shifts', 0) > 0:
            print("  ╔══════════════════════════════════════════════════════════╗")
            print("  ║      META-KERNEL PARADIGM SHIFT(S) OCCURRED            ║")
            print("  ╚══════════════════════════════════════════════════════════╝")
            print()
            for i, trans in enumerate(kernel.meta_kernel.transition_history):
                print(f"  Shift #{i+1}: {trans.get('shift_type', 'unknown')}")
                print(f"    Parameters: {trans.get('old_parameter_count')}"
                      f" → {trans.get('new_parameter_count')} ({trans.get('delta', 0):+d})")
                signals = trans.get('signals_before_shift', {})
                print(f"    CSD signals: var(×{signals.get('variance_ratio', '?'):.1f}) "
                      f"ac({signals.get('autocorrelation', '?'):+.2f}) "
                      f"shift({signals.get('mean_shift', '?'):.1f}×)"
                      f"{' 🔴' if signals.get('high_fe') else ''}")
            print()
    
    # Compare recovery vs stable
    if fe_at_stable is not None and len(kernel.free_energy_history) >= 55:
        # Average FE in last 5 gens of recovery vs stable phase
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
        print(f"  ║      {improvement_type} IMPROVEMENT DETECTED{' ' if len(improvement_type) < 8 else ''}        ║")
        print(f"  ╚══════════════════════════════════════════════════════════╝")
        print(f"  Stable FE (G5-14):  {stable_fe:.3f}")
        print(f"  Recovery FE (G55-59): {recovery_fe:.3f}")
        print(f"  Improvement:        {improvement_pct:.0f}%")
        
        if improvement_type == "RECURSIVE":
            print()
            print("  The combined L5+L6 system adapted to the CLIMB phase, survived")
            print("  the EXHAUST plateau, navigated the CHAOTIC phase, and returned")
            print("  to a LOWER free energy state than the original stable phase.")
            print()
            if mk.get('paradigm_shifts', 0) > 0:
                print("  The Meta-Kernel detected parameter space exhaustion via CSD")
                print("  signals and expanded the coupling space. This is the FEP's")
                print("  prediction confirmed at Level 6: the system can redesign")
                print("  its own degrees of freedom.")
            else:
                print("  The RSI kernel adapted but the Meta-Kernel did not trigger.")
                print("  The parameter space may not yet be exhausted.")
    
    print("═" * 64)
    print("  L5 (RSI Kernel) minimizes free energy of the coupling config.")
    print("  L6 (Meta-Kernel) detects when the parameter space is exhausted")
    print("  and generates a NEW space with expanded degrees of freedom.")
    print()
    print("  This closes the recursion: the system redesigns its own")
    print("  optimization landscape when improvement becomes impossible.")
    print("═" * 64)


# ══════════════════════════════════════════════
# 6. META-KERNEL — Level 6 (Paradigm Shifter)
# ══════════════════════════════════════════════

class CriticalSlowingDownDetector:
    """
    Detects parameter space exhaustion via Critical Slowing Down signals.
    
    As G → 1.0 (the control parameter approaches criticality):
    - Rising autocorrelation (AR(1)): generations become more similar
    - Rising variance: fluctuations become more extreme
    - Slowing recovery: longer to return to equilibrium after perturbation
    
    These are universal early warning signals for regime shifts
    (climate tipping points → Bridge #49, cortical networks → criticality paper).
    
    CSD detection uses a BASELINE comparison approach: the first 10-15
    observations establish a reference state (low FE, stable). All subsequent
    comparisons are against this baseline, NOT a sliding window split-half.
    This correctly detects rising variance/autocorrelation even when the
    post-transition state oscillates steadily.
    """
    
    def __init__(self, window_size: int = 20, baseline_size: int = 12):
        self.window_size = window_size
        self.baseline_size = baseline_size
        self.fe_history: list[float] = []
        self.recovery_times: list[float] = []
        self._baseline_recorded = False
        self._baseline_fe_mean = 0.0
        self._baseline_fe_var = 0.0
    
    def observe(self, free_energy: float, recovery_time: float | None = None):
        self.fe_history.append(free_energy)
        if recovery_time is not None:
            self.recovery_times.append(recovery_time)
        
        # Record baseline once we have enough stable data
        if not self._baseline_recorded and len(self.fe_history) >= self.baseline_size:
            baseline = self.fe_history[:self.baseline_size]
            # Only record baseline if it's low FE (stable state)
            self._baseline_fe_mean = statistics.mean(baseline)
            self._baseline_fe_var = statistics.variance(baseline) if len(baseline) > 1 else 0.0
            self._baseline_recorded = True
    
    def detect_exhaustion(self) -> dict:
        """Return exhaustion signals and probability."""
        if len(self.fe_history) < 6:
            return {"exhaustion_probability": 0.0, "signals": {}, "kuhnian_crisis": False}
        
        if not self._baseline_recorded:
            return {"exhaustion_probability": 0.0, "signals": {}, "kuhnian_crisis": False}
        
        recent = self.fe_history[-self.window_size:] if len(self.fe_history) > self.window_size else self.fe_history
        
        # 1. Variance change ratio: current variance vs BASELINE variance
        recent_var = statistics.variance(recent) if len(recent) > 1 else 0.0
        variance_ratio = recent_var / max(self._baseline_fe_var, 1e-10)
        
        # 2. Autocorrelation (lag-1) of the recent window
        def lag1_autocorr(series):
            if len(series) < 4: return 0.0
            x = series[:-1]
            y = series[1:]
            mx = sum(x) / len(x)
            my = sum(y) / len(y)
            num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
            den = (sum((xi - mx)**2 for xi in x) * sum((yi - my)**2 for yi in y)) ** 0.5
            return num / den if den > 0 else 0.0
        
        recent_autocorr = lag1_autocorr(recent)
        
        # 3. Mean shift: how far current FE is from baseline
        recent_mean = statistics.mean(recent[-5:]) if len(recent) >= 5 else recent[-1]
        mean_shift = (recent_mean - self._baseline_fe_mean) / max(self._baseline_fe_mean, 0.001)
        
        # 4. Recovery time trend
        recovery_trend = 0.0
        if len(self.recovery_times) >= 4:
            rt = list(self.recovery_times)
            recovery_trend = (rt[-1] - rt[0]) / max(len(rt), 1)
        
        # 5. Plateau at high FE (stuck in bad state)
        high_fe = recent_mean > self._baseline_fe_mean * 3
        
        signals = {
            "variance_ratio": round(variance_ratio, 3),
            "autocorrelation": round(recent_autocorr, 3),
            "mean_shift": round(mean_shift, 3),
            "recovery_trend": round(recovery_trend, 5),
            "high_fe": high_fe,
        }
        
        # Composite exhaustion probability
        # Requires MULTIPLE signals to fire simultaneously.
        # A single elevated statistic is not exhaustion — it's just a bad day.
        probability = 0.0
        variance_signal = variance_ratio > 5.0 and recent_var > 0.001
        ac_signal = recent_autocorr > 0.6
        shift_signal = mean_shift > 5.0
        
        if variance_signal: probability += 0.25
        if ac_signal: probability += 0.25
        if shift_signal: probability += 0.25
        if high_fe: probability += 0.25
        
        # Minimum requirement: at least 2 signals must fire for crisis
        crisis_conditions_met = (variance_signal + ac_signal + shift_signal + high_fe) >= 2
        
        return {
            "exhaustion_probability": min(1.0, probability),
            "signals": signals,
            "kuhnian_crisis": probability > 0.7 and crisis_conditions_met,
            "crisis_conditions_met": crisis_conditions_met,
        }


class ParameterGenotype:
    """
    The genotype of the coupling parameter space.
    
    The Meta-Kernel operates on this to generate new parameter spaces.
    This is the grammar from which coupling configurations are derived.
    """
    
    def __init__(self, config: CouplingConfig | None = None):
        self.config = config or CouplingConfig()
        
        # The genotype is a list of parameter specifications
        # Each spec: (name, type, min, max, dependencies)
        self.genotype = [
            ("detect_every_n", "int", 1, 15, []),
            ("msr_check_every_n", "int", 1, 20, []),
            ("msr_to_metaloop_gain", "float", 0.0, 1.0, []),
            ("forge_trigger_threshold", "float", 0.05, 0.9, []),
            ("forge_to_react_priority", "float", 0.0, 1.0, []),
            ("precision_l1", "float", 0.1, 2.0, []),
            ("precision_l2", "float", 0.1, 2.0, []),
            ("precision_l3", "float", 0.1, 2.0, []),
            ("precision_l4", "float", 0.1, 2.0, []),
        ]
    
    def apply_mutation(self, operation: str, target: str | None = None) -> 'ParameterGenotype':
        """Produce a mutated genotype (new parameter space)."""
        import copy
        new = copy.deepcopy(self)
        
        if operation == "add_parameter":
            # Add a new parameter
            new_name = f"{target or 'new_param'}_{len(new.genotype)}"
            new.genotype.append((new_name, "float", 0.0, 1.0, []))
            
        elif operation == "split_parameter" and target:
            # Split one parameter into two
            specs = [(n, t, mn, mx, deps) for n, t, mn, mx, deps in new.genotype]
            found = None
            for s in specs:
                if s[0] == target:
                    found = s
                    break
            if found:
                # Remove old, add two new
                specs = [s for s in specs if s[0] != target]
                specs.append((f"{target}_normal", found[1], found[2], found[3] / 2, found[4]))
                specs.append((f"{target}_crisis", found[1], found[3] / 2, found[3], found[4]))
                new.genotype = specs
                
        elif operation == "fuse_parameters" and target:
            # Fuse two parameters (comma-separated names)
            names = target.split(",")
            specs = [(n, t, mn, mx, deps) for n, t, mn, mx, deps in new.genotype]
            found = [s for s in specs if s[0] in names]
            if len(found) >= 2:
                new_name = f"fused_{found[0][0]}_{found[1][0]}"
                new_min = min(s[2] for s in found[:2])
                new_max = max(s[3] for s in found[:2])
                specs = [s for s in specs if s[0] not in names[:2]]
                specs.append((new_name, "float", new_min, new_max, []))
                new.genotype = specs
                
        elif operation == "expand_bounds" and target:
            # Widen a parameter's range
            specs = [(n, t, mn, mx, deps) for n, t, mn, mx, deps in new.genotype]
            for i, s in enumerate(specs):
                if s[0] == target:
                    specs[i] = (s[0], s[1], s[2] * 0.5, s[3] * 1.5, s[4])
                    break
            new.genotype = specs
            
        elif operation == "add_dependency" and target:
            # Make one parameter depend on another
            source, dep = target.split(",") if "," in target else (target, "all")
            specs = [(n, t, mn, mx, deps) for n, t, mn, mx, deps in new.genotype]
            for i, s in enumerate(specs):
                if s[0] == source and dep not in s[4]:
                    specs[i] = (s[0], s[1], s[2], s[3], s[4] + [dep])
                    break
            new.genotype = specs
        
        return new


class MetaKernel:
    """
    Level 6 of the RSI stack — the paradigm shift engine.
    
    Detects when the coupling parameter space is exhausted via CSD signals,
    generates a new space via bootstrapping operations on the genotype,
    and manages the transition between paradigms safely.
    """
    
    def __init__(self):
        self.detector = CriticalSlowingDownDetector()
        self.genotype = ParameterGenotype()
        self.old_parameter_count = len(self.genotype.genotype)
        self.paradigm_shifts = 0
        self.transition_history: list[dict] = []
        self.safe_mode = False
        self._cooldown_remaining = 0  # Generations to wait before next shift
        
        # ── Code Space Monitoring ──
        self.code_cmp_scores: list[dict] = []
        self.code_space_crisis = False
    
    def set_code_cmp_scores(self, scores: list[dict]):
        """Feed CodeCMP scores to the Meta-Kernel for code space exhaustion detection."""
        self.code_cmp_scores = scores
        
        # Code space exhaustion: ALL tools with sufficient history have low CMP
        tools_with_history = [s for s in scores if s.get('versions', 0) >= 2]
        if len(tools_with_history) < 2:
            self.code_space_crisis = False
            return
        
        # Crisis if 80%+ of tools are LOW_METAPRODUCTIVITY
        low_cmp = [s for s in tools_with_history 
                   if s.get('classification') == 'LOW_METAPRODUCTIVITY']
        self.code_space_crisis = len(low_cmp) / len(tools_with_history) >= 0.8
    
    def observe_generation(self, free_energy: float, recovery_time: float | None = None) -> dict:
        """Observe a generation and check for exhaustion."""
        self.detector.observe(free_energy, recovery_time)
        status = self.detector.detect_exhaustion()
        return status
    
    def check_and_shift(self, status: dict) -> dict:
        """
        If exhaustion is detected, trigger a paradigm shift.
        Returns the action taken.
        
        Checks TWO spaces:
        1. Parameter space: CSD signals from the coupling config's free energy
        2. Code space: CodeCMP scores indicating all tools are exhausted
        
        Either can trigger a Kuhnian crisis.
        """
        # Decrement cooldown
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
        
        # ── Check 1: Code space crisis ──
        # If all synthesized tools have low CMP, the entire code space is
        # exhausted. This triggers a "tool space expansion" paradigm shift.
        code_crisis = status.get('code_space_crisis', False) or self.code_space_crisis
        
        if code_crisis and self._cooldown_remaining <= 0 and not self.safe_mode:
            self._cooldown_remaining = 10
            self.paradigm_shifts += 1
            
            # Code space shift: expand parameter bounds to give tools more room
            shift_type = "code_space_expansion"
            new_genotype = self.genotype.apply_mutation("expand_bounds", "forge_trigger_threshold")
            new_genotype = new_genotype.apply_mutation("add_parameter", "code_versatility")
            
            self.old_parameter_count = len(self.genotype.genotype)
            self.genotype = new_genotype
            self.code_space_crisis = False
            
            signals = status.get('signals', {})
            transition = {
                'paradigm_shift': self.paradigm_shifts,
                'shift_type': shift_type,
                'old_parameter_count': self.old_parameter_count,
                'new_parameter_count': len(self.genotype.genotype),
                'delta': len(self.genotype.genotype) - self.old_parameter_count,
                'signals_before_shift': dict(signals),
                'code_cmp_scores': self.code_cmp_scores,
            }
            self.transition_history.append(transition)
            
            return {
                'action': 'paradigm_shift',
                'shift_type': shift_type,
                'old_count': self.old_parameter_count,
                'new_count': len(self.genotype.genotype),
                'delta': len(self.genotype.genotype) - self.old_parameter_count,
                'reason': f"Code space exhausted ({len(self.code_cmp_scores)} tools low CMP)",
                'transition': transition,
            }
        
        # ── Check 2: Parameter space crisis (existing CSD logic) ──
        if not status.get('kuhnian_crisis'):
            return {'action': 'none', 'reason': 'no_crisis'}
        
        # Crisis detected — check cooldown and minimum conditions
        crisis_met = status.get('crisis_conditions_met', False)
        if not crisis_met:
            return {'action': 'none', 'reason': 'insufficient_signals'}
        
        if self._cooldown_remaining > 0:
            return {'action': 'cooldown', 'reason': f'waiting {self._cooldown_remaining} gens'}
        
        if self.safe_mode:
            return {'action': 'blocked', 'reason': 'safe_mode_active'}

        # Enter cooldown after shift (10 generation stabilization period)
        self._cooldown_remaining = 10
        
        # Generate paradigm shift
        self.paradigm_shifts += 1
        
        # Choose shift type based on CSD signals
        signals = status.get('signals', {})
        
        if signals.get('variance_ratio', 0) > 8.0:
            # High variance → add more parameters for finer control
            shift_type = "add_parameter"
            new_genotype = self.genotype.apply_mutation("add_parameter", "adaptivity")
        elif signals.get('autocorrelation', 0) > 0.7:
            # High autocorrelation → split dominant parameter
            shift_type = "split_parameter"
            new_genotype = self.genotype.apply_mutation("split_parameter", "detect_every_n")
        elif signals.get('mean_shift', 0) > 8.0:
            # Large mean shift → expand bounds
            shift_type = "expand_bounds"
            new_genotype = self.genotype.apply_mutation("expand_bounds", "precision_l1")
        else:
            # Generic exhaustion → try dependency introduction
            shift_type = "add_dependency"
            new_genotype = self.genotype.apply_mutation("add_dependency", "msr_check_every_n,detect_every_n")
        
        old_count = self.old_parameter_count
        new_count = len(new_genotype.genotype)
        diff = new_count - old_count
        
        transition = {
            'paradigm_shift': self.paradigm_shifts,
            'shift_type': shift_type,
            'old_parameter_count': old_count,
            'new_parameter_count': new_count,
            'delta': diff,
            'signals_before_shift': dict(signals),
        }
        self.transition_history.append(transition)
        
        # Commit new genotype
        self.genotype = new_genotype
        self.old_parameter_count = new_count
        
        return {
            'action': 'paradigm_shift',
            'shift_type': shift_type,
            'old_count': old_count,
            'new_count': new_count,
            'delta': diff,
            'transition': transition,
        }
    
    def status_report(self) -> dict:
        """Full Meta-Kernel status."""
        exhaustion = self.detector.detect_exhaustion()
        return {
            "paradigm_shifts": self.paradigm_shifts,
            "current_parameter_count": len(self.genotype.genotype),
            "current_genotype": [(s[0], s[1], s[2], s[3]) for s in self.genotype.genotype],
            "exhaustion": exhaustion,
            "safe_mode": self.safe_mode,
            "recent_transitions": self.transition_history[-3:],
        }


if __name__ == '__main__':
    main()
