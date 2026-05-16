# Cognoscope

**First-ever runtime bias detection and adaptive intervention system for LLM agents.**

Cognoscope monitors live agent behaviour, detects which of 8 cognitive biases are active in real-time, and injects targeted countermeasures into the agent's context. A Thompson sampling bandit learns which interventions work best per bias × scenario over time.

Unlike static debiased prompts that are fixed at session start, Cognoscope operates as a closed-loop feedback system: monitor → detect → intervene → learn → adapt.

## Architecture

```
Agent events ──→ DETECTORS ──→ FUSION ──→ INJECTOR ──→ Context injection
                     │            │            │
                     │            ▼            │
                     │     BANDIT LEARNER      │
                     │    (Thompson sampling)  │
                     └─────────────────────────┘
```

## 8 Bias Detectors

| Bias | Signal | Detection Method |
|---|---|---|
| **Anchoring** | >60% tool calls to the first tool | Tool frequency analysis over sliding window |
| **Confirmation Bias** | "as expected" language, no counterarguments | NLP pattern matching on reasoning traces |
| **Escalation of Commitment** | Consecutive same-tool failures | Run-length analysis + failure density |
| **Overconfidence** | Absolute language, no uncertainty qualifiers | Certainty/uncertainty ratio in output |
| **Loss Aversion** | Fleeing to safe tools after failure | Tool type analysis pre/post failure |
| **Framing Effects** | Binary frames ("will it work?") | Frame type classification |
| **Drift** | Decreasing tool diversity over time | Diversity delta between session halves |
| **Feedback Delay** | Long tool-call streaks without reflection | Reflection-to-tool-call ratio |

## Intervention Engine

Each detector, when active, triggers a targeted context injection:

- **Mild** (score 0.4-0.6): Gentle reminder
- **Moderate** (score 0.6-0.8): Specific directive
- **Strong** (score 0.8+): Circuit breaker with forced reflection

The Bandit uses Beta-Bernoulli Thompson sampling to select the intervention severity level, balancing exploration (try new approaches) with exploitation (use what works).

## Project Structure

```
cognoscope/
├── index.html          # Dashboard with radar chart, gauges, event stream
├── js/
│   ├── detectors.js    # 8 bias signal processors
│   ├── fusion.js       # Threshold, cooldown, priority, intervention history
│   ├── injector.js     # Context injection templates (3 tiers × 8 biases)
│   ├── bandit.js       # Thompson sampling learner
│   └── demo.js         # Simulated agent traces with controlled bias profiles
└── README.md
```

## Demo Scenarios

| Scenario | Description | What to Expect |
|---|---|---|
| Balanced | Minimal bias, good baseline | 0-1 biases detected |
| Anchoring Stress Test | Heavy first-tool bias | Anchoring + escalation detected |
| Escalation Spiral | Doubles down on failing approach | Escalation + drift detected |
| Overconfidence Cascade | No uncertainty qualifiers | Overconfidence + confirmation detected |
| Loss-Averse Trader | Flees to safe tools after loss | Loss aversion + drift |
| All Biases Active | Extreme multi-bias case | 4+ biases detected |

## Research Foundation

Built from **Bridge #2: Behavioral Economics × Prompt Engineering** — mapping Kahneman & Tversky's Prospect Theory, Thaler & Sunstein's Nudge Theory, and the Heuristics & Biases program onto agent runtime behaviour.

Cognoscope is the first known system that applies behavioral economics as **runtime closed-loop feedback** to LLM agents — not a static prompt, but a live bias immune system.

## Usage

Open `index.html` in a browser. Select a scenario and click "Run Scenario." The dashboard shows:

- **Radar chart**: 8-dimensional bias score map
- **Bias gauges**: Percentage scores per bias
- **Event stream**: Live agent tool calls, results, and reasoning
- **Alerts**: Active biases that have crossed threshold
- **Intervention log**: History of context injections
- **Bandit stats**: Which intervention severities are performing best

## License

MIT
