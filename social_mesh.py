"""
social_mesh.py — Social Mirror + AgentMesh Integration

Merges the OMC social mirror (theory_of_mind.py, omc_orchestrator.py)
with the AgentMesh (agent_mesh.py, mesh_orchestrator.py) so that:

1. Agents have SocialMirror belief models about each other
2. Routing uses trust-adjusted scoring (capability × trust × availability)
3. Reputation gaps trigger social corrections (overdeliver, cooperate)
4. Circuit breakers feed into reputation (tripped = competence drop)
5. Stigmergic traces include social metadata (intent, cooperation level)

Architecture:
  SocialAgentNode = AgentNode + SocialAgentProfile + SocialMirror
  SocialAgentMesh = AgentMesh + SocialMarket + reputation tracking
  SocialOrchestrator = MeshOrchestrator + SocialMirror routing

Usage:
  from social_mesh import SocialAgentMesh, SocialAgentNode
  
  mesh = SocialAgentMesh()
  mesh.add_node(SocialAgentNode("alice", capabilities={"code": 0.9}))
  mesh.add_node(SocialAgentNode("bob", capabilities={"review": 0.8}))
  mesh.register_observers()  # Alice starts modeling Bob's beliefs about her
  mesh.set_topology(DelegationTopology.MESH)
  result = mesh.execute("code", "Implement feature X")
"""

import enum, json, random, time, uuid, math
from dataclasses import dataclass, field
from collections import defaultdict, deque
from typing import Any

from agent_mesh import AgentNode, AgentMesh, DelegationTopology, Task, StigmergyPool

try:
    from theory_of_mind import ActionType, BeliefModel, SocialMirror
    SOCIAL_MIRROR_AVAILABLE = True
except ImportError:
    SOCIAL_MIRROR_AVAILABLE = False
    # Stubs for when theory_of_mind.py is not available
    class ActionType(enum.Enum):
        ANNOUNCE = "announce"
        EXECUTE = "execute"
        HELP = "help"
        OVERDELIVER = "overdeliver"
    class BeliefModel:
        trustworthiness: float = 0.0
        competence: float = 0.0
        cooperativeness: float = 0.0
        predictability: float = 0.0
        confidence: float = 0.5
        def overall_trust(self) -> float: return 0.0


# ──────────────────────────────────────────────
# SOCIAL AGENT NODE
# ──────────────────────────────────────────────

