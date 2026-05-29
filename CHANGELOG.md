# Changelog

## [0.5.0] — 2026-05-29

### Added

#### A2A Protocol — Level 11: Agent-to-Agent Communication Layer

- `a2a_protocol.py` — Google's Agent2Agent protocol implemented in cognoscope: AgentCard (public metadata, capability vector, skills), A2ATask lifecycle (submitted→working→input-required→completed→failed→canceled), Message with Parts (text/file/data/code/error), Artifact, DiscoveryService (skill-based + capability-based lookup), A2AClient (task routing), A2AAgent (task processing with capability-weighted stochastic execution).
- `a2a_mesh_adapter.py` — Three adapters bridging A2A with existing cognoscope infrastructure:
  - **A2AMeshAdapter**: wraps agents via A2A protocol with AgentCard registration via DiscoveryService — supports execute(), execute_chain() (CHAIN topology), execute_pipeline() (PIPELINE topology)
  - **A2ASocialMeshAdapter**: trust-adjusted routing with social scoring (capability × trust × success × exploration), reputation crisis detection, cold-start boost for untested agents
  - **A2AOrchestratorAdapter**: decomposes complex goals into typed sub-tasks (retrieval/synthesis/execution/verification/planning), routes through configurable topology (chain/pipeline/mesh), retries failures on different agents

#### A2A Architecture

```
DiscoveryService (AgentCard registry)
    │
    ├── A2AMeshAdapter       → Basic routing (agent_mesh via A2A)
    ├── A2ASocialMeshAdapter → Trust-adjusted routing (social_mesh via A2A)
    └── A2AOrchestratorAdapter → Complex task decomposition (mesh_orchestrator via A2A)
```

### Verified

- `a2a_protocol.py` — 4 agents registered, 3 tasks routed, 100% success
- `a2a_mesh_adapter.py` — 4 demos:
  - **A2A Mesh**: 6 tasks, 6/6 success ✅
  - **A2A Social Mesh**: 5 tasks, trust-adjusted routing with exploration (avg trust 0.60)
  - **A2A Orchestrator**: 2 complex goals decomposed into 3 sub-tasks each, 6/6 success ✅
  - **A2A Chain**: research→build→verify chain, 3/3 success ✅

## [0.4.0] — 2026-05-29

### Added

#### Dream Loop — Background Session Analysis

- `dream_loop.py` — The Dreaming Agent: overnight session analysis engine. Analyzes all new Hermes sessions since last run, extracts tool patterns, detects cross-session patterns (tool_churn, guardrail_spike, low_diversity), consolidates lessons (merge by Jaccard > 0.4, archive stale > 72h), records patterns to archive, refreshes pre-warm cache.
- `~/.hermes/.dream_state.json` — persists processed session IDs so it only processes new ones each run.
- Cron job `dream-loop` at 03:00 nightly (no_agent=True, 0 tokens). Script at `~/.hermes/scripts/dream_loop.py`.

#### Pattern Detection (4 detectors)

| Pattern | Severity | What | Recommendation |
|:--------|:--------:|:-----|:--------------|
| tool_churn | 🔴 high | ≥8 consecutive same tool in any session | Tighten max_consecutive |
| guardrail_spike | 🟡 medium | ≥3 guardrail hits per session | Review triggers |
| low_tool_diversity | 🟡 medium | ≤2 unique tools with >20 messages | Force tool rotation |
| tool_dominance | 🟢 low | One tool >60% of all calls | Distribute work |

#### Breaktruth #15 — The Dreaming Agent
Published in vault: "the first agent that dreams about its own sessions, consolidates memory overnight, and refreshes its identity before morning." Breaktruth MOC updated.

#### Hermes Self-Aware CLI

- `hermes_selfaware.py --startup` now tries cache first (fast path ~1ms), falls back to generation (~50ms).

### Changed
- `dream_loop.py` — NEW (682 lines, 26KB)
- `hermes_selfaware.py` — startup cache fast path
- `hermes-self-knowledge` skill — updated references



### Added

#### Push Memory — Agent Self-Model

- `autobiography.py` — **Push-based** living self-model. `generate_prewarm()` produces a ~500 token context block at session start. The agent reads it because it's ALREADY in context — no tool call needed. Five sources: identity, momentum, lessons (from `correct()`), patterns, session continuity.
- `pattern_archive.py` — Added structured `add_lesson()` and `get_lessons_for_prewarm()`. Failures are **first-class objects**: {context, mistake, cause, lesson, category}. Auto-deduplicates by mistake text.
- `hermes_selfaware.py` — Rewritten for push integration:
  - `--startup` / `--inject`: generates pre-warm block for system prompt injection
  - `--cache`: loads from `.memory_prewarm.json` (~1ms vs ~50ms)
  - `--correct`: record a correction mid-session (mirrors Mnemos.correct())
- `.memory_prewarm.json` — file-based cache for zero-parsing pre-warm loading

#### Insight (from Figueira's "Agent memory is push, not pull")
Every memory layer ships with the same broken assumption: "The agent will call your memory tool when it needs a memory." It won't. Not reliably. Not at the right moment. Push memory at session start — the one moment the agent is GUARANTEED to look.

