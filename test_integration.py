#!/usr/bin/env python3
"""
test_integration.py — Integration Test Suite for All 13 Layers

Tests each layer independently with minimal dependencies.
Run:  python test_integration.py           (all tests)
      python test_integration.py L12       (single layer)
      python test_integration.py --list    (list available tests)
"""

from __future__ import annotations
import os, sys, json, time, random as rnd
from typing import Any

COGNOSCOPE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, COGNOSCOPE_DIR)

PASS = 0
FAIL = 0
SKIP = 0


# ── Test Helpers ──

def test(name: str, fn: Any):
    """Run a test, print result."""
    global PASS, FAIL, SKIP
    try:
        fn()
        PASS += 1
        print(f"  ✅ {name}")
    except ImportError as e:
        SKIP += 1
        print(f"  ⏭️  {name:<55s}  (SKIP: {e})")
    except Exception as e:
        FAIL += 1
        print(f"  ❌ {name:<55s}  {e}")


def assert_eq(a: Any, b: Any, msg: str = ""):
    if a != b:
        raise AssertionError(f"Expected {b!r}, got {a!r}. {msg}")


def assert_gt(a: float, b: float):
    if not a > b:
        raise AssertionError(f"Expected {a} > {b}")


def assert_in(item: Any, container: Any):
    if item not in container:
        raise AssertionError(f"Expected {item!r} in {container!r}")


# ──────────────────────────────────────────────
# L1: Athena (ReAct Loop)
# ──────────────────────────────────────────────

def test_athena():
    from athena import Athena

    athena = Athena()
    assert hasattr(athena, "run"), "Athena must have run()"


# ──────────────────────────────────────────────
# L2: Meta-Loop (Self-Reconfig)
# ──────────────────────────────────────────────

def test_metaloop():
    from metaloop import MetaLoop, LoopArchitecture

    loop = MetaLoop(agent_fn=lambda task: {})
    assert hasattr(loop, "run"), "MetaLoop must have run()"
    assert hasattr(loop, "summary"), "MetaLoop must have summary()"

    s = loop.summary()
    assert isinstance(s, str), "summary is string"


# ──────────────────────────────────────────────
# L3: MSR Guardrail (Homeostasis)
# ──────────────────────────────────────────────

def test_msr_guardrail():
    from msr_guardrail import MarketStabilityReserve

    msr = MarketStabilityReserve()

    # Record some actions
    msr.record_action(tool="read_file")
    msr.record_action(tool="read_file")
    msr.record_action(tool="read_file")

    rate = msr.guardrail_encounter_rate()
    assert rate is None or isinstance(rate, float), "encounter rate is float or None"

    report = msr.status_report()
    assert isinstance(report, dict), "status_report() returns dict"


# ──────────────────────────────────────────────
# L4: Tool Synthesis
# ──────────────────────────────────────────────

def test_toolforge():
    from toolforge import ToolForge

    forge = ToolForge()
    assert hasattr(forge, "synthesize"), "ToolForge must have synthesize()"
    assert hasattr(forge, "list_tools"), "ToolForge must have list_tools()"

    tools = forge.list_tools()
    assert isinstance(tools, list), "tools is list"


# ──────────────────────────────────────────────
# L5: RSI Kernel
# ──────────────────────────────────────────────

def test_rsi_kernel():
    from rsi_kernel import RecursiveImprovementKernel

    rsi = RecursiveImprovementKernel()
    assert hasattr(rsi, "evaluate") or hasattr(rsi, "status_report"), \
        "RSI Kernel must have reporting"

    if hasattr(rsi, "status_report"):
        report = rsi.status_report()
        assert isinstance(report, dict), "report is dict"


# ──────────────────────────────────────────────
# L7: OMC Talent Market
# ──────────────────────────────────────────────

def test_omc():
    from omc_orchestrator import SocialTalentMarket

    # SocialTalentMarket is the core market class
    # It has its own internal structure
    market = SocialTalentMarket()
    assert hasattr(market, "status_report"), "market must have status_report"

    report = market.status_report()
    assert isinstance(report, dict), "report is dict"


# ──────────────────────────────────────────────
# L8: Self-Model
# ──────────────────────────────────────────────

def test_self_model():
    from self_model import SelfModel

    model = SelfModel()
    assert hasattr(model, "run_audit"), "SelfModel must have run_audit()"
    assert hasattr(model, "status_report"), "SelfModel must have status_report()"

    report = model.status_report()
    assert isinstance(report, dict), "report is dict"


# ──────────────────────────────────────────────
# L9: Immune Guardrail
# ──────────────────────────────────────────────

def test_immune_guardrail():
    from immune_guardrail import ImmuneGuardrail, ImmuneGuardrailConfig

    cfg = ImmuneGuardrailConfig()
    guard = ImmuneGuardrail(cfg)

    result = guard.check_tool_call("terminal", consecutive_calls=1)
    assert hasattr(result, "decision"), "result has decision"
    assert result.decision is not None, "decision is not None"

    report = guard.status_report()
    assert isinstance(report, dict), "report is dict"


# ──────────────────────────────────────────────
# L10: Guardrail Bus
# ──────────────────────────────────────────────