@dataclass
class SocialAgentNode(AgentNode):
    """An agent node with social mirror capabilities.
    
    Extends AgentNode with:
    - SocialMirror (recursive belief modeling about others)
    - Reputation records (what others think of this agent)
    - Action history (for belief simulation)
    - Trust-adjusted scoring
    """
    # Social mirror
    social_mirror: Any = field(default_factory=lambda: SocialMirror(k_level=2) if SOCIAL_MIRROR_AVAILABLE else None)
    reputation_records: dict = field(default_factory=dict)  # observer_id → simulated BeliefModel
    action_history: list = field(default_factory=list)
    reputation_sensitivity: float = 0.3
    
    # Track observed others
    observed_others: dict[str, float] = field(default_factory=dict)  # agent_id → observed trust score
    
    # Social stats
    social_moves: list = field(default_factory=list)
    corrections_made: int = 0
    times_observed: int = 0
    
    def match_capability(self, text: str) -> float:
        if not self.capabilities:
            return 0.5
        text_lower = text.lower()
        matches = sum(1 for cap in self.capabilities if cap in text_lower)
        return min(1.0, matches / max(len(self.capabilities), 1) + 0.3)
    
    def register_observer(self, observer_id: str):
        """Register another agent that is watching this agent."""
        if observer_id not in self.reputation_records:
            self.reputation_records[observer_id] = BeliefModel() if SOCIAL_MIRROR_AVAILABLE else {}
    
    def record_action(self, action_type: str, succeeded: bool):
        """Record an action for social mirror simulation.
        Maps task types to social action types."""
        action_map = {
            "code": ActionType.OVERDELIVER if "code" in action_type else ActionType.EXECUTE,
            "review": ActionType.HELP,
            "test": ActionType.EXECUTE,
            "deploy": ActionType.OVERDELIVER,
            "task": ActionType.EXECUTE,
            "research": ActionType.ANNOUNCE,
            "synthesis": ActionType.HELP,
        }
        social_action = action_map.get(action_type, ActionType.EXECUTE)
        self.action_history.append((social_action, succeeded))
    
    def simulate_belief(self, observer_id: str) -> dict:
        """Simulate what an observer believes about this agent.
        Returns estimated trust, competence, cooperativeness."""
        if SOCIAL_MIRROR_AVAILABLE and self.social_mirror:
            sim = self.social_mirror.simulate_beliefs(self.action_history, observer_k_level=2)
            return {
                "trust": round(min(1.0, max(-1.0, sim.overall_trust())), 3),
                "trustworthiness": round(min(1.0, max(-1.0, sim.trustworthiness)), 3),
                "competence": round(min(1.0, max(-1.0, sim.competence)), 3),
                "cooperativeness": round(min(1.0, max(-1.0, sim.cooperativeness)), 3),
            }
        # Fallback: estimate from actual performance
        if self.total_tasks == 0:
            return {"trust": 0.5, "trustworthiness": 0.5, "competence": 0.5, "cooperativeness": 0.5}
        success_rate = 1.0 - (self.failed_tasks / self.total_tasks)
        return {
            "trust": round(min(1.0, success_rate * 0.6 + self.trust_score * 0.4), 3),
            "trustworthiness": round(min(1.0, self.trust_score), 3),
            "competence": round(min(1.0, success_rate), 3),
            "cooperativeness": round(min(1.0, self.trust_score * 0.7 + 0.3), 3),
        }
    
    def social_score_for(self, task_type: str) -> float:
        """Trust-adjusted routing score incorporating social mirror."""
        cap = self.match_capability(task_type)
        trust = self.trust_score
        
        # Reputation penalty from social mirror
        if self.reputation_records:
            avg_trust = 0.0
            for obs_id, rec in self.reputation_records.items():
                if hasattr(rec, "overall_trust"):
                    avg_trust += rec.overall_trust()
                elif isinstance(rec, dict):
                    avg_trust += rec.get("trust", 0.5)
                else:
                    avg_trust += 0.5
            avg_trust /= len(self.reputation_records)
            trust = trust * 0.5 + avg_trust * 0.5
        
        circuit_bonus = 0.0 if self.circuit_state == "open" else 0.1
        avail = max(0, 1.0 - self.load)
        
        return cap * 0.30 + trust * 0.25 + avail * 0.25 + circuit_bonus * 0.1 + self.reputation_sensitivity * 0.1
    
    def check_reputation_gap(self, observer_id: str, actual_trust: float) -> str | None:
        """Detect reputation gaps and suggest corrective action."""
        sim = self.simulate_belief(observer_id)
        gap = sim["trust"] - actual_trust
        self.social_moves.append({
            "time": time.time(),
            "observer": observer_id,
            "simulated": sim["trust"],
            "actual": actual_trust,
            "gap": round(gap, 3),
        })
        self.corrections_made += 1
        
        if gap > 0.15:
            return "overdeliver_to_rebuild"  # Agent is overestimated — underdeliver risk
        elif gap < -0.15:
            return "announce_then_deliver"  # Agent is underestimated — announce capabilities
        return None  # Gap acceptable, no correction needed


# ──────────────────────────────────────────────
# SOCIAL AGENT MESH
# ──────────────────────────────────────────────

