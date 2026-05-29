"""
a2a_protocol.py — Agent2Agent (A2A) Protocol Implementation (Level 11)

Google's Agent2Agent protocol ported to cognoscope. Provides a standard
agent-to-agent communication layer on top of the existing cognoscope stack
(agent_mesh, social_mesh, mesh_orchestrator).

Key A2A concepts:
  - AgentCard: public metadata an agent publishes (capabilities, skills, endpoint)
  - Task: a unit of work with a lifecycle {submitted→working→input-required→completed→failed→canceled}
  - Message: communication primitive with parts (text, file, data)
  - Artifact: structured output of a completed task

Architecture:
  OMC Talent Market (L7)  →  A2A Protocol  →  Agent Mesh (L7)
       social_mesh                    |           agent_mesh
                                      v
                              mesh_orchestrator
                              (Hermes delegate_task)

This file contains the CORE protocol types. Adapters live in adjacent files.

Bridge #65: The Agent2Agent Protocol — Standardizing Agent Communication
"""

from __future__ import annotations
import json, uuid, time, enum, random
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import auto


# ──────────────────────────────────────────────
# 1. AGENT CARD — Public agent metadata
# ──────────────────────────────────────────────

@dataclass
class AgentCard:
    """Public metadata an agent publishes for discovery and routing.
    
    The AgentCard is the first thing another agent reads before deciding
    to interact. It contains capabilities, skills, and connection info.
    
    A2A spec: https://a2a-protocol.org/specification#agent-card
    """
    name: str
    description: str = ""
    url: str = ""  # Endpoint URL (or "local" for same-process agents)
    agent_id: str = field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    
    # Capabilities vector (maps to agent_mesh capabilities)
    capabilities: dict[str, float] = field(default_factory=lambda: {
        "retrieval": 0.5, "synthesis": 0.5, "execution": 0.5,
        "verification": 0.5, "planning": 0.3, "debugging": 0.3,
    })
    
    # Skills — A2A-specific: what domains this agent can handle
    skills: list[str] = field(default_factory=list)
    
    # Trust and reputation
    trust_score: float = 0.5
    total_tasks: int = 0
    success_rate: float = 0.0
    
    # Who issued this card (self or discovery service)
    issuer: str = "self"
    
    # When this card expires (timestamp or 0 for no expiry)
    expires_at: float = 0
    
    @property
    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "skills": self.skills,
            "trust_score": self.trust_score,
            "total_tasks": self.total_tasks,
            "success_rate": self.success_rate,
            "issuer": self.issuer,
            "expires_at": self.expires_at,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "AgentCard":
        kwargs = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        skills = kwargs.get("skills")
        if skills is None:
            kwargs["skills"] = []
        elif isinstance(skills, list):
            kwargs["skills"] = skills
        return cls(**kwargs)


# ──────────────────────────────────────────────
# 2. A2A TYPES
# ──────────────────────────────────────────────

