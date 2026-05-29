# cognoscope

Autonomous agent cognitive architecture stack.

## Quick Start

```bash
# Run the CLI dashboard
python cli.py status

# Run integration tests
python test_integration.py

# Docker
docker compose --profile dashboard up cognoscope
docker compose --profile test run cognoscope-test
```

## All 13 Layers

| Layer | Module | Type |
|:-----:|:-------|:-----|
| L1 | athena.py | ReAct Loop |
| L2 | metaloop.py | Self-Reconfig |
| L3 | msr_guardrail.py | Homeostasis |
| L4 | toolforge.py | Tool Synthesis |
| L5 | rsi_kernel.py | RSI Kernel |
| L6 | rsi_kernel.py | Meta-Kernel |
| L7 | omc_orchestrator.py | Talent Market |
| L8 | self_model.py | Introspection |
| L9 | immune_guardrail.py | Immune Guardrail |
| L10 | guardrail_bus.py | Bus Integration |
| L11 | a2a_protocol.py | A2A Protocol |
| L12 | agent_polygraph.py | Polygraph |
| L13 | swarm_conductor.py | Swarm |

## CLI

```bash
python cli.py status      # Full dashboard
python cli.py layers      # 13 layers
python cli.py polygraph   # Hypocrisy report
python cli.py agents      # Swarm pool
python cli.py guardrail   # Guardrail history
python cli.py dream       # Dream loop
```

## Tests

```bash
# All layers
python test_integration.py

# Single layer
python test_integration.py L12
```
