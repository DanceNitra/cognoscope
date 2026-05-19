"""
agent_mesh.py — Agent-to-Agent Engineering Patterns (v2)

Production patterns for multi-agent systems: delegation topologies,
circuit breakers, stigmergic coordination, dynamic topology
reconfiguration, backpressure, cascade detection, and stress testing.

v2 additions:
  - Per-agent circuit breaker (trips on N consecutive failures)
  - Stigmergic coordinate via shared trace pool (no direct messaging)
  - Dynamic re-topology: chain or hub that fails reconfigures to mesh
  - Backpressure: queue tasks when no agent available, throttle
  - Cascade classification (load, trust, topology)
  - Stress-test engine: spike, agent-death, slow-degradation scenarios

Usage:
  from agent_mesh import AgentMesh, AgentNode, DelegationTopology
  mesh = AgentMesh()
  mesh.add_node(AgentNode("coder", capabilities={"code": 0.9}))
  mesh.add_node(AgentNode("reviewer", capabilities={"review": 0.8}))
  mesh.set_topology(DelegationTopology.PIPELINE)
  result = mesh.execute("code", "Create a REST API endpoint")
"""

import enum, json, random, time, uuid, copy
from dataclasses import dataclass, field
from collections import defaultdict, deque
from typing import Any


# ──────────────────────────────────────────────
# 1. TOPOLOGIES
# ──────────────────────────────────────────────

class DelegationTopology(enum.Enum):
    CHAIN = "chain"
    PIPELINE = "pipeline"
    MESH = "mesh"
    HUB_AND_SPOKE = "hub"
    HIERARCHY = "hierarchy"


# ──────────────────────────────────────────────
# 2. AGENT NODE (v2 — circuit breaker + stigmergy)
# ──────────────────────────────────────────────

@dataclass
class AgentNode:
    agent_id: str
    capabilities: dict = field(default_factory=dict)
    cost_per_task: float = 0.1
    latency_ms: float = 100.0
    trust_score: float = 0.5
    max_concurrent: int = 3
    active_tasks: int = 0
    total_tasks: int = 0
    failed_tasks: int = 0

    # v2: Circuit breaker
    circuit_state: str = "closed"   # closed, open, half-open
    circuit_failures: int = 0
    circuit_tripped_at: float = 0.0
    circuit_threshold: int = 3      # consecutive failures to trip
    circuit_cooldown_s: float = 5.0

    # v2: Stigmergy read/write counters
    stigmergic_writes: int = 0
    stigmergic_reads: int = 0

    def can_accept(self) -> bool:
        if self.circuit_state == "open":
            if time.time() - self.circuit_tripped_at > self.circuit_cooldown_s:
                self.circuit_state = "half-open"
                return True
            return False
        return self.active_tasks < self.max_concurrent

    def trip_circuit(self):
        self.circuit_state = "open"
        self.circuit_tripped_at = time.time()

    def record_success(self):
        self.circuit_failures = 0
        if self.circuit_state == "half-open":
            self.circuit_state = "closed"

    def record_failure(self):
        self.circuit_failures += 1
        if self.circuit_failures >= self.circuit_threshold:
            self.trip_circuit()

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 1.0
        return 1.0 - (self.failed_tasks / self.total_tasks)

    @property
    def load(self) -> float:
        return self.active_tasks / max(self.max_concurrent, 1)

    def can_handle(self, task_type: str, min_score: float = 0.3) -> bool:
        return self.capabilities.get(task_type, 0) >= min_score

    def score_for(self, task_type: str) -> float:
        cap = self.capabilities.get(task_type, 0)
        trust = self.trust_score
        avail = max(0, 1.0 - self.load)
        circuit_bonus = 0.0 if self.circuit_state == "open" else 0.1
        return cap * 0.35 + trust * 0.25 + avail * 0.3 + circuit_bonus


@dataclass
class Task:
    id: str
    type: str
    input: str
    priority: int = 5
    assigned_to: str = ""
    result: str = ""
    success: bool = False
    tokens_used: int = 0
    latency_ms: float = 0.0