class TaskState(enum.Enum):
    """A2A Task lifecycle states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    
    def is_terminal(self) -> bool:
        return self in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED)
    
    def is_active(self) -> bool:
        return self in (TaskState.SUBMITTED, TaskState.WORKING, TaskState.INPUT_REQUIRED)


class MessageRole(enum.Enum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


class PartType(enum.Enum):
    TEXT = "text"
    FILE = "file"
    DATA = "data"
    CODE = "code"
    ERROR = "error"


@dataclass
class Part:
    """A single piece of content in a message.
    
    Parts are typed so agents can render them appropriately.
    A text part is plain text. A file part references an artifact.
    A data part is structured JSON.
    """
    type: PartType = PartType.TEXT
    text: str = ""
    file_path: str = ""
    mime_type: str = "text/plain"
    data: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "text": self.text,
            "file_path": self.file_path,
            "mime_type": self.mime_type,
            "data": self.data,
        }
    
    @classmethod
    def text_part(cls, text: str) -> "Part":
        return cls(type=PartType.TEXT, text=text)
    
    @classmethod
    def file_part(cls, file_path: str, mime_type: str = "application/octet-stream") -> "Part":
        return cls(type=PartType.FILE, file_path=file_path, mime_type=mime_type)
    
    @classmethod
    def data_part(cls, data: dict) -> "Part":
        return cls(type=PartType.DATA, data=data)
    
    @classmethod
    def error_part(cls, message: str) -> "Part":
        return cls(type=PartType.ERROR, text=message)


@dataclass
class Message:
    """A communication between agents.
    
    Messages are the basic unit of A2A communication. Each message
    contains one or more Parts (text, file, data, code).
    """
    role: MessageRole = MessageRole.AGENT
    parts: list[Part] = field(default_factory=list)
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
    
    def add_text(self, text: str):
        self.parts.append(Part.text_part(text))
    
    def add_file(self, file_path: str, mime_type: str = "application/octet-stream"):
        self.parts.append(Part.file_part(file_path, mime_type))
    
    def add_data(self, data: dict):
        self.parts.append(Part.data_part(data))
    
    def add_error(self, error: str):
        self.parts.append(Part.error_part(error))
    
    @property
    def text_content(self) -> str:
        """Concatenate all text parts."""
        return "\n".join(p.text for p in self.parts if p.type == PartType.TEXT)
    
    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "parts": [p.to_dict() for p in self.parts],
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class Artifact:
    """Structured output of a completed task.
    
    Unlike a Message (which is conversational), an Artifact is a
    completed deliverable — a file, a JSON result, or a synthesized summary.
    """
    artifact_id: str = field(default_factory=lambda: f"art_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    parts: list[Part] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "description": self.description,
            "parts": [p.to_dict() for p in self.parts],
            "metadata": self.metadata,
        }


@dataclass
class A2ATask:
    """A unit of work in the A2A protocol.
    
    A Task has a lifecycle:
      submitted → working → (input-required → working)* → completed | failed | canceled
    
    Each transition generates a Message. Messages accumulate in history.
    """
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    state: TaskState = TaskState.SUBMITTED
    sender_id: str = ""
    target_id: str = ""
    
    # The task content
    goal: str = ""
    input_messages: list[Message] = field(default_factory=list)
    output_messages: list[Message] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    
    # Task metadata
    task_type: str = ""  # research, synthesis, code, review, deploy, etc.
    priority: int = 5
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Error tracking
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    
    def transition_to(self, new_state: TaskState, reason: str = ""):
        """Transition task to a new state, recording the change."""
        old = self.state
        self.state = new_state
        self.updated_at = time.time()
        
        # Record transition as a system message
        msg = Message(
            role=MessageRole.SYSTEM,
            parts=[Part.text_part(f"State: {old.value} → {new_state.value}. {reason}")]
        )
        self.output_messages.append(msg)
    
    def add_input(self, message: Message):
        self.input_messages.append(message)
        self.updated_at = time.time()
    
    def add_output(self, message: Message):
        self.output_messages.append(message)
        self.updated_at = time.time()
    
    def add_artifact(self, artifact: Artifact):
        self.artifacts.append(artifact)
        self.updated_at = time.time()
    
    @property
    def duration(self) -> float:
        return self.updated_at - self.created_at
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "sender_id": self.sender_id,
            "target_id": self.target_id,
            "goal": self.goal,
            "task_type": self.task_type,
            "priority": self.priority,
            "input_messages": [m.to_dict() for m in self.input_messages],
            "output_messages": [m.to_dict() for m in self.output_messages],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_message": self.error_message,
        }


# ──────────────────────────────────────────────
# 3. DISCOVERY SERVICE
# ──────────────────────────────────────────────

class DiscoveryService:
    """A2A-compatible agent discovery service.
    
    Agents publish their AgentCards here. Other agents query to find
    the right agent for a task. Supports skill-based and capability-based lookup.
    """
    
    def __init__(self):
        self.cards: dict[str, AgentCard] = {}  # agent_id → AgentCard
        self._history: list[dict] = []
    
    def register(self, card: AgentCard):
        """Register or update an agent card."""
        self.cards[card.agent_id] = card
        self._history.append({
            "action": "register",
            "agent_id": card.agent_id,
            "name": card.name,
            "timestamp": time.time(),
        })
    
    def unregister(self, agent_id: str):
        if agent_id in self.cards:
            del self.cards[agent_id]
            self._history.append({
                "action": "unregister",
                "agent_id": agent_id,
                "timestamp": time.time(),
            })
    
    def find_by_capability(self, capability: str, min_score: float = 0.3) -> list[AgentCard]:
        """Find agents with a minimum capability score."""
        results = []
        for card in self.cards.values():
            score = card.capabilities.get(capability, 0)
            if score >= min_score:
                results.append((score, card))
        results.sort(key=lambda x: -x[0])
        return [c for _, c in results]
    
    def find_by_skill(self, skill: str) -> list[AgentCard]:
        """Find agents with a specific skill."""
        return [c for c in self.cards.values() if skill in c.skills]
    
    def find_best_for_task(self, task_type: str, required_capabilities: list[str] = None) -> AgentCard | None:
        """Find the best agent for a given task type and capabilities."""
        if not required_capabilities:
            required_capabilities = [task_type]
        candidates = []
        for card in self.cards.values():
            score = sum(card.capabilities.get(c, 0) for c in required_capabilities) / len(required_capabilities)
            if score > 0.2:
                candidates.append((score, card))
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1] if candidates else None
    
    def list_all(self) -> list[AgentCard]:
        return list(self.cards.values())
    
    def get_stats(self) -> dict:
        if not self.cards:
            return {"total_agents": 0}
        avg_trust = sum(c.trust_score for c in self.cards.values()) / len(self.cards)
        cap_counts = {}
        for card in self.cards.values():
            for cap in card.capabilities:
                cap_counts[cap] = cap_counts.get(cap, 0) + 1
        return {
            "total_agents": len(self.cards),
            "avg_trust": round(avg_trust, 3),
            "capability_distribution": cap_counts,
        }


# ──────────────────────────────────────────────
# 4. A2A PROTOCOL CLIENT — Task lifecycle executor
# ──────────────────────────────────────────────

class A2AClient:
    """A2A Protocol client — sends tasks, manages lifecycle, receives results.
    
    This is the main interface for agent-to-agent communication.
    An agent creates an A2AClient, sends a task to another agent's
    AgentCard, and tracks the task through its lifecycle.
    """
    
    def __init__(self, discovery: DiscoveryService | None = None):
        self.discovery = discovery or DiscoveryService()
        self.tasks: dict[str, A2ATask] = {}
        self.completed_tasks: list[A2ATask] = []
        self.task_history: list[dict] = []
    
    def send_task(self, card: AgentCard, goal: str,
                  task_type: str = "", priority: int = 5) -> A2ATask:
        """Send a task to an agent via its AgentCard.
        
        In a real A2A implementation this would make an HTTP call to
        the agent's URL. In cognoscope, it creates the task locally
        and returns it for the recipient to process.
        """
        task = A2ATask(
            goal=goal,
            sender_id="local",
            target_id=card.agent_id,
            task_type=task_type or "task",
            priority=priority,
        )
        task.transition_to(TaskState.WORKING, "Task sent to agent")
        self.tasks[task.task_id] = task
        self.task_history.append({
            "action": "send",
            "task_id": task.task_id,
            "target": card.name,
            "goal": goal[:50],
        })
        return task
    
    def receive_result(self, task: A2ATask):
        """Receive a completed/failed task result."""
        if task.task_id in self.tasks:
            self.tasks[task.task_id] = task
            if task.state.is_terminal():
                self.completed_tasks.append(task)
                del self.tasks[task.task_id]
    
    def get_active_tasks(self) -> list[A2ATask]:
        return [t for t in self.tasks.values() if t.state.is_active()]
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel an active task."""
        task = self.tasks.get(task_id)
        if task and task.state.is_active():
            task.transition_to(TaskState.CANCELED, "Canceled by sender")
            self.completed_tasks.append(task)
            del self.tasks[task_id]
            return True
        return False
    
    def get_stats(self) -> dict:
        total = len(self.completed_tasks) + len(self.tasks)
        success = sum(1 for t in self.completed_tasks if t.state == TaskState.COMPLETED)
        failed = sum(1 for t in self.completed_tasks if t.state == TaskState.FAILED)
        return {
            "total_tasks": total,
            "active": len(self.tasks),
            "completed": len(self.completed_tasks),
            "successful": success,
            "failed": failed,
            "success_rate": round(success / max(total, 1), 3),
        }


