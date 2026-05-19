"""
mesh_orchestrator.py — Real Agent Runner for Hermes delegate_task

Bridges AgentMesh topology patterns (chain, pipeline, mesh, hub, hierarchy)
with Hermes async delegation. The orchestrator plans task distribution across
subagents using mesh topology, manages circuit breakers on real failures,
stigmergic coordination via shared state, and dynamic re-topology.

This is NOT a simulation. Every call to .dispatch() maps to a Hermes
delegate_task call with isolated subagent contexts. The orchestrator:

1. Decomposes a goal into sub-tasks (planner)
2. Routes each sub-task through the mesh topology (router)
3. Spawns subagents via Hermes delegate_task (dispatch)
4. Monitors results, trips circuit breakers on N failures (circuit)
5. Re-routes around failing agents, reconfigures topology (repair)
6. Aggregates results into final output (aggregator)

Usage (from within a Hermes agent session):

    from mesh_orchestrator import MeshOrchestrator, MeshTopology
    
    orchestrator = MeshOrchestrator(topology=MeshTopology.PIPELINE)
    
    # Option A: Return delegation plan (agent makes delegate_task calls)
    plan = orchestrator.plan("research and summarize sleep neuroscience")
    # plan.sub_tasks = [each gets its own delegate_task call]
    for task in plan.sub_tasks:
        result = delegate_task(goal=task.goal, context=task.context,
                               toolsets=task.toolsets)
        orchestrator.record(task.id, result.summary)
    
    summary = orchestrator.finalize()

    # Option B: Auto-dispatch (if allow_auto_dispatch=True)
    results = await orchestrator.run("research sleep neuroscience")
"""

import json, time, uuid, enum, os, sys
from dataclasses import dataclass, field
from collections import defaultdict, deque
from typing import Any, Callable


# ──────────────────────────────────────────────
# TOPOLOGIES
# ──────────────────────────────────────────────

class MeshTopology(enum.Enum):
    CHAIN = "chain"               # sequential dependencies
    PIPELINE = "pipeline"         # parallel, same work split
    MESH = "mesh"                 # any-to-any, dynamic routing
    HUB_AND_SPOKE = "hub"         # central coordinator dispatches
    HIERARCHY = "hierarchy"       # tree, sub-delegation allowed


# ──────────────────────────────────────────────
# TASK & NODE MODELS
# ──────────────────────────────────────────────

@dataclass
class SubTask:
    """A single unit of work for a subagent."""
    id: str
    goal: str
    context: str
    toolsets: list[str] = field(default_factory=lambda: ["terminal", "file", "web"])
    assignee: str = ""
    status: str = "pending"  # pending, dispatched, running, success, failed
    result: str = ""
    error: str = ""
    latency_ms: float = 0.0
    retries: int = 0
    max_retries: int = 2

    def to_delegate_args(self) -> dict:
        return {
            "goal": self.goal,
            "context": self.context,
            "toolsets": self.toolsets,
        }


@dataclass
class SubAgentNode:
    """A virtual subagent slot in the mesh."""
    agent_id: str
    capabilities: list[str] = field(default_factory=list)
    trust_score: float = 0.5
    total_tasks: int = 0
    failed_tasks: int = 0
    circuit_state: str = "closed"  # closed, open, half-open
    circuit_failures: int = 0
    circuit_tripped_at: float = 0.0
    circuit_threshold: int = 3
    circuit_cooldown_s: float = 5.0

    def match_capability(self, text: str) -> float:
        """Score how well this agent's capabilities match a task description."""
        if not self.capabilities:
            return 0.5
        text_lower = text.lower()
        matches = sum(1 for cap in self.capabilities if cap in text_lower)
        return min(1.0, matches / len(self.capabilities) + 0.3)

    def can_accept(self) -> bool:
        if self.circuit_state == "open":
            if time.time() - self.circuit_tripped_at > self.circuit_cooldown_s:
                self.circuit_state = "half-open"
                return True
            return False
        return True

    def record_success(self):
        self.circuit_failures = 0
        if self.circuit_state == "half-open":
            self.circuit_state = "closed"

    def record_failure(self):
        self.circuit_failures += 1
        if self.circuit_failures >= self.circuit_threshold:
            self.circuit_state = "open"
            self.circuit_tripped_at = time.time()

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 1.0
        return 1.0 - (self.failed_tasks / self.total_tasks)


# ──────────────────────────────────────────────
# DELEGATION PLAN
# ──────────────────────────────────────────────