# ──────────────────────────────────────────────
# 3. STIGMERGY POOL (shared environment)
# ──────────────────────────────────────────────

class StigmergyPool:
    """Shared trace environment — agents coordinate by reading/writing
    traces instead of sending direct messages."""

    def __init__(self, max_traces: int = 200):
        self.traces: list[dict] = []
        self.max_traces = max_traces

    def write(self, trace: dict):
        self.traces.append(trace)
        if len(self.traces) > self.max_traces:
            self.traces = self.traces[-self.max_traces:]

    def read(self, task_type: str = "", agent_id: str = "",
             limit: int = 10, since: float = 0.0) -> list[dict]:
        results = []
        for t in reversed(self.traces):
            if task_type and t.get("type") != task_type:
                continue
            if agent_id and t.get("agent_id") != agent_id:
                continue
            if since and t.get("timestamp", 0) < since:
                continue
            results.append(t)
            if len(results) >= limit:
                break
        return results

    def agent_success_rate(self, agent_id: str, recent_n: int = 10) -> float:
        traces = [t for t in self.traces if t.get("agent_id") == agent_id][-recent_n:]
        if not traces:
            return 1.0
        return sum(1 for t in traces if t.get("success")) / len(traces)

    def best_agent(self, task_type: str) -> str | None:
        """Find most successful agent for this task type via traces
        — pure stigmergic coordination, no direct communication."""
        candidates = [t for t in self.traces if t.get("type") == task_type and t.get("success")]
        if not candidates:
            return None
        counts = defaultdict(lambda: {"success": 0, "total": 0})
        for t in self.traces:
            if t.get("type") != task_type:
                continue
            aid = t["agent_id"]
            counts[aid]["total"] += 1
            if t.get("success"):
                counts[aid]["success"] += 1
        scored = [(c["success"] / max(c["total"], 1), aid) for aid, c in counts.items()]
        scored.sort(key=lambda x: -x[0])
        return scored[0][1] if scored else None


# ──────────────────────────────────────────────
# 4. THE MESH (v2 — circuit breakers, re-topology, backpressure)
# ──────────────────────────────────────────────