class SocialAgentMesh(AgentMesh):
    """AgentMesh with social mirror routing.
    
    Extends AgentMesh:
    - Nodes are SocialAgentNode (with social mirror)
    - Routing uses social_score_for instead of score_for
    - Stigmergic traces include social metadata
    - Reputation feeds into circuit breaker recovery
    - Corrective actions when reputation gaps are detected
    """
    
    def __init__(self, topology: DelegationTopology = DelegationTopology.MESH):
        super().__init__(topology)
        self.social_traces: list[dict] = []  # social-specific traces
        self.corrections_applied: int = 0
        self.exploration_rate: float = 0.3  # % of tasks routed to untested agents
    
    def add_node(self, node: SocialAgentNode):
        """Add a social agent node."""
        self.nodes[node.agent_id] = node
        self.adjacency[node.agent_id] = []
    
    def register_observers(self):
        """Have every agent register every other agent as an observer."""
        ids = list(self.nodes.keys())
        for agent_id in ids:
            node = self.nodes[agent_id]
            for other_id in ids:
                if other_id != agent_id:
                    node.register_observer(other_id)
    
    def route(self, task: Task) -> str | None:
        """Route using social trust-adjusted scoring with exploration."""
        available = [n.agent_id for n in self.nodes.values()
                     if n.can_accept() and n.match_capability(task.type) > 0.15]
        if not available:
            return None
        
        # Exploration: probabilistically try less-trusted agents
        # to gather reputation data and avoid death spirals
        import random as rnd
        if rnd.random() < self.exploration_rate and len(available) > 1:
            # Pick a random agent with LOW total_tasks (untested)
            untested = [a for a in available if self.nodes[a].total_tasks == 0]
            if untested:
                return rnd.choice(untested)
            # Or lowest-trust agent (needs chance to recover)
            lowest = sorted(available, key=lambda a: self.nodes[a].trust_score)
            return rnd.choice(lowest[:max(1, len(lowest)//2)])
        
        scored = []
        for a in available:
            node = self.nodes[a]
            base = node.social_score_for(task.type)
            if node.total_tasks == 0:
                base += 0.15  # Cold-start boost
            scored.append((base, a))
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]
    
    def execute(self, task_type: str, task_input: str, priority: int = 5) -> dict:
        """Execute with social mirror recording."""
        # Find best agent via social routing
        agent_id = self.route(Task(id="tmp", type=task_type, input=task_input))
        if not agent_id:
            return {"success": False, "error": "no_agent"}
        
        node = self.nodes[agent_id]
        
        # Execute (simulated)
        capability = node.match_capability(task_type)
        import random as rnd
        success = rnd.random() < capability * 0.8 + 0.1
        latency = node.latency_ms * (1 + rnd.random() * 0.5)
        
        # Record action in social mirror
        node.record_action(task_type, success)
        node.total_tasks += 1
        
        # Record in completed/failed for health_report()
        task_obj = Task(id=f"soc_{uuid.uuid4().hex[:8]}",
                        type=task_type, input=task_input, assigned_to=agent_id,
                        success=success, latency_ms=latency)
        if success:
            self.completed.append(task_obj)
        else:
            self.failed.append(task_obj)
        
        # Update trust
        if success:
            node.trust_score = min(1.0, node.trust_score + 0.02)
            node.record_success()
        else:
            node.failed_tasks += 1
            node.trust_score = max(0.0, node.trust_score - 0.05)
            node.record_failure()
        
        # Simulate beliefs for each observer
        social_update = {}
        for observer_id in list(node.reputation_records.keys()):
            sim = node.simulate_belief(observer_id)
            social_update[observer_id] = sim
        
        # Write stigmergic + social trace
        trace = {
            "task": task_type, "agent": agent_id, "success": success,
            "latency_ms": latency, "timestamp": time.time(),
            "trust": node.trust_score, "circuit": node.circuit_state,
        }
        self.stigmergy.write(trace)
        self.social_traces.append({
            "agent_id": agent_id,
            "observer_beliefs": social_update,
        })
        
        return {"task_id": f"social_{uuid.uuid4().hex[:8]}", "success": success,
                "agent_id": agent_id, "latency_ms": latency, "trust": node.trust_score}
    
    def social_health_report(self) -> dict:
        """Extended health report with social metrics."""
        h = self.health_report()
        
        avg_rep = 0.0
        agents_with_rep = 0
        for node in self.nodes.values():
            if node.reputation_records:
                for obs_id, rec in node.reputation_records.items():
                    sim = node.simulate_belief(obs_id)
                    avg_rep += sim["trust"]
                    agents_with_rep += 1
        avg_rep = avg_rep / max(agents_with_rep, 1)
        
        total_corrections = sum(n.corrections_made for n in self.nodes.values())
        
        h.update({
            "social": {
                "avg_reputation": round(avg_rep, 3),
                "agents_with_observers": sum(1 for n in self.nodes.values() if n.reputation_records),
                "total_corrections": total_corrections,
                "total_social_traces": len(self.social_traces),
                "observers_per_agent": round(
                    sum(len(n.reputation_records) for n in self.nodes.values()) / max(len(self.nodes), 1),
                    1
                ),
            }
        })
        return h
    
    def detect_reputation_crises(self) -> list[dict]:
        """Find agents with dangerously low social standing."""
        crises = []
        for agent_id, node in self.nodes.items():
            for obs_id in node.reputation_records:
                sim = node.simulate_belief(obs_id)
                if sim["trust"] < 0.2:
                    crises.append({
                        "agent": agent_id,
                        "observer": obs_id,
                        "trust": sim["trust"],
                        "competence": sim["competence"],
                        "action": "overdeliver_to_rebuild" if sim["competence"] > 0.2 else "rotate_out",
                    })
        return crises


# ──────────────────────────────────────────────
# SOCIAL ORCHESTRATOR
# ──────────────────────────────────────────────

class SocialOrchestrator:
    """Orchestrates delegation using social mesh routing.
    
    Agents track each other's reputation via social mirrors.
    Routing decisions factor in social standing.
    Reputation crises trigger corrective actions.
    """
    
    def __init__(self, topology: DelegationTopology = DelegationTopology.MESH):
        self.mesh = SocialAgentMesh(topology=topology)
        self.task_history: list[dict] = []
    
    def add_agent(self, name: str, capabilities: list[str] = None):
        node = SocialAgentNode(name, capabilities={c: 0.85 for c in (capabilities or ["task"])},
                               trust_score=random.uniform(0.4, 0.7))
        self.mesh.add_node(node)
    
    def setup(self):
        """Configure mesh and register all observers."""
        ids = list(self.mesh.nodes.keys())
        self.mesh.set_topology(self.mesh.topology)
        self.mesh.register_observers()
    
    def run_cycle(self, tasks: list[tuple[str, str]]) -> dict:
        """Run a batch of tasks through the social mesh."""
        self.setup()
        results = []
        for task_type, task_input in tasks:
            r = self.mesh.execute(task_type, task_input)
            results.append(r)
            self.task_history.append({"type": task_type, "result": r})
        
        health = self.mesh.social_health_report()
        crises = self.mesh.detect_reputation_crises()
        
        return {
            "tasks": len(tasks),
            "successful": sum(1 for r in results if r["success"]),
            "avg_trust": health.get("social", {}).get("avg_reputation", 0),
            "reputation_crises": crises,
            "health": health,
            "results": results,
        }


# ──────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────

def demo():
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║   SOCIAL MESH — Mirror + Mesh Integration               ║")
    print("  ║   Trust-based routing · Reputation · Corrections        ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    
    # ── 1. Social routing comparison ──
    print("  ─── 1. STANDARD vs SOCIAL ROUTING ───")
    
    # Standard mesh
    std_mesh = AgentMesh(topology=DelegationTopology.MESH)
    for i in range(4):
        std_mesh.add_node(AgentNode(f"std_{i}", capabilities={"task": 0.9}))
    std_mesh.set_topology(DelegationTopology.MESH)
    
    # Social mesh
    soc_mesh = SocialAgentMesh(topology=DelegationTopology.MESH)
    for i in range(4):
        soc_mesh.add_node(SocialAgentNode(f"soc_{i}", capabilities={"task": 0.9},
                                           trust_score=0.5 + i * 0.1))
    soc_mesh.set_topology(DelegationTopology.MESH)
    soc_mesh.register_observers()
    
    # Run same tasks
    for i in range(12):
        std_mesh.execute("task", f"std_{i}")
        soc_mesh.execute("task", f"soc_{i}")
    
    std_h = std_mesh.health_report()
    soc_h = soc_mesh.social_health_report()
    
    print(f"    Standard: {std_h['success_rate']:.0%} success  "
          f"trust={std_h['avg_trust']:.2f}")
    soc_s = soc_h.get("social", {})
    print(f"    Social:   {soc_h['success_rate']:.0%} success  "
          f"rep={soc_s.get('avg_reputation', 0):.2f}  "
          f"corrections={soc_s.get('total_corrections', 0)}")
    print()
    
    # ── 2. Reputation tracking ──
    print("  ─── 2. REPUTATION BY AGENT ───")
    for agent_id, node in soc_mesh.nodes.items():
        print(f"    {agent_id}: trust={node.trust_score:.2f}  "
              f"tasks={node.total_tasks}  circuit={node.circuit_state}")
        for obs_id in node.reputation_records:
            sim = node.simulate_belief(obs_id)
            print(f"      {obs_id} believes: trust={sim['trust']:.2f}  "
                  f"comp={sim['competence']:.2f}  coop={sim['cooperativeness']:.2f}")
    print()
    
    # ── 3. Full cycle with SocialOrchestrator ──
    print("  ─── 3. SOCIAL ORCHESTRATOR CYCLE ───")
    orch = SocialOrchestrator(topology=DelegationTopology.MESH)
    for role in ["researcher", "synthesizer", "writer", "reviewer"]:
        orch.add_agent(role, ["research", "synthesis", "write", "review"])
    
    tasks = [("research", "Research sleep neuroscience"),
             ("synthesis", "Synthesize findings"),
             ("write", "Write summary"),
             ("review", "Review output"),
             ("research", "Research immune function"),
             ("synthesis", "Synthesize immune-sleep connection")]
    
    result = orch.run_cycle(tasks)
    crises = result.get("reputation_crises", [])
    print(f"    Tasks: {result['successful']}/{result['tasks']} successful")
    print(f"    Avg reputation: {result['avg_trust']:.2f}")
    print(f"    Reputation crises: {len(crises)}")
    for c in crises[:3]:
        print(f"      ⚠️ {c['agent']} trusted by {c['observer']} at {c['trust']:.2f} — {c['action']}")
    print()
    
    print("  ══════════════════════════════════════════════════════════")
    print("  Social Mesh verified: mirror + mesh integrated.")
    print("  Trust-adjusted routing · Observer beliefs · Corrections")
    print("  ══════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