# ──────────────────────────────────────────────
# 5. A2A AGENT — Minimal A2A-compliant agent
# ──────────────────────────────────────────────

class A2AAgent:
    """A minimal agent that processes A2A tasks.
    
    In production, this would hook into an LLM. For cognoscope,
    it uses capability-based stochastic execution to simulate
    agent behavior for testing the protocol.
    """
    
    def __init__(self, card: AgentCard):
        self.card = card
        self.task_queue: list[A2ATask] = []
        self.completed_tasks: list[A2ATask] = []
        self.worker = A2AAgentWorker(card)
    
    def receive_task(self, task: A2ATask):
        """Accept a task into the queue."""
        task.target_id = self.card.agent_id
        task.transition_to(TaskState.WORKING, f"Accepted by {self.card.name}")
        self.task_queue.append(task)
    
    def process_next(self) -> A2ATask | None:
        """Process one task from the queue. Returns the completed task."""
        if not self.task_queue:
            return None
        task = self.task_queue.pop(0)
        result = self.worker.execute(task)
        result.transition_to(TaskState.COMPLETED if result.error_message == "" else TaskState.FAILED,
                             "Processing complete" if result.error_message == "" else result.error_message)
        result.updated_at = time.time()
        
        # Update card stats
        self.card.total_tasks += 1
        if result.state == TaskState.COMPLETED:
            self.card.success_rate = (
                (self.card.success_rate * (self.card.total_tasks - 1) + 1.0)
                / self.card.total_tasks
            )
            self.card.trust_score = min(1.0, self.card.trust_score + 0.02)
        else:
            self.card.success_rate = (
                (self.card.success_rate * (self.card.total_tasks - 1))
                / self.card.total_tasks
            )
            self.card.trust_score = max(0.0, self.card.trust_score - 0.05)
        
        self.completed_tasks.append(result)
        return result
    
    def process_all(self) -> list[A2ATask]:
        results = []
        while self.task_queue:
            r = self.process_next()
            if r:
                results.append(r)
        return results
    
    def get_stats(self) -> dict:
        return {
            "agent": self.card.name,
            "agent_id": self.card.agent_id,
            "queue": len(self.task_queue),
            "completed": len(self.completed_tasks),
            "trust": self.card.trust_score,
            "success_rate": self.card.success_rate,
            "capabilities": self.card.capabilities,
        }


