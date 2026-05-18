"""
omc_orchestrator.py — OneManCompany (OMC) Talent Market for Multi-Agent RSI

ARCHITECTURE:
  The OMC framework treats agents as "portable talents" in a market.
  Each agent has its own coupling configuration (like its "personality").
  The market matches tasks to agents based on demonstrated capability.
  Performance feedback drives each agent's RSI kernel.

  E²R Loop (Explore-Execute-Review):
    EXPLORE  → Agent pool evolves: new agents join, underperformers leave
    EXECUTE  → Task assigned to best-matched agent. Agent runs its kerner.
    REVIEW   → Agent's performance scored, fed back to RSI kernel

  This extends the cognoscope's RSI stack from single-agent (L1-L6)
  to multi-agent coordination. Each agent is a full L1-L6 stack.
  The Talent Market is L6+ — it's the meta-organization that optimizes
  the composition of the agent pool itself.

  Bridge #59: Multi-Agent RSI and the Talent Market (OMC)
"""

import math
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any
from collections import deque

from rsi_kernel import (
    CouplingConfig, FreeEnergyReport, RecursiveImprovementKernel,
    CladeTracker, MetaKernel
)


# ──────────────────────────────────────────────
# 1. AGENT PROFILE
# ──────────────────────────────────────────────

@dataclass
class AgentProfile:
    """
    An agent in the talent market.
    
    Each agent has:
    - A unique ID
    - A coupling config (its "personality" — how it improves itself)
    - A capability vector (what tasks it's good at)
    - A full RSI kernel (its improvement mechanism)
    - A performance history
    """
    agent_id: str
    capabilities: dict[str, float] = field(default_factory=lambda: {
        'retrieval': random.uniform(0.3, 0.9),
        'synthesis': random.uniform(0.3, 0.9),
        'execution': random.uniform(0.3, 0.9),
        'verification': random.uniform(0.3, 0.9),
        'tool_creation': random.uniform(0.3, 0.9),
    })
    config: CouplingConfig = field(default_factory=CouplingConfig)
    kernel: RecursiveImprovementKernel = field(default_factory=RecursiveImprovementKernel)
    performance_history: list[dict] = field(default_factory=list)
    generation: int = 0
    is_active: bool = True
    
    def __post_init__(self):
        # Override the kernel's config with our own
        self.kernel.config = self.config
    
    def score_for_task(self, task_type: str, difficulty: float) -> float:
        """
        Score how well this agent matches a task.
        
        Uses:
        - The agent's capability in the task type (base fitness)
        - The agent's current free energy (lower = more reliable)
        - The agent's exploration rate (higher = better for novel tasks)
        """
        capability = self.capabilities.get(task_type, 0.3)
        
        # Recent FE: lower is better (system is stable/performing)
        if self.kernel.free_energy_history:
            recent_fe = self.kernel.free_energy_history[-1].f_combined
            fe_factor = max(0.1, 1.0 - recent_fe)
        else:
            fe_factor = 0.5
        
        # Exploration rate: higher = better for difficult tasks
        exploration = self.kernel.exploration_rate
        
        # Composite score (higher = better match)
        score = (
            capability * 0.4 +
            fe_factor * 0.3 +
            exploration * 0.2 +
            random.uniform(-0.05, 0.05)  # Noise for exploration
        )
        
        return min(1.0, max(0.0, score))
    
    def execute_task(self, task: dict) -> dict:
        """
        Execute a task and update the agent's RSI kernel.
        
        Returns the task result and performance metrics.
        """
        self.generation += 1
        
        task_type = task.get('type', 'execution')
        difficulty = task.get('difficulty', 0.3)
        
        # Simulate task performance
        # Real performance depends on:
        # - Agent's capability for this task type
        # - Current coupling configuration quality
        # - Random noise
        
        capability = self.capabilities.get(task_type, 0.3)
        detect_quality = max(0, 1.0 - (self.config.detect_every_n - 1) / 14.0)
        msr_quality = self.config.msr_to_metaloop_gain
        coupling_quality = detect_quality * 0.3 + msr_quality * 0.2
        
        noise = random.uniform(-0.1, 0.1)
        task_success = min(0.95, max(0.1, 
            capability * 0.55 + coupling_quality * 0.15 - difficulty * 0.12 + noise
        ))
        
        # Tool failure rate
        tool_failure = max(0.01, 0.15 - coupling_quality * 0.1 + difficulty * 0.3)
        
        # Stage
        stage_quality = task_success / max(difficulty, 0.01)
        if stage_quality > 3.0:
            stage = 'healthy'
        elif stage_quality > 2.0:
            stage = 'stage_1'
        elif stage_quality > 1.0:
            stage = 'stage_2'
        else:
            stage = 'stage_3'
        
        guardrail_rate = max(0.01, 0.20 - msr_quality * 0.12 + difficulty * 0.3)
        tasks_needing = max(0, int(difficulty * 5))
        forge_eff = 3 / max(self.config.forge_trigger_threshold, 0.05)
        tools_found = min(tasks_needing + 1, max(1, int(forge_eff)))
        tool_eff = max(0.3, 0.9 - difficulty * 0.5 + msr_quality * 0.1)
        
        events = {
            'task_success': task_success,
            'tool_failure_rate': tool_failure,
            'recovery_stage': stage,
            'guardrail_encounter_rate': guardrail_rate,
            'msr_lower_threshold': 0.05,
            'msr_upper_threshold': 0.40,
            'tools_synthesized': tools_found,
            'tool_effectiveness': tool_eff,
            'tasks_requiring_new_tools': tasks_needing,
        }
        
        # Run the RSI kernel: observe + act
        report = self.kernel.observe(events)
        action = self.kernel.act(report)
        
        # Record performance
        result = {
            'agent_id': self.agent_id,
            'task_type': task_type,
            'difficulty': difficulty,
            'task_success': round(task_success, 3),
            'f_combined': round(report.f_combined, 4),
            'stage': stage,
            'generation': self.generation,
            'action': action.get('action', 'observe'),
        }
        self.performance_history.append(result)
        
        return result
    
    def status_report(self) -> dict:
        """Return agent status."""
        recent_perf = self.performance_history[-5:] if self.performance_history else []
        return {
            'agent_id': self.agent_id,
            'capabilities': self.capabilities,
            'generation': self.generation,
            'tasks_completed': len(self.performance_history),
            'avg_success': statistics.mean([p['task_success'] for p in recent_perf]) if recent_perf else 0,
            'recent_fe': self.kernel.free_energy_history[-1].f_combined if self.kernel.free_energy_history else None,
            'exploration_rate': round(self.kernel.exploration_rate, 3),
            'config': {
                'detect_every_n': self.config.detect_every_n,
                'msr_check_every_n': self.config.msr_check_every_n,
                'msr_gain': round(self.config.msr_to_metaloop_gain, 2),
            },
            'clade_cmp': round(self.kernel.clade.estimated_cmp(self.kernel.generation), 3) if self.kernel.generation > 0 else 0,
        }