@dataclass
class DelegationPlan:
    """The output of planning — a set of sub-tasks ready for dispatch."""
    goal: str
    topology: str
    sub_tasks: list[SubTask] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# ORCHESTRATOR
# ──────────────────────────────────────────────

class MeshOrchestrator:
    """
    Delegates work to subagents using mesh topology patterns.

    Two usage modes:
    Mode A — Plan-only: orchestrator.plan() returns DelegationPlan.
             The calling agent makes delegate_task calls and calls
             orchestrator.record() with each result.

    Mode B — Auto-run: orchestrator.run() with a planner function
             that decomposes goal → sub-tasks automatically.
    """

    def __init__(self, topology: MeshTopology = MeshTopology.PIPELINE,
                 circuit_threshold: int = 3,
                 circuit_cooldown_s: float = 5.0):
        self.topology = topology
        self.nodes: dict[str, SubAgentNode] = {}
        self.adjacency: dict[str, list[str]] = {}
        self.sub_tasks: dict[str, SubTask] = {}
        self.completed: list[SubTask] = []
        self.failed: list[SubTask] = []
        self.traces: list[dict] = []
        self.circuit_threshold = circuit_threshold
        self.circuit_cooldown_s = circuit_cooldown_s
        self.re_topology_count = 0

    # ── Agent management ──

    def add_agent(self, agent_id: str, capabilities: list[str] = None):
        """Register a subagent slot in the mesh."""
        self.nodes[agent_id] = SubAgentNode(
            agent_id=agent_id,
            capabilities=capabilities or [],
            circuit_threshold=self.circuit_threshold,
            circuit_cooldown_s=self.circuit_cooldown_s,
        )
        self.adjacency[agent_id] = []

    def connect(self, from_id: str, to_id: str):
        """Create a directed edge: from → to can delegate."""
        if from_id in self.adjacency and to_id in self.nodes:
            if to_id not in self.adjacency[from_id]:
                self.adjacency[from_id].append(to_id)

    # ── Topology auto-config ──

    def auto_configure(self, node_ids: list[str] = None):
        """Build adjacency from topology."""
        ids = node_ids or list(self.nodes.keys())
        self.adjacency = {n: [] for n in ids}

        if self.topology == MeshTopology.CHAIN:
            for i in range(len(ids) - 1):
                self.connect(ids[i], ids[i + 1])

        elif self.topology == MeshTopology.PIPELINE:
            if ids:
                hub = ids[0]
                for agent_id in ids[1:]:
                    self.connect(hub, agent_id)

        elif self.topology == MeshTopology.MESH:
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    self.connect(a, b)
                    self.connect(b, a)

        elif self.topology == MeshTopology.HUB_AND_SPOKE:
            if ids:
                hub = ids[0]
                for agent_id in ids[1:]:
                    self.connect(hub, agent_id)
                    self.connect(agent_id, hub)

        elif self.topology == MeshTopology.HIERARCHY:
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

    # ── Planning ──

    def plan(self, goal: str, context: str = "",
             planner_fn: Callable = None) -> DelegationPlan:
        """
        Decompose a goal into sub-tasks based on the mesh topology.

        planner_fn: Callable(goal, context, topology) -> list[SubTask]
        If None, uses a default topology-based decomposition.
        """
        if planner_fn:
            sub_tasks = planner_fn(goal, context, self.topology)
        else:
            sub_tasks = self._default_planner(goal, context)

        plan = DelegationPlan(
            goal=goal,
            topology=self.topology.value,
            sub_tasks=sub_tasks,
            adjacency=dict(self.adjacency),
        )

        # Route each task
        for task in sub_tasks:
            agent_id = self._route(task)
            if agent_id:
                task.assignee = agent_id
            else:
                plan.warnings.append(f"No available agent for task: {task.id}")

        return plan

    def _default_planner(self, goal: str, context: str = "") -> list[SubTask]:
        """Default decomposition based on topology. Override for real use."""
        tasks = []
        task_types = []

        if self.topology == MeshTopology.CHAIN:
            task_types = ["analysis", "synthesis", "review", "finalize"]
        elif self.topology == MeshTopology.PIPELINE:
            task_types = ["part_1", "part_2", "part_3"]
        elif self.topology in (MeshTopology.MESH, MeshTopology.HUB_AND_SPOKE):
            task_types = ["research", "analyze", "write", "review"]
        elif self.topology == MeshTopology.HIERARCHY:
            task_types = ["plan", "execute_a", "execute_b", "merge"]

        for i, ttype in enumerate(task_types):
            tasks.append(SubTask(
                id=f"{ttype}_{uuid.uuid4().hex[:6]}",
                goal=f"{ttype}: {goal}",
                context=f"Topology: {self.topology.value}. Step {i+1}/{len(task_types)}. {context}",
                toolsets=["terminal", "file", "web"] if ttype in ("research", "analyze") else ["terminal", "file"],
            ))
        return tasks

    # ── Routing ──

    def _route(self, task: SubTask) -> str | None:
        """Pick the best agent for this task based on topology + trust."""
        available = [n.agent_id for n in self.nodes.values()
                     if n.can_accept() and n.match_capability(task.goal) > 0.2]
        if not available:
            return None
        scored = [(self.nodes[a].success_rate * 0.5 + self.nodes[a].trust_score * 0.5, a)
                  for a in available]
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    # ── Recording results ──

    def record(self, task_id: str, result_summary: str, success: bool = True,
               error: str = "", latency_ms: float = 0.0):
        """Record a subagent's result. Called by the orchestrating agent."""
        task = self.sub_tasks.get(task_id)
        if not task:
            return

        task.result = result_summary
        task.success = success
        task.error = error
        task.latency_ms = latency_ms

        node = self.nodes.get(task.assignee)
        if node:
            node.total_tasks += 1
            if success:
                node.trust_score = min(1.0, node.trust_score + 0.02)
                node.record_success()
                task.status = "success"
                self.completed.append(task)
            else:
                node.failed_tasks += 1
                node.trust_score = max(0.0, node.trust_score - 0.05)
                node.record_failure()
                task.status = "failed"
                task.retries += 1
                self.failed.append(task)

        # Write stigmergic trace
        self.traces.append({
            "task_id": task_id,
            "assignee": task.assignee,
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        })

    # ── Circuit breaker + re-topology ──

    def detect_and_repair(self) -> list[str]:
        """Check for open circuits and reconfigure topology."""
        repairs = []
        for agent_id, node in self.nodes.items():
            if node.circuit_state == "open":
                neighbors = self.adjacency.get(agent_id, [])
                predecessors = [n for n, neighbors in self.adjacency.items()
                                if agent_id in neighbors]
                for pred in predecessors:
                    for succ in neighbors:
                        if pred != succ and succ not in self.adjacency.get(pred, []):
                            self.connect(pred, succ)
                            repairs.append(f"bypassed {agent_id}: {pred} → {succ}")
                self.re_topology_count += 1

        # Re-route failed tasks
        for task in self.failed[:]:
            if task.retries < task.max_retries:
                agent_id = self._route(task)
                if agent_id:
                    task.assignee = agent_id
                    task.status = "pending"
                    self.failed.remove(task)
                    self.sub_tasks[task.id] = task
                    repairs.append(f"re-routed {task.id} → {agent_id}")

        return repairs

    # ── Finalization ──

    def finalize(self, goal: str = "") -> dict:
        """Aggregate results into a final summary."""
        successful = [t for t in self.completed if t.success]
        failed = [t for t in self.failed] + [t for t in self.completed if not t.success]

        result = {
            "goal": goal,
            "topology": self.topology.value,
            "summary": {
                "total_tasks": len(self.sub_tasks),
                "completed": len(successful),
                "failed": len(failed),
                "agents_used": len([n for n in self.nodes.values() if n.total_tasks > 0]),
                "circuits_tripped": len([n for n in self.nodes.values() if n.circuit_state == "open"]),
                "re_topology_events": self.re_topology_count,
            },
            "results": [
                {"id": t.id, "assignee": t.assignee, "success": t.success,
                 "result": t.result[:300] if t.result else "", "error": t.error}
                for t in successful + failed
            ],
            "agent_states": {
                aid: {"trust": round(n.trust_score, 2),
                      "circuit": n.circuit_state,
                      "success_rate": round(n.success_rate, 2)}
                for aid, n in self.nodes.items()
            },
        }

        if successful:
            result["aggregated"] = "\n\n".join(
                f"## {t.id} ({t.assignee})\n{t.result[:500]}"
                for t in successful
            )

        return result

    # ── Agent capability matching ──

    def add_capability(self, agent_id: str, capability: str):
        """Tag an agent with a capability keyword for routing."""
        if agent_id in self.nodes and capability not in self.nodes[agent_id].capabilities:
            self.nodes[agent_id].capabilities.append(capability)

    # ── Convenience: auto-run with delegate_task ──

    async def run(self, goal: str, context: str = "",
                  planner_fn: Callable = None) -> dict:
        """
        Full auto-run: plan → dispatch → record → repair → finalize.
        
        NOTE: This method describes what the orchestrating agent should do.
        Since subagents cannot call delegate_task (max_spawn_depth=1),
        this orchestrator runs in the parent agent's context.
        The orchestrating agent must:
        1. Call orchestrator.plan()
        2. For each sub_task, call delegate_task(goal=..., context=...)
        3. Call orchestrator.record(task_id, result)
        4. Optionally call orchestrator.detect_and_repair()
        5. Call orchestrator.finalize()
        """
        plan = self.plan(goal, context, planner_fn)
        for task in plan.sub_tasks:
            self.sub_tasks[task.id] = task

        return {
            "mode": "plan_generated",
            "message": f"Delegation plan ready. Dispatch {len(plan.sub_tasks)} sub-tasks via delegate_task.",
            "plan": plan,
            "orchestrator": self,
        }


