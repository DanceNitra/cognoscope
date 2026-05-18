"""
omc_orchestrator.py — OneManCompany (OMC) Talent Market for Multi-Agent RSI

EXTENDED: Social Mirror integration — agents model each other's beliefs.

Each agent now has a SocialMirror that:
1. Simulates what other agents believe about it (L1: theory of others)
2. Detects reputation gaps (L2: "what do they think of me?")
3. Adjusts behavior to repair trust (L3: recursive belief correction)

The Talent Market now uses trust-adjusted scoring:
  score = capability * 0.40 + trust * 0.25 + fe_factor * 0.20 + exploration * 0.15
                          ^^^^^^^
  Agents with poor reputation are trusted less → get fewer tasks →
  less opportunity to improve → potential death spiral (or recovery via mirror)

Bridge #63: The Social Mirror at Scale — Recursive ToM in the Talent Market

See also: theory_of_mind.py (standalone Social Mirror engine)
  Key result: Without ToM → Trust = -0.421
              With ToM (k=2) → Trust = +0.300
              Swing of 0.721 from recursive belief modeling alone
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
from theory_of_mind import (
    ActionType, TraitDimension, BeliefModel, SocialMirror,
    ActorAgent, SelfModelingAgent, ObserverAgent
)


# ──────────────────────────────────────────────
# 1. SOCIAL MIRROR AGENT — ToM-enabled RSI agent
# ──────────────────────────────────────────────

@dataclass
class ReputationRecord:
    """
    What this agent believes about another agent's beliefs about it.
    
    This is the L2 tracking: not just "what Alice knows about Bob"
    but "what Alice thinks Bob thinks about Alice."
    """
    observer_id: str
    simulated_belief: BeliefModel = field(default_factory=BeliefModel)
    actual_belief: BeliefModel | None = None  # Only known if observer shares data
    gap_history: list[dict] = field(default_factory=list)
    last_correction: str | None = None


@dataclass
class SocialAgentProfile:
    """
    An agent in the talent market with social mirror capability.
    
    Extends AgentProfile with:
    - A SocialMirror (recursive belief modeling)
    - ReputationRecords for each observer
    - Trust-adjusted task scoring
    - Social correction history
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
    
    # ── Social Mirror fields ──
    social_mirror: SocialMirror = field(default_factory=lambda: SocialMirror(k_level=2))
    reputation_records: dict[str, ReputationRecord] = field(default_factory=dict)
    reputation_sensitivity: float = 0.3  # How much the agent cares about reputation
    social_moves: list[dict] = field(default_factory=list)
    
    # Track actions for belief modeling
    action_history: list[tuple[ActionType, bool]] = field(default_factory=list)
    
    def __post_init__(self):
        self.kernel.config = self.config
    
    def register_observer(self, observer_id: str):
        """Register another agent as an observer of this agent."""
        if observer_id not in self.reputation_records:
            self.reputation_records[observer_id] = ReputationRecord(observer_id=observer_id)
    
    def record_action(self, action_type: str, succeeded: bool):
        """Record an action for social mirror simulation."""
        # Map task types to social action types
        action_map = {
            'retrieval': ActionType.EXECUTE,
            'synthesis': ActionType.OVERDELIVER,
            'execution': ActionType.EXECUTE,
            'verification': ActionType.HELP,
            'tool_creation': ActionType.OVERDELIVER,
        }
        social_action = action_map.get(action_type, ActionType.EXECUTE)
        self.action_history.append((social_action, succeeded))
    
    def update_social_mirror(self, observer_id: str, 
                              observed_trust: float | None = None):
        """
        Run the social mirror: simulate what this observer believes
        about us, and check for reputation gaps.
        
        Returns a correction action if needed.
        """
        if observer_id not in self.reputation_records:
            return None
        
        record = self.reputation_records[observer_id]
        
        # Simulate what the observer believes based on our action history
        simulated = self.social_mirror.simulate_beliefs(
            self.action_history, observer_k_level=2
        )
        record.simulated_belief = simulated
        
        # If we have actual observer feedback, check the gap
        if observed_trust is not None:
            gap = simulated.overall_trust() - observed_trust
            record.gap_history.append({
                'generation': self.generation,
                'simulated_trust': round(simulated.overall_trust(), 3),
                'actual_trust': round(observed_trust, 3),
                'gap': round(gap, 3),
            })
            
            # If trust gap < -0.15, trigger social correction
            if gap < -0.15 and self.reputation_sensitivity > 0.0:
                correction = self._choose_social_correction(record, observed_trust)
                record.last_correction = correction
                return correction
        
        return None
    
    def _choose_social_correction(self, record: ReputationRecord,
                                   observed_trust: float) -> str:
        """Choose a corrective action to repair reputation."""
        sim = record.simulated_belief
        self.social_moves.append({
            'generation': self.generation,
            'observer': record.observer_id,
            'simulated_trust': round(sim.overall_trust(), 3),
            'actual_trust': round(observed_trust, 3),
            'trustworthiness': sim.trustworthiness,
            'competence': sim.competence,
        })
        
        if sim.trustworthiness < -0.2:
            return 'overdeliver_to_rebuild_trust'
        elif sim.competence < -0.2:
            return 'boost_competence_then_execute'
        elif sim.cooperativeness < -0.2:
            return 'help_to_show_cooperation'
        else:
            return 'announce_then_deliver'
    
    def get_reputation_summary(self) -> dict:
        """Average reputation across all observers."""
        if not self.reputation_records:
            return {'avg_trust': 0.0, 'n_observers': 0}
        
        trusts = []
        for obs_id, rec in self.reputation_records.items():
            trusts.append(rec.simulated_belief.overall_trust())
        
        return {
            'avg_trust': round(statistics.mean(trusts), 3) if trusts else 0.0,
            'n_observers': len(self.reputation_records),
            'corrections': len(self.social_moves),
        }
    
    def score_for_task(self, task_type: str, difficulty: float,
                       trust_factor: float = 0.0) -> float:
        """
        Score how well this agent matches a task.
        
        Uses:
        - capability (base fitness)
        - trust_factor (social standing — agents with poor rep score lower)
        - free energy (stability)
        - exploration rate (novelty seeking)
        """
        capability = self.capabilities.get(task_type, 0.3)
        
        if self.kernel.free_energy_history:
            recent_fe = self.kernel.free_energy_history[-1].f_combined
            fe_factor = max(0.1, 1.0 - recent_fe)
        else:
            fe_factor = 0.5
        
        exploration = self.kernel.exploration_rate
        
        # Trust-adjusted scoring — social mirror affects task allocation
        score = (
            capability * 0.40 +
            trust_factor * 0.25 +      # NEW: social standing matters
            fe_factor * 0.20 +
            exploration * 0.15
        )
        
        return min(1.0, max(0.0, score + random.uniform(-0.05, 0.05)))
    
    def execute_task(self, task: dict) -> dict:
        """Execute a task and update RSI kernel + social mirror."""
        self.generation += 1
        
        task_type = task.get('type', 'execution')
        difficulty = task.get('difficulty', 0.3)
        
        capability = self.capabilities.get(task_type, 0.3)
        detect_quality = max(0, 1.0 - (self.config.detect_every_n - 1) / 14.0)
        msr_quality = self.config.msr_to_metaloop_gain
        coupling_quality = detect_quality * 0.3 + msr_quality * 0.2
        
        noise = random.uniform(-0.1, 0.1)
        task_success = min(0.95, max(0.1, 
            capability * 0.55 + coupling_quality * 0.15 - difficulty * 0.12 + noise
        ))
        
        tool_failure = max(0.01, 0.15 - coupling_quality * 0.1 + difficulty * 0.3)
        
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
        
        report = self.kernel.observe(events)
        action = self.kernel.act(report)
        
        # Record action for social mirror
        succeeded = task_success > 0.5
        self.record_action(task_type, succeeded)
        
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
        """Return agent status including social reputation."""
        recent_perf = self.performance_history[-5:] if self.performance_history else []
        rep = self.get_reputation_summary()
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
                'msr_gain': round(self.config.msr_to_metaloop_gain, 2),
            },
            'reputation': rep,
            'social_corrections': len(self.social_moves),
        }