class A2AAgentWorker:
    """Simulates task execution for A2A agents.
    
    In production this would call an LLM. Here it uses capability-weighted
    stochastic success/failure to test the protocol flow.
    """
    
    def __init__(self, card: AgentCard):
        self.card = card
    
    def execute(self, task: A2ATask) -> A2ATask:
        """Execute a task. Simulates capability-based work."""
        # Determine capability score for this task type
        cap_score = self.card.capabilities.get(task.task_type, 0.3)
        
        # Add randomness
        import random as rnd
        success_prob = cap_score * 0.7 + 0.15 + rnd.gauss(0, 0.05)
        success = rnd.random() < success_prob
        
        # Generate output message
        output = Message(role=MessageRole.AGENT)
        if success:
            output.add_text(f"Completed: {task.goal}")
            output.add_data({
                "agent": self.card.name,
                "task_type": task.task_type,
                "capability_used": cap_score,
                "latency_ms": round(50 + rnd.random() * 200, 1),
            })
        else:
            output.add_error(f"Failed: {task.goal} — capability {cap_score:.2f} insufficient under load")
            task.error_message = output.text_content
        
        task.add_output(output)
        task.updated_at = time.time()
        return task


# ──────────────────────────────────────────────
# 6. A2A PROTOCOL DEMO
# ──────────────────────────────────────────────