### Changed
- `autobiography.py` — v2 rewrite with push engine, `correct()` method, pre-warm cache
- `pattern_archive.py` — v2 rewrite with lesson store, pre-warm formatting
- `hermes_selfaware.py` — full push integration with 4 CLI commands

### Added

#### Analysis Package — Causal Agent Evaluation

- `analysis/optimal_fingerprint.py` — Climate-science optimal fingerprinting adapted for agent behavior. Ridge regression + bootstrap structural uncertainty across multi-ensemble runs.
- `analysis/agent_profile.py` — Behavioral profiler. Extracts `AgentBehaviorFingerprint` from agent event traces (accuracy, guardrail hit rate, reflection, tool diversity, latency per task type). Integrates with athena.py via fingerprint hook.
- `analysis/agent_evaluator.py` — Full evaluation pipeline orchestrator. Runs baseline/variant/noise ensembles, profiles each run, runs optimal fingerprinting, produces structured `EvalResult` with summary report.
- `athena.py` — Added `AgentProfiler` integration: each `Athena.run()` now generates a fingerprint. Available as `summary['fingerprint']`.

#### Immune Guardrail Layer (Layer 9)

- `immune_guardrail.py` — Immune-inspired guardrail orchestrator. Three layers:
  - **Innate immunity**: Hard-coded limits (position size, daily loss, drawdown, leverage) — immune privileged, agent cannot override
  - **Adaptive immunity**: Pattern matching from past guardrail events. Learns which tool/ticker combos are dangerous
  - **Circuit breaker**: Progressive levels (WARN → REJECT → FREEZE → ESCALATE)

#### Guardrail Integration Bus

- `guardrail_bus.py` — Event bus connecting 3 layers: ImmuneGuardrail (L9) → MSR (L10) → Athena. Single entry point for all guardrail checks.
- **Regime-adaptive thresholds**: `set_regime('high_vol')` tightens all innate limits by 50%, `crisis` factor 0.3 widens drawdown tolerance
- Full pipeline demo: normal → BLOCK → drawdown → tool storm → MSR drift detection

#### Detection Criteria Fixed
- Optimal fingerprinting now uses proper SNR-based detection (SNR >= 2.0 = detected, >= 1.0 = inconclusive, < 1.0 = not detected). Previously used flawed noise_std division.

# Changelog

## [0.1.0] — 2026-05-19

### Added

#### Core Agent Mesh (`agent_mesh.py`)
- Agent node model with capabilities, trust scoring, load tracking, and cost-per-task metrics
- Five delegation topologies: Chain, Pipeline, Mesh, Hub-and-Spoke, and Hierarchy
- Per-agent circuit breaker — trips on N consecutive failures with cooldown and half-open recovery
- Stigmergic coordination via shared trace pool (agents coordinate by reading/writing traces instead of direct messaging)
- Dynamic re-topology — chain or hub that fails reconfigures to mesh
- Backpressure — queue tasks when no agent available, throttle at configurable limit
- Health reporting: success rate, avg load, avg trust, overloaded/untrusted/tripped agents
- Cascade classification (load, trust, topology)
- Stress-test engine (spike, agent-death, slow-degradation scenarios)

#### Real Agent Orchestrator (`mesh_orchestrator.py`)
- Bridges AgentMesh topology patterns with Hermes async delegation
- Sub-agent node model with capability matching, trust, circuit breaker
- Plugable planner function (default topology-based decomposition, research planner, development planner)
- Routing by trust × capability scoring
- Recording results with stigmergic traces
- Circuit breaker detection and re-topology repair
- Finalization with aggregated summary and agent state reports

#### Social Mesh (`social_mesh.py`)
- SocialAgentNode: extends AgentNode with SocialMirror belief modeling
- Reputation records — each agent tracks what others believe about it
- Trust-adjusted routing using social scoring (capability × trust × availability)
- Reputation gap detection and corrective actions (overdeliver, announce)
- SocialAgentMesh: extends AgentMesh with exploration rate and cold-start boost
- SocialOrchestrator: full lifecycle — setup, run cycle, reputation crisis detection

#### Bridge Recommender (`bridge_recommender.py`)
- Full vault connectome scanner (loads ~700 concepts, 8000+ edges, 100 domains)
- Domain-level bridge candidate scoring (Jaccard similarity × combined Φ × size factor)
- Existing bridge deduplication
- Top 15 recommendations with rationale
- Concept-level gap detection (orphans, domain-aligned orphans, cross-domain gaps)
- Vault note output mode (--write)
- JSON output mode (--json)

#### Reasoning Path Engine (`reasoning_path.py`)
- Lightweight vault graph loader (ReasonGraph) with Φ integration scoring
- Bidirectional BFS with beam-width pruning between distant concepts
- Path scoring: length, domain diversity, avg Φ, path novelty
- Random novel pair sampling biased toward high-Φ, different-domain concepts
- Bridge draft generation from best novel path
- Domain alias normalization and existing-bridge deduplication

#### Other
- Initial project structure with package layout