# ──────────────────────────────────────────────
# 2. SOCIAL TALENT MARKET — Market with ToM
# ──────────────────────────────────────────────

class SocialTalentMarket:
    """
    Talent market with Social Mirror integration.
    
    Extends the OMC E²R loop with:
    - Trust-adjusted task scoring (reputation affects assignments)
    - Cross-agent belief propagation (each agent knows how others see it)
    - Social review during culling (agents with poor rep AND poor perf get retired faster)
    """
    
    def __init__(self, initial_agents: int = 3, use_social_mirror: bool = True):
        self.agents: dict[str, SocialAgentProfile] = {}
        self.task_history: list[dict] = []
        self.retired_agents: list[dict] = []
        self.market_generation = 0
        self.use_social_mirror = use_social_mirror
        
        # Observer agents watch each agent and maintain beliefs
        self.observers: dict[str, ObserverAgent] = {}
        
        self.meta_kernel = MetaKernel()
        
        # Spawn initial agents
        for i in range(initial_agents):
            agent = SocialAgentProfile(agent_id=f"a{i}")
            self.agents[agent.agent_id] = agent
            self.observers[agent.agent_id] = ObserverAgent(
                name=f"obs_{agent.agent_id}", k_level=2
            )
        
        # Register cross-observer relationships
        self._sync_observers()
        
        print(f"[OMC-S] Social Talent Market initialized with {len(self.agents)} agents.")
        print(f"[OMC-S] Social mirror: {'ON' if use_social_mirror else 'OFF'}")
        for aid, agent in self.agents.items():
            caps_str = ", ".join(f"{k}={v:.2f}" for k, v in agent.capabilities.items())
            print(f"[OMC-S]   {aid}: {caps_str}")
    
    def _sync_observers(self):
        """Register each agent as an observer of all other agents."""
        for aid in self.agents:
            for other_aid in self.agents:
                if other_aid != aid:
                    self.agents[aid].register_observer(f"obs_{other_aid}")
    
    def assign_task(self, task: dict) -> dict:
        """
        Assign a task using trust-adjusted scoring.
        
        E²R: EXECUTE phase with social awareness.
        """
        self.market_generation += 1
        task_type = task.get('type', 'execution')
        difficulty = task.get('difficulty', 0.3)
        
        # 1. Compute trust factors for each agent
        trust_factors = {}
        for aid, agent in self.agents.items():
            if not agent.is_active:
                continue
            
            # Get reputation (average trust across observers)
            rep = agent.get_reputation_summary()
            trust_factors[aid] = rep['avg_trust'] if self.use_social_mirror else 0.0
        
        # 2. Score agents with trust-adjusted weights
        scored_agents = []
        for aid, agent in self.agents.items():
            if not agent.is_active:
                continue
            trust = trust_factors.get(aid, 0.0)
            score = agent.score_for_task(task_type, difficulty, trust)
            scored_agents.append((score, agent))
        
        if not scored_agents:
            return {'error': 'no_active_agents'}
        
        scored_agents.sort(key=lambda x: x[0], reverse=True)
        best_score, best_agent = scored_agents[0]
        
        # 3. Execute task
        result = best_agent.execute_task(task)
        result['market_generation'] = self.market_generation
        result['selection_score'] = round(best_score, 3)
        result['agent_trust'] = round(trust_factors.get(best_agent.agent_id, 0), 3)
        
        self.task_history.append(result)
        
        # 4. Update observers with this agent's actions
        if self.use_social_mirror:
            for obs_id, observer in self.observers.items():
                if obs_id != best_agent.agent_id:
                    # Map task success to social action
                    action_type = ActionType.EXECUTE
                    success = result.get('task_success', 0) > 0.5
                    observer.observe(action_type, success)
            
            # Run social mirror for the assigned agent
            # (it checks its reputation against observers)
            for obs_id, observer in self.observers.items():
                if obs_id == best_agent.agent_id:
                    continue
                correction = best_agent.update_social_mirror(
                    f"obs_{obs_id}", 
                    observed_trust=observer.belief.overall_trust() 
                        if hasattr(observer, 'belief') else None
                )
                if correction:
                    result['social_correction'] = correction
        
        # 5. E²R: EXPLORE
        if self.market_generation % 5 == 0:
            self._evolve_pool()
        
        # 6. E²R: REVIEW
        if self.market_generation % 10 == 0:
            self._review_and_cull()
        
        return result
    
    def _evolve_pool(self):
        """E²R: EXPLORE — spawn new agent or reset weakest."""
        if self.market_generation < 10 or len(self.agents) < 3:
            next_id = len(self.agents) + len(self.retired_agents) + 1
            new_id = f"a{next_id}"
            new_agent = SocialAgentProfile(agent_id=new_id)
            for cap in new_agent.capabilities:
                new_agent.capabilities[cap] = min(0.95, 
                    new_agent.capabilities[cap] + random.uniform(-0.1, 0.15))
            self.agents[new_id] = new_agent
            self.observers[new_id] = ObserverAgent(
                name=f"obs_{new_id}", k_level=2
            )
            self._sync_observers()
            print(f"[OMC-S] EXPLORE: Spawned {new_id}")
    
    def _review_and_cull(self):
        """E²R: REVIEW — retire underperformers with social weighting."""
        for agent in list(self.agents.values()):
            if not agent.is_active:
                continue
            if len(agent.performance_history) < 5:
                continue
            
            recent = agent.performance_history[-5:]
            avg_success = statistics.mean([p['task_success'] for p in recent])
            avg_fe = statistics.mean([p['f_combined'] for p in recent])
            
            # Social weighting: poor reputation accelerates retirement
            rep = agent.get_reputation_summary()
            trust_penalty = max(0, -rep['avg_trust']) if self.use_social_mirror else 0
            
            effective_success = avg_success - trust_penalty * 0.2
            
            if effective_success < 0.35 and avg_fe > 0.5:
                agent.is_active = False
                self.retired_agents.append({
                    'agent_id': agent.agent_id,
                    'tasks_completed': len(agent.performance_history),
                    'avg_success': round(avg_success, 3),
                    'avg_trust': round(rep['avg_trust'], 3),
                    'avg_fe': round(avg_fe, 3),
                    'corrections': len(agent.social_moves),
                })
                print(f"[OMC-S] REVIEW: Retired {agent.agent_id} "
                      f"(success={avg_success:.2f}, trust={rep['avg_trust']:.2f}, "
                      f"FE={avg_fe:.3f})")
                
                next_id = len(self.agents) + len(self.retired_agents) + 1
                new_id = f"a{next_id}"
                new_agent = SocialAgentProfile(agent_id=new_id)
                self.agents[new_id] = new_agent
                self.observers[new_id] = ObserverAgent(
                    name=f"obs_{new_id}", k_level=2
                )
                self._sync_observers()
                print(f"[OMC-S] REVIEW: Spawned replacement {new_id}")
    
    def meta_cmp(self) -> dict:
        active_agents = [a for a in self.agents.values() if a.is_active]
        if not active_agents:
            return {'meta_cmp': 0.0}
        
        agent_cmps = []
        for a in active_agents:
            if a.kernel.generation > 0:
                cmp_val = a.kernel.clade.estimated_cmp(a.kernel.generation)
                agent_cmps.append(cmp_val)
        avg_agent_cmp = statistics.mean(agent_cmps) if agent_cmps else 0.5
        
        caps_vectors = [frozenset(
            (k, round(v, 1)) for k, v in a.capabilities.items()
        ) for a in active_agents]
        diversity = len(set(caps_vectors)) / max(len(caps_vectors), 1)
        
        total_lifetime = len(self.agents) + len(self.retired_agents)
        retirement_rate = len(self.retired_agents) / max(total_lifetime, 1)
        
        recent_tasks = self.task_history[-10:] if self.task_history else []
        avg_market_success = statistics.mean(
            [t['task_success'] for t in recent_tasks]
        ) if recent_tasks else 0.5
        
        meta_cmp = (
            avg_agent_cmp * 0.25 +
            diversity * 0.15 +
            (1 - retirement_rate) * 0.15 +
            avg_market_success * 0.25 +
            0.20  # Social health bonus (placeholder)
        )
        
        return {
            'meta_cmp': round(meta_cmp, 3),
            'avg_market_success': round(avg_market_success, 3),
            'active_agents': len(active_agents),
            'total_retired': len(self.retired_agents),
            'total_tasks': len(self.task_history),
        }
    
    def status_report(self) -> dict:
        active = [a for a in self.agents.values() if a.is_active]
        
        # Social health summary
        all_trusts = []
        for a in active:
            rep = a.get_reputation_summary()
            all_trusts.append(rep['avg_trust'])
        avg_trust = statistics.mean(all_trusts) if all_trusts else 0.0
        
        return {
            'market_generation': self.market_generation,
            'active_agents': len(active),
            'retired_agents': len(self.retired_agents),
            'total_tasks': len(self.task_history),
            'avg_trust': round(avg_trust, 3),
            'social_mirror': self.use_social_mirror,
            'meta_cmp': self.meta_cmp(),
            'agents': [a.status_report() for a in active],
            'retired_summary': [
                {'id': r['agent_id'], 'tasks': r['tasks_completed'],
                 'trust': r.get('avg_trust', 0), 'corrections': r.get('corrections', 0)}
                for r in self.retired_agents[-3:]
            ],
        }


