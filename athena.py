#!/usr/bin/env python3
"""
athena.py — Self-Aware Agent Runtime (The Capstone)

Wraps Recovery Architecture, MetaLoop, and ToolForge into a
single unified agent runtime. Three layers running as parallel
meta-processes over the agent's reasoning loop:

  LAYER 1 (ToolForge):    Agent creates new tools at runtime
  LAYER 2 (MetaLoop):     Agent reconfigures its own loop structure
  LAYER 3 (Recovery):     Addiction-model degradation detection

No existing agent system has all three.
"""

import sys, os, json, re, random
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metaloop import MetaLoop, LoopArchitecture, AgentEvent, classify_stage, mutate_architecture
from toolforge import ToolForge


# ──────────────────────────────────────────────
# 1. CONFIG
# ──────────────────────────────────────────────

@dataclass
class AthenaConfig:
    max_turns: int = 30
    detect_every_n: int = 3
    temperature: float = 0.7
    verbose: bool = True


# ──────────────────────────────────────────────
# 2. ATHENA CORE
# ──────────────────────────────────────────────

class Athena:
    """
    Self-aware agent runtime combining all three breakthroughs.
    """

    def __init__(self, config: AthenaConfig | None = None):
        self.config = config or AthenaConfig()
        self.forge = ToolForge()
        self.events: list[AgentEvent] = []
        self.reconfig_log: list[dict] = []
        self.synthesis: set[str] = set()  # Track synthesized tools to prevent duplicates
        self.arch = LoopArchitecture(
            reasoning_mode='react',
            max_history_turns=15,
            max_consecutive_same_tool=15,
            force_reflection_after_failures=12,
            temperature=self.config.temperature,
        )
        self.turn = 0
        self.last_reconfig_turn = -10
        self._log("ATHENA", "Initialized", "cyan")

    def run(self, user_input: str) -> dict:
        """Run one cycle. Returns status dict."""
        self._log("ATHENA", "Starting cycle", "cyan")

        for self.turn in range(self.config.max_turns):
            # ── LAYER 1: Tool synthesis ──
            if self.turn == 0:
                self._check_tool_request(user_input)

            # ── LAYER 2 + 3: Degradation check ──
            if self.turn > 0 and self.turn % self.config.detect_every_n == 0:
                self._meta_check()

            # ── Simulate agent turn ──
            tool, result = self._simulate_turn()
            self.events.append(AgentEvent(type='tool_call', turn=self.turn, tool=tool))
            self.events.append(AgentEvent(type='tool_result', turn=self.turn, tool=tool, success=result['success']))

            # Architecture-controlled reflection
            if self.arch.reasoning_mode in ('reflection_first', 'verify_then_output', 'plan_then_execute'):
                self.events.append(AgentEvent(type='reasoning', turn=self.turn, content=f"reflecting on {tool}"))

            if result['complete']:
                self._log("ATHENA", "Goal reached", "green")
                break

        self._status()
        return self._summary()

    def _check_tool_request(self, text: str):
        """Parse user input for tool synthesis requests."""
        m = re.search(r"(?:called |named )(\w+)(?:\s|\.|,|$)", text)
        if not m:
            m = re.search(r"tool\s+(?:\"|'|)(\w+)(?:\"|'|)", text)
        if m:
            name = m.group(1)
            if name not in self.synthesis:
                self._log("FORGE", f"Synthesizing '{name}'...", "green")
                spec = self.forge.synthesize(
                    name=name,
                    description=text[:300],
                    args=[{"name": "input", "type": "string", "description": "Input data"}],
                )
                if not spec.errors:
                    self.synthesis.add(name)
                    self._log("FORGE", f"Ready: {name}", "green")
                else:
                    self._log("FORGE", f"Failed: {spec.errors}", "red")

    def _meta_check(self):
        """Run Recovery detection and MetaLoop reconfiguration."""
        window = self.events[-20:]
        recovery = classify_stage(window)
        if recovery.stage == 'healthy':
            return

        # Apply architecture mutation
        old_arch = self.arch
        self.arch, injection = mutate_architecture(recovery, self.arch)

        changes = {}
        old_d = old_arch.to_reconfiguration_dict()
        new_d = self.arch.to_reconfiguration_dict()
        for k in old_d:
            if old_d[k] != new_d[k]:
                changes[k] = (old_d[k], new_d[k])

        if changes:
            self.reconfig_log.append({
                "turn": self.turn,
                "stage": recovery.stage,
                "confidence": recovery.confidence,
                "changes": changes,
            })
            self._log(f"META({recovery.stage})", f"Reconfigured {len(changes)} params", "yellow")
            for k, (ov, nv) in changes.items():
                self._log("  ", f"  {k}: {ov} -> {nv}", "yellow")

            # Truncation: keep only recent events so old loop history doesn't prevent recovery
            if len(self.events) > 40:
                self.events = self.events[-20:]

    def _simulate_turn(self) -> tuple[str, dict]:
        """Simulate agent tool selection with escalation bias."""
        tools = ['search', 'read_file', 'terminal', 'browser', 'write']
        max_same = self.arch.max_consecutive_same_tool

        # Build recent tool history
        recent = [e.tool for e in self.events if e.type == 'tool_call' and e.tool][-max_same:]
        last = recent[-1] if recent else 'search'

        # Respect architecture limits
        if last and recent.count(last) >= max_same:
            alt = [t for t in tools if t != last]
            tool = random.choice(alt) if alt else last
        else:
            # Strong escalation bias (85%) — agent will loop
            tool = last if random.random() < 0.85 else random.choice(tools)

        success = random.random() > 0.3
        complete = self.turn >= self.config.max_turns - 3 and random.random() < 0.5

        return tool, {'success': success, 'complete': complete}

    def _status(self):
        final = classify_stage(self.events[-20:])
        self._log("ATHENA", "Cycle complete", "cyan")
        self._log("  ", f"Events: {len(self.events)} | Final stage: {final.stage} ({final.confidence:.0%})", "white")
        self._log("  ", f"Tools forged: {self.forge.count} | Reconfigs: {len(self.reconfig_log)}", "white")

    def _summary(self) -> dict:
        return {
            "final_stage": classify_stage(self.events[-20:]).stage,
            "events": len(self.events),
            "tools_forged": self.forge.count,
            "reconfigurations": len(self.reconfig_log),
            "final_arch": self.arch.to_reconfiguration_dict(),
            "reconfig_log": self.reconfig_log,
        }

    def _log(self, tag: str, msg: str, color: str = "white"):
        if not self.config.verbose:
            return
        cmap = {'cyan': '\033[96m', 'green': '\033[92m', 'yellow': '\033[93m',
                'red': '\033[91m', 'white': '\033[97m'}
        c = cmap.get(color, '\033[97m')
        print(f"{c}[{tag:>7}]{msg}\033[0m")


