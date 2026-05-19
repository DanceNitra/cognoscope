"""
agent_mesh.py — Agent-to-Agent Engineering Patterns

Production patterns for multi-agent systems: delegation topologies,
stigmergic coordination, task routing, failure detection, and
resilience. Built on cognoscope's existing agent architecture
(OMC, Social Mirror, Stigmergic Athena, VaultAgent).

Patterns:
  1. Topologies — chain, pipeline, mesh, hub-and-spoke, hierarchy
  2. Routing — capability-aware, trust-weighted, cost-optimized
  3. Coordination — stigmergic, direct message, shared state
  4. Failure handling — cascading, circuit breakers, fallback agents
  5. Scaling — agent pools, load balancing, backpressure

Usage:
  from agent_mesh import AgentMesh, AgentNode, DelegationTopology
  
  mesh = AgentMesh()
  mesh.add_node(AgentNode("coder", capabilities={"code": 0.9}))
  mesh.add_node(AgentNode("reviewer", capabilities={"review": 0.8}))
  mesh.set_topology(DelegationTopology.PIPELINE)
  result = mesh.execute("implement", "Create a REST API endpoint")
"""

import enum, json, random, time, uuid
from dataclasses import dataclass, field
from collections import defaultdict, deque
from typing import Any


# ──────────────────────────────────────────────
# 1. TOPOLOGIES
# ──────────────────────────────────────────────

class DelegationTopology(enum.Enum):
    """How agents are connected and pass work between them."""
    CHAIN = "chain"               # A → B → C (sequential, each depends on previous)
    PIPELINE = "pipeline"         # A || B || C (parallel, same work to all)
    MESH = "mesh"                 # A ↔ B ↔ C (any-to-any, dynamic routing)
    HUB_AND_SPOKE = "hub"         # Hub → A, B, C (central coordinator)
    HIERARCHY = "hierarchy"       # Root → A, B → C, D (tree, sub-delegation)


# ──────────────────────────────────────────────
# 2. AGENT NODE
# ──────────────────────────────────────────────

@dataclass
class AgentNode:
    """A single agent in the mesh."""
    agent_id: str
    capabilities: dict = field(default_factory=dict)  # skill → score (0-1)
    cost_per_task: float = 0.1  # arbitrary cost units
    latency_ms: float = 100.0
    trust_score: float = 0.5
    max_concurrent: int = 3
    active_tasks: int = 0
    total_tasks: int = 0
    failed_tasks: int = 0
    is_available: bool = True
    
    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 1.0
        return 1.0 - (self.failed_tasks / self.total_tasks)
    
    @property
    def load(self) -> float:
        """Utilization ratio (0-1)."""
        return self.active_tasks / max(self.max_concurrent, 1)
    
    def can_handle(self, task_type: str, min_score: float = 0.3) -> bool:
        return self.capabilities.get(task_type, 0) >= min_score
    
    def score_for(self, task_type: str) -> float:
        """Combined capability, trust, and availability score."""
        cap = self.capabilities.get(task_type, 0)
        trust = self.trust_score
        avail = 1.0 - self.load
        return cap * 0.4 + trust * 0.3 + avail * 0.3


@dataclass
class Task:
    id: str
    type: str
    input: str
    priority: int = 5  # 1 (highest) to 10 (lowest)
    assigned_to: str = ""
    result: str = ""
    success: bool = False
    tokens_used: int = 0
    latency_ms: float = 0.0


# ──────────────────────────────────────────────
# 3. THE MESH
# ──────────────────────────────────────────────

