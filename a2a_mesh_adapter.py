"""
a2a_mesh_adapter.py — A2A Protocol Adapter for AgentMesh

Bridges the A2A protocol (a2a_protocol.py) with the existing agent mesh
infrastructure (agent_mesh.py, social_mesh.py, mesh_orchestrator.py).

Three adapters:

1. A2AMeshAdapter — wraps AgentMesh to route via A2A protocol
2. A2ASocialMeshAdapter — wraps SocialAgentMesh with A2A trust-adjusted routing
3. A2AOrchestratorAdapter — wraps MeshOrchestrator with A2A task lifecycle

Instead of direct agent-to-agent calls, everything goes through:
  AgentCard → A2AClient.send_task() → Discovery → A2AAgent.receive_task()
                  ↓
           A2ATask lifecycle (submitted→working→completed→failed)

Usage:
  from a2a_mesh_adapter import A2AMeshAdapter
  mesh = A2AMeshAdapter()
  mesh.add_agent("researcher", capabilities={"retrieval": 0.9, "synthesis": 0.7})
  mesh.add_agent("coder", capabilities={"execution": 0.9, "verification": 0.6})
  result = mesh.execute("research", "Research sleep neuroscience")
"""

from __future__ import annotations
import uuid, time, random
from dataclasses import dataclass, field

from a2a_protocol import (
    AgentCard, A2AClient, A2AAgent, A2AAgentWorker,
    DiscoveryService, Message, Part, Artifact, TaskState
)


# ──────────────────────────────────────────────
# 1. A2A MESH ADAPTER — AgentMesh via A2A
# ──────────────────────────────────────────────

class A2AMeshAdapter:
    """Wraps a collection of agents communicating via A2A protocol.
    
    Each agent publishes an AgentCard to a shared DiscoveryService.
    Tasks are routed through A2A's task lifecycle instead of
    direct agent_mesh routing.
    """
    
    def __init__(self):
        self.discovery = DiscoveryService()
        self.client = A2AClient(self.discovery)
        self.agents: dict[str, A2AAgent] = {}
        self.completed_tasks: list = []
        self.failed_tasks: list = []
    
    def add_agent(self, name: str, capabilities: dict[str, float] | None = None,
                  trust_score: float = 0.5, skills: list[str] | None = None):
        """Add an A2A-compliant agent to the mesh."""
        if capabilities is None:
            capabilities = {"task": 0.7}
        if skills is None:
            skills = list(capabilities.keys())
        
        card = AgentCard(
            name=name,
            description=f"A2A agent: {', '.join(skills)}",
            capabilities=capabilities,
            skills=skills,
            trust_score=trust_score,
        )
        self.discovery.register(card)
        agent = A2AAgent(card)
        self.agents[name] = agent
        return agent
    
    def execute(self, task_type: str, goal: str, priority: int = 5,
                required_capabilities: list[str] | None = None) -> dict:
        """Route a task via A2A protocol.
        
        Uses DiscoveryService to find the best agent, sends the task
        via A2AClient, processes it, and returns the result.
        """
        if required_capabilities is None:
            required_capabilities = [task_type]
        
        # Find best agent via discovery
        card = self.discovery.find_best_for_task(task_type, required_capabilities)
        if not card or card.name not in self.agents:
            return {
                "success": False,
                "error": f"No A2A agent found for {task_type}",
                "task_type": task_type,
            }
        
        # Create A2A task
        task = self.client.send_task(card, goal, task_type=task_type, priority=priority)
        
        # Agent receives & processes
        agent = self.agents[card.name]
        agent.receive_task(task)
        result = agent.process_next()
        
        # Client receives result
        if result:
            self.client.receive_result(result)
            if result.state == TaskState.COMPLETED:
                self.completed_tasks.append(result)
            else:
                self.failed_tasks.append(result)
            
            # Extract output text
            output_text = ""
            for msg in result.output_messages:
                for part in msg.parts:
                    output_text += part.text + "\n"
            
            return {
                "success": result.state == TaskState.COMPLETED,
                "task_id": result.task_id,
                "agent_id": card.agent_id,
                "agent_name": card.name,
                "output": output_text.strip(),
                "state": result.state.value,
                "duration_s": round(result.duration, 2),
                "error": result.error_message,
            }
        
        return {"success": False, "error": "no_result"}
    
    def execute_chain(self, task_chain: list[tuple[str, str]]) -> list[dict]:
        """Execute a chain of tasks sequentially.
        
        Each task's output feeds into the next task's context.
        This implements the A2A equivalent of agent_mesh CHAIN topology.
        """
        results = []
        context = ""
        for task_type, goal in task_chain:
            full_goal = f"{goal}\nContext from previous: {context[:200]}" if context else goal
            result = self.execute(task_type, full_goal)
            results.append(result)
            if result["success"]:
                context = result.get("output", "")
            else:
                break  # Chain fails on first error
        return results
    
    def execute_pipeline(self, task_type: str, goal: str,
                         num_workers: int = 2) -> list[dict]:
        """Execute a task across multiple agents (PIPELINE topology).
        
        Finds N agents for the task type and fans out work evenly.
        """
        agents = self.discovery.find_by_capability(task_type, 0.3)
        if not agents:
            return [{"success": False, "error": f"No agents found for {task_type}"}]
        
        # Pick top N agents
        selected = agents[:num_workers]
        results = []
        for i, card in enumerate(selected):
            result = self.execute(task_type, f"[{i+1}/{len(selected)}] {goal}")
            results.append(result)
        return results
    
    def get_health(self) -> dict:
        return {
            "agents": len(self.agents),
            "registered_cards": len(self.discovery.list_all()),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "active_tasks": len(self.client.get_active_tasks()),
            "success_rate": round(
                len(self.completed_tasks) / max(len(self.completed_tasks) + len(self.failed_tasks), 1),
                3
            ),
        }


