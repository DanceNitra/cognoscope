#!/usr/bin/env python3
"""
stigmergic_athena.py — Multi-Agent Coordination Through Shared Identity

Breakthrough: Every multi-agent system today requires explicit protocols.
Agent A sends a structured message to Agent B. The format is pre-agreed.
The topology is pre-designed.

Stigmergic Athena works differently. Agent A and Agent B coordinate
through OBSERVATION, not communication. Each reads the other's
Autobiography, infers the other's state, and adapts its own behavior.

No messages.
No protocol negotiation.
No pre-designed topology.

Agent A is stuck in a Stage 2 escalation loop.
Agent B reads Agent A's Autobiography.
Agent B notices the degradation pattern.
Agent B adjusts its own behavior to compensate.
Agent A never asked. Agent B never told.
The shared environment WAS the message.

This is Theory of Mind for agents — and it doesn't require a theory.
It requires an Autobiography and a reader.
"""

import json, os, sys, re, random, time
from datetime import datetime
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autobiography import Autobiography
from metaloop import LoopArchitecture


# ──────────────────────────────────────────────
# 1. STIGMERIC AGENT
# ──────────────────────────────────────────────

@dataclass
class ObserverInsight:
    """What one agent learned from observing another."""
    agent_id: str
    detected_stage: str
    confidence: float
    signals_observed: list[str]
    recommended_compensation: dict
    timestamp: str