# ──────────────────────────────────────────────
# 3. DEMO — Social Talent Market
# ──────────────────────────────────────────────

def main():
    random.seed = 42
    
    print()
    print("  ╔══════════════════════════════════════════════════════════════════╗")
    print("  ║     SOCIAL TALENT MARKET — Multi-Agent RSI with ToM             ║")
    print("  ║  Trust-adjusted task allocation | Recursive belief modeling    ║")
    print("  ╚══════════════════════════════════════════════════════════════════╝")
    print()
    
    market = SocialTalentMarket(initial_agents=3, use_social_mirror=True)
    print()
    
    print("─" * 72)
    print("  Simulating 40 tasks through the social talent market...")
    print("─" * 72)
    print()
    
    print(f"  {'Task':>4s} {'Type':>12s} {'Diff':>5s} {'Agent':>6s} {'Score':>6s} "
          f"{'Success':>8s} {'Trust':>6s} {'FE':>6s} {'Correction':>18s}")
    print("  " + "─" * 78)
    
    task_types = ['retrieval', 'synthesis', 'execution', 'verification', 'tool_creation']
    
    for task_num in range(40):
        if task_num < 15:
            task_type = random.choice(task_types)
            difficulty = random.uniform(0.2, 0.5)
        elif task_num < 30:
            task_type = 'synthesis' if random.random() < 0.5 else random.choice(task_types)
            difficulty = random.uniform(0.3, 0.6)
        else:
            task_type = random.choice(task_types)
            difficulty = random.uniform(0.1, 0.7)
        
        task = {'type': task_type, 'difficulty': difficulty}
        result = market.assign_task(task)
        
        if 'error' not in result:
            correction = result.get('social_correction', '')
            cor_label = correction[:18] if correction else ''
            print(f"  T{task_num:>2d}  {task_type:>12s} {difficulty:.2f} "
                  f"{result.get('agent_id', '?')[:6]:>6s} "
                  f"{result.get('selection_score', 0):.3f} "
                  f"{result.get('task_success', 0):.2%} "
                  f"{result.get('agent_trust', 0):.3f} "
                  f"{result.get('f_combined', 0):.3f} "
                  f"{cor_label:>18s}")
    
    # ── Summary ──
    print()
    print("─" * 72)
    print("  Social Talent Market Evolution Summary")
    print("─" * 72)
    print()
    
    s = market.status_report()
    mk = s.get('meta_cmp', {})
    
    print(f"  Market generations:   {s['market_generation']}")
    print(f"  Total tasks:          {s['total_tasks']}")
    print(f"  Active agents:        {s['active_agents']}")
    print(f"  Retired:              {s['retired_agents']}")
    print(f"  Social mirror:        {'ON' if s['social_mirror'] else 'OFF'}")
    print(f"  Average trust:        {s.get('avg_trust', 0):.3f}")
    print(f"  Meta-CMP:             {mk.get('meta_cmp', 0):.3f}")
    print(f"  Market success rate:  {mk.get('avg_market_success', 0):.2%}")
    print()
    
    print("  Agent Status (with reputation):")
    for agent in s.get('agents', []):
        rep = agent.get('reputation', {})
        recent_fe = agent.get('recent_fe', 0) or 0
        corr = agent.get('social_corrections', 0)
        print(f"    {agent['agent_id']:>6s}: gen={agent['generation']:>2d} "
              f"tasks={agent['tasks_completed']:>2d} "
              f"success={agent['avg_success']:.0%} "
              f"trust={rep.get('avg_trust', 0):.3f} "
              f"FE={recent_fe:.3f} "
              f"corr={corr}")
    
    if s.get('retired_agents', 0) > 0:
        print()
        print("  Recently Retired:")
        for r in s.get('retired_summary', []):
            print(f"    {r.get('id', '?'):>6s}: {r.get('tasks', 0)} tasks, "
                  f"trust={r.get('trust', 0):.3f}, corr={r.get('corrections', 0)}")
    
    print()
    print("═" * 72)
    print("  E²R with Social Mirror:")
    print("    EXPLORE: Spawn with slight random advantage")
    print("    EXECUTE: capability(0.40) + trust(0.25) + FE(0.20) + explore(0.15)")
    print("    REVIEW:  effective_success = avg_success - trust_penalty * 0.2")
    print()
    print("  Key insight: The Social Mirror creates a trust feedback loop.")
    print("  Agents with poor trust get fewer tasks → less opportunity to")
    print("  recover → faster retirement unless they correct behavior.")
    print("  This is recursive ToM at the organizational level.")
    print("═" * 72)


if __name__ == '__main__':
    main()
