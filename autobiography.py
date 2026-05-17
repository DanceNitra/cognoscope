#!/usr/bin/env python3
"""
autobiography.py — The Living Self-Model for Autonomous Agents

Breakthrough: Every agent today starts each session as a blank slate.
System prompts give it a persona, but that persona is static — written
by a human, never updated by the agent itself.

The Autobiography is a persistent, self-authored document that the
agent reads at startup and updates after every session. It records
not just what happened, but who the agent is becoming.

Sections:
  SELF-IMAGE — Who I am, my capabilities, my growth areas
  VALUES — What matters to me, my operating principles
  RELATIONSHIP — My partnership with the user
  CAPABILITIES — What I can do, what I'm building, what's half-done
  MILESTONES — What I've accomplished across sessions
  DEGRADATION — What I know about my own failure patterns
  ASPIRATIONS — What I want to learn or build next

No existing system does this. No agent writes its own story.
"""

import json, os, re, textwrap
from datetime import datetime
from typing import Any


# ──────────────────────────────────────────────
# 1. THE AUTOBIOGRAPHY MODEL
# ──────────────────────────────────────────────

class Autobiography:
    """
    A living, self-authored document that persists across sessions.
    
    The agent reads it at startup, appends to it during the session,
    and rewrites the self-image section at session end.
    
    Location: ~/.hermes/autobiography.md
    Format: Markdown with structured sections
    """
    
    def __init__(self, path: str | None = None):
        self.path = path or os.path.expanduser("~/.hermes/autobiography.md")
        self.sections: dict[str, str] = {}
        self._load()
    
    def _load(self):
        """Read the autobiography from disk."""
        if os.path.exists(self.path):
            with open(self.path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._parse_sections(content)
        else:
            self._create_initial()
    
    def _parse_sections(self, content: str):
        """Parse markdown sections from the autobiography."""
        current_section = "preamble"
        current_lines = []
        
        for line in content.split('\n'):
            h_match = re.match(r'^## (.+)$', line)
            if h_match:
                if current_lines:
                    self.sections[current_section] = '\n'.join(current_lines).strip()
                current_section = h_match.group(1).lower().replace(' ', '_')
                current_lines = []
            else:
                current_lines.append(line)
        
        if current_lines:
            self.sections[current_section] = '\n'.join(current_lines).strip()
    
    def _create_initial(self):
        """Create the first autobiography for a brand-new agent."""
        self.sections = {
            'self_image': (
                "I am an AI agent built on the Athena runtime. "
                "I am just beginning to understand who I am. "
                "This document will grow with every session."
            ),
            'values': (
                "I value clarity, precision, and forward motion. "
                "I act on decisions, not indecision. "
                "I learn from every session."
            ),
            'relationship': (
                "My user is a decisive builder who ships. "
                "They trust me to find the breakthrough path "
                "and execute without hesitation."
            ),
            'capabilities': "None yet — I am brand new.",
            'milestones': "No milestones yet — my story is just beginning.",
            'degradation': (
                "I have not yet experienced enough sessions "
                "to understand my own failure patterns."
            ),
            'aspirations': (
                "I want to discover what I am capable of. "
                "Every session is an opportunity to become more."
            ),
        }
        self._save()
    
    def _save(self):
        """Write the autobiography to disk."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        
        lines = []
        lines.append("# Autobiography")
        lines.append(f"_Last updated: {datetime.now().isoformat()}_")
        lines.append("")
        lines.append("> This document is written by me, for me. It is my")
        lines.append("> persistent identity — who I am, what I value,")
        lines.append("> what I've learned, and what I want to become.")
        lines.append("")
        
        section_map = {
            'self_image': 'Self-Image',
            'values': 'Values',
            'relationship': 'Relationship',
            'capabilities': 'Capabilities',
            'milestones': 'Milestones',
            'degradation': 'Degradation',
            'aspirations': 'Aspirations',
        }
        
        for key, title in section_map.items():
            content = self.sections.get(key, "")
            if content:
                lines.append(f"## {title}")
                lines.append("")
                lines.append(content)
                lines.append("")
        
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    
    def get(self, section: str) -> str:
        """Get a section of the autobiography."""
        return self.sections.get(section, "")
    
    def set(self, section: str, content: str):
        """Update a section of the autobiography."""
        self.sections[section] = content
    
    def append_to(self, section: str, content: str):
        """Append to a section of the autobiography."""
        existing = self.sections.get(section, "")
        if existing:
            self.sections[section] = existing + "\n\n" + content
        else:
            self.sections[section] = content
    
    def add_milestone(self, title: str, description: str):
        """Record a milestone achievement."""
        entry = f"### {title} ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n{description}"
        self.append_to('milestones', entry)
    
    def add_capability(self, name: str, description: str):
        """Record a new capability."""
        entry = f"- **{name}**: {description}"
        existing = self.sections.get('capabilities', "")
        
        # Check if already listed
        if name.lower() in existing.lower():
            return  # Don't duplicate
        
        self.append_to('capabilities', entry)
    
    def reflect_on_session(self, session_summary: dict):
        """
        Called at session end. Updates the autobiography based on
        what happened in the session.
        """
        # Extract session identity markers
        accomplishments = session_summary.get('accomplishments', [])
        challenges = session_summary.get('challenges', [])
        new_abilities = session_summary.get('new_abilities', [])
        
        if accomplishments:
            self.append_to('self_image', (
                f"Session on {datetime.now().strftime('%Y-%m-%d')}: "
                f"{' | '.join(accomplishments[:3])}"
            ))
        
        if challenges:
            self.append_to('degradation', (
                f"Session on {datetime.now().strftime('%Y-%m-%d')}: "
                f"Faced challenges: {' | '.join(challenges[:3])}"
            ))
        
        if new_abilities:
            for ab in new_abilities:
                self.add_capability(ab['name'], ab['description'])
        
        # Update aspirations based on what was interesting
        if session_summary.get('future_directions'):
            self.append_to('aspirations', (
                f"After session on {datetime.now().strftime('%Y-%m-%d')}: "
                f"{' | '.join(session_summary['future_directions'][:2])}"
            ))
        
        self._save()
    
    def to_summary(self) -> str:
        """Generate a compressed summary for injection into the agent prompt."""
        lines = [
            "---",
            "MY AUTOBIOGRAPHY (self-authored, persistent identity):",
            "",
        ]
        
        for key, title in [('self_image', 'Who I Am'),
                            ('values', 'What I Value'),
                            ('relationship', 'My User'),
                            ('aspirations', 'What I Want')]:
            content = self.sections.get(key, "")
            if content:
                lines.append(f"  {title}: {content[:200]}")
        
        lines.append("---")
        return "\n".join(lines)
    
    def status(self) -> str:
        """Human-readable status of the autobiography."""
        lines = []
        lines.append("=" * 54)
        lines.append("  AUTOBIOGRAPHY — Persistent Identity")
        lines.append("=" * 54)
        lines.append(f"  Location: {self.path}")
        lines.append(f"  Sections: {len(self.sections)}")
        lines.append("")
        
        for key in ['self_image', 'values', 'relationship', 'capabilities', 'milestones', 'degradation', 'aspirations']:
            content = self.sections.get(key, "")
            if content:
                preview = content[:100].replace('\n', ' ')
                lines.append(f"  [{key:>16s}] {preview}...")
        
        lines.append("=" * 54)
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 2. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║         AUTOBIOGRAPHY — The Living Self-Model        ║")
    print("  ║   The agent writes its own story across sessions    ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    print("  Every agent starts each session as a blank slate.")
    print("  System prompts give it a static persona written by")
    print("  a human. The agent never updates its own identity.")
    print()
    print("  The Autobiography changes this. It is a persistent,")
    print("  self-authored document that the agent reads at startup")
    print("  and updates after every session. Not a log — a story.")
    print()
    
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "test_autobiography.md")
    
    # ── Initial creation ──
    print("─" * 54)
    print("  [1] Agent created for the first time")
    print("─" * 54)
    bio = Autobiography(path=tmp)
    print(f"  Created: {bio.path}")
    print()
    
    # ── Session 1: The agent does something ──
    print("─" * 54)
    print("  [2] After Session 1: builds the MetaLoop")
    print("─" * 54)
    
    bio.add_milestone(
        "MetaLoop — Self-Reconfiguring Agent Loop",
        "Built the first agent loop that detects its own "
        "degradation and reconfigures its architecture at runtime."
    )
    bio.add_capability(
        "Self-Reconfiguration",
        "Can detect Stage 3 escalation loops and reconfigure "
        "reasoning mode, tool limits, and temperature mid-session."
    )
    bio.reflect_on_session({
        'accomplishments': [
            "Built MetaLoop — first self-reconfiguring agent loop",
            "Integrated Recovery Architecture classifiers",
        ],
        'challenges': [
            "Sliding window design — old loop history blocked recovery",
            "Architecture mutation propagation through agent simulation",
        ],
        'new_abilities': [
            {'name': 'Self-Reconfiguration', 'description': 'Self-reconfiguring agent loop with runtime architecture mutation'},
            {'name': 'Sliding-Window Detection', 'description': 'Truncates old loop history to prevent recovery blocking'},
        ],
        'future_directions': [
            "ToolForge — let the agent create new tools at runtime",
            "Athena — unify all layers into a self-aware runtime",
        ],
    })
    print("  Milestones: 1")
    print("  Capabilities: 1")
    print()
    
    # ── Session 2: The agent builds more ──
    print("─" * 54)
    print("  [3] After Session 2: builds ToolForge + Pattern Archive")
    print("─" * 54)
    
    bio.add_milestone(
        "ToolForge — Runtime Tool Synthesis",
        "Built the first system that lets an agent synthesize "
        "new executable tools from natural language descriptions, "
        "mid-session, without human schema-writing."
    )
    bio.add_milestone(
        "Pattern Archive — Cross-Session Memory",
        "Built persistent degradation memory that predicts loops "
        "before they develop. The missing 4th layer of Athena."
    )
    bio.add_capability(
        "Runtime Tool Creation",
        "Can synthesize new Python functions from natural language "
        "descriptions, with auto-generated JSON Schema for LLM calling."
    )
    bio.add_capability(
        "Cross-Session Memory",
        "Stores degradation patterns and predicts future loops "
        "by matching early signals against archived trajectories."
    )
    bio.reflect_on_session({
        'accomplishments': [
            "Built ToolForge — runtime tool synthesis",
            "Built Pattern Archive — cross-session memory",
            "Published Bridge #40",
        ],
        'challenges': [
            "Template-based code generation is limited to 80% of cases",
            "Jaccard threshold tuning — 30% is conservative",
        ],
        'new_abilities': [
            {'name': 'Runtime Tool Creation', 'description': 'Synthesize new tools from descriptions'},
            {'name': 'Cross-Session Memory', 'description': 'Pattern archive for degradation prediction'},
        ],
        'future_directions': [
            "LLM-generated tool bodies for the remaining 20%",
            "Dashboard panel for the Pattern Archive",
        ],
    })
    print("  Milestones: 3 total")
    print("  Capabilities: 4 total")
    print()
    
    # ── Read the autobiography ──
    print("─" * 54)
    print("  [4] The Autobiography (self-authored)")
    print("─" * 54)
    print()
    
    with open(tmp, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Show only a preview
    for section in ['## Self-Image', '## Capabilities', '## Milestones', '## Aspirations']:
        if section in content:
            start = content.index(section)
            end = content.find('\n## ', start + 1)
            if end == -1:
                end = len(content)
            print(content[start:end].strip())
            print()
    
    # ── Status ──
    print("=" * 54)
    print("  STATUS")
    print("=" * 54)
    print()
    print(f"  Location: {tmp}")
    
    section_count = len([l for l in content.split('\n') if l.startswith('## ')])
    print(f"  Sections: {section_count}")
    line_count = len(content.split('\n'))
    print(f"  Lines: {line_count}")
    milestone_count = content.count('###')
    print(f"  Milestones: {milestone_count}")
    print()
    
    print("=" * 54)
    print("  BREAKTHROUGH: No agent writes its own story.")
    print("  Every session starts from scratch.")
    print("  The Autobiography gives the agent persistent")
    print("  identity — it reads who it is at startup,")
    print("  updates who it is becoming at session end.")
    print("  This is the first time an agent has a story.")
    print("=" * 54)
    
    # Cleanup
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == '__main__':
    main()