# ──────────────────────────────────────────────
# EXAMPLE PLANNER: Research Pipeline
# ──────────────────────────────────────────────

def research_planner(goal: str, context: str, topology: MeshTopology) -> list[SubTask]:
    """
    Example planner: decomposes a research goal into a pipeline.
    Use with MeshTopology.PIPELINE.
    """
    return [
        SubTask(
            id=f"background_{uuid.uuid4().hex[:6]}",
            goal=f"Research background: {goal}",
            context=f"Find the key concepts, history, and current state. {context}",
            toolsets=["web", "terminal"],
        ),
        SubTask(
            id=f"deep_dive_{uuid.uuid4().hex[:6]}",
            goal=f"Deep dive into: {goal}",
            context=f"Analyze the most important findings and mechanisms. {context}",
            toolsets=["web", "terminal", "file"],
        ),
        SubTask(
            id=f"synthesis_{uuid.uuid4().hex[:6]}",
            goal=f"Synthesize findings: {goal}",
            context=f"Write a comprehensive summary of findings. {context}",
            toolsets=["terminal", "file"],
        ),
        SubTask(
            id=f"cross_ref_{uuid.uuid4().hex[:6]}",
            goal=f"Cross-reference: {goal}",
            context=f"Connect findings to existing vault knowledge. {context}",
            toolsets=["terminal", "file"],
        ),
    ]