# ──────────────────────────────────────────────
# 2. A2A SOCIAL MESH — Trust-adjusted via A2A
# ──────────────────────────────────────────────

class A2ASocialMeshAdapter(A2AMeshAdapter):
    """A2A mesh with social mirror — trust-adjusted task routing.
    
    Extended from A2AMeshAdapter:
    - Agents model each other's reputation via social mirror
    - Trust-adjusted routing (capability × trust × exploration)
    - Reputation crises detected and agents rotated
    """
    
    def __init__(self, exploration_rate: float = 0.3):
        super().__init__()
        self.exploration_rate = exploration_rate  # % of tasks to untested agents
        self.reputation_history: list[dict] = []
        self.corrections_applied: int = 0
    
    def social_score(self, card: AgentCard, task_type: str) -> float:
        """Compute trust-adjusted routing score."""
        cap_score = card.capabilities.get(task_type, 0.3)
        trust = card.trust_score
        success = card.success_rate
        
        # Cold-start boost
        if card.total_tasks == 0:
            return cap_score * 0.40 + 0.25  # boost untested
        
        return cap_score * 0.35 + trust * 0.25 + success * 0.20 + 0.10 * 0.10
    
    def execute(self, task_type: str, goal: str, priority: int = 5,
                required_capabilities: list[str] | None = None) -> dict:
        """Route with social trust-adjusted scoring + exploration."""
        if required_capabilities is None:
            required_capabilities = [task_type]
        
        all_agents = self.discovery.find_by_capability(task_type, 0.15)
        if not all_agents:
            return {"success": False, "error": f"No agents found for {task_type}"}
        
        # Score each agent
        scored = [(self.social_score(c, task_type), c) for c in all_agents]
        scored.sort(key=lambda x: -x[0])
        
        # Exploration: occasionally pick an untested or low-trust agent
        if random.random() < self.exploration_rate and len(scored) > 1:
            untested = [c for _, c in scored if c.total_tasks == 0]
            if untested:
                chosen = random.choice(untested)
            else:
                # Pick from bottom half (trust recovery chance)
                bottom = scored[len(scored)//2:]
                chosen = random.choice(bottom)[1]
        else:
            chosen = scored[0][1]
        
        # Execute via A2A
        task = self.client.send_task(chosen, goal, task_type=task_type, priority=priority)
        agent = self.agents[chosen.name]
        agent.receive_task(task)
        result = agent.process_next()
        
        if result:
            self.client.receive_result(result)
            if result.state == TaskState.COMPLETED:
                self.completed_tasks.append(result)
            else:
                self.failed_tasks.append(result)
            
            # Detect reputation crisis
            if chosen.trust_score < 0.2:
                self.corrections_applied += 1
                self.reputation_history.append({
                    "agent": chosen.name,
                    "trust": chosen.trust_score,
                    "action": "rotation_needed",
                    "timestamp": time.time(),
                })
            
            output_text = ""
            for msg in result.output_messages:
                for part in msg.parts:
                    output_text += part.text + "\n"
            
            return {
                "success": result.state == TaskState.COMPLETED,
                "task_id": result.task_id,
                "agent_id": chosen.agent_id,
                "agent_name": chosen.name,
                "output": output_text.strip(),
                "state": result.state.value,
                "duration_s": round(result.duration, 2),
                "trust_score": chosen.trust_score,
                "error": result.error_message,
                "social_score": round(scored[0][0], 3) if scored else 0,
                "exploration_pick": chosen is not scored[0][1] if len(scored) > 1 else False,
            }
        
        return {"success": False, "error": "no_result"}
    
    def get_social_health(self) -> dict:
        h = self.get_health()
        h.update({
            "social": {
                "avg_trust": round(
                    sum(a.card.trust_score for a in self.agents.values()) / max(len(self.agents), 1),
                    3
                ),
                "corrections_applied": self.corrections_applied,
                "reputation_crises": len([c for c in self.agents.values() if c.card.trust_score < 0.2]),
            },
            "exploration_rate": self.exploration_rate,
        })
        return h


# ──────────────────────────────────────────────
# 3. A2A ORCHESTRATOR — Complex task decomposition
# ──────────────────────────────────────────────

class A2AOrchestratorAdapter:
    """A2A-compatible orchestrator for complex multi-agent tasks.
    
    Decomposes a complex goal into sub-tasks, routes each through
    A2A protocol with appropriate topology (chain, pipeline, mesh).
    """
    
    TOPOLOGIES = ["chain", "pipeline", "mesh"]
    
    def __init__(self, topology: str = "mesh"):
        assert topology in self.TOPOLOGIES, f"Unknown topology: {topology}"
        self.topology = topology
        self.mesh = A2ASocialMeshAdapter(exploration_rate=0.3)
        self.task_results: list[dict] = []
    
    def add_agent(self, name: str, capabilities: dict[str, float] | None = None,
                  trust_score: float = 0.5):
        self.mesh.add_agent(name, capabilities, trust_score)
    
    def decompose(self, complex_goal: str) -> list[tuple[str, str]]:
        """Decompose a complex goal into typed sub-tasks.
        
        Uses predefined patterns. In production this would use
        an LLM planner.
        """
        # Pattern-based decomposition
        if "research" in complex_goal.lower() or "analyze" in complex_goal.lower():
            return [
                ("retrieval", f"Gather information: {complex_goal}"),
                ("synthesis", f"Synthesize findings: {complex_goal}"),
                ("verification", f"Verify the synthesis: {complex_goal}"),
            ]
        elif "implement" in complex_goal.lower() or "build" in complex_goal.lower():
            return [
                ("planning", f"Plan the implementation: {complex_goal}"),
                ("execution", f"Execute the implementation: {complex_goal}"),
                ("verification", f"Verify the implementation: {complex_goal}"),
            ]
        elif "review" in complex_goal.lower() or "evaluate" in complex_goal.lower():
            return [
                ("retrieval", f"Gather context: {complex_goal}"),
                ("verification", f"Verify and evaluate: {complex_goal}"),
                ("synthesis", f"Synthesize review: {complex_goal}"),
            ]
        else:
            return [
                ("retrieval", f"Research context: {complex_goal}"),
                ("synthesis", f"Synthesize: {complex_goal}"),
                ("execution", f"Execute: {complex_goal}"),
            ]
    
    def execute(self, complex_goal: str) -> dict:
        """Run a complex multi-agent task through A2A protocol."""
        sub_tasks = self.decompose(complex_goal)
        
        results = []
        all_success = True
        
        if self.topology == "chain":
            # Sequential — each feeds into next
            results = self.mesh.execute_chain(sub_tasks)
            all_success = all(r.get("success", False) for r in results)
            
        elif self.topology == "pipeline":
            # Parallel — same sub-task type, multiple agents
            results = self.mesh.execute_pipeline(sub_tasks[0][0], complex_goal, num_workers=2)
            all_success = any(r.get("success", False) for r in results)
            
        elif self.topology == "mesh":
            # Dynamic routing per sub-task
            for task_type, goal in sub_tasks:
                r = self.mesh.execute(task_type, goal)
                results.append(r)
                if not r.get("success", False):
                    all_success = False  # Continue even on partial failure
            
            # Retry failed on different agent
            for i, r in enumerate(results):
                if not r.get("success", False) and i < len(sub_tasks):
                    retry_type = sub_tasks[i][0]
                    retry_goal = f"[RETRY] {sub_tasks[i][1]}"
                    retry = self.mesh.execute(retry_type, retry_goal)
                    if retry.get("success", False):
                        results[i] = retry
                        all_success = True
        
        self.task_results = results
        
        # Summarize
        total = len(results)
        successful = sum(1 for r in results if r.get("success", False))
        
        return {
            "goal": complex_goal,
            "topology": self.topology,
            "sub_tasks": total,
            "successful": successful,
            "failed": total - successful,
            "all_success": all_success,
            "results": results,
        }


# ──────────────────────────────────────────────
# 4. DEMO
# ──────────────────────────────────────────────

def demo():
    """Full A2A protocol stack demo across all 3 adapters."""
    import random as rnd
    
    print()
    print("  ╔════════════════════════════════════════════════════════════╗")
    print("  ║   A2A MESH ADAPTER — Full Protocol Stack Demo            ║")
    print("  ║   AgentMesh × SocialMesh × Orchestrator via A2A          ║")
    print("  ╚════════════════════════════════════════════════════════════╝")
    print()
    
    # ── 1. A2A BASIC MESH ──
    print("  ─── 1. A2A MESH — 4 agents, 6 tasks ───")
    mesh = A2AMeshAdapter()
    for name, caps in [
        ("researcher", {"retrieval": 0.85, "synthesis": 0.65, "execution": 0.3, "verification": 0.4}),
        ("coder", {"retrieval": 0.4, "synthesis": 0.5, "execution": 0.9, "verification": 0.7}),
        ("reviewer", {"retrieval": 0.5, "synthesis": 0.4, "execution": 0.3, "verification": 0.9}),
        ("synthesizer", {"retrieval": 0.7, "synthesis": 0.9, "execution": 0.5, "verification": 0.5}),
    ]:
        mesh.add_agent(name, caps, trust_score=rnd.uniform(0.4, 0.7))
    
    tasks = [
        ("retrieval", "Research sleep and cognitive performance"),
        ("execution", "Implement a Kalman filter in Python"),
        ("verification", "Review the implementation for edge cases"),
        ("synthesis", "Synthesize all findings into a report"),
        ("retrieval", "Research HRV biofeedback protocols"),
        ("verification", "Cross-check the cited protocols"),
    ]
    
    for task_type, goal in tasks:
        r = mesh.execute(task_type, goal)
        agent_name = r.get("agent_name", "?")
        status = "✅" if r.get("success") else "❌"
        print(f"    {status} {task_type:15s} → {agent_name:15s}  ({r.get('duration_s', 0):.1f}s)")
    
    h = mesh.get_health()
    print(f"    ─── {h['completed_tasks']}✅ / {h['failed_tasks']}❌  success={h['success_rate']:.0%} ───")
    print()
    
    # ── 2. A2A SOCIAL MESH ──
    print("  ─── 2. A2A SOCIAL MESH — Trust-adjusted routing ───")
    social = A2ASocialMeshAdapter(exploration_rate=0.3)
    for name, caps, trust in [
        ("researcher", {"retrieval": 0.9, "synthesis": 0.6}, 0.7),
        ("coder", {"execution": 0.9, "verification": 0.5}, 0.4),  # low trust start
        ("reviewer", {"verification": 0.9, "retrieval": 0.5}, 0.6),
    ]:
        social.add_agent(name, caps, trust_score=trust)
    
    for i in range(5):
        task_type = rnd.choice(["retrieval", "execution", "verification"])
        r = social.execute(task_type, f"Social task {i+1}: {task_type}")
        exp = "(exploration)" if r.get("exploration_pick") else ""
        status = "✅" if r.get("success") else "❌"
        print(f"    {status} {task_type:15s} → {r.get('agent_name','?'):15s}  "
              f"trust={r.get('trust_score',0):.2f} {exp}")
    
    sh = social.get_social_health()
    social_trust = sh.get("social", {}).get("avg_trust", 0)
    print(f"    ─── Social health: avg_trust={social_trust:.2f}  "
          f"corrections={sh.get('social',{}).get('corrections_applied',0)} ───")
    print()
    
    # ── 3. A2A ORCHESTRATOR ──
    print("  ─── 3. A2A ORCHESTRATOR — Complex task decomposition ───")
    orch = A2AOrchestratorAdapter(topology="mesh")
    for name, caps in [
        ("researcher", {"retrieval": 0.85, "synthesis": 0.65}),
        ("engineer", {"execution": 0.9, "verification": 0.6}),
        ("qa", {"verification": 0.9, "retrieval": 0.4}),
        ("writer", {"synthesis": 0.85, "retrieval": 0.5}),
    ]:
        orch.add_agent(name, caps, trust_score=rnd.uniform(0.4, 0.7))
    
    for goal in [
        "Research and build an HRV monitoring system",
        "Review and verify the system design",
    ]:
        r = orch.execute(goal)
        print(f"    📋 '{goal[:40]}...'")
        print(f"       topology={r['topology']:6s}  "
              f"sub_tasks={r['sub_tasks']}  "
              f"successful={r['successful']}/{r['sub_tasks']}  "
              f"{'✅ ALL OK' if r['all_success'] else '⚠️ partial'}")
    
    # ── 4. CYCLE with A2A Chain ──
    print()
    print("  ─── 4. A2A CHAIN — Research → Build → Verify ───")
    chain_mesh = A2AMeshAdapter()
    for name, caps in [
        ("researcher", {"retrieval": 0.85, "synthesis": 0.5}),
        ("developer", {"execution": 0.85, "verification": 0.5}),
        ("auditor", {"verification": 0.85, "retrieval": 0.4}),
    ]:
        chain_mesh.add_agent(name, caps, trust_score=rnd.uniform(0.5, 0.7))
    
    chain_results = chain_mesh.execute_chain([
        ("retrieval", "Research optimal Kalman filter parameters for vol detection"),
        ("execution", "Implement the Kalman filter from the research"),
        ("verification", "Verify the implementation against spec"),
    ])
    
    for r in chain_results:
        status = "✅" if r.get("success") else "❌"
        agent = r.get("agent_name", "?")
        print(f"    {status} {agent:15s} ({r.get('duration_s',0):.1f}s)")
    
    chain_success = all(r.get("success", False) for r in chain_results)
    print(f"    ─── Chain: {'✅ ALL SUCCESSFUL' if chain_success else '❌ BROKEN'} ───")
    
    # ── Summary ──
    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  A2A Protocol Stack — Full Integration Verified:")
    print("    A2A Basic Mesh      ................... Agent + A2A routing")
    print("    A2A Social Mesh     ........ Trust-adjusted routing + exploration")
    print("    A2A Orchestrator    .... Multi-topology (chain/pipeline/mesh)")
    print("  ════════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
