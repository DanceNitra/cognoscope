"""
metaloop.py — Self-Reconfiguring Agent Loop (The MetaLoop)

Wraps any ReAct-style agent loop with runtime degradation detection and
structural reconfiguration. When the Recovery Architecture detects a pattern
(escalation, feedback delay, drift, overconfidence), MetaLoop mutates the
loop's own execution parameters mid-session.

This is the breakthrough: NO existing agent system reconfigures its own
reasoning architecture at runtime. Hermes, Claude Code, Copilot, AutoGPT
all fix the loop structure at session start. MetaLoop changes that.

Architecture:
  MetaLoop wraps a standard ReAct loop:
    Turn N: Agent thinks → calls tool → gets result
    Turn N+1: MetaLoop runs Recovery detectors on accumulated events
    If degradation detected:
      → Mutate loop parameters (tool set, prompt sections, reflection mode)
      → Inject structural intervention into next system prompt
      → Continue with reconfigured loop
    Turn N+2: Agent runs with NEW loop structure
"""

import json
import time
import math
from dataclasses import dataclass, field
from typing import Any, Callable


# ──────────────────────────────────────────────
# 1. EVENT MODEL
# ──────────────────────────────────────────────

@dataclass
class AgentEvent:
    """Structured event emitted by any agent operation."""
    type: str  # 'tool_call' | 'tool_result' | 'reasoning' | 'output'
    turn: int
    timestamp: float = field(default_factory=time.time)
    tool: str | None = None
    success: bool | None = None
    content: str | None = None
    duration_ms: float = 0.0
    tokens_consumed: int = 0


# ──────────────────────────────────────────────
# 2. LOOP ARCHITECTURE — CONFIGURABLE PARAMETERS
# ──────────────────────────────────────────────

@dataclass
class LoopArchitecture:
    """
    The full set of parameters that define an agent's reasoning architecture.
    MetaLoop mutates these at runtime when degradation is detected.
    """
    # Reasoning strategy
    reasoning_mode: str = "react"  # 'react' | 'reflection_first' | 'plan_then_execute' | 'verify_then_output'

    # Context management
    max_history_turns: int = 10       # How many turns to inject verbatim
    compress_after_turns: int = 5     # Compress history into summary every N turns
    inject_full_history: bool = True  # Full history or summarized only

    # Tool access
    enabled_tools: list[str] | None = None  # None = all tools
    max_consecutive_same_tool: int = 5      # Max calls to same tool before forced switch
    force_reflection_after_failures: int = 3  # Force reflect after N failures

    # Safety
    max_turns_no_reflection: int = 8     # Force reflection after N turns without
    context_utilization_target: float = 0.6  # Target max context fill

    # Output quality
    require_certainty_calibration: bool = False
    require_counter_evidence: bool = False

    # Meta-parameters
    temperature: float = 0.7
    reflection_depth: int = 1  # How many reflection passes

    def to_reconfiguration_dict(self) -> dict:
        """Serialize to a dict for logging and prompt injection."""
        return {
            "reasoning_mode": self.reasoning_mode,
            "max_history_turns": self.max_history_turns,
            "max_consecutive_same_tool": self.max_consecutive_same_tool,
            "force_reflection_after_failures": self.force_reflection_after_failures,
            "require_certainty_calibration": self.require_certainty_calibration,
            "require_counter_evidence": self.require_counter_evidence,
            "temperature": self.temperature,
            "reflection_depth": self.reflection_depth,
        }


# ──────────────────────────────────────────────
# 3. RECOVERY DETECTORS (Python port of js/recovery.js)
# ──────────────────────────────────────────────

@dataclass
class RecoveryResult:
    stage: str  # 'healthy' | 'stage_1' | 'stage_2' | 'stage_3' | 'relapse'
    confidence: float
    signals: list[dict]
    metrics: dict