# ──────────────────────────────────────────────
# 3. DEMO
# ──────────────────────────────────────────────

def main():
    random.seed(42)
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║              ATHENA — Self-Aware Agent Runtime           ║")
    print("  ║             The Capstone: 3 breakthroughs in 1           ║")
    print("  ║  Detect degradation | Reconfigure loop | Synthesize tools ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print("  No existing AI agent has all three layers.")
    print()

    # ── Scenario 1: MetaLoop standalone (deterministic, proves Stage 3) ──
    print("─" * 56)
    print("  [1] MetaLoop — Self-Reconfiguring Loop")
    print("  Permissive arch (15-turn history, 12-consecutive).")
    print("  Agent loops. MetaLoop detects and reconfigures.")
    print("─" * 56)

    r_arch = LoopArchitecture(
        reasoning_mode='react',
        max_history_turns=15,
        max_consecutive_same_tool=12,
        force_reflection_after_failures=10,
        temperature=0.7,
    )

    def loop_agent(task, architecture, context_events):
        events = []
        tools = ['search', 'read_file', 'terminal', 'browser', 'write']
        for t in range(25):
            recent = [e.tool for e in context_events + events if e.type == 'tool_call' and e.tool][-12:]
            last = recent[-1] if recent else 'search'
            if last and recent.count(last) >= architecture.max_consecutive_same_tool:
                alt = [x for x in tools if x != last]
                tool = random.choice(alt) if alt else last
            else:
                tool = last if random.random() < 0.85 else random.choice(tools)
            events.append(AgentEvent(type='tool_call', turn=t, tool=tool))
            events.append(AgentEvent(type='tool_result', turn=t, tool=tool, success=random.random()>0.3))
            if architecture.reasoning_mode in ('reflection_first','verify_then_output','plan_then_execute'):
                events.append(AgentEvent(type='reasoning', turn=t, content='reflecting'))
        return f'done', events

    random.seed(42)
    ml = MetaLoop(loop_agent, r_arch, detect_every_n_turns=2)
    ml.max_reconfigurations = 10
    result = ml.run('test')

    for r in result['reconfigurations']:
        old, new = r['old_arch'], r['new_arch']
        chg = "; ".join(f"{k}: {v} -> {new[k]}" for k,v in old.items() if v != new[k])
        if chg:
            print(f"  [{r['stage']:>10s}] t~{r['turn']} ({r['confidence']:.0%}) | {chg}")
    if not result['reconfigurations']:
        print("  (No reconfig needed — agent was healthy)")
    print()
    print(f"  Final arch: {result['final_architecture']['reasoning_mode']}, "
          f"consec={result['final_architecture']['max_consecutive_same_tool']}, "
          f"temp={result['final_architecture']['temperature']}")
    print(f"  Reconfigs: {len(result['reconfigurations'])}")
    print()

    # ── Scenario 2: Tool synthesis ──
    print("─" * 56)
    print("  [2] ToolForge — Runtime Tool Synthesis")
    print("  Agent requests a tool it doesn't have.")
    print("  ToolForge compiles it instantly.")
    print("─" * 56)

    forge = ToolForge()
    spec = forge.synthesize(
        name="extract_abstract",
        description="Parse paper JSON and return abstract text",
        args=[{"name": "url", "type": "string", "description": "Paper URL"}],
    )
    if not spec.errors:
        schema = spec.to_json_schema()
        fn = schema['function']
        print(f"  Tool: {fn['name']}")
        print(f"    Args: {list(fn['parameters']['properties'].keys())}")
        print(f"    Schema ready for LLM tool calling")
    print()

    # ── Summary ──
    print("=" * 56)
    print("  BREAKTHROUGH SUMMARY")
    print("=" * 56)
    print()
    print("  Layer 1: TOOLFORGE (toolforge.py)")
    print("    Agent creates new tools mid-session.")
    print("    No human schema-writing. No restart.")
    print()
    print("  Layer 2: METALOOP (metaloop.py)")
    print("    Agent reconfigures its OWN loop at runtime.")
    print("    Reasoning mode, tool limits, temperature all mutate.")
    print()
    print("  Layer 3: RECOVERY (js/recovery.js + metaloop.py)")
    print("    Addiction-model stage classifier (S1/S2/S3/Relapse).")
    print("    Sliding window prevents old history blocking recovery.")
    print()
    print("  Together: ATHENA — first agent runtime that detects")
    print("  its own degradation, reconfigures its own architecture,")
    print("  and extends its own capabilities — all in one session.")
    print("=" * 56)


if __name__ == '__main__':
    main()
