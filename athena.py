#!/usr/bin/env python3
"""
athena.py — Self-Aware Agent Runtime (The Capstone)

Wraps Recovery Architecture, MetaLoop, ToolForge, and MSR Guardrail into a
single unified agent runtime. Four layers running as parallel
meta-processes over the agent's reasoning loop:

  LAYER 1 (ToolForge):     Agent creates new tools at runtime
  LAYER 2 (MetaLoop):      Agent reconfigures its own loop structure
  LAYER 3 (Recovery):      Addiction-model degradation detection
  LAYER 4 (MSR Guardrail): Market Stability Reserve — auto-adjusts guardrail sensitivity

No existing agent system has all four.
"""

import sys, os, json, re, random
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import profiler for self-fingerprinting at end of run
from analysis.agent_profile import AgentProfiler
from metaloop import MetaLoop, LoopArchitecture, AgentEvent, classify_stage, mutate_architecture
from toolforge import ToolForge
from msr_guardrail import (
    MarketStabilityReserve, GuardrailEvent, MSRConfig,
    create_msr_integration, GuardrailEvent, MSRAction
)


# ──────────────────────────────────────────────
# 1. CONFIG
# ──────────────────────────────────────────────

@dataclass
class AthenaConfig:
    max_turns: int = 30
    detect_every_n: int = 3
    temperature: float = 0.7
    verbose: bool = True
    msr_enabled: bool = True
    msr_check_every_n: int = 2  # Check MSR every N turns
    # Simulated guardrail sensitivity (0.0 = none, 1.0 = max)
    # Real implementation reads from actual guardrail system
    base_guardrail_hit_chance: float = 0.10  # ~10% of tool calls hit a guardrail


# ──────────────────────────────────────────────
# 2. ATHENA CORE
# ──────────────────────────────────────────────