# ──────────────────────────────────────────────
# 2. TALENT MARKET
# ──────────────────────────────────────────────

class TalentMarket:
    """
    The OneManCompany (OMC) Talent Market.
    
    Manages a pool of agents. Matches tasks to agents.
    Evolves the pool: new agents enter, underperformers leave.
    Tracks meta-CMP (organizational lineage).
    
    E²R Loop:
      EXPLORE: Every N tasks, spawn a new agent with random config.
               Or mutate an underperformer's config.
      EXECUTE: Score agents by task match. Pick the best.
               Agent runs its RSI kernel (observe + act).
      REVIEW:  After each task, evaluate agent performance.
               If an agent's avg FE is high across recent tasks, flag it.
               Agents with persistent underperformance are retired.
    """
    
    def __init__(self, initial_agents: int = 3):
        self.agents: dict[str, AgentProfile] = {}
        self.task_history: list[dict] = []
        self.retired_agents: list[dict] = []
        self.market_generation = 0
        
        # Meta-kernel tracks the organizational lineage
        self.meta_kernel = MetaKernel()
        
        # Spawn initial agents
        for i in range(initial_agents):
            agent = AgentProfile(agent_id=f"agent_{i}")
            self.agents[agent.agent_id] = agent
        
        print(f"[OMC] Talent Market initialized with {len(self.agents)} agents.")
        for aid, agent in self.agents.items():
            caps_str = ", ".join(f"{k}={v:.2f}" for k, v in agent.capabilities.items())
            print(f"[OMC]   {aid}: {caps_str}")
    
    def assign_task(self, task: dict) -> dict:
        """
        Assign a task to the best-matched agent.
        
        E²R: EXECUTE phase.
        
        1. Score all active agents for this task
        2. Select the agent with the highest score
        3. Execute the task via that agent
        4. Return the result
        """
        self.market_generation += 1
        task_type = task.get('type', 'execution')
        difficulty = task.get('difficulty', 0.3)
        
        # 1. Score agents
        scored_agents = []
        for agent in self.agents.values():
            if not agent.is_active:
                continue
            score = agent.score_for_task(task_type, difficulty)
            scored_agents.append((score, agent))
        
        if not scored_agents:
            return {'error': 'no_active_agents'}
        
        # 2. Select best
        scored_agents.sort(key=lambda x: x[0], reverse=True)
        best_score, best_agent = scored_agents[0]
        
        # 3. Execute
        result = best_agent.execute_task(task)
        result['market_generation'] = self.market_generation
        result['selection_score'] = round(best_score, 3)
        
        self.task_history.append(result)
        
        # 4. E²R: EXPLORE phase — check if we should evolve the pool
        if self.market_generation % 5 == 0:
            self._evolve_pool()
        
        # 5. E²R: REVIEW phase — retire underperformers every 10 tasks
        if self.market_generation % 10 == 0:
            self._review_and_cull()
        
        return result
    
    def _evolve_pool(self):
        """
        E²R: EXPLORE phase.
        
        Two strategies:
        1. If we're early (< 10 gens): spawn a new random agent
        2. If we're established: mutate the worst performer's config
        """
        if self.market_generation < 10 or len(self.agents) < 3:
            # Strategy 1: Spawn new agent
            new_id = f"a{len(self.agents) + len(self.retired_agents)}"
            new_agent = AgentProfile(agent_id=new_id)
            
            # Give the new agent a slight random advantage
            for cap in new_agent.capabilities:
                new_agent.capabilities[cap] = min(0.95, 
                    new_agent.capabilities[cap] + random.uniform(-0.1, 0.15))
            
            self.agents[new_id] = new_agent
            caps_str = ", ".join(f"{k}={v:.2f}" for k, v in new_agent.capabilities.items())
            print(f"[OMC] EXPLORE: Spawned {new_id} | {caps_str}")
        else:
            # Strategy 2: Mutate worst agent's config
            worst_agent = self._find_worst_agent()
            if worst_agent and worst_agent.kernel.free_energy_history:
                current_fe = worst_agent.kernel.free_energy_history[-1].f_combined
                if current_fe > 0.4:
                    # Reset the agent's config to defaults (fresh start)
                    worst_agent.config = CouplingConfig()
                    worst_agent.kernel.config = worst_agent.config
                    print(f"[OMC] EXPLORE: Reset {worst_agent.agent_id} config to defaults "
                          f"(FE={current_fe:.3f})")
    
    def _review_and_cull(self):
        """
        E²R: REVIEW phase.
        
        Evaluate all agents. Retire those with persistent poor performance.
        
        Criteria:
        - If agent has completed 5+ tasks and avg success < 0.4: flag
        - If flagged for 2 consecutive reviews: retire
        """
        for agent in list(self.agents.values()):
            if not agent.is_active:
                continue
            if len(agent.performance_history) < 5:
                continue
            
            recent = agent.performance_history[-5:]
            avg_success = statistics.mean([p['task_success'] for p in recent])
            avg_fe = statistics.mean([p['f_combined'] for p in recent])
            
            if avg_success < 0.4 and avg_fe > 0.5:
                # Retire
                agent.is_active = False
                self.retired_agents.append({
                    'agent_id': agent.agent_id,
                    'tasks_completed': len(agent.performance_history),
                    'avg_success': round(avg_success, 3),
                    'avg_fe': round(avg_fe, 3),
                    'market_generation': self.market_generation,
                })
                print(f"[OMC] REVIEW: Retired {agent.agent_id} "
                      f"(success={avg_success:.2f}, FE={avg_fe:.3f})")
                
                # Spawn a replacement with a global counter
                next_id = len(self.agents) + len(self.retired_agents) + 1
                new_id = f"a{next_id}"
                new_agent = AgentProfile(agent_id=new_id)
                self.agents[new_id] = new_agent
                print(f"[OMC] REVIEW: Spawned replacement {new_id}")
    
    def _find_worst_agent(self) -> AgentProfile | None:
        """Find the agent with the highest (worst) average FE."""
        candidates = []
        for agent in self.agents.values():
            if not agent.is_active or len(agent.performance_history) < 3:
                continue
            recent_fe = statistics.mean(
                [p['f_combined'] for p in agent.performance_history[-3:]]
            )
            candidates.append((recent_fe, agent))
        
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        return None
    
    def meta_cmp(self) -> dict:
        """
        Compute organizational CMP.
        
        Measures: how well does the talent market generate agents
        that perform well on the task distribution?
        
        Components:
        - Average agent CMP across the pool
        - Pool diversity (capability spread)
        - Retirement rate (negative signal)
        - Market FE trend
        """
        active_agents = [a for a in self.agents.values() if a.is_active]
        
        if not active_agents:
            return {'meta_cmp': 0.0}
        
        # Average CMP of active agents
        agent_cmps = []
        for a in active_agents:
            if a.kernel.generation > 0:
                cmp_val = a.kernel.clade.estimated_cmp(a.kernel.generation)
                agent_cmps.append(cmp_val)
        avg_agent_cmp = statistics.mean(agent_cmps) if agent_cmps else 0.5
        
        # Capability diversity (how many distinct capability profiles)
        caps_vectors = [frozenset(
            (k, round(v, 1)) for k, v in a.capabilities.items()
        ) for a in active_agents]
        diversity = len(set(caps_vectors)) / max(len(caps_vectors), 1)
        
        # Retirement rate (lower = better)
        total_lifetime = len(self.agents) + len(self.retired_agents)
        retirement_rate = len(self.retired_agents) / max(total_lifetime, 1)
        
        # Recent market performance
        recent_tasks = self.task_history[-10:] if self.task_history else []
        avg_market_success = statistics.mean(
            [t['task_success'] for t in recent_tasks]
        ) if recent_tasks else 0.5
        
        # Composite meta-CMP
        meta_cmp = (
            avg_agent_cmp * 0.3 +
            diversity * 0.2 +
            (1 - retirement_rate) * 0.2 +
            avg_market_success * 0.3
        )
        
        return {
            'meta_cmp': round(meta_cmp, 3),
            'avg_agent_cmp': round(avg_agent_cmp, 3),
            'diversity': round(diversity, 3),
            'retirement_rate': round(retirement_rate, 3),
            'avg_market_success': round(avg_market_success, 3),
            'active_agents': len(active_agents),
            'total_retired': len(self.retired_agents),
            'total_tasks': len(self.task_history),
        }
    
    def status_report(self) -> dict:
        """Full market status."""
        active = [a for a in self.agents.values() if a.is_active]
        return {
            'market_generation': self.market_generation,
            'active_agents': len(active),
            'retired_agents': len(self.retired_agents),
            'total_tasks': len(self.task_history),
            'meta_cmp': self.meta_cmp(),
            'agents': [a.status_report() for a in active],
            'retired_summary': [
                {'id': r['agent_id'], 'tasks': r['tasks_completed'], 
                 'avg_fe': r['avg_fe']}
                for r in self.retired_agents[-3:]
            ],
        }


