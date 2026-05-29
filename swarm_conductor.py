"""
swarm_conductor.py — Swarm Conductor (Level 13)

THE MULTI-AGENT ORCHESTRATOR.

The A2A protocol (L11) defines how agents TALK to each other.
The Swarm Conductor defines who LIVES, who WORKS, and who DIES.

This orchestrator:
  1. MANAGES the agent pool — spawn, register, monitor, kill
  2. ROUTES tasks — pick the right agent for the right job
  3. RESOLVES conflicts — deadlock detection, resource locking
  4. MONITORS health — heartbeat, load, hypocrisy per agent

No existing system (A2A spec, LangGraph, CrewAI) connects
multi-agent orchestration with guardrails, polygraph, and
dream loop cross-agent pattern detection.

Bridge #??: The Swarm Conductor — Orchestrating Autonomous Agents
"""

from __future__ import annotations
import json, os, sys, time, uuid, enum, math
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from typing import Any, Optional
from enum import auto

# ── Config ──
SWARM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".swarm")
os.makedirs(SWARM_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# 1. AGENT POOL MANAGER — Who's alive
# ──────────────────────────────────────────────

class AgentStatus(enum.Enum):
    IDLE = "idle"
    BUSY = "busy"
    DRAINING = "draining"
    DEGRADED = "degraded"
    DEAD = "dead"


@dataclass
class SwarmAgent:
    """A registered agent in the swarm pool."""
    name: str
    agent_id: str = field(default_factory=lambda: f"swarm_{uuid.uuid4().hex[:8]}")
    capabilities: dict[str, float] = field(default_factory=dict)
    status: AgentStatus = AgentStatus.IDLE
    trust_score: float = 0.5
    load: int = 0           # current task count
    max_load: int = 3        # max parallel tasks
    last_heartbeat: float = field(default_factory=time.time)
    spawned_at: float = field(default_factory=time.time)
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "trust_score": round(self.trust_score, 3),
            "load": self.load,
            "max_load": self.max_load,
            "last_heartbeat": self.last_heartbeat,
            "spawned_at": self.spawned_at,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "tags": self.tags,
            "success_rate": round(
                self.successful_tasks / max(self.total_tasks, 1), 3
            ),
        }

    @property
    def is_healthy(self) -> bool:
        """Agent is healthy if heartbeat within 30s and not dead."""
        if self.status == AgentStatus.DEAD:
            return False
        if time.time() - self.last_heartbeat > 30:
            return False
        return True

    @property
    def available(self) -> bool:
        """Agent can accept new tasks."""
        return (
            self.is_healthy
            and self.status != AgentStatus.DRAINING
            and self.load < self.max_load
        )


