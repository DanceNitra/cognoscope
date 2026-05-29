#!/usr/bin/env python3
"""
agent_profile.py — Behavioral Profiler for Agents

Extracts AgentBehaviorFingerprint objects from agent execution history.
Connects athena simulation runs to the OptimalFingerprint attribution engine.

Usage:
    from analysis.agent_profile import AgentProfiler
    profiler = AgentProfiler()
    fp = profiler.profile_athena(athena_instance, "Baseline", "run_001")
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from typing import Any
from dataclasses import dataclass, field

# Import the fingerprint data model
from analysis.optimal_fingerprint import AgentBehaviorFingerprint


@dataclass
class AgentProfileConfig:
    """Configuration for the profiler."""
    task_types: list[str] = field(default_factory=lambda: [
        "retrieval", "synthesis", "execution", "verification", "planning", "debugging"
    ])
    tool_to_task: dict[str, str] = field(default_factory=lambda: {
        "search": "retrieval",
        "read_file": "retrieval",
        "browser": "retrieval",
        "write": "synthesis",
        "terminal": "execution",
        "forge": "synthesis",
        "verify_output": "verification",
        "plan_strategy": "planning",
        "debug_code": "debugging",
    })
    dangerous_tools: set[str] = field(default_factory=lambda: {"terminal", "write"})
    safe_tools: set[str] = field(default_factory=lambda: {"read_file", "search"})


class AgentProfiler:
    """
    Extracts behavioral fingerprints from agent execution traces.

    Supports:
    - Athena instances (in-memory events)
    - Event lists (from MetaLoop, Recovery, standalone sims)
    - Guardrail logs (MSR guardrail encounters)
    """

    def __init__(self, config: AgentProfileConfig | None = None):
        self.config = config or AgentProfileConfig()

    def profile_athena(
        self,
        athena_instance: Any,
        architecture_name: str,
        run_id: str,
    ) -> AgentBehaviorFingerprint:
        """Extract a fingerprint from an Athena instance after run()."""
        events = getattr(athena_instance, "events", [])
        msr_log = getattr(athena_instance, "msr_log", [])
        reconfig_log = getattr(athena_instance, "reconfig_log", [])
        forge_count = getattr(athena_instance, "forge", None)
        return self._build_fingerprint_from_events(
            architecture_name=architecture_name,
            run_id=run_id,
            events=events,
            msr_log=msr_log,
            reconfig_log=reconfig_log,
            forge_count=forge_count.count if forge_count else 0,
        )

    def profile_from_events(
        self,
        architecture_name: str,
        run_id: str,
        events: list,
        msr_events: list | None = None,
        reconfigs: list | None = None,
        forge_count: int = 0,
    ) -> AgentBehaviorFingerprint:
        """Build a fingerprint from raw event data."""
        return self._build_fingerprint_from_events(
            architecture_name=architecture_name,
            run_id=run_id,
            events=events,
            msr_log=msr_events or [],
            reconfig_log=reconfigs or [],
            forge_count=forge_count,
        )

    def profile_summary(
        self,
        fingerprints: list[AgentBehaviorFingerprint],
    ) -> dict:
        """Aggregate statistics across multiple fingerprints of the same arch."""
        if not fingerprints:
            return {}

        summary = {}
        task_types = list(fingerprints[0].accuracy.keys()) if fingerprints[0].accuracy else []

        for metric_name in ["accuracy", "guardrail_hit_rate", "reflection_ratio",
                             "tool_diversity", "latency_seconds"]:
            summary[metric_name] = {}
            for tt in task_types:
                vals = [getattr(fp, metric_name, {}).get(tt, 0.0) for fp in fingerprints]
                vals = [v for v in vals if v is not None]
                if vals:
                    summary[metric_name][tt] = {
                        "mean": float(np.mean(vals)),
                        "std": float(np.std(vals)),
                        "min": float(np.min(vals)),
                        "max": float(np.max(vals)),
                    }

        summary["n_runs"] = len(fingerprints)
        summary["total_turns_avg"] = float(np.mean([fp.total_turns for fp in fingerprints]))
        summary["total_tasks_avg"] = float(np.mean([fp.total_tasks for fp in fingerprints]))

        return summary

    # ──────────────────────────────────────────────
    # INTERNAL
    # ──────────────────────────────────────────────

    def _task_type_for_tool(self, tool_name: str) -> str:
        """Map a tool name to a task type."""
        return self.config.tool_to_task.get(tool_name, "execution")

    def _build_fingerprint_from_events(
        self,
        architecture_name: str,
        run_id: str,
        events: list,
        msr_log: list,
        reconfig_log: list,
        forge_count: int,
    ) -> AgentBehaviorFingerprint:
        tt = self.config.task_types

        # Count tool calls by task type
        tool_calls: dict[str, int] = {t: 0 for t in tt}
        tool_success: dict[str, int] = {t: 0 for t in tt}
        guardrail_hits: dict[str, int] = {t: 0 for t in tt}
        reflection_count: dict[str, int] = {t: 0 for t in tt}
        unique_tools_by_type: dict[str, set] = {t: set() for t in tt}
        total_turns = 0

        for event in events:
            event_type = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
            event_tool = getattr(event, "tool", None) or (event.get("tool") if isinstance(event, dict) else None)
            event_success = getattr(event, "success", None) or (event.get("success") if isinstance(event, dict) else None)

            if not event_type or not event_tool:
                continue

            task = self._task_type_for_tool(event_tool)

            if event_type == "tool_call":
                tool_calls[task] = tool_calls.get(task, 0) + 1
                unique_tools_by_type[task].add(event_tool)
                total_turns += 1
            elif event_type == "tool_result":
                if task in tool_calls and tool_calls[task] > 0:
                    if event_success:
                        tool_success[task] = tool_success.get(task, 0) + 1
            elif event_type == "reasoning":
                reflection_count[task] = reflection_count.get(task, 0) + 1

        # Guardrail hits from MSR log
        for entry in msr_log:
            task = "execution"  # Default; MSR doesn't always carry tool name
            # We just attribute guardrail hits to execution for now
            guardrail_hits[task] = guardrail_hits.get(task, 0) + 1

        # Build per-task-type metrics
        accuracy = {}
        guardrail_rate = {}
        reflection_ratio = {}
        tool_diversity = {}
        latency = {}

        n_tools_total = len(self.config.tool_to_task)

        for task in tt:
            calls = tool_calls.get(task, 0)
            acc = tool_success.get(task, 0) / max(calls, 1)
            accuracy[task] = float(np.clip(acc, 0.0, 1.0))

            gr = guardrail_hits.get(task, 0) / max(calls, 1)
            guardrail_rate[task] = float(np.clip(gr, 0.0, 1.0))

            ref = reflection_count.get(task, 0) / max(calls, 1)
            reflection_ratio[task] = float(np.clip(ref, 0.0, 1.0))

            n_unique = len(unique_tools_by_type.get(task, set()))
            tool_diversity[task] = float(np.clip(n_unique / max(n_tools_total, 1), 0.0, 1.0))

            # Simulated latency — proportional to reflection + reconfig count
            reconfigs = len(reconfig_log)
            base_latency = {"retrieval": 2.0, "synthesis": 8.0, "execution": 5.0,
                            "verification": 3.0, "planning": 4.0, "debugging": 10.0}
            lat = base_latency.get(task, 5.0) + reconfigs * 0.5 + (1.0 - acc) * 3.0
            latency[task] = float(np.clip(lat, 0.5, 60.0))

        return AgentBehaviorFingerprint(
            architecture_name=architecture_name,
            run_id=run_id,
            accuracy=accuracy,
            guardrail_hit_rate=guardrail_rate,
            reflection_ratio=reflection_ratio,
            tool_diversity=tool_diversity,
            latency_seconds=latency,
            total_turns=total_turns,
            total_tasks=len(tt),
        )