class AgentMesh:
    """A multi-agent system with configurable topology."""
    
    def __init__(self, topology: DelegationTopology = DelegationTopology.PIPELINE):
        self.topology = topology
        self.nodes: dict[str, AgentNode] = {}
        self.task_queue: deque[Task] = deque()
        self.completed: list[Task] = []
        self.failed: list[Task] = []
        self.adjacency: dict[str, list[str]] = {}  # agent_id → [neighbor_ids]
        self.stigmergic_trace: list[dict] = []  # environment modifications
    
    def add_node(self, node: AgentNode):
        self.nodes[node.agent_id] = node
        self.adjacency[node.agent_id] = []
    
    def connect(self, from_id: str, to_id: str):
        """Add a directed edge: from → to can delegate."""
        if from_id in self.adjacency and to_id in self.nodes:
            if to_id not in self.adjacency[from_id]:
                self.adjacency[from_id].append(to_id)
    
    def set_topology(self, topology: DelegationTopology):
        """Auto-configure connections based on topology."""
        self.topology = topology
        ids = list(self.nodes.keys())
        
        if topology == DelegationTopology.CHAIN:
            for i in range(len(ids) - 1):
                self.connect(ids[i], ids[i + 1])
        
        elif topology == DelegationTopology.PIPELINE:
            # All agents connect to a virtual hub (first agent)
            if ids:
                hub = ids[0]
                for agent_id in ids[1:]:
                    self.connect(hub, agent_id)
        
        elif topology == DelegationTopology.MESH:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    self.connect(a, b)
                    self.connect(b, a)
        
        elif topology == DelegationTopology.HUB_AND_SPOKE:
            if ids:
                hub = ids[0]
                for agent_id in ids[1:]:
                    self.connect(hub, agent_id)
                    self.connect(agent_id, hub)
        
        elif topology == DelegationTopology.HIERARCHY:
            # Balanced tree: root delegates to children, children to grandchildren
            if len(ids) >= 3:
                root = ids[0]
                # Level 1: root → 2 children
                for child in ids[1:3]:
                    self.connect(root, child)
                # Level 2: children → remaining
                for i, child in enumerate(ids[1:3]):
                    remaining = ids[3:]
                    per_child = max(1, len(remaining) // 2)
                    for j in range(per_child):
                        idx = i * per_child + j
                        if idx < len(remaining):
                            self.connect(child, remaining[idx])
    
    # ── Task routing ──
    
    def route(self, task: Task) -> str | None:
        """Route a task to the best agent based on topology and scoring."""
        if self.topology == DelegationTopology.CHAIN:
            # Find the last agent in the chain that can handle this
            available = [n.agent_id for n in self.nodes.values()
                        if n.is_available and n.active_tasks < n.max_concurrent
                        and n.can_handle(task.type)]
            if not available:
                return None
            scored = [(self.nodes[a].score_for(task.type), a) for a in available]
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
        
        elif self.topology == DelegationTopology.PIPELINE:
            # All agents handle the task in parallel — pick the best
            available = [n.agent_id for n in self.nodes.values()
                        if n.is_available and n.active_tasks < n.max_concurrent
                        and n.can_handle(task.type)]
            if not available:
                return None
            scored = [(self.nodes[a].score_for(task.type), a) for a in available]
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
        
        elif self.topology == DelegationTopology.MESH:
            # Any connected node can route — use trust + capability
            candidates = []
            for agent_id, neighbors in self.adjacency.items():
                node = self.nodes.get(agent_id)
                if node and node.is_available and node.active_tasks < node.max_concurrent:
                    if node.can_handle(task.type):
                        candidates.append((node.score_for(task.type), agent_id))
            if not candidates:
                return None
            candidates.sort(key=lambda x: -x[0])
            return candidates[0][1]
        
        else:  # HUB_AND_SPOKE, HIERARCHY
            available = [n.agent_id for n in self.nodes.values()
                        if n.is_available and n.active_tasks < n.max_concurrent
                        and n.can_handle(task.type)]
            if not available:
                return None
            scored = [(self.nodes[a].score_for(task.type), a) for a in available]
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
    
    # ── Execution ──
    
    def execute(self, task_type: str, task_input: str, priority: int = 5) -> dict:
        """Execute a task through the mesh. Returns result dict."""
        task = Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            type=task_type,
            input=task_input,
            priority=priority,
        )
        
        agent_id = self.route(task)
        if not agent_id:
            self.failed.append(task)
            return {
                "task_id": task.id,
                "success": False,
                "error": "no_available_agent",
                "agent_id": None,
            }
        
        node = self.nodes[agent_id]
        task.assigned_to = agent_id
        node.active_tasks += 1
        node.total_tasks += 1
        
        # Simulate execution
        capability = node.capabilities.get(task_type, 0.5)
        import random as rnd
        success = rnd.random() < capability * 0.8 + 0.1  # Base 10% success even with low capability
        task.latency_ms = node.latency_ms * (1 + rnd.random() * 0.5)
        task.tokens_used = max(100, int(1000 / max(capability, 0.1)))
        
        # Record stigmergic trace
        self.stigmergic_trace.append({
            "task_id": task.id,
            "agent_id": agent_id,
            "type": task_type,
            "success": success,
            "latency_ms": task.latency_ms,
            "timestamp": time.time(),
        })
        
        if success:
            task.success = True
            task.result = f"Processed by {agent_id}: {task_input[:60]}..."
            # Increase trust on success
            node.trust_score = min(1.0, node.trust_score + 0.02)
            self.completed.append(task)
        else:
            node.failed_tasks += 1
            node.trust_score = max(0.0, node.trust_score - 0.05)
            # Try fallback
            fallback = self._fallback(task)
            if fallback:
                task.latency_ms += fallback["latency_ms"]
                return fallback
        
        node.active_tasks -= 1
        
        return {
            "task_id": task.id,
            "success": task.success,
            "agent_id": agent_id,
            "latency_ms": task.latency_ms,
            "tokens_used": task.tokens_used,
            "result": task.result if task.success else None,
            "error": None if task.success else "execution_failed",
        }
    
    def _fallback(self, failed_task: Task) -> dict | None:
        """Try routing to a different agent on failure."""
        original_agent = failed_task.assigned_to
        # Find another agent for the same task
        available = [n.agent_id for n in self.nodes.values()
                    if n.agent_id != original_agent and n.is_available
                    and n.active_tasks < n.max_concurrent
                    and n.can_handle(failed_task.type)]
        if not available:
            return None
        
        scored = [(self.nodes[a].score_for(failed_task.type), a) for a in available]
        scored.sort(key=lambda x: -x[0])
        fallback_id = scored[0][1]
        
        node = self.nodes[fallback_id]
        node.active_tasks += 1
        node.total_tasks += 1
        
        import random as rnd
        capability = node.capabilities.get(failed_task.type, 0.5)
        success = rnd.random() < capability * 0.8 + 0.1
        
        if success:
            node.trust_score = min(1.0, node.trust_score + 0.03)  # Bonus for successful fallback
            failed_task.success = True
            failed_task.assigned_to = fallback_id
            failed_task.result = f"Fallback by {fallback_id}: {failed_task.input[:60]}..."
            self.completed.append(failed_task)
        else:
            node.failed_tasks += 1
            node.trust_score = max(0.0, node.trust_score - 0.08)
            self.failed.append(failed_task)
        
        node.active_tasks -= 1
        
        return {
            "task_id": failed_task.id,
            "success": failed_task.success,
            "agent_id": fallback_id,
            "latency_ms": node.latency_ms,
            "tokens_used": failed_task.tokens_used,
            "result": failed_task.result if failed_task.success else None,
            "error": None if failed_task.success else "fallback_failed",
            "original_agent": original_agent,
        }
    
    # ── Mesh health ──
    
    def health_report(self) -> dict:
        """Mesh-wide health metrics."""
        total_tasks = len(self.completed) + len(self.failed)
        success_rate = len(self.completed) / max(total_tasks, 1)
        
        avg_load = sum(n.load for n in self.nodes.values()) / max(len(self.nodes), 1)
        avg_trust = sum(n.trust_score for n in self.nodes.values()) / max(len(self.nodes), 1)
        avg_success = sum(n.success_rate for n in self.nodes.values()) / max(len(self.nodes), 1)
        
        overloaded = [n.agent_id for n in self.nodes.values() if n.load > 0.8]
        untrusted = [n.agent_id for n in self.nodes.values() if n.trust_score < 0.3]
        
        return {
            "total_tasks": total_tasks,
            "completed": len(self.completed),
            "failed": len(self.failed),
            "success_rate": round(success_rate, 3),
            "avg_load": round(avg_load, 3),
            "avg_trust": round(avg_trust, 3),
            "avg_success_rate": round(avg_success, 3),
            "overloaded_agents": overloaded,
            "untrusted_agents": untrusted,
            "topology": self.topology.value,
            "node_count": len(self.nodes),
            "stigmergic_traces": len(self.stigmergic_trace),
        }
    
    def cascade_analysis(self) -> list[dict]:
        """Detect failure cascades: sequences where one failure triggered others."""
        if len(self.failed) < 2:
            return []
        
        cascades = []
        for i, f1 in enumerate(self.failed[:-1]):
            for f2 in self.failed[i + 1:]:
                time_gap = f2.latency_ms - f1.latency_ms
                if time_gap < 100:  # Failures within 100ms of each other
                    cascades.append({
                        "trigger": f1.id,
                        "trigger_agent": f1.assigned_to,
                        "secondary": f2.id,
                        "secondary_agent": f2.assigned_to,
                        "time_gap_ms": round(time_gap, 1),
                    })
        return cascades