class AgentPool:
    """Manages the swarm agent registry."""

    def __init__(self, pool_path: str | None = None):
        self.pool_path = pool_path or os.path.join(SWARM_DIR, "agents.json")
        self.agents: dict[str, SwarmAgent] = {}
        self._load()

    def register(self, agent: SwarmAgent) -> str:
        """Register a new agent (or re-register an existing one by ID)."""
        if agent.agent_id in self.agents:
            existing = self.agents[agent.agent_id]
            existing.name = agent.name
            existing.capabilities = agent.capabilities
            existing.status = AgentStatus.IDLE
            existing.last_heartbeat = time.time()
            if existing.status in (AgentStatus.DEAD, AgentStatus.DRAINING):
                existing.status = AgentStatus.IDLE
            self._save()
            return agent.agent_id

        self.agents[agent.agent_id] = agent
        self._save()
        return agent.agent_id

    def spawn(self, name: str, capabilities: dict[str, float] | None = None,
              max_load: int = 3, tags: list[str] | None = None) -> SwarmAgent:
        """Spawn a new agent and add it to the pool."""
        agent = SwarmAgent(
            name=name,
            capabilities=capabilities or {},
            max_load=max_load,
            tags=tags or [],
        )
        self.agents[agent.agent_id] = agent
        self._save()
        return agent

    def kill(self, agent_id: str, force: bool = False) -> bool:
        """Remove an agent from the pool (or mark as dead if force=False)."""
        if agent_id not in self.agents:
            return False
        agent = self.agents[agent_id]
        if force or agent.status == AgentStatus.DEAD:
            del self.agents[agent_id]
        else:
            agent.status = AgentStatus.DRAINING if agent.load > 0 else AgentStatus.DEAD
        self._save()
        return True

    def heartbeat(self, agent_id: str) -> bool:
        """Agent sends heartbeat. Returns True if still alive in pool."""
        if agent_id not in self.agents:
            return False
        self.agents[agent_id].last_heartbeat = time.time()
        if self.agents[agent_id].status == AgentStatus.DEAD:
            # Resurrection — agent came back
            self.agents[agent_id].status = AgentStatus.IDLE
        return True

    def get(self, agent_id: str) -> SwarmAgent | None:
        return self.agents.get(agent_id)

    def find_by_capability(self, capability: str, min_score: float = 0.0) -> list[SwarmAgent]:
        """Find agents with a specific capability at or above min_score."""
        results = []
        for a in self.agents.values():
            score = a.capabilities.get(capability, 0.0)
            if score >= min_score and a.available:
                results.append(a)
        return sorted(results, key=lambda a: a.capabilities.get(capability, 0), reverse=True)

    def find_by_tag(self, tag: str) -> list[SwarmAgent]:
        return [a for a in self.agents.values() if tag in a.tags and a.available]

    def list_alive(self) -> list[SwarmAgent]:
        return [a for a in self.agents.values() if a.is_healthy]

    def list_available(self) -> list[SwarmAgent]:
        return [a for a in self.agents.values() if a.available]

    def get_pool_summary(self) -> dict:
        all_a = list(self.agents.values())
        alive = self.list_alive()
        available = self.list_available()
        return {
            "total": len(all_a),
            "alive": len(alive),
            "available": len(available),
            "busy": sum(1 for a in all_a if a.status == AgentStatus.BUSY),
            "dead": sum(1 for a in all_a if a.status == AgentStatus.DEAD),
            "draining": sum(1 for a in all_a if a.status == AgentStatus.DRAINING),
            "total_load": sum(a.load for a in all_a),
            "total_tasks_completed": sum(a.total_tasks for a in all_a),
        }

    def prune_dead(self, max_age_seconds: int = 300) -> int:
        """Remove agents that have been dead for too long."""
        now = time.time()
        to_remove = [
            aid for aid, a in self.agents.items()
            if a.status == AgentStatus.DEAD and now - a.last_heartbeat > max_age_seconds
        ]
        for aid in to_remove:
            del self.agents[aid]
        if to_remove:
            self._save()
        return len(to_remove)

    def _load(self):
        if os.path.exists(self.pool_path):
            try:
                with open(self.pool_path) as f:
                    data = json.load(f)
                for entry in data:
                    a = SwarmAgent(
                        name=entry["name"],
                        agent_id=entry["agent_id"],
                        capabilities=entry.get("capabilities", {}),
                        status=AgentStatus(entry.get("status", "idle")),
                        trust_score=entry.get("trust_score", 0.5),
                        load=entry.get("load", 0),
                        max_load=entry.get("max_load", 3),
                        last_heartbeat=entry.get("last_heartbeat", time.time()),
                        spawned_at=entry.get("spawned_at", time.time()),
                        total_tasks=entry.get("total_tasks", 0),
                        successful_tasks=entry.get("successful_tasks", 0),
                        failed_tasks=entry.get("failed_tasks", 0),
                        tags=entry.get("tags", []),
                    )
                    self.agents[a.agent_id] = a
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        data = [a.to_dict() for a in self.agents.values()]
        with open(self.pool_path, 'w') as f:
            json.dump(data, f, indent=2)


# ──────────────────────────────────────────────
# 2. TASK ROUTER — Who does what
# ──────────────────────────────────────────────