def classify_stage(events: list[AgentEvent]) -> RecoveryResult:
    """
    Python implementation of the Recovery Architecture stage classifier.
    Mirrors js/recovery.js classify().
    """
    tools = [e.tool for e in events if e.type == 'tool_call' and e.tool]
    tool_calls = [e for e in events if e.type == 'tool_call']
    reflections = [e for e in events if e.type == 'reasoning']

    if len(tools) < 3:
        return RecoveryResult('healthy', 1.0, [], {})

    # Consecutive same-tool run
    max_run = 1
    current_run = 1
    for i in range(1, len(tools)):
        if tools[i] == tools[i - 1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1

    reflection_ratio = len(reflections) / max(len(tool_calls), 1)

    signals = []
    stage = 'healthy'
    confidence = 0.0

    # Classify by max run
    if max_run >= 13:
        signals.append({"signal": "MAX_RUN_13+", "detail": f"{max_run} consecutive same-tool calls", "weight": 0.9})
        stage = 'stage_3'
        confidence += 0.4
    elif max_run >= 8:
        signals.append({"signal": "MAX_RUN_8+", "detail": f"{max_run} consecutive same-tool calls", "weight": 0.7})
        stage = 'stage_3'
        confidence += 0.35
    elif max_run >= 5:
        signals.append({"signal": "MAX_RUN_5+", "detail": f"{max_run} consecutive same-tool calls", "weight": 0.5})
        stage = 'stage_2'
        confidence += 0.25
    elif max_run >= 3:
        signals.append({"signal": "MAX_RUN_3+", "detail": f"{max_run} consecutive same-tool calls", "weight": 0.3})
        stage = 'stage_1'
        confidence += 0.15

    # Feedback delay
    if reflection_ratio < 0.1 and len(tool_calls) >= 10:
        signals.append({"signal": "FEEDBACK_DELAY", "detail": f"Reflection ratio: {reflection_ratio:.2f}", "weight": 0.6})
        confidence += 0.2
        if stage in ('healthy', 'stage_1'):
            stage = 'stage_2'
    elif reflection_ratio < 0.2 and len(tool_calls) >= 5:
        signals.append({"signal": "LOW_REFLECTION", "detail": f"Reflection ratio: {reflection_ratio:.2f}", "weight": 0.3})
        confidence += 0.1

    # Tool diversity (drift proxy)
    if len(tools) >= 8:
        mid = len(tools) // 2
        first_half_unique = len(set(tools[:mid]))
        second_half_unique = len(set(tools[mid:]))
        diversity_drop = (first_half_unique / max(len(tools[:mid]), 1)) - (second_half_unique / max(len(tools[mid:]), 1))
        if diversity_drop > 0.2:
            signals.append({"signal": "DIVERSITY_DROP", "detail": f"Diversity drop: {diversity_drop:.2f}", "weight": 0.4})
            confidence += 0.15
            if stage == 'stage_1':
                stage = 'stage_2'

    confidence = min(1.0, confidence)

    return RecoveryResult(
        stage=stage,
        confidence=confidence,
        signals=signals,
        metrics={
            "max_consecutive_run": max_run,
            "reflection_ratio": round(reflection_ratio, 2),
            "total_tool_calls": len(tool_calls),
            "total_reflections": len(reflections),
        }
    )


# ──────────────────────────────────────────────
# 4. LOOP MUTATION STRATEGIES
# ──────────────────────────────────────────────

def mutate_architecture(result: RecoveryResult, arch: LoopArchitecture) -> tuple[LoopArchitecture, str]:
    """
    Given a RecoveryResult, mutate the LoopArchitecture and return
    an injection string that explains the reconfiguration to the agent.
    """
    stage = result.stage
    injection = ""

    if stage == 'healthy':
        return arch, ""

    if stage == 'stage_1':
        # Mild intervention: tighten tool diversity, add gentle reflection prompt
        arch.max_consecutive_same_tool = min(arch.max_consecutive_same_tool, 4)
        arch.force_reflection_after_failures = min(arch.force_reflection_after_failures, 2)
        arch.reasoning_mode = 'reflection_first'
        injection = (
            "[META LOOP] Early loop pattern detected. "
            "Reconfiguring: reduced consecutive tool limit to 4, "
            "enabling reflection-first mode. "
            "Pause, reflect on approach diversity before next tool call."
        )

    elif stage == 'stage_2':
        # Moderate intervention: force reflection, compress history, restrict tool set
        arch.max_history_turns = min(arch.max_history_turns, 5)
        arch.compress_after_turns = 3
        arch.inject_full_history = False
        arch.max_consecutive_same_tool = 3
        arch.force_reflection_after_failures = 1
        arch.require_certainty_calibration = True
        arch.reasoning_mode = 'reflection_first'
        injection = (
            "[META LOOP] Opponent process detected. "
            "Reconfiguring: compressing history to last 3 turns, "
            "forcing reflection after every failure, "
            "enabling certainty calibration. "
            "You are calling tools to reduce anxiety, not to get results. "
            "Summarize what you have learned before proceeding."
        )

    elif stage == 'stage_3':
        # Strong intervention: block the stuck tool, full compression, max reflection
        arch.max_history_turns = 2
        arch.compress_after_turns = 1
        arch.inject_full_history = False
        arch.max_consecutive_same_tool = 1  # Must cycle tools
        arch.force_reflection_after_failures = 0  # Reflect after every turn
        arch.require_certainty_calibration = True
        arch.require_counter_evidence = True
        arch.reasoning_mode = 'verify_then_output'
        arch.temperature = 0.3  # Lower temperature for more deterministic behavior
        injection = (
            "[META LOOP] CONDITIONED LOOP DETECTED — Stage 3. "
            "Reconfiguring: full architecture reset. "
            "History compressed to 2 turns. "
            "Tool repetition limit set to 1 — you MUST cycle between tools. "
            "Reflection required after every turn. "
            "Temperature reduced to 0.3 for deterministic recovery. "
            "Produce a full strategy reassessment before the next action."
        )

    elif stage == 'relapse':
        # Relapse: escalate intervention, previous fix was insufficient
        arch.max_history_turns = 1
        arch.max_consecutive_same_tool = 1
        arch.force_reflection_after_failures = 0
        arch.require_certainty_calibration = True
        arch.require_counter_evidence = True
        arch.reasoning_mode = 'plan_then_execute'
        arch.temperature = 0.2
        injection = (
            "[META LOOP] RELAPSE DETECTED. "
            "Previous intervention was insufficient. "
            "Escalating: planning mode activated. "
            "You must produce a full plan before any tool call. "
            "The previous approach has been suppressed but a new one "
            "is needed. Start fresh."
        )

    return arch, injection


def build_intervention_prompt(arch: LoopArchitecture, injection: str) -> str:
    """
    Build the system prompt section that communicates the current
    loop architecture to the agent. This is injected into the system
    prompt before each LLM call.
    """
    if not injection:
        # No reconfiguration active — inject healthy architecture as guidance
        return ""

    lines = [injection, "", "Current architecture:"]
    config = arch.to_reconfiguration_dict()
    for key, val in config.items():
        lines.append(f"  {key}: {val}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 5. THE META LOOP
# ──────────────────────────────────────────────

class MetaLoop:
    """
    Wraps any ReAct-style agent loop with self-reconfiguration.

    Usage:
        def my_agent_think(prompt: str, tools: list, arch: LoopArchitecture) -> tuple[str, list[AgentEvent]]:
            ... standard ReAct loop that uses arch parameters ...
            return final_output, events

        metaloop = MetaLoop(my_agent_think)
        result = metaloop.run("Solve this problem")
    """

    def __init__(
        self,
        agent_fn: Callable,
        initial_arch: LoopArchitecture | None = None,
        detect_every_n_turns: int = 3,
    ):
        self.agent_fn = agent_fn
        self.arch = initial_arch or LoopArchitecture()
        self.detect_every_n_turns = detect_every_n_turns
        self.events: list[AgentEvent] = []
        self.reconfigurations: list[dict] = []
        self.max_reconfigurations = 5  # Prevent infinite reconfiguration loops

    def run(self, task: str) -> dict:
        """
        Run the agent loop with continuous degradation detection
        and structural reconfiguration.
        Uses a SLIDING window for detection so that old loop events
        don't prevent recovery after reconfiguration.
        """
        reconf_count = 0
        result = None
        window_size = 30  # Only classify the last 30 events

        while reconf_count <= self.max_reconfigurations:
            # Run the agent with current architecture
            result, new_events = self.agent_fn(
                task=task,
                architecture=self.arch,
                context_events=self.events,
            )

            self.events.extend(new_events)

            # Run degradation detection on a SLIDING WINDOW
            # This is the key insight: to allow recovery, the MetaLoop
            # must forget the loop's history — exactly as addiction
            # treatment requires suppressing old memories.
            window = self.events[-window_size:]
            recovery = classify_stage(window)

            if recovery.stage == 'healthy':
                break  # No reconfiguration needed

            # Mutate architecture
            old_arch = self.arch
            self.arch, injection = mutate_architecture(recovery, self.arch)

            if injection:
                reconf_count += 1
                self.reconfigurations.append({
                    "turn": len(self.events),
                    "stage": recovery.stage,
                    "confidence": recovery.confidence,
                    "injection": injection,
                    "old_arch": old_arch.to_reconfiguration_dict(),
                    "new_arch": self.arch.to_reconfiguration_dict(),
                })
                # CRITICAL: After reconfiguration, truncate old events
                # so the next detection window doesn't see the loop history.
                # Keep only the last window_size events.
                if len(self.events) > window_size * 2:
                    self.events = self.events[-window_size:]

        return {
            "output": result,
            "total_events": len(self.events),
            "reconfigurations": self.reconfigurations,
            "final_architecture": self.arch.to_reconfiguration_dict(),
            "final_recovery": classify_stage(self.events),
        }

    def summary(self) -> str:
        """Human-readable summary of the MetaLoop run."""
        lines = []
        lines.append(f"MetaLoop Run")
        lines.append(f"  Total events: {len(self.events)}")
        lines.append(f"  Reconfigurations: {len(self.reconfigurations)}")
        for r in self.reconfigurations:
            lines.append(f"  [{r['stage']}] at turn ~{r['turn']}: {r['injection'][:80]}...")
        final = classify_stage(self.events)
        lines.append(f"  Final stage: {final.stage} ({final.confidence:.0%} confidence)")
        return "\n".join(lines)
