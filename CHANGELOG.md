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