def demo():
    """Demonstrate the A2A protocol with multiple agents."""
    import random as rnd
    
    print()
    print("  ╔════════════════════════════════════════════════════════════╗")
    print("  ║   A2A PROTOCOL — Agent2Agent Communication Layer (L11)     ║")
    print("  ║   Agent Cards · Task Lifecycle · Messages · Discovery     ║")
    print("  ╚════════════════════════════════════════════════════════════╝")
    print()
    
    # ── 1. Register agents ──
    print("  ─── 1. DISCOVERY — 4 Agents Registered ───")
    
    discovery = DiscoveryService()
    agents = {}
    
    agent_specs = [
        ("Researcher", 0.8, 0.6, 0.3, ["retrieval", "synthesis"]),
        ("Coder", 0.4, 0.9, 0.5, ["execution", "verification"]),
        ("Reviewer", 0.5, 0.4, 0.9, ["verification", "planning"]),
        ("Synthesizer", 0.9, 0.3, 0.4, ["synthesis", "retrieval"]),
    ]
    
    for name, retrieval, execution, verification, skills in agent_specs:
        card = AgentCard(
            name=name,
            description=f"Specialist in {', '.join(skills)}",
            capabilities={
                "retrieval": retrieval, "synthesis": 0.5,
                "execution": execution, "verification": verification,
                "planning": 0.3, "debugging": 0.3,
            },
            skills=skills,
            trust_score=rnd.uniform(0.4, 0.7),
        )
        discovery.register(card)
        agents[name] = A2AAgent(card)
        print(f"    {name:<15s}  caps={retrieval},{execution},{verification}  trust={card.trust_score:.2f}")
    
    print(f"    ─── Registered: {len(discovery.list_all())} agents ───")
    print()
    
    # ── 2. Discovery query ──
    print("  ─── 2. DISCOVERY QUERIES ───")
    best = discovery.find_best_for_task("execution", ["execution", "verification"])
    print(f"    Best for execution+verification: {best.name if best else 'none'}")
    
    synthers = discovery.find_by_skill("synthesis")
    print(f"    Agents with synthesis skill: {len(synthers)} ({[a.name for a in synthers]})")
    print()
    
    # ── 3. Task lifecycle ──
    print("  ─── 3. TASK LIFECYCLE — Full Demo ───")
    
    client = A2AClient(discovery)
    tasks = [
        ("retrieval", "Research sleep neuroscience and its impact on cognitive performance"),
        ("execution", "Implement a Kalman filter for regime detection"),
        ("verification", "Review the Kalman filter implementation for edge cases"),
        ("synthesis", "Synthesize the research and review into a comprehensive report"),
    ]
    
    for task_type, goal in tasks:
        card = discovery.find_best_for_task(task_type, [task_type])
        if not card:
            print(f"    ⚠️ No agent found for {task_type}")
            continue
        
        # Send task via A2A
        task = client.send_task(card, goal, task_type=task_type)
        print(f"\n    📤 {task_type:15s} → {card.name}")
        print(f"       State: {task.state.value}")
        print(f"       Task ID: {task.task_id[:16]}...")
        
        # Agent receives & processes
        agent = agents[card.name]
        agent.receive_task(task)
        result = agent.process_next()
        
        # Client receives result
        if result:
            client.receive_result(result)
            print(f"       ✅ Result: {result.state.value}  "
                  f"({result.duration:.1f}s, err='{result.error_message[:30] if result.error_message else ''}')")
            
            # Show message content
            for msg in result.output_messages:
                if msg.parts:
                    preview = msg.parts[0].text[:60]
                    print(f"       💬 {preview}")
    
    # ── 4. Stats ──
    print()
    print("  ─── 4. FINAL STATS ───")
    stats = client.get_stats()
    print(f"    Tasks: {stats['total_tasks']} total, {stats['successful']} ✅ / {stats['failed']} ❌")
    print(f"    Success rate: {stats['success_rate']:.0%}")
    
    for name, agent in agents.items():
        s = agent.get_stats()
        print(f"    Agent {s['agent']:15s}  trust={s['trust']:.2f}  "
              f"success={s['success_rate']:.0%}  queue={s['queue']}")
    
    print()
    print(f"  ════════════════════════════════════════════════════════════")
    print(f"  A2A Protocol verified: {stats['total_tasks']} tasks routed, {stats['successful']} completed")
    print(f"  ════════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