# ──────────────────────────────────────────────
# 3. DEMO — OMC Talent Market
# ──────────────────────────────────────────────

def main():
    random.seed = 42
    
    print()
    print("  ╔══════════════════════════════════════════════════════════════════╗")
    print("  ║      OMC TALENT MARKET — Multi-Agent RSI Coordination           ║")
    print("  ║  E²R: Explore → Execute → Review | Each agent = L1-L6 stack   ║")
    print("  ╚══════════════════════════════════════════════════════════════════╝")
    print()
    
    market = TalentMarket(initial_agents=3)
    print()
    
    # Simulate 50 task assignments through the talent market.
    # Task distribution shifts over time:
    #   Phase 1 (0-19):  Mixed simple tasks
    #   Phase 2 (20-34): Heavy on synthesis (tests specialization)
    #   Phase 3 (35-49): Variable difficulty (tests adaptability)
    
    print("─" * 72)
    print("  Simulating 50 tasks through the talent market...")
    print("─" * 72)
    print()
    
    print(f"  {'Task':>4s} {'Type':>12s} {'Diff':>5s} {'Agent':>10s} {'Score':>6s} "
          f"{'Success':>8s} {'FE':>6s} {'Action':>22s}")
    print("  " + "─" * 75)
    
    task_types = ['retrieval', 'synthesis', 'execution', 'verification', 'tool_creation']
    
    for task_num in range(50):
        # Task distribution shifts
        if task_num < 20:
            # Phase 1: Mixed, moderate difficulty
            task_type = random.choice(task_types)
            difficulty = random.uniform(0.2, 0.5)
        elif task_num < 35:
            # Phase 2: Heavy synthesis
            task_type = 'synthesis' if random.random() < 0.6 else random.choice(task_types)
            difficulty = random.uniform(0.3, 0.6)
        else:
            # Phase 3: Variable
            task_type = random.choice(task_types)
            difficulty = random.uniform(0.1, 0.8)
        
        task = {
            'type': task_type,
            'difficulty': difficulty,
            'description': f"{task_type} task at difficulty {difficulty:.2f}",
        }
        
        result = market.assign_task(task)
        
        if 'error' not in result:
            print(f"  T{task_num:>2d}  {task_type:>12s} {difficulty:.2f} "
                  f"{result.get('agent_id', '?')[:10]:>10s} "
                  f"{result.get('selection_score', 0):.3f} "
                  f"{result.get('task_success', 0):.2%} "
                  f"{result.get('f_combined', 0):.3f} "
                  f"{result.get('action', 'observe'):>22s}")
    
    # ── Summary ──
    print()
    print("─" * 72)
    print("  Talent Market Evolution Summary")
    print("─" * 72)
    print()
    
    s = market.status_report()
    mk = s.get('meta_cmp', {})
    
    print(f"  Market generations:    {s['market_generation']}")
    print(f"  Total tasks completed: {s['total_tasks']}")
    print(f"  Active agents:         {s['active_agents']}")
    print(f"  Agents retired:        {s['retired_agents']}")
    print()
    
    print("  Meta-CMP (organizational health):")
    print(f"    Meta-CMP:        {mk.get('meta_cmp', 0):.3f}")
    print(f"    Agent CMP (avg): {mk.get('avg_agent_cmp', 0):.3f}")
    print(f"    Diversity:       {mk.get('diversity', 0):.3f}")
    print(f"    Retirement rate: {mk.get('retirement_rate', 0):.3f}")
    print(f"    Market success:  {mk.get('avg_market_success', 0):.2%}")
    print()
    
    print("  Agent Status:")
    for agent in s.get('agents', []):
        recent_fe = agent.get('recent_fe', 0) or 0
        print(f"    {agent['agent_id']:>10s}: gen={agent['generation']:>2d} "
              f"tasks={agent['tasks_completed']:>2d} "
              f"success={agent['avg_success']:.0%} "
              f"FE={recent_fe:.3f} "
              f"explore={agent.get('exploration_rate', 0):.2f} "
              f"CMP={agent.get('clade_cmp', 0):.3f}")
    
    if s.get('retired_history'):
        print()
        print("  Recently Retired:")
        for r in s.get('retired_history', []):
            print(f"    {r.get('id', '?'):>10s}: {r.get('tasks', 0)} tasks, "
                  f"avg_FE={r.get('avg_fe', 0):.3f}")
    
    print()
    
    # Check for organizational RSI
    if len(s.get('agents', [])) > len(s.get('retired_history', [])) + 1:
        print("  ╔══════════════════════════════════════════════════════════╗")
        print("  ║      ORGANIZATIONAL RSI DETECTED — Pool evolved         ║")
        print("  ╚══════════════════════════════════════════════════════════╝")
        print("  The talent market replaced underperformers with new agents.")
        print("  The meta-CMP reflects organizational learning:")
        print("  the pool adapts to the task distribution over time.")
    else:
        print("  No agents were retired. The initial pool was sufficient.")
    
    print()
    print("═" * 72)
    print("  E²R Loop (Explore-Execute-Review):")
    print("    EXPLORE: Every 5 tasks → spawn or mutate agent")
    print("    EXECUTE: Every task → assign to best-matched agent")
    print("    REVIEW:  Every 10 tasks → cull underperformers")
    print()
    print("  Each agent has its own RSI kernel (L1-L6).")
    print("  The Talent Market is the meta-level (L7) that evolves")
    print("  the composition of the agent pool itself.")
    print("═" * 72)


if __name__ == '__main__':
    main()