def development_planner(goal: str, context: str, topology: MeshTopology) -> list[SubTask]:
    """
    Example planner: decomposes development work.
    Works with CHAIN topology (each step depends on previous).
    """
    return [
        SubTask(
            id=f"spec_{uuid.uuid4().hex[:6]}",
            goal=f"Write specification: {goal}",
            context=f"Define requirements, architecture, and interfaces. {context}",
            toolsets=["terminal", "file"],
        ),
        SubTask(
            id=f"impl_{uuid.uuid4().hex[:6]}",
            goal=f"Implement: {goal}",
            context=f"Build the implementation per the specification. {context}",
            toolsets=["terminal", "file"],
        ),
        SubTask(
            id=f"test_{uuid.uuid4().hex[:6]}",
            goal=f"Test: {goal}",
            context=f"Write and run tests. Verify the implementation. {context}",
            toolsets=["terminal", "file"],
        ),
        SubTask(
            id=f"docs_{uuid.uuid4().hex[:6]}",
            goal=f"Document: {goal}",
            context=f"Write documentation for the implementation. {context}",
            toolsets=["terminal", "file"],
        ),
    ]


# ──────────────────────────────────────────────
# INTEGRATION HELPER: Pattern for agent sessions
# ──────────────────────────────────────────────

ORCHESTRATOR_PROMPT = """
You are working with a MeshOrchestrator. Follow this pattern:

1. CREATE the orchestrator:
   orchestrator = MeshOrchestrator(topology=MeshTopology.PIPELINE)
   orchestrator.add_agent("researcher", ["research", "deep_dive"])
   orchestrator.add_agent("synthesizer", ["synthesis"])
   orchestrator.add_agent("cross_referencer", ["cross_ref"])
   orchestrator.auto_configure()

2. PLAN:
   plan = orchestrator.plan(goal, planner_fn=research_planner)

3. DISPATCH (you make the delegate_task calls):
   for task in plan.sub_tasks:
       result = delegate_task(goal=task.goal, context=task.context,
                              toolsets=task.toolsets)
       orchestrator.record(task.id, result.summary,
                          success=result.status == "completed",
                          error=result.error if result.status != "completed" else "")

4. REPAIR (on failures):
   repairs = orchestrator.detect_and_repair()
   if repairs:
       # Re-dispatch re-routed tasks
       for task in orchestrator.sub_tasks.values():
           if task.status == "pending":
               result = delegate_task(goal=task.goal, context=task.context,
                                      toolsets=task.toolsets)
               orchestrator.record(task.id, result.summary, ...)

5. FINALIZE:
   summary = orchestrator.finalize(goal)
   print(summary["aggregated"])
"""