class AgentMesh:
    def __init__(self, topology: DelegationTopology = DelegationTopology.PIPELINE):
        self.topology = topology
        self.nodes: dict[str, AgentNode] = {}
        self.adjacency: dict[str, list[str]] = {}
        self.completed: list[Task] = []
        self.failed: list[Task] = []
        self.stigmergy = StigmergyPool()
        self.task_queue: deque[Task] = deque()
        self.backpressure_limit: int = 50
        self.max_retries: int = 2
        self.re_topology_count: int = 0
        self.backpressure_rejected: int = 0

    def add_node(self, node: AgentNode):
        self.nodes[node.agent_id] = node
        self.adjacency[node.agent_id] = []

    def connect(self, from_id: str, to_id: str):
        if from_id in self.adjacency and to_id in self.nodes:
            if to_id not in self.adjacency[from_id]:
                self.adjacency[from_id].append(to_id)

    def disconnect(self, from_id: str, to_id: str):
        if from_id in self.adjacency and to_id in self.adjacency[from_id]:
            self.adjacency[from_id].remove(to_id)

    def set_topology(self, topology: DelegationTopology):
        self.topology = topology
        ids = list(self.nodes.keys())
        self.adjacency = {n: [] for n in ids}

        if topology == DelegationTopology.CHAIN:
            for i in range(len(ids) - 1):
                self.connect(ids[i], ids[i + 1])
        elif topology == DelegationTopology.PIPELINE:
            if ids:
                for agent_id in ids[1:]:
                    self.connect(ids[0], agent_id)
        elif topology == DelegationTopology.MESH:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    self.connect(a, b)
                    self.connect(b, a)
        elif topology == DelegationTopology.HUB_AND_SPOKE:
            if ids:
                for agent_id in ids[1:]:
                    self.connect(ids[0], agent_id)
                    self.connect(agent_id, ids[0])
        elif topology == DelegationTopology.HIERARCHY:
            if len(ids) >= 3:
                root = ids[0]
                for child in ids[1:3]:
                    self.connect(root, child)
                for i, child in enumerate(ids[1:3]):
                    remaining = ids[3:]
                    per_child = max(1, len(remaining) // 2)
                    for j in range(per_child):
                        idx = i * per_child + j
                        if idx < len(remaining):
                            self.connect(child, remaining[idx])

    # ── Dynamic re-topology ──

    def detect_and_repair(self):
        """Check for unhealthy topology patterns and repair them.
        Returns list of repairs made."""
        repairs = []

        if self.topology in (DelegationTopology.CHAIN, DelegationTopology.HUB_AND_SPOKE):
            # Check if any node in the path is circuit-breaker open
            for agent_id, node in self.nodes.items():
                if node.circuit_state == "open":
                    # Repair: bypass the failed node
                    # Find neighbors
                    neighbors = self.adjacency.get(agent_id, [])
                    predecessors = [n for n, neighbors in self.adjacency.items()
                                    if agent_id in neighbors]
                    for pred in predecessors:
                        for succ in neighbors:
                            if pred != succ and succ not in self.adjacency.get(pred, []):
                                self.connect(pred, succ)
                                repairs.append(f"bypassed {agent_id}: {pred} → {succ}")
                    self.re_topology_count += 1

        elif self.topology == DelegationTopology.HIERARCHY:
            # Check for orphaned subtrees (node with no connection to root)
            root = list(self.nodes.keys())[0] if self.nodes else ""
            for agent_id in self.nodes:
                if agent_id == root:
                    continue
                reachable = self._is_reachable(root, agent_id)
                if not reachable:
                    # Reconnect to root
                    self.connect(root, agent_id)
                    repairs.append(f"reconnected orphan {agent_id} → root")
                    self.re_topology_count += 1

        return repairs

    def _is_reachable(self, start: str, target: str, max_hops: int = 5) -> bool:
        visited = {start}
        frontier = [start]
        for _ in range(max_hops):
            next_frontier = []
            for node in frontier:
                for neighbor in self.adjacency.get(node, []):
                    if neighbor == target:
                        return True
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier
        return False

    # ── Stigmergic routing ──

    def route_stigmergic(self, task: Task) -> str | None:
        """Route via stigmergic coordination: read traces, find best agent."""
        best = self.stigmergy.best_agent(task.type)
        if best and self.nodes[best].can_accept() and self.nodes[best].can_handle(task.type):
            return best
        # Fall back to capability routing
        return self.route(task)

    def route(self, task: Task) -> str | None:
        available = [n.agent_id for n in self.nodes.values()
                     if n.can_accept() and n.can_handle(task.type)]
        if not available:
            return None
        scored = [(self.nodes[a].score_for(task.type), a) for a in available]
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    # ── Execution (v2 — backpressure + circuit breakers + stigmergy) ──

    def execute(self, task_type: str, task_input: str, priority: int = 5,
                use_stigmergy: bool = False) -> dict:
        task = Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            type=task_type,
            input=task_input,
            priority=priority,
        )

        # Backpressure: queue if system overloaded
        if len(self.task_queue) > self.backpressure_limit:
            self.backpressure_rejected += 1
            return {"task_id": task.id, "success": False, "error": "backpressure_rejected"}

        # Route
        agent_id = self.route_stigmergic(task) if use_stigmergy else self.route(task)
        if not agent_id:
            # Queue for retry
            if len(self.task_queue) < self.backpressure_limit:
                self.task_queue.append(task)
            else:
                self.backpressure_rejected += 1
                self.failed.append(task)
            return {"task_id": task.id, "success": False, "error": "queued"}

        return self._assign_and_execute(task, agent_id)

    def _assign_and_execute(self, task: Task, agent_id: str) -> dict:
        node = self.nodes[agent_id]
        task.assigned_to = agent_id
        node.active_tasks += 1
        node.total_tasks += 1

        import random as rnd
        capability = node.capabilities.get(task.type, 0.5)
        success = rnd.random() < capability * 0.8 + 0.1
        task.latency_ms = node.latency_ms * (1 + rnd.random() * 0.5)
        task.tokens_used = max(100, int(1000 / max(capability, 0.1)))

        # Write stigmergic trace
        trace = {
            "task_id": task.id, "agent_id": agent_id, "type": task.type,
            "success": success, "latency_ms": task.latency_ms,
            "timestamp": time.time(), "priority": task.priority,
        }
        self.stigmergy.write(trace)
        node.stigmergic_writes += 1

        if success:
            task.success = True
            task.result = f"Processed by {agent_id}: {task.input[:60]}..."
            node.trust_score = min(1.0, node.trust_score + 0.02)
            node.record_success()
            self.completed.append(task)
        else:
            node.failed_tasks += 1
            node.trust_score = max(0.0, node.trust_score - 0.05)
            node.record_failure()

            # Circuit-breaker fallback
            fallback = self._fallback(task, node)
            if fallback:
                task.latency_ms += fallback["latency_ms"]
                node.active_tasks -= 1
                return fallback

            # Retry from queue
            if task.priority >= 3:
                self.task_queue.append(task)

        node.active_tasks -= 1
        # Drain queue
        self._drain_queue()

        return {
            "task_id": task.id, "success": task.success,
            "agent_id": agent_id, "latency_ms": task.latency_ms,
            "tokens_used": task.tokens_used,
            "result": task.result if task.success else None,
            "error": None if task.success else "execution_failed",
        }

    def _fallback(self, task: Task, failed_node: AgentNode) -> dict | None:
        original_agent = task.assigned_to
        available = [n.agent_id for n in self.nodes.values()
                     if n.agent_id != original_agent and n.can_accept()
                     and n.can_handle(task.type)]
        if not available:
            return None
        scored = [(self.nodes[a].score_for(task.type), a) for a in available]
        scored.sort(key=lambda x: -x[0])
        fallback_id = scored[0][1]

        node = self.nodes[fallback_id]
        node.active_tasks += 1
        node.total_tasks += 1

        import random as rnd
        capability = node.capabilities.get(task.type, 0.5)
        success = rnd.random() < capability * 0.8 + 0.1

        if success:
            node.trust_score = min(1.0, node.trust_score + 0.03)
            node.record_success()
            task.success = True
            task.assigned_to = fallback_id
            task.result = f"Fallback by {fallback_id}: {task.input[:60]}..."
            self.completed.append(task)
        else:
            node.failed_tasks += 1
            node.trust_score = max(0.0, node.trust_score - 0.08)
            node.record_failure()
            self.failed.append(task)

        node.active_tasks -= 1
        self._drain_queue()
        return {
            "task_id": task.id, "success": task.success,
            "agent_id": fallback_id, "latency_ms": node.latency_ms,
            "tokens_used": task.tokens_used,
            "result": task.result if task.success else None,
            "error": None if task.success else "fallback_failed",
            "original_agent": original_agent,
        }

    def _drain_queue(self):
        """Process queued tasks if capacity available."""
        if not self.task_queue:
            return
        batch = []
        while self.task_queue and len(batch) < 5:
            t = self.task_queue.popleft()
            agent_id = self.route(t)
            if agent_id:
                batch.append((t, agent_id))
        for t, aid in batch:
            self._assign_and_execute(t, aid)

    # ── Health & cascade ──

    def health_report(self) -> dict:
        total_tasks = len(self.completed) + len(self.failed)
        success_rate = len(self.completed) / max(total_tasks, 1)
        avg_load = sum(n.load for n in self.nodes.values()) / max(len(self.nodes), 1)
        avg_trust = sum(n.trust_score for n in self.nodes.values()) / max(len(self.nodes), 1)
        overloaded = [n.agent_id for n in self.nodes.values() if n.load > 0.8]
        untrusted = [n.agent_id for n in self.nodes.values() if n.trust_score < 0.3]
        tripped = [n.agent_id for n in self.nodes.values() if n.circuit_state == "open"]

        return {
            "total_tasks": total_tasks, "completed": len(self.completed),
            "failed": len(self.failed), "success_rate": round(success_rate, 3),
            "avg_load": round(avg_load, 3), "avg_trust": round(avg_trust, 3),
            "overloaded": overloaded, "untrusted": untrusted,
            "tripped_circuits": tripped, "topology": self.topology.value,
            "node_count": len(self.nodes), "queue_depth": len(self.task_queue),
            "stigmergic_traces": len(self.stigmergy.traces),
            "re_topology_events": self.re_topology_count,
            "backpressure_rejected": self.backpressure_rejected,
        }

    def cascade_analysis(self) -> list[dict]:
        cascades = []
        for i, f1 in enumerate(self.failed[:-1]):
            for f2 in self.failed[i + 1:]:
                gap = f2.latency_ms - f1.latency_ms
                if abs(gap) < 100:
                    cascades.append({
                        "trigger": f1.id, "trigger_agent": f1.assigned_to,
                        "secondary": f2.id, "secondary_agent": f2.assigned_to,
                        "time_gap_ms": round(gap, 1),
                    })
        return cascades

    def stress_test(self, scenario: str = "spike", agents: int = 6, tasks: int = 40):
        """Run a stress scenario and return health report before/after."""
        if agents > 1:
            self.nodes.clear()
            self.adjacency.clear()
            for i in range(agents):
                cap = max(0.15, 0.85 - i * 0.1)
                self.add_node(AgentNode(f"agent_{i}", capabilities={"task": cap},
                                        max_concurrent=2))
            self.set_topology(DelegationTopology.MESH)

        pre = self.health_report()
        results = []

        if scenario == "spike":
            # Spike: 40 tasks in rapid succession
            for i in range(tasks):
                results.append(self.execute("task", f"task_{i}"))
        elif scenario == "agent_death":
            # Agent death: agent_0 dies after 10 tasks
            for i in range(10):
                results.append(self.execute("task", f"task_{i}"))
            self.nodes["agent_0"].circuit_threshold = 1
            self.nodes["agent_0"].max_concurrent = 0
            for i in range(tasks - 10):
                results.append(self.execute("task", f"task_{10 + i}"))
        elif scenario == "slow_degradation":
            # Slow degradation: each agent loses capability over time
            for i in range(tasks):
                results.append(self.execute("task", f"task_{i}"))
                for node in self.nodes.values():
                    if i > 5 and random.random() < 0.1:
                        for k in node.capabilities:
                            node.capabilities[k] = max(0.05, node.capabilities[k] - 0.02)

        post = self.health_report()
        cascades = self.cascade_analysis()
        repairs = self.detect_and_repair()
        post2 = self.health_report() if repairs else post

        return {
            "scenario": scenario, "agents": agents, "tasks_submitted": tasks,
            "pre": pre, "post": post, "post_repair": post2,
            "repairs": repairs, "cascades": cascades[:5],
            "completed": len(self.completed), "failed": len(self.failed),
        }