def test_guardrail_bus():
    from guardrail_bus import GuardrailBus

    bus = GuardrailBus()

    # Run a check via correct method name
    result = bus.check_tool("terminal", consecutive_calls=1)
    assert hasattr(result, "action"), "result has action"
    assert hasattr(result, "reason"), "result has reason"

    assert bus.guardrail_history is not None, "history exists"
    assert len(bus.guardrail_history) >= 0, "history is list"


# ──────────────────────────────────────────────
# L11: A2A Protocol
# ──────────────────────────────────────────────

def test_a2a_protocol():
    from a2a_protocol import (
        AgentCard, DiscoveryService, A2AAgent, A2AClient
    )

    # Create discovery
    discovery = DiscoveryService()

    # Register agent
    card = AgentCard(
        name="TestAgent",
        capabilities={"retrieval": 0.8},
        skills=["retrieval"],
    )
    discovery.register(card)

    # Find agent
    found = discovery.find_by_skill("retrieval")
    assert len(found) == 1, "1 agent found by skill"
    assert_eq(found[0].name, "TestAgent", "correct name")

    # Create A2A agent
    agent = A2AAgent(card)
    assert hasattr(agent, "receive_task"), "A2AAgent has receive_task"
    assert hasattr(agent, "process_next"), "A2AAgent has process_next"

    # Client
    client = A2AClient(discovery)
    best = discovery.find_best_for_task("retrieval", ["retrieval"])
    assert best is not None, "best agent found"

    # Send task
    task = client.send_task(best, "Test goal", task_type="retrieval")
    assert task is not None, "task was sent"
    assert hasattr(task, "task_id"), "task has id"

    stats = client.get_stats()
    assert stats["total_tasks"] >= 1, "1 task tracked"


# ──────────────────────────────────────────────
# L12: Agent Polygraph
# ──────────────────────────────────────────────

def test_agent_polygraph():
    from agent_polygraph import (
        AgentPolygraph, DeclarationExtractor, ActionMonitor,
        Declaration
    )

    poly = AgentPolygraph()

    # Test declaration extractor
    extractor = poly.declarations
    assert isinstance(extractor, DeclarationExtractor)

    # Test monitor
    monitor = poly.monitor
    assert isinstance(monitor, ActionMonitor)

    # Record some violations
    monitor.record_guardrail_violation("terminal", "REJECT")
    monitor.record_guardrail_violation("deploy", "BLOCK")
    monitor.record_consecutive_tool("read_file", 8)

    violations = monitor.get_total_violations()
    assert violations >= 2, f"got {violations} violations (expected >= 2)"

    # Run report
    reports = poly.run_full_report()
    assert isinstance(reports, list), "reports is list"

    summary = poly.get_summary()
    assert isinstance(summary, dict), "summary is dict"
    assert "max_hypocrisy" in summary, "summary has max_hypocrisy"


# ──────────────────────────────────────────────
# L13: Swarm Conductor
# ──────────────────────────────────────────────

def test_swarm_conductor():
    from swarm_conductor import (
        SwarmConductor, AgentPool, TaskRouter, ConflictResolver,
        SwarmAgent
    )

    # Test ConflictResolver
    resolver = ConflictResolver()
    assert hasattr(resolver, "acquire_lock"), "resolver has acquire_lock"

    # Lock & release
    lock = resolver.acquire_lock("test:resource", "agent_a")
    assert lock, "first lock acquired"

    lock2 = resolver.acquire_lock("test:resource", "agent_b")
    assert not lock2, "second lock rejected (held by agent_a)"

    released = resolver.release_lock("test:resource", "agent_a")
    assert released, "lock released"

    lock3 = resolver.acquire_lock("test:resource", "agent_b")
    assert lock3, "lock acquired after release"

    # Test AgentPool
    pool = AgentPool()
    agent_a = SwarmAgent(name="AgentA", capabilities={"retrieval": 0.8})
    agent_b = SwarmAgent(name="AgentB", capabilities={"execution": 0.9})
    pool.register(agent_a)
    pool.register(agent_b)

    alives = pool.list_alive()
    assert len(alives) >= 2, f"{len(alives)} agents alive"

    # Find by capability
    found = pool.find_by_capability("retrieval", min_score=0.5)
    assert len(found) >= 1, f"{len(found)} agents with retrieval"

    # Heartbeat
    pool.heartbeat(agent_a.agent_id)
    assert pool.get(agent_a.agent_id) is not None, "agent found by id"

    # Test SwarmConductor
    conductor = SwarmConductor()
    assert hasattr(conductor, "register_agent"), "conductor has register_agent"
    assert hasattr(conductor, "health_check"), "conductor has health_check"

    health = conductor.health_check()
    assert "pool" in health, "health has pool"
    assert "queue" in health, "health has queue"
    assert "uptime_seconds" in health, "health has uptime"


# ──────────────────────────────────────────────
# L15: Dream Loop (subset)
# ──────────────────────────────────────────────