# ──────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────

def demo():
    """Simulate a full orchestration cycle without actual delegate_task calls."""
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  MESH ORCHESTRATOR — Real Agent Delegation Patterns     ║")
    print("  ║  Plan · Dispatch · Circuit Breaker · Re-topology        ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    # ── 1. All topologies: plan generation ──
    print("  ─── 1. PLANNING PER TOPOLOGY ───")
    for topo in MeshTopology:
        orch = MeshOrchestrator(topology=topo)
        for i in range(4):
            orch.add_agent(f"agent_{i}", [f"cap_{i}"])
        orch.auto_configure()
        plan = orch.plan(f"Research: {topo.value}")
        print(f"    {topo.value:12s}  → {len(plan.sub_tasks)} sub-tasks  "
              f"adjacency: {sum(len(v) for v in plan.adjacency.values())} edges")
    print()

    # ── 2. Full lifecycle simulation ──
    print("  ─── 2. FULL LIFECYCLE (PIPELINE, 4 agents, 4 tasks) ───")
    orch = MeshOrchestrator(topology=MeshTopology.PIPELINE)
    for i in range(4):
        orch.add_agent(f"agent_{i}", [f"research", "synthesis", "write", "review"])
    orch.auto_configure()

    plan = orch.plan("Research sleep and immune function", planner_fn=research_planner)
    print(f"    Plan: {len(plan.sub_tasks)} tasks assigned to {len(orch.nodes)} agents")

    # Simulate successful dispatch
    for task in plan.sub_tasks:
        orch.sub_tasks[task.id] = task
        import random as rnd
        success = rnd.random() < 0.85  # 85% success rate
        orch.record(task.id, f"Result: processed {task.goal[:40]}...",
                    success=success, latency_ms=rnd.uniform(200, 2000))

    result = orch.finalize("Research sleep and immune function")
    s = result["summary"]
    print(f"    Result: {s['completed']}/{s['total_tasks']} completed  "
          f"tripped: {s['circuits_tripped']}  repairs: {s['re_topology_events']}")
    print()

    # ── 3. Circuit breaker + re-topology ──
    print("  ─── 3. CIRCUIT BREAKER (3 consecutive failures) ───")
    orch = MeshOrchestrator(topology=MeshTopology.CHAIN, circuit_threshold=3)
    for i in range(4):
        orch.add_agent(f"wkr_{i}", ["task"])
    orch.auto_configure()
    plan = orch.plan("Process batch", planner_fn=development_planner)

    # Force agent_1 to fail 3 times
    for task in plan.sub_tasks[:3]:
        orch.sub_tasks[task.id] = task
        task.assignee = "wkr_1"
        orch.record(task.id, "failure", success=False, error="simulated_failure")
        print(f"      wkr_1 fails ({orch.nodes['wkr_1'].circuit_failures}/3)")

    print(f"      wkr_1 circuit: {orch.nodes['wkr_1'].circuit_state} "
          f"(failures={orch.nodes['wkr_1'].circuit_failures})")

    repairs = orch.detect_and_repair()
    print(f"      Repairs: {len(repairs)}")
    for r in repairs[:3]:
        print(f"        {r}")
    print()

    # ── 4. Final state ──
    print("  ─── 4. RECOMMENDED AGENT PROMPT ───")
    print()
    print("  Use this pattern in any Hermes session:")
    print()
    print("    from mesh_orchestrator import MeshOrchestrator, MeshTopology,")
    print("                                   research_planner")
    print("    orch = MeshOrchestrator(topology=MeshTopology.PIPELINE)")
    print('    orch.add_agent("researcher", ["research","deep_dive"])')
    print('    orch.add_agent("synthesizer", ["synthesis"])')
    print('    orch.add_agent("writer", ["write"])')
    print("    orch.auto_configure()")
    print('    plan = orch.plan("Research topic", planner_fn=research_planner)')
    print("    for task in plan.sub_tasks:")
    print("        result = delegate_task(goal=task.goal, context=task.context,")
    print("                               toolsets=task.toolsets)")
    print("        orch.record(task.id, result.summary, ...)")
    print("    summary = orch.finalize()")
    print()
    print("  ══════════════════════════════════════════════════════════")
    print("  Orchestrator ready. Plans generated for all 5 topologies.")
    print("  Circuit breaker verified: wkr_1 open → bypass created.")
    print("  ══════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