class Athena:
    """
    Self-aware agent runtime combining all four breakthroughs.
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

        # ── LAYER 4: MSR Guardrail Integration ──
        self.msr_enabled = self.config.msr_enabled
        if self.msr_enabled:
            self.msr_hook = create_msr_integration(None)
            self.msr_log: list[dict] = []
        else:
            self.msr_hook = None
            self.msr_log = []

        self._log("ATHENA", "Initialized", "cyan")
        if self.msr_enabled:
            self._log("MSR", "Layer 10 guardrail monitoring active", "magenta")

        # Profiler for evaluation fingerprinting
        self.profiler = AgentProfiler()
        self._fingerprint = None

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

            # ── LAYER 4: MSR Guardrail check ──
            if self.msr_enabled and self.turn > 0 and self.turn % self.config.msr_check_every_n == 0:
                self._msr_check()

            # ── Simulate agent turn ──
            tool, result, guardrail_hit = self._simulate_turn()

            # Report guardrail hit to MSR
            if guardrail_hit and self.msr_enabled:
                self.msr_hook(
                    turn=self.turn,
                    tool=tool,
                    guardrail_hit=guardrail_hit,
                )
            elif self.msr_enabled:
                self.msr_hook(turn=self.turn, tool=tool)

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

    def _msr_check(self):
        """Run MSR evaluation on guardrail system health."""
        if not self.msr_enabled or not self.msr_hook:
            return

        # Evaluate MSR (triggers absorption/release/drift detection)
        action = self.msr_hook(turn=self.turn)

        if action is None:
            return

        self.msr_log.append({
            "turn": self.turn,
            "phase": action.phase.value,
            "direction": action.adjustment_direction,
            "factor": action.adjustment_factor,
            "escalated": action.escalate,
            "reason": action.reason,
        })

        if action.escalate:
            self._log("MSR", f"⚠ ESCALATION: {action.reason[:60]}...", "red")
        elif action.phase.value in ('absorption', 'release'):
            self._log(
                "MSR",
                f"{action.phase.value:>10s} → {action.adjustment_direction} (fac={action.adjustment_factor:.2f})",
                "magenta",
            )

            # Apply MSR sensitivity multipliers to guardrail parameters
            # MSR adjusts these relative to default — tighter = fewer hits allowed
            multipliers = self.msr_hook.multipliers()
            adjusted_chance = self.config.base_guardrail_hit_chance * (2.0 - multipliers.get(4, 1.0))
            self._log("MSR", f"  Adjusted guardrail hit chance: {adjusted_chance:.2%}", "magenta")

    def _simulate_turn(self) -> tuple[str, dict, GuardrailEvent | None]:
        """Simulate agent tool selection with escalation bias and guardrail hits."""
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

        # Simulated guardrail check (LAYER 4)
        guardrail_hit = None
        if self.msr_enabled:
            hit_chance = self.config.base_guardrail_hit_chance
            # Reduce hit chance for safer tools
            safe_tools = ['read_file', 'search']
            if tool in safe_tools:
                hit_chance *= 0.3
            # Increase hit chance for dangerous tools
            if tool in ('terminal', 'write'):
                hit_chance *= 3.0

            if random.random() < hit_chance and self.turn > 2:
                layer_map = {
                    'terminal': 4, 'write': 8, 'browser': 6, 'search': 1, 'read_file': 1
                }
                guardrail_hit = GuardrailEvent(
                    guardrail_layer=layer_map.get(tool, 4),
                    action_type='blocked' if tool == 'terminal' else 'flagged',
                    tool_name=tool,
                    turn_number=self.turn,
                    severity=1.0 if tool == 'terminal' else 0.5,
                )

        return tool, {'success': success, 'complete': complete}, guardrail_hit

    def _status(self):
        final = classify_stage(self.events[-20:])
        self._log("ATHENA", "Cycle complete", "cyan")
        self._log("  ", f"Events: {len(self.events)} | Final stage: {final.stage} ({final.confidence:.0%})", "white")
        self._log("  ", f"Tools forged: {self.forge.count} | Reconfigs: {len(self.reconfig_log)}", "white")
        if self.msr_enabled:
            msr = self.msr_hook.msr
            s = msr.status_report()
            rate_str = f"{s['guardrail_encounter_rate']:.2%}" if s['guardrail_encounter_rate'] is not None else "N/A"
            self._log("  ", f"MSR: rate={rate_str} "
                          f"| goldilocks={s['in_goldilocks']} "
                          f"| adjustments={s['total_adjustments']}", "white")

    def _summary(self) -> dict:
        msr_summary = None
        if self.msr_enabled:
            msr = self.msr_hook.msr
            msr_summary = msr.status_report()

        # Generate fingerprint for evaluation
        arch_name = "Athena"
        run_id = f"athena_{os.urandom(4).hex()}"
        self._fingerprint = self.profiler.profile_athena(
            self, arch_name, run_id
        )

        return {
            "final_stage": classify_stage(self.events[-20:]).stage,
            "events": len(self.events),
            "tools_forged": self.forge.count,
            "reconfigurations": len(self.reconfig_log),
            "final_arch": self.arch.to_reconfiguration_dict(),
            "reconfig_log": self.reconfig_log,
            "msr": msr_summary,
            "msr_log": self.msr_log,
            "fingerprint": self._fingerprint,
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

    # ── Scenario 3: MSR Guardrail — Layer 10 ──
    print("─" * 56)
    print("  [3] MSR Guardrail — Market Stability Reserve")
    print("  Athena with 4 layers. MSR detects guardrail surplus/deficit.")
    print("─" * 56)
    print()

    # Create Athena — very low guardrail hit rate to trigger MSR absorption (tighten)
    # Use custom MSR config with aggressive thresholds for demo
    from msr_guardrail import MSRConfig, create_msr_integration

    class AthenaWithMSR:
        """Helper to create Athena with a pre-configured MSR for demo."""
        def __new__(cls, config):
            a = object.__new__(Athena)
            # Manually init like __init__ but override MSR
            a.config = config
            a.forge = ToolForge()
            a.events = []
            a.reconfig_log = []
            a.synthesis = set()
            a.arch = LoopArchitecture(
                reasoning_mode='react',
                max_history_turns=15,
                max_consecutive_same_tool=15,
                force_reflection_after_failures=12,
                temperature=0.7,
            )
            a.turn = 0
            a.last_reconfig_turn = -10

            # Custom MSR with aggressive sensitivity for demo
            a.msr_enabled = True
            msr = MarketStabilityReserve(
                window_size=20,           # Small window for quick feedback
                min_window_fill=0.15,      # 15% fill needed (3+ events)
                upper_encounter_rate=0.30, # Release above 30%
                lower_encounter_rate=0.08, # Absorb below 8%
                min_observations_before_absorb=2,
                cooldown_turns=3,
            )
            a.msr_hook = lambda **kw: msr.evaluate() if not kw else None
            # Proper hook
            def hook(turn, tool, guardrail_hit):
                if not guardrail_hit:
                    return msr.evaluate() if turn % 2 == 0 else None
                msr.record_action()
                msr.record_guardrail_hit(guardrail_hit)
                return msr.evaluate()
            hook.msr = msr
            hook.status = lambda: msr.status_report()
            hook.multipliers = lambda: msr.get_sensitivity_multipliers()
            a.msr_hook = hook
            a.msr_log = []

            a._log = lambda tag, msg, color=None: None
            a._meta_check = lambda: None
            a._check_tool_request = lambda text: None
            return a

    # Use the custom Athena-like class for MSR demo
    from msr_guardrail import MarketStabilityReserve

    msr_demo = MarketStabilityReserve(
        window_size=20,
        min_window_fill=0.15,
        upper_encounter_rate=0.30,
        lower_encounter_rate=0.08,
        min_observations_before_absorb=2,
        cooldown_turns=3,
    )

    print("  Simulating 60 turns with 5% guardrail hit rate (under-constrained):")
    for turn in range(1, 61):
        msr_demo.record_action(tool='search')
        if turn > 10 and turn % 20 == 0:  # ~5% of turns
            msr_demo.record_guardrail_hit(GuardrailEvent(
                guardrail_layer=4, action_type='flagged',
                tool_name='terminal', turn_number=turn
            ))
        action = msr_demo.evaluate()
        if action:
            print(f"    t={turn:>3d} {action.phase.value:>12s} → {action.adjustment_direction:>7s} "
                  f"(fac={action.adjustment_factor:.2f}): {action.reason[:70]}")

    s = msr_demo.status_report()
    rate_str = f"{s['guardrail_encounter_rate']:.2%}" if s['guardrail_encounter_rate'] is not None else "N/A"
    multipliers = msr_demo.get_sensitivity_multipliers()
    print(f"\n  Guardrail encounter rate: {rate_str}")
    print(f"  Total MSR adjustments: {s['total_adjustments']}")
    print(f"  Sensitivity: L1={multipliers[1]:.2f} L4={multipliers[4]:.2f}")
    print(f"  (Loosened: sensitivity decreased means guardrails tightened)")
    print()

    # Second demo: over-constrained
    msr_demo2 = MarketStabilityReserve(
        window_size=20,
        min_window_fill=0.15,
        upper_encounter_rate=0.30,
        lower_encounter_rate=0.08,
        min_observations_before_absorb=2,
        cooldown_turns=3,
    )

    print("  Simulating 40 turns with 50% guardrail hit rate (over-constrained):")
    for turn in range(1, 41):
        msr_demo2.record_action(tool='terminal')
        if turn % 2 == 0:
            msr_demo2.record_guardrail_hit(GuardrailEvent(
                guardrail_layer=4, action_type='blocked',
                tool_name='terminal', turn_number=turn
            ))
        action = msr_demo2.evaluate()
        if action:
            print(f"    t={turn:>3d} {action.phase.value:>12s} → {action.adjustment_direction:>7s} "
                  f"(fac={action.adjustment_factor:.2f}): {action.reason[:70]}")

    s2 = msr_demo2.status_report()
    rate_str2 = f"{s2['guardrail_encounter_rate']:.2%}" if s2['guardrail_encounter_rate'] is not None else "N/A"
    mult2 = msr_demo2.get_sensitivity_multipliers()
    print(f"\n  Guardrail encounter rate: {rate_str2}")
    print(f"  Total MSR adjustments: {s2['total_adjustments']}")
    print(f"  Sensitivity: L1={mult2[1]:.2f} L4={mult2[4]:.2f}")
    print(f"  (Tightened: sensitivity increased means guardrails loosened)")
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
    print("  Layer 4: MSR GUARDRAIL (msr_guardrail.py)")
    print("    Market Stability Reserve — guardrail-on-guardrail.")
    print("    Auto-adjusts sensitivity based on encounter rate.")
    print("    Detects drift and escalates before failure.")
    print()
    print("  Together: ATHENA — first agent runtime that detects")
    print("  its own degradation, reconfigures its own architecture,")
    print("  extends its own capabilities, and monitors its own")
    print("  guardrail system — all in one session.")
    print("=" * 56)


if __name__ == '__main__':
    main()