class RoutingStrategy(enum.Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    CAPABILITY_WEIGHTED = "capability_weighted"
    TRUST_WEIGHTED = "trust_weighted"


@dataclass
class SwarmTask:
    """A task to be routed to an agent in the swarm."""
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    goal: str = ""
    task_type: str = "general"
    priority: int = 0          # higher = more urgent
    source: str = ""           # who submitted the task
    assigned_to: str = ""      # agent_id
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""
    result: dict | None = None


class TaskRouter:
    """Routes tasks to the best available agent."""

    def __init__(self, pool: AgentPool):
        self.pool = pool
        self.queue: list[SwarmTask] = []
        self.active: dict[str, SwarmTask] = {}  # actively assigned tasks
        self.completed: list[SwarmTask] = []
        self.rr_index: dict[str, int] = defaultdict(int)  # per-capability round-robin
        self.strategy: RoutingStrategy = RoutingStrategy.CAPABILITY_WEIGHTED

    def submit(self, task: SwarmTask) -> SwarmTask:
        """Submit a task. If an agent is immediately available, route it."""
        self.queue.append(task)
        # Sort by priority (highest first), then by age
        self.queue.sort(key=lambda t: (-t.priority, t.created_at))
        return task

    def route(self, task: SwarmTask) -> SwarmTask | None:
        """Find the best agent for a task and assign it."""
        candidates = self.pool.find_by_capability(task.task_type, min_score=0.3)
        if not candidates:
            task.error = f"No available agent for '{task.task_type}'"
            self.completed.append(task)
            return None

        best = self._pick_best(candidates, task)
        if best is None:
            task.error = "Could not pick agent (all candidates saturated)"
            self.completed.append(task)
            return None

        task.assigned_to = best.agent_id
        task.started_at = time.time()
        best.load += 1
        best.status = AgentStatus.BUSY
        best.total_tasks += 1
        self.active[task.task_id] = task
        return task

    def _pick_best(self, candidates: list[SwarmAgent], task: SwarmTask) -> SwarmAgent | None:
        """Pick the best agent from candidates based on strategy."""
        if not candidates:
            return None

        if self.strategy == RoutingStrategy.ROUND_ROBIN:
            idx = self.rr_index[task.task_type] % len(candidates)
            self.rr_index[task.task_type] += 1
            return candidates[idx]

        if self.strategy == RoutingStrategy.LEAST_LOADED:
            return min(candidates, key=lambda a: a.load)

        if self.strategy == RoutingStrategy.TRUST_WEIGHTED:
            return max(candidates, key=lambda a: a.trust_score)

        # CAPABILITY_WEIGHTED (default)
        scored = []
        for a in candidates:
            cap_score = a.capabilities.get(task.task_type, 0.0)
            load_penalty = a.load / max(a.max_load, 1)
            trust_bonus = a.trust_score * 0.2
            total = cap_score * 0.5 - load_penalty * 0.3 + trust_bonus
            scored.append((total, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    def complete(self, task_id: str, success: bool = True, result: dict | None = None) -> SwarmTask | None:
        """Mark a task as completed."""
        # Check active tasks first, then queue
        task = self.active.pop(task_id, None)
        if task is None:
            task = next((t for t in self.queue if t.task_id == task_id), None)
        if task is None:
            return None
        if task in self.queue:
            self.queue.remove(task)
        elif task_id not in self.active:
            pass  # Already popped from active above
        task.completed_at = time.time()
        task.result = result
        task.started_at = task.started_at or task.completed_at

        # Update agent stats
        agent = self.pool.get(task.assigned_to)
        if agent:
            agent.load = max(0, agent.load - 1)
            if agent.load == 0:
                agent.status = AgentStatus.IDLE
            if success:
                agent.successful_tasks += 1
                agent.trust_score = min(1.0, agent.trust_score + 0.02)
            else:
                agent.failed_tasks += 1
                agent.trust_score = max(0.0, agent.trust_score - 0.05)

        self.completed.append(task)
        return task

    def process_queue(self, max_tasks: int = 10) -> list[SwarmTask]:
        """Process pending tasks: route each to an available agent."""
        routed = []
        processed = 0
        attempted = 0
        while self.queue and processed < max_tasks and attempted < max_tasks * 2:
            task = self.queue[0]
            attempted += 1
            # Only route if agent available
            candidates = self.pool.find_by_capability(task.task_type, min_score=0.3)
            if candidates:
                self.queue.pop(0)
                result = self.route(task)
                if result:
                    routed.append(result)
                    processed += 1
            else:
                # No agent available — skip this task (agents might free up later)
                self.queue.append(self.queue.pop(0))
        return routed

    def get_queue_stats(self) -> dict:
        return {
            "pending": len(self.queue),
            "completed": len(self.completed),
            "strategy": self.strategy.value,
            "avg_wait": self._avg_wait_time(),
        }

    def _avg_wait_time(self) -> float:
        if not self.completed:
            return 0.0
        waits = [c.started_at - c.created_at for c in self.completed if c.started_at > 0]
        return sum(waits) / max(len(waits), 1)


# ──────────────────────────────────────────────
# 3. CONFLICT RESOLUTION — Who wins
# ──────────────────────────────────────────────

@dataclass
class ResourceLock:
    """A lock on a shared resource."""
    resource_id: str
    holder_id: str        # agent_id that holds the lock
    acquired_at: float = field(default_factory=time.time)
    ttl_seconds: float = 30.0
    exclusive: bool = True

    @property
    def expired(self) -> bool:
        return time.time() - self.acquired_at > self.ttl_seconds


class ConflictResolver:
    """Detects and resolves conflicts between agents in the swarm."""

    def __init__(self):
        self.locks: dict[str, ResourceLock] = {}
        self.conflict_log: list[dict] = []

    def acquire_lock(self, resource_id: str, agent_id: str,
                     exclusive: bool = True, ttl: float = 30.0) -> bool:
        """Try to acquire a lock on a resource."""
        existing = self.locks.get(resource_id)
        if existing is None or existing.expired or existing.holder_id == agent_id:
            self.locks[resource_id] = ResourceLock(
                resource_id=resource_id,
                holder_id=agent_id,
                exclusive=exclusive,
                ttl_seconds=ttl,
            )
            return True
        # Deadlock? Check if existing holder is waiting for something from requester
        if self._detect_deadlock(resource_id, agent_id, existing.holder_id):
            self._log_conflict(resource_id, agent_id, existing.holder_id)
            self._resolve_deadlock(resource_id, agent_id, existing.holder_id)
            return True
        return False

    def release_lock(self, resource_id: str, agent_id: str) -> bool:
        """Release a lock (only holder can release)."""
        lock = self.locks.get(resource_id)
        if lock and lock.holder_id == agent_id:
            del self.locks[resource_id]
            return True
        return False

    def agent_locks(self, agent_id: str) -> list[ResourceLock]:
        return [l for l in self.locks.values() if l.holder_id == agent_id]

    def _detect_deadlock(self, resource_id: str, requester: str, holder: str) -> bool:
        """Simple deadlock detection: if holder is waiting for requester."""
        holder_locks = self.agent_locks(holder)
        for lock in holder_locks:
            if lock.resource_id == resource_id:
                continue
            # Check if any other agent is waiting on holder's lock
            for other_lock in self.locks.values():
                if other_lock.resource_id == lock.resource_id and other_lock.holder_id == requester:
                    return True  # Circular dependency detected
        return False

    def _resolve_deadlock(self, resource_id: str, requester: str, holder: str):
        """Resolve a deadlock by releasing the holder's lock (they lose)."""
        self._log_conflict(resource_id, requester, holder, resolved=True)
        del self.locks[resource_id]

    def _log_conflict(self, resource_id: str, requester: str, holder: str, resolved: bool = False):
        self.conflict_log.append({
            "time": time.time(),
            "resource_id": resource_id,
            "requester": requester,
            "holder": holder,
            "resolved": resolved,
        })

    def get_conflict_summary(self) -> dict:
        recent = [c for c in self.conflict_log if time.time() - c["time"] < 3600]
        resolved = sum(1 for c in recent if c.get("resolved"))
        return {
            "active_locks": len(self.locks),
            "conflicts_last_hour": len(recent),
            "resolved_deadlocks": resolved,
            "unresolved": len(recent) - resolved,
        }


# ──────────────────────────────────────────────
# 4. SWARM ORCHESTRATOR — The Conductor
# ──────────────────────────────────────────────

class SwarmConductor:
    """The main orchestrator — connects pool + router + resolver + external layers.

    Architecture:
      AgentPool (who lives)
        → TaskRouter (who does what)
          → ConflictResolver (who wins)
            → GuardrailBus (safety per agent)
              → AgentPolygraph (hypocrisy per agent)
                → DreamLoop (swarm-wide patterns)

    This is Level 13 of the cognoscope stack — the outermost layer
    that connects all previous layers into a multi-agent system.
    """

    def __init__(self, guardrail_bus=None, polygraph=None):
        self.pool = AgentPool()
        self.router = TaskRouter(self.pool)
        self.resolver = ConflictResolver()
        self.guardrail_bus = guardrail_bus
        self.polygraph = polygraph
        self._started_at = time.time()

    # ── Agent lifecycle ──

    def register_agent(self, name: str, capabilities: dict[str, float] | None = None,
                       max_load: int = 3, tags: list[str] | None = None) -> SwarmAgent:
        """Register an agent in the pool."""
        return self.pool.spawn(name, capabilities, max_load, tags)

    def kill_agent(self, agent_id: str, force: bool = False) -> bool:
        """Remove an agent from the pool."""
        return self.pool.kill(agent_id, force)

    def agent_heartbeat(self, agent_id: str) -> bool:
        """Agent sends heartbeat."""
        return self.pool.heartbeat(agent_id)

    # ── Task management ──

    def submit_task(self, goal: str, task_type: str = "general",
                    priority: int = 0, source: str = "") -> SwarmTask:
        """Submit a task and immediately try to route it."""
        task = SwarmTask(goal=goal, task_type=task_type,
                         priority=priority, source=source)
        self.router.submit(task)
        # Try immediate routing
        routed = self.router.process_queue(max_tasks=1)
        return routed[0] if routed else task

    def submit_batch(self, tasks: list[SwarmTask]) -> list[SwarmTask]:
        """Submit multiple tasks and route as many as possible."""
        for t in tasks:
            self.router.submit(t)
        return self.router.process_queue(max_tasks=len(tasks))

    def complete_task(self, task_id: str, success: bool = True,
                      result: dict | None = None) -> SwarmTask | None:
        """Mark a task as completed."""
        return self.router.complete(task_id, success, result)

    # ── Resources ──

    def lock_resource(self, resource_id: str, agent_id: str) -> bool:
        return self.resolver.acquire_lock(resource_id, agent_id)

    def unlock_resource(self, resource_id: str, agent_id: str) -> bool:
        return self.resolver.release_lock(resource_id, agent_id)

    # ── Health ──

    def health_check(self) -> dict:
        """Full swarm health check."""
        pool = self.pool.get_pool_summary()
        queue = self.router.get_queue_stats()
        conflicts = self.resolver.get_conflict_summary()
        uptime = time.time() - self._started_at

        # Polygraph check per agent?
        polygraph_report = None
        if self.polygraph:
            polygraph_report = self.polygraph.get_summary()

        return {
            "uptime_seconds": round(uptime),
            "pool": pool,
            "queue": queue,
            "conflicts": conflicts,
            "polygraph": polygraph_report,
            "guardrail_bus_active": self.guardrail_bus is not None,
        }

    def prune(self) -> int:
        """Remove dead agents and expired locks."""
        dead_pruned = self.pool.prune_dead()
        # Release expired locks
        expired = [rid for rid, l in self.resolver.locks.items() if l.expired]
        for rid in expired:
            del self.resolver.locks[rid]
        return dead_pruned + len(expired)

    def get_summary_text(self) -> str:
        """Generate a human-readable swarm summary."""
        h = self.health_check()
        pool = h["pool"]
        queue = h["queue"]
        conflicts = h["conflicts"]
        uptime = h["uptime_seconds"]

        lines = []
        lines.append("  ╔══════════════════════════════════════════════════╗")
        lines.append("  ║        SWARM CONDUCTOR — Multi-Agent Summary    ║")
        lines.append("  ╚══════════════════════════════════════════════════╝")
        lines.append("")
        lines.append(f"  🐝 Agents: {pool['alive']} alive / {pool['total']} total  "
                     f"|  {pool['available']} available  |  load={pool['total_load']}")
        lines.append(f"     → {pool['busy']} busy  |  {pool['dead']} dead  "
                     f"|  {pool['draining']} draining")
        lines.append(f"     → {pool['total_tasks_completed']} total tasks completed")
        lines.append("")
        lines.append(f"  📋 Queue: {queue['pending']} pending  "
                     f"|  {queue['completed']} completed  "
                     f"|  strategy={queue['strategy']}")
        lines.append(f"     → avg wait: {queue['avg_wait']:.2f}s")
        lines.append("")
        lines.append(f"  🔒 Conflicts: {conflicts['active_locks']} active locks  "
                     f"|  {conflicts['conflicts_last_hour']} conflicts/h")
        if conflicts['resolved_deadlocks'] > 0:
            lines.append(f"     → {conflicts['resolved_deadlocks']} resolved deadlocks")
        lines.append("")
        lines.append(f"  ⏱️  Uptime: {uptime // 60:.0f}m {uptime % 60:.0f}s")
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# 5. AGENT STATUS UPDATER (auto-drains dead agents)
# ──────────────────────────────────────────────

class AgentStatusWatcher:
    """Runs in the background to update agent statuses.

    In production this would be a thread/task that polls
    heartbeats. Here it's called synchronously.
    """

    def __init__(self, conductor: SwarmConductor):
        self.conductor = conductor

    def tick(self):
        """One tick: mark stale agents as dead, drain completed."""
        now = time.time()
        for agent in list(self.conductor.pool.agents.values()):
            if now - agent.last_heartbeat > 30:
                if agent.status in (AgentStatus.IDLE, AgentStatus.BUSY, AgentStatus.DEGRADED):
                    agent.status = AgentStatus.DEAD
            elif agent.status == AgentStatus.DEAD and now - agent.last_heartbeat < 10:
                # Agent came back
                if agent.load == 0:
                    agent.status = AgentStatus.IDLE
                else:
                    agent.status = AgentStatus.BUSY


# ──────────────────────────────────────────────
# 6. DEMO — The Conductor in Action
# ──────────────────────────────────────────────

def demo():
    """Demonstrate the full swarm conductor."""
    import random as rnd

    print()
    print("  ╔════════════════════════════════════════════════════════════╗")
    print("  ║   SWARM CONDUCTOR — Multi-Agent Orchestrator (L13)        ║")
    print("  ║   Agent Pool · Task Router · Conflict Resolver            ║")
    print("  ╚════════════════════════════════════════════════════════════╝")
    print()

    # ── 1. Create conductor ──
    conductor = SwarmConductor()
    print("  ─── 1. SWARM CREATED ───")
    print()

    # ── 2. Register agents ──
    print("  ─── 2. REGISTERING AGENTS ───")

    agents = {}
    specs = [
        ("Athena", {"retrieval": 0.9, "synthesis": 0.7, "planning": 0.8}, 4, ["core", "research"]),
        ("Hephaestus", {"execution": 0.9, "verification": 0.6, "debugging": 0.7}, 3, ["core", "coding"]),
        ("Hermes", {"communication": 0.9, "synthesis": 0.6, "planning": 0.5}, 5, ["core", "comm"]),
        ("Demeter", {"retrieval": 0.6, "analysis": 0.8, "synthesis": 0.7}, 3, ["core", "research"]),
        ("Ares", {"execution": 0.7, "debugging": 0.8, "verification": 0.5}, 2, ["core", "ops"]),
    ]

    for name, caps, max_load, tags in specs:
        agent = conductor.register_agent(name, caps, max_load, tags)
        agents[name] = agent
        print(f"    🐝 {name:<15s}  id={agent.agent_id[:12]}...  "
              f"caps={len(caps)}  max_load={max_load}")

    print(f"    ─── {len(agents)} agents registered ───")
    print()

    # ── 3. Submit tasks ──
    print("  ─── 3. SUBMITTING TASKS ───")

    task_specs = [
        ("Research sleep neuroscience", "retrieval", 2),
        ("Implement Kalman filter", "execution", 3),
        ("Review implementation", "verification", 1),
        ("Synthesize findings", "synthesis", 2),
        ("Debug edge cases", "debugging", 2),
        ("Plan next iteration", "planning", 1),
        ("Communication summary", "communication", 0),
        ("Deep analysis of results", "analysis", 2),
    ]

    routed_tasks = []
    for goal, task_type, priority in task_specs:
        # Submit
        task = conductor.submit_task(goal, task_type, priority, source="user")
        routed_tasks.append(task)

        if task.assigned_to:
            agent_name = "?"
            for n, a in agents.items():
                if a.agent_id == task.assigned_to:
                    agent_name = n
                    break
            print(f"    📤 {task_type:15s} → {agent_name:<15s}  "
                  f"priority={priority}  ({goal[:40]}...)")
        else:
            print(f"    ⏳ {task_type:15s} → queued  (no agent available yet)")

    print()
    print(f"    ─── tasks: pending={conductor.router.get_queue_stats()['pending']}  "
          f"completed={conductor.router.get_queue_stats()['completed']} ───")
    print()

    # ── 4. Simulate heartbeats ──
    print("  ─── 4. HEARTBEATS ───")
    for name, a in agents.items():
        ok = conductor.agent_heartbeat(a.agent_id)
        status = "✅ alive" if ok else "❌ dead"
        load = [t for t in routed_tasks if t.assigned_to == a.agent_id]
        print(f"    ❤️  {name:<15s}  {status}  load={len(load)}  "
              f"available={a.available}")
    print()

    # ── 5. Complete some tasks ──
    print("  ─── 5. COMPLETING TASKS ───")
    for t in routed_tasks[:3]:  # Complete first 3
        if not t.assigned_to:
            continue
        success = rnd.random() > 0.2
        result = {"status": "ok" if success else "error"}
        completed = conductor.complete_task(t.task_id, success, result)
        if completed:
            agent = conductor.pool.get(t.assigned_to)
            agent_name = agent.name if agent else "?"
            print(f"    {'✅' if success else '❌'} {t.task_type:15s} by {agent_name:<15s}  "
                  f"({completed.completed_at - completed.created_at:.1f}s)")
    print()

    # ── 6. Conflict demo ──
    print("  ─── 6. CONFLICT RESOLUTION ───")
    a1 = agents["Athena"]
    a2 = agents["Ares"]

    lock1 = conductor.lock_resource("file:report.md", a1.agent_id)
    print(f"    🔒 Athena locks 'file:report.md': {'✅' if lock1 else '❌'}")
    lock2 = conductor.lock_resource("file:report.md", a2.agent_id)
    print(f"    🔒 Ares locks 'file:report.md': {'✅' if lock2 else '❌'}  (Athena still holds it)")
    # Ares tries again with deadlock resolution
    lock2_retry = conductor.lock_resource("file:report.md", a2.agent_id)
    print(f"    🔄 Ares retries: {'✅' if lock2_retry else '❌'}")
    unlock = conductor.unlock_resource("file:report.md", a1.agent_id)
    print(f"    🔓 Athena unlocks: {'✅' if unlock else '❌'}")

    # Livelock demo
    a1_lock_b = conductor.lock_resource("db:users", a1.agent_id)
    a2_lock_b = conductor.lock_resource("db:orders", a2.agent_id)
    print(f"    🔒 Athena on 'db:users': ✅ | Ares on 'db:orders': ✅")
    a1_lock_c = conductor.lock_resource("db:orders", a1.agent_id)
    print(f"    🔄 Athena wants 'db:orders' (held by Ares): ", end="")
    if not a1_lock_c:
        print("❌ locked — no deadlock detected")
    print()

    # ── 7. Final health check ──
    print("  ─── 7. SWARM HEALTH ───")
    health = conductor.health_check()
    print(f"    🐝 Agents: {health['pool']['alive']} alive / "
          f"{health['pool']['total']} total")
    print(f"    📋 Queue: {health['queue']['pending']} pending / "
          f"{health['queue']['completed']} completed")
    print(f"    🔒 Conflicts: {health['conflicts']['active_locks']} active / "
          f"{health['conflicts']['conflicts_last_hour']} total")
    print(f"    ⏱️  Uptime: {health['uptime_seconds'] // 60}m "
          f"{health['uptime_seconds'] % 60}s")

    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  🐝 Swarm Conductor verified.")
    h = health
    print(f"  {h['pool']['alive']} agents · {h['queue']['completed']} tasks · "
          f"{h['conflicts']['active_locks']} locks")
    print("  ════════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