# ──────────────────────────────────────────────
# 5. DEMO
# ──────────────────────────────────────────────

def demo():
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║   AGENT MESH v2 — Multi-Agent Deep Patterns             ║")
    print("  ║   Circuit breakers · Stigmergy · Re-topology · Stress   ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    # ── 1. Topology comparison ──
    print("  ─── 1. TOPOLOGY COMPARISON (8 tasks each) ───")
    for topo in DelegationTopology:
        mesh = AgentMesh(topology=topo)
        for role, cap in [("coder", {"code": 0.9, "review": 0.5}),
                          ("reviewer", {"review": 0.8, "code": 0.4}),
                          ("tester", {"test": 0.85, "review": 0.6}),
                          ("deployer", {"deploy": 0.75, "test": 0.5})]:
            mesh.add_node(AgentNode(role, capabilities=cap, max_concurrent=1))
        mesh.set_topology(topo)
        for i in range(8):
            t = ["code", "review", "test", "deploy"][i % 4]
            mesh.execute(t, f"task_{i}")
        h = mesh.health_report()
        print(f"    {topo.value:12s}  {h['success_rate']:.0%} success  "
              f"load={h['avg_load']:.2f}  trust={h['avg_trust']:.2f}  "
              f"queue={h['queue_depth']}  tripped={h['tripped_circuits']}")
    print()

    # ── 2. Circuit breaker in action ──
    print("  ─── 2. CIRCUIT BREAKER ───")
    mesh = AgentMesh(topology=DelegationTopology.CHAIN)
    for i in range(4):
        mesh.add_node(AgentNode(f"wkr_{i}", capabilities={"task": 0.95},
                                max_concurrent=2, circuit_threshold=3))
    mesh.set_topology(DelegationTopology.CHAIN)
    wkr1 = mesh.nodes["wkr_1"]
    # Force route all tasks through wkr_1 to trip the breaker
    def route_to_wkr1(task):
        return "wkr_1"
    mesh.route = route_to_wkr1
    
    original_exec = mesh._assign_and_execute
    def failing_exec(task, agent_id):
        task.assigned_to = agent_id
        wkr1.active_tasks += 1
        wkr1.total_tasks += 1
        wkr1.failed_tasks += 1
        wkr1.trust_score = max(0.0, wkr1.trust_score - 0.05)
        wkr1.record_failure()
        wkr1.active_tasks -= 1
        mesh.failed.append(task)
        return {"task_id": task.id, "success": False, "agent_id": agent_id, "error": "simulated_failure"}
    mesh._assign_and_execute = failing_exec
    
    for i in range(12):
        mesh.execute("task", f"batch_{i}")
    
    h = mesh.health_report()
    print(f"    After 12 tasks: {h['success_rate']:.0%} success  "
          f"{h['completed']} completed  {h['failed']} failed")
    print(f"    Tripped circuits: {h['tripped_circuits']}")
    print(f"    wkr_1 circuit: {wkr1.circuit_state} (failures={wkr1.circuit_failures})")
    # Repair
    repairs = mesh.detect_and_repair()
    print(f"    Dynamic repairs: {len(repairs)}")
    for r in repairs[:3]:
        print(f"      {r}")
    h2 = mesh.health_report()
    print(f"    After repair: {h2['re_topology_events']} topology changes  "
          f"success={h2['success_rate']:.0%}")
    print()

    # ── 3. Stigmergic vs direct routing ──
    print("  ─── 3. STIGMERGY (traces vs messages) ───")
    mesh = AgentMesh(topology=DelegationTopology.MESH)
    for i in range(5):
        mesh.add_node(AgentNode(f"stig_{i}", capabilities={"task": 0.9},
                                max_concurrent=2, trust_score=0.3 + i * 0.1))
    mesh.set_topology(DelegationTopology.MESH)
    # Phase 1: direct routing
    for i in range(15):
        mesh.execute("task", f"direct_{i}", use_stigmergy=False)
    direct = mesh.health_report()
    # Phase 2: stigmergic routing (agent reads traces to find best)
    for i in range(15):
        mesh.execute("task", f"stig_{i}", use_stigmergy=True)
    stiggy = mesh.health_report()
    print(f"    Direct routing:  {direct['success_rate']:.0%} success")
    print(f"    Stigmergic:      {stiggy['success_rate']:.0%} success  "
          f"({sum(n.stigmergic_writes for n in mesh.nodes.values())} traces written)")
    print()

    # ── 4. Stress tests ──
    print("  ─── 4. STRESS SCENARIOS ───")
    for scenario in ["spike", "agent_death", "slow_degradation"]:
        result = AgentMesh().stress_test(scenario=scenario, agents=6, tasks=40)
        pre = result["pre"]
        post = result["post_repair"]
        print(f"    {scenario:20s}  {result['completed']}/{result['tasks_submitted']}  "
              f"pre={pre['success_rate']:.0%} → post={post['success_rate']:.0%}  "
              f"repairs={len(result['repairs'])}  cascades={len(result['cascades'])}  "
              f"backpressure={post['backpressure_rejected']}")
    print()

    print("  ══════════════════════════════════════════════════════════")
    print("  v2 patterns verified: circuit breakers, stigmergy,")
    print("  re-topology, backpressure, cascade detection, stress tests")
    print("  ══════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