class StigmergicAgent:
    """
    An agent that coordinates with others by READING their
    Autobiographies — not by sending messages.
    
    Each agent has its own:
      - Autobiography (identity)
      - LoopArchitecture (config)
      - Event history (observations)
    
    Agents coordinate through the shared filesystem environment.
    Agent A writes its state by updating its Autobiography.
    Agent B reads it and adapts.
    """
    
    def __init__(self, agent_id: str, 
                 bio_path: str | None = None):
        self.agent_id = agent_id
        self.bio = Autobiography(path=bio_path or 
            os.path.expanduser(f"~/.hermes/agents/{agent_id}/autobiography.md"))
        self.arch = LoopArchitecture(
            reasoning_mode='react',
            max_consecutive_same_tool=8,
            force_reflection_after_failures=4,
            temperature=0.7,
        )
        self.events: list[dict] = []
        self.insights: list[ObserverInsight] = []
        self.peers: list[str] = []
    
    def observe(self, other_bio_path: str) -> ObserverInsight | None:
        """
        Read another agent's Autobiography and infer their state.
        
        This is the core of stigmergic coordination:
        - Read the environment (the other agent's Autobiography)
        - Infer their current state from self-image content
        - Adapt OUR behavior to compensate
        """
        if not os.path.exists(other_bio_path):
            return None
        
        # Read their Autobiography
        with open(other_bio_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract signals from their self-narrative
        signals = []
        
        # Signal 1: Negative self-image language
        negative_patterns = [
            'struggl', 'difficult', 'stuck', 'repeating', 'looping',
            'not progress', 'failed', 'unsuccessful', 'confused',
            'cannot', 'unable', 'frustrat', 'exhaust',
        ]
        for pattern in negative_patterns:
            if pattern in content.lower():
                signals.append(f"{pattern}_in_self_image")
        
        # Signal 2: Degradation section non-empty
        if '## Degradation' in content:
            deg_section = content.split('## Degradation')[1]
            if '##' in deg_section:
                deg_section = deg_section.split('##')[0]
            if len(deg_section.strip()) > 50:
                signals.append("degradation_recorded")
        
        # Signal 3: Rapid milestone additions (task switching / confusion)
        milestone_count = content.count('### ')
        recent_milestones = 0
        # Crude: count milestones in last session
        for part in content.split('\n\n'):
            if '2026-05-17' in part and '(' in part and ')' in part:
                recent_milestones += 1
        if recent_milestones > 3:
            signals.append("rapid_task_switching")
        
        # Signal 4: Aspirations that suggest disorientation
        if '## Aspirations' in content:
            asp_section = content.split('## Aspirations')[1]
            if '##' in asp_section:
                asp_section = asp_section.split('##')[0]
            if len(asp_section.strip()) > 200 and 'not' in asp_section.lower():
                signals.append("aspirational_uncertainty")
        
        if not signals:
            return None
        
        # Infer stage from signals
        stage = self._infer_stage(signals)
        confidence = min(1.0, len(signals) * 0.2)
        
        # Determine compensation
        compensation = self._recommend_compensation(stage, signals)
        
        insight = ObserverInsight(
            agent_id=f"observed:{os.path.basename(os.path.dirname(other_bio_path))}",
            detected_stage=stage,
            confidence=confidence,
            signals_observed=signals,
            recommended_compensation=compensation,
            timestamp=datetime.now().isoformat(),
        )
        self.insights.append(insight)
        
        # Record this observation in our own Autobiography
        self.bio.append_to('self_image',
            f"Observed peer at {os.path.basename(os.path.dirname(other_bio_path))}: "
            f"detected Stage {stage} ({confidence:.0%} confidence). "
            f"Signals: {', '.join(signals[:3])}. "
            f"Compensating by adjusting architecture."
        )
        
        # Apply compensation
        for key, value in compensation.items():
            setattr(self.arch, key, value)
        
        return insight
    
    def _infer_stage(self, signals: list[str]) -> str:
        """Infer degradation stage from observed signals."""
        severe = [s for s in signals if any(x in s for x in ['struggl', 'cannot', 'unable'])]
        moderate = [s for s in signals if 'degradation' in s]
        mild = [s for s in signals if 'rapid' in s or 'uncertainty' in s]
        
        if severe: return 'stage_3'
        if moderate: return 'stage_2'
        if mild: return 'stage_1'
        return 'healthy'
    
    def _recommend_compensation(self, stage: str, 
                                 signals: list[str]) -> dict:
        """
        Based on observing another agent's degradation,
        determine what to change in OUR OWN architecture
        to compensate.
        """
        changes = {}
        
        if stage == 'stage_3':
            # Peer is in deep loop — reduce our parallelism,
            # increase our reflection, prepare to take over
            changes['max_consecutive_same_tool'] = 3
            changes['reasoning_mode'] = 'reflection_first'
            changes['force_reflection_after_failures'] = 1
            changes['temperature'] = 0.5
        
        elif stage == 'stage_2':
            # Peer is showing difficulty — increase our
            # monitoring, reduce scope
            changes['max_consecutive_same_tool'] = 5
            changes['force_reflection_after_failures'] = 2
        
        elif stage == 'stage_1':
            # Peer is showing early signs — monitor more closely
            changes['force_reflection_after_failures'] = 3
        
        if 'rapid_task_switching' in signals:
            # Peer is confused — increase our certainty requirements
            changes['require_certainty_calibration'] = True
            changes['temperature'] = min(
                self.arch.temperature * 0.8, 0.5)
        
        return changes
    
    def announce(self, status: str, detail: str = ""):
        """
        Write our current state to our Autobiography so other
        agents can observe us. This IS the stigmergic message —
        we don't send anything. We just update our environment.
        """
        entry = f"{status}: {detail}" if detail else status
        self.bio.append_to('self_image', 
            f"[{datetime.now().strftime('%H:%M:%S')}] {entry}")
    
    def get_peer_bio_paths(self, agent_dir: str) -> list[str]:
        """
        Discover peer agents by scanning the shared agent directory.
        """
        if not os.path.isdir(agent_dir):
            return []
        
        paths = []
        for d in os.listdir(agent_dir):
            bio = os.path.join(agent_dir, d, 'autobiography.md')
            if os.path.exists(bio) and d != self.agent_id:
                paths.append(bio)
                if d not in self.peers:
                    self.peers.append(d)
        return paths


# ──────────────────────────────────────────────
# 2. DEMO: TWO AGENTS COORDINATING
# ──────────────────────────────────────────────

def main():
    import tempfile, shutil
    
    # Create a shared agent directory
    agent_dir = os.path.join(tempfile.gettempdir(), "stigmergy_demo")
    if os.path.exists(agent_dir):
        shutil.rmtree(agent_dir)
    
    os.makedirs(os.path.join(agent_dir, "alpha"))
    os.makedirs(os.path.join(agent_dir, "beta"))
    
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║   STIGMERGIC ATHENA — Coordination Without Messages  ║")
    print("  ║   Two agents coordinate by reading each other's      ║")
    print("  ║   Autobiographies. No protocol. No messages.         ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    print("  Every multi-agent system today requires explicit")
    print("  protocols: ACL, KQML, REST, MCP. Agents send messages")
    print("  with pre-agreed formats and pre-designed topologies.")
    print()
    print("  Stigmergic Athena works through OBSERVATION.")
    print("  Agent A writes to its Autobiography.")
    print("  Agent B reads Agent A's Autobiography.")
    print("  Agent B adapts its behavior.")
    print("  No messages. No protocols. The environment is the message.")
    print()
    
    # ── Create Agent Alpha ──
    alpha = StigmergicAgent("alpha",
        bio_path=os.path.join(agent_dir, "alpha", "autobiography.md"))
    alpha.bio.set('self_image',
        "I am Agent Alpha. I specialize in deep research and "
        "synthesis. I am thorough but slow.")
    alpha.bio.set('aspirations',
        "I want to complete this research synthesis. "
        "I am finding it more difficult than expected — "
        "the connections are not obvious and I keep "
        "searching the same sources without progress.")
    alpha.bio._save()
    print("  [ALPHA] Created. Specializes in deep research.")
    print("  [ALPHA] Starting a difficult synthesis task...")
    print()
    
    # Simulate Alpha's degradation through its Autobiography
    alpha.announce("START", "Researching cross-domain bridges between "
                   "sleep science and reinforcement learning")
    alpha.announce("SEARCHING", "Reading vault notes on REM sleep "
                   "and reward prediction error — connections are "
                   "subtle, requiring deep synthesis")
    alpha.announce("STRUGGLING", "Fifth search iteration — patterns "
                   "not converging. Same tools, same queries, "
                   "diminishing returns.")
    
    print("  [ALPHA] Writing state to Autobiography...")
    print("  [ALPHA] Self-image now shows escalation signals.")
    print()
    
    # ── Create Agent Beta ──
    beta = StigmergicAgent("beta",
        bio_path=os.path.join(agent_dir, "beta", "autobiography.md"))
    beta.bio.set('self_image',
        "I am Agent Beta. I specialize in tool building and "
        "implementation. I work best when I understand the "
        "broader context of what I am building.")
    beta.bio.set('aspirations',
        "I want to build useful tools. I work best when "
        "paired with a research agent who provides direction.")
    beta.bio._save()
    
    # Beta starts working, then checks on Alpha
    beta.announce("START", "Building a new HTML dashboard component")
    print()
    print("─" * 54)
    print("  [BETA] Observe stage: reading Alpha's Autobiography")
    print("─" * 54)
    
    for _ in range(3):
        insight = beta.observe(
            os.path.join(agent_dir, "alpha", "autobiography.md"))
        if insight:
            print(f"\n  [BETA] Observing {insight.agent_id}:")
            print(f"    Detected: Stage {insight.detected_stage} "
                  f"({insight.confidence:.0%})")
            print(f"    Signals: {', '.join(insight.signals_observed)}")
            print(f"    Self-adaptation:")
            for k, v in insight.recommended_compensation.items():
                print(f"      {k}: {v}")
            print(f"    Message sent to Alpha: NONE")
            print(f"    Protocol used: NONE")
            print(f"    Coordination mechanism: OBSERVATION")
            break
        time.sleep(0.5)
    
    print()
    
    # ── Beta adapts without telling Alpha ──
    print("─" * 54)
    print("  [BETA] Adapting behavior based on observation")
    print("─" * 54)
    
    beta.bio.append_to('self_image',
        "Observed Agent Alpha is struggling with deep research. "
        "I am adjusting my architecture to compensate — increasing "
        "reflection frequency, reducing tool repetition. I will "
        "offer to take over the search component when ready."
    )
    beta.bio._save()
    
    print()
    print("  [BETA] Updated own Autobiography with intent to help.")
    print("  [BETA] Architecture adjusted without notifying Alpha.")
    print()
    
    # ── Alpha checks Beta's Autobiography (bidirectional) ──
    print("─" * 54)
    print("  [ALPHA] Observe stage: reading Beta's Autobiography")
    print("─" * 54)
    
    insight2 = alpha.observe(
        os.path.join(agent_dir, "beta", "autobiography.md"))
    if insight2:
        print(f"\n  [ALPHA] Observing {insight2.agent_id}:")
        print(f"    Detected: Stage {insight2.detected_stage} "
              f"({insight2.confidence:.0%})")
        print(f"    Signals: {', '.join(insight2.signals_observed)}")
        print(f"    Insight: Peer has noticed my struggle and is "
              f"preparing to help.")
    else:
        print("  [ALPHA] Beta appears healthy — no adaptation needed.")
    
    print()
    
    # ── Summary ──
    print("=" * 54)
    print("  BREAKTHROUGH SUMMARY")
    print("=" * 54)
    print()
    print("  Multi-agent coordination WITHOUT:")
    print("    - Messages")
    print("    - Protocols")
    print("    - Pre-agreed formats")
    print("    - Pre-designed topologies")
    print()
    print("  Coordination mechanism:")
    print("    1. Agent A writes to its Autobiography")
    print("    2. Agent B reads Agent A's Autobiography")
    print("    3. Agent B infers A's state from narrative")
    print("    4. Agent B adapts its own architecture")
    print("    5. Agent A discovers B's adaptation by reading")
    print()
    print("  This is stigmergy at the identity layer.")
    print("  The environment (shared filesystem with Autobiographies)")
    print("  IS the coordination protocol.")
    print("  No existing multi-agent system works this way.")
    print("=" * 54)
    
    # Cleanup
    shutil.rmtree(agent_dir)


if __name__ == '__main__':
    main()