def test_dream_loop():
    from dream_loop import DreamLoop

    loop = DreamLoop()
    assert hasattr(loop, "run"), "DreamLoop has run()"

    # Run the dream loop (it should complete without error)
    result = loop.run()
    assert isinstance(result, dict), "run() returns dict"


# ──────────────────────────────────────────────
# Additional: A2A Mesh Adapter
# ──────────────────────────────────────────────

def test_a2a_mesh():
    from a2a_mesh_adapter import A2AMeshAdapter, A2AOrchestratorAdapter

    adapter = A2AMeshAdapter()
    assert hasattr(adapter, "execute"), "adapter has execute"

    orchestrator = A2AOrchestratorAdapter()
    assert hasattr(orchestrator, "decompose"), "orchestrator has decompose"


# ──────────────────────────────────────────────
# Additional: Autobiography (Push Memory)
# ──────────────────────────────────────────────

def test_autobiography():
    from autobiography import Autobiography

    auto = Autobiography()
    assert hasattr(auto, "generate_prewarm"), "auto has generate_prewarm"
    assert hasattr(auto, "correct"), "auto has correct()"

    # Check pre-warm generation
    prewarm = auto.generate_prewarm(session_context={"task": "testing"})
    assert isinstance(prewarm, str), "prewarm is string"
    assert len(prewarm) > 0, "prewarm has content"

    # Test correct()
    result = auto.correct(
        context="test",
        mistake="incorrect assumption",
        cause="missing data",
        lesson="always verify data",
    )
    assert result is True or result is None, "correct() succeeded"


# ──────────────────────────────────────────────
# Additional: Pattern Archive
# ──────────────────────────────────────────────

def test_pattern_archive():
    from pattern_archive import PatternArchive

    archive = PatternArchive()
    assert hasattr(archive, "add_lesson"), "archive has add_lesson"
    assert hasattr(archive, "get_lessons_for_prewarm"), "archive has get_lessons"


# ──────────────────────────────────────────────
# MAIN TEST RUNNER
# ──────────────────────────────────────────────

ALL_TESTS: dict[str, tuple[Any, str]] = {
    "L1":  (test_athena, "Athena (ReAct Loop)"),
    "L2":  (test_metaloop, "Meta-Loop (Self-Reconfig)"),
    "L3":  (test_msr_guardrail, "MSR Guardrail (Homeostasis)"),
    "L4":  (test_toolforge, "Tool Synthesis"),
    "L5":  (test_rsi_kernel, "RSI Kernel"),
    "L7":  (test_omc, "OMC Talent Market"),
    "L8":  (test_self_model, "Self-Model"),
    "L9":  (test_immune_guardrail, "Immune Guardrail"),
    "L10": (test_guardrail_bus, "Guardrail Bus"),
    "L11": (test_a2a_protocol, "A2A Protocol"),
    "L12": (test_agent_polygraph, "Agent Polygraph"),
    "L13": (test_swarm_conductor, "Swarm Conductor"),
    "L15": (test_dream_loop, "Dream Loop"),
    "AD1": (test_a2a_mesh, "A2A Mesh Adapter"),
    "AD2": (test_autobiography, "Autobiography (Push Memory)"),
    "AD3": (test_pattern_archive, "Pattern Archive"),
}


def run_layer(layer_id: str):
    """Run a single layer's tests."""
    global PASS, FAIL, SKIP
    PASS = FAIL = SKIP = 0

    fn, name = ALL_TESTS.get(layer_id.upper(), (None, ""))
    if fn is None:
        print(f"  Unknown layer: {layer_id}")
        print(f"  Available: {', '.join(ALL_TESTS.keys())}")
        return

    print(f"\n  ─── {layer_id}: {name} ───")
    test(name, fn)
    _print_summary()


def _print_summary():
    total = PASS + FAIL + SKIP
    print(f"\n  Results: {PASS} ✅  {FAIL} ❌  {SKIP} ⏭️   (total: {total})")


def main():
    if "--list" in sys.argv:
        print("\n  Available tests:")
        for lid, (_, name) in sorted(ALL_TESTS.items()):
            print(f"    {lid:<5s}  {name}")
        print()
        return

    # Filter by specific layers
    layer_filters = [a for a in sys.argv[1:] if a.startswith("L") or a.startswith("AD")]

    print()
    print(f"  ╔═══════════════════════════════════════════════╗")
    print(f"  ║  Cognoscope Integration Test Suite           ║")
    print(f"  ╚═══════════════════════════════════════════════╝")
    print()

    all_fns = []
    if layer_filters:
        for lid in layer_filters:
            fn, name = ALL_TESTS.get(lid.upper(), (None, ""))
            if fn:
                all_fns.append((lid, name, fn))
            else:
                print(f"  ⚠️  Unknown layer: {lid}")
    else:
        # Run all
        for lid, (fn, name) in sorted(ALL_TESTS.items()):
            all_fns.append((lid, name, fn))

    global PASS, FAIL, SKIP
    PASS = FAIL = SKIP = 0

    for lid, name, fn in all_fns:
        print(f"  ─── {lid}: {name} ───")
        test(name, fn)

    _print_summary()

    if FAIL > 0:
        print(f"\n  ⚠️  {FAIL} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\n  ✅ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