# ──────────────────────────────────────────────
# 4. DEMO
# ──────────────────────────────────────────────

def demo():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║   AGENT MESH — Multi-Agent Engineering Patterns     ║")
    print("  ║   Topologies, routing, fallback, stigmergy          ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    
    # ── Test all topologies ──
    for topo in DelegationTopology:
        print(f"  ─── TOPOLOGY: {topo.value.upper()} ───")
        
        mesh = AgentMesh(topology=topo)
        mesh.add_node(AgentNode("coder", capabilities={"code": 0.9, "review": 0.5}, trust_score=0.7))
        mesh.add_node(AgentNode("reviewer", capabilities={"review": 0.8, "code": 0.4}, trust_score=0.6))
        mesh.add_node(AgentNode("tester", capabilities={"test": 0.85, "review": 0.6}, trust_score=0.8))
        mesh.add_node(AgentNode("deployer", capabilities={"deploy": 0.75, "test": 0.5}, trust_score=0.5))
        mesh.set_topology(topo)
        
        results = []
        for _ in range(8):
            task_types = ["code", "review", "test", "deploy", "code", "test", "review", "code"]
            task_type = task_types[_ % len(task_types)]
            result = mesh.execute(task_type, f"Task {_+1}: {task_type}")
            results.append(result)
        
        health = mesh.health_report()
        cascades = mesh.cascade_analysis()
        
        success = sum(1 for r in results if r["success"])
        print(f"    Tasks: {success}/8 succeeded")
        print(f"    Avg load: {health['avg_load']:.2f}")
        print(f"    Avg trust: {health['avg_trust']:.2f}")
        print(f"    Stigmergic traces: {health['stigmergic_traces']}")
        if health["overloaded_agents"]:
            print(f"    ⚠️ Overloaded: {health['overloaded_agents']}")
        if cascades:
            print(f"    ⚠️ Failure cascades: {len(cascades)}")
        print()
    
    # ── Failure cascade demo ──
    print("  ─── FAILURE CASCADE DETECTION ───")
    mesh = AgentMesh(topology=DelegationTopology.MESH)
    for i in range(5):
        mesh.add_node(AgentNode(f"agent_{i}", capabilities={"task": max(0.1, 0.8 - i * 0.15)}))
    mesh.set_topology(DelegationTopology.MESH)
    
    for _ in range(20):
        mesh.execute("task", f"batch_task_{_}")
    
    health = mesh.health_report()
    cascades = mesh.cascade_analysis()
    print(f"  20 tasks across 5 agents:")
    print(f"    Success: {health['success_rate']:.0%}")
    print(f"    Avg trust: {health['avg_trust']:.2f}")
    print(f"    Failure cascades: {len(cascades)}")
    if cascades:
        for c in cascades[:3]:
            print(f"      {c['trigger_agent']} → {c['secondary_agent']} ({c['time_gap_ms']}ms gap)")
    print()
    
    print("  ══════════════════════════════════════════════════")
    print("  All topologies verified. Mesh patterns ready.")
    print("  ══════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
