#!/usr/bin/env python3
"""
autobiography.py — Push-Based Living Self-Model + Pre-Warm Engine

INSIGHT (from Figueira's Mnemos):
  Every memory layer ships with the same broken assumption:
  "The agent will call your memory tool when it needs a memory."
  It won't. Not reliably. Not at the right moment.

  The fix: push memory at session start — the one moment the agent
  is GUARANTEED to look. generate_prewarm() produces a ~500 token
  block that lands directly in the system prompt. Zero agent effort.

Upgrade over v1:
  - generate_prewarm() — context block ready for injection (push)
  - 5 sources: identity, momentum (recent successes), 
    lessons (failures as first-class), active patterns, 
    session continuity (where we left off)
  - .memory_prewarm.json cache for fast file-based injection
  - correct() method — agent calls this when it makes a mistake

Usage:
    from autobiography import Autobiography
    bio = Autobiography()
    prewarm = bio.generate_prewarm()  # ~500 token block
    # → inject into system prompt at session start
"""

import json, os, re, textwrap
from datetime import datetime, timedelta
from typing import Any


PREWARM_PATH = os.path.expanduser("~/.hermes/.memory_prewarm.json")


class Autobiography:
    """
    Push-based living self-model.

    The agent reads generate_prewarm() at session start (it's already
    in context — nothing to call). Updates via correct() + add_milestone()
    during the session. Session-end via reflect_on_session().
    """
    
    def __init__(self, path: str | None = None):
        self.path = path or os.path.expanduser("~/.hermes/autobiography.md")
        self.sections: dict[str, str] = {}
        self._load()
    
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._parse_sections(content)
        else:
            self._create_initial()
    
    def _parse_sections(self, content: str):
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
            'lessons': "No lessons recorded yet.",
            'aspirations': (
                "I want to discover what I am capable of. "
                "Every session is an opportunity to become more."
            ),
        }
        self._save()
    
    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lines = [
            "# Autobiography",
            f"_Last updated: {datetime.now().isoformat()}_",
            "",
            "> This document is written by me, for me. It is my",
            "> persistent identity — who I am, what I value,",
            "> what I've learned, and what I want to become.",
            "",
        ]
        section_map = {
            'self_image': 'Self-Image',
            'values': 'Values',
            'relationship': 'Relationship',
            'capabilities': 'Capabilities',
            'milestones': 'Milestones',
            'degradation': 'Degradation',
            'lessons': 'Lessons',
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
    
    # ──────────────────────────────────────────────
    # PUSH MEMORY: THE PRE-WARM ENGINE
    # ──────────────────────────────────────────────

    def generate_prewarm(self, session_context: dict | None = None) -> str:
        """
        Generate a ~500 token pre-warmed context block.

        Called automatically at session start. Returns a text block
        ready for system prompt injection. Five sources:

        1. IDENTITY — who I am, what I value
        2. MOMENTUM — what I accomplished recently (last 3 milestones)
        3. LESSONS — failures as first-class objects (from correct())
        4. PATTERNS — known degradation patterns to watch for
        5. CONTINUITY — where the last session left off

        The agent reads this because it's ALREADY IN CONTEXT.
        No tool call needed. No "remember to check memory."
        """
        ctx = session_context or {}
        now = datetime.now()
        lines = []
        
        # ── Header ──
        lines.append("═══ PRE-WARMED MEMORY (auto-injected at session start) ═══")
        lines.append("")
        
        # ── 1. Identity (~100 tokens) ──
        self_image = self.sections.get('self_image', '')
        values = self.sections.get('values', '')
        relationship = self.sections.get('relationship', '')
        aspirations = self.sections.get('aspirations', '')
        
        identity_parts = []
        if self_image:
            identity_parts.append(self_image[:200])
        if values:
            identity_parts.append(f"I value: {values[:150]}")
        if relationship:
            identity_parts.append(f"User: {relationship[:150]}")
        if aspirations:
            identity_parts.append(f"Direction: {aspirations[:100]}")
        
        if identity_parts:
            lines.append("📋 Who I am:")
            for part in identity_parts:
                lines.append(f"  • {part}")
            lines.append("")
        
        # ── 2. Momentum (~100 tokens) ──
        milestones_raw = self.sections.get('milestones', '')
        if milestones_raw and milestones_raw != "No milestones yet — my story is just beginning.":
            # Extract last 3 milestones
            milestones = [m.strip() for m in milestones_raw.split('###') if m.strip()]
            recent = milestones[-3:] if len(milestones) >= 3 else milestones
            if recent:
                lines.append("🏆 Recent progress:")
                for m in recent:
                    # Take just the title line
                    title_line = m.split('\n')[0].strip()
                    if title_line:
                        lines.append(f"  • {title_line[:120]}")
                lines.append("")
        
        # ── 3. Lessons (failures as first-class) ──
        lessons_raw = self.sections.get('lessons', '')
        if lessons_raw and lessons_raw != "No lessons recorded yet.":
            # Extract last 3 lessons
            lessons = [l.strip() for l in lessons_raw.split('\n') if l.strip().startswith('-')]
            recent = lessons[-3:] if len(lessons) >= 3 else lessons
            if recent:
                lines.append("📚 Things I learned from mistakes:")
                for l in recent:
                    lines.append(f"  {l[:150]}")
                lines.append("")
        
        # ── 4. Patterns (degradation watchlist) ──
        deg = self.sections.get('degradation', '')
        if deg and deg != (
            "I have not yet experienced enough sessions "
            "to understand my own failure patterns."
        ):
            lines.append("⚠️ Known failure patterns (watch for these):")
            deg_lines = deg.split('\n')[:2]
            for d in deg_lines:
                if d.strip():
                    lines.append(f"  {d.strip()[:120]}")
            lines.append("")
        
        # ── 5. Continuity (from session context) ──
        if ctx.get('continuity'):
            lines.append("🔄 Where we left off:")
            lines.append(f"  {ctx['continuity'][:200]}")
            lines.append("")
        
        # ── Footer instruction ──
        lines.append("(This memory was pushed at session start. No need to fetch it.)")
        lines.append("═══ END PRE-WARMED MEMORY ═══")
        
        prewarm_text = "\n".join(lines)
        
        # Cache to .memory_prewarm.json for fast file-based injection
        self._cache_prewarm(prewarm_text)
        
        return prewarm_text
    
    def _cache_prewarm(self, prewarm_text: str):
        """Cache the prewarm block so hermes_selfknowledge can inject it fast."""
        os.makedirs(os.path.dirname(PREWARM_PATH), exist_ok=True)
        cache = {
            "generated_at": datetime.now().isoformat(),
            "prewarm": prewarm_text,
            "token_estimate": len(prewarm_text.split()),
        }
        with open(PREWARM_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    
    @staticmethod
    def load_prewarm_from_cache() -> str | None:
        """Load the cached prewarm block. Fast — no parsing needed."""
        if os.path.exists(PREWARM_PATH):
            try:
                with open(PREWARM_PATH, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                return cache.get('prewarm')
            except Exception:
                return None
        return None
    
    # ──────────────────────────────────────────────
    # CORRECT: FAILURES AS FIRST-CLASS OBJECTS
    # ──────────────────────────────────────────────
    
    def correct(self, context: str, mistake: str, cause: str, lesson: str):
        """
        Record a mistake as a first-class lesson.

        Called by the agent mid-session when it catches itself
        making a mistake OR when the user corrects it.

        The four fields mirror Figueira's Mnemos.correct():
          context: what were you doing?
          mistake: what went wrong?
          cause: why did it happen?
          lesson: what should you do differently next time?

        Stores as structured markdown for both human and agent readability.
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        entry = (
            f"- **{now}** [{context[:40]}…] {mistake[:80]}. "
            f"Cause: {cause[:80]}. Lesson: {lesson[:80]}"
        )
        
        existing = self.sections.get('lessons', "")
        if existing == "No lessons recorded yet.":
            self.sections['lessons'] = entry
        else:
            # Deduplicate: check if same mistake already recorded
            if mistake[:50].lower() not in existing.lower():
                self.sections['lessons'] = existing + "\n" + entry
        
        # Also update self-image to reflect the learning
        existing_self = self.sections.get('self_image', "")
        lesson_short = lesson[:60]
        if lesson_short not in existing_self:
            update = f" | Learned: {lesson_short}"
            self.sections['self_image'] = (existing_self + update)[:500]
        
        self._save()
        self._cache_prewarm(self.generate_prewarm())
    
    # ──────────────────────────────────────────────
    # EXISTING METHODS (v1-compatible)
    # ──────────────────────────────────────────────
    
    def get(self, section: str) -> str:
        return self.sections.get(section, "")
    
    def set(self, section: str, content: str):
        self.sections[section] = content
    
    def append_to(self, section: str, content: str):
        existing = self.sections.get(section, "")
        if existing:
            self.sections[section] = existing + "\n\n" + content
        else:
            self.sections[section] = content
    
    def add_milestone(self, title: str, description: str):
        entry = f"### {title} ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n{description}"
        self.append_to('milestones', entry)
    
    def add_capability(self, name: str, description: str):
        entry = f"- **{name}**: {description}"
        existing = self.sections.get('capabilities', "")
        if name.lower() in existing.lower():
            return
        self.append_to('capabilities', entry)
    
    def reflect_on_session(self, session_summary: dict):
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
        
        if session_summary.get('future_directions'):
            self.append_to('aspirations', (
                f"After session on {datetime.now().strftime('%Y-%m-%d')}: "
                f"{' | '.join(session_summary['future_directions'][:2])}"
            ))
        
        self._save()
    
    def to_summary(self) -> str:
        """v1-compatible summary (legacy). Use generate_prewarm() instead."""
        return self.generate_prewarm()
    
    def status(self) -> str:
        lines = []
        lines.append("=" * 54)
        lines.append("  AUTOBIOGRAPHY — Persistent Identity")
        lines.append("=" * 54)
        lines.append(f"  Location: {self.path}")
        lines.append(f"  Sections: {len(self.sections)}")
        lines.append("")
        for key in ['self_image', 'values', 'relationship', 'capabilities',
                     'milestones', 'degradation', 'lessons', 'aspirations']:
            content = self.sections.get(key, "")
            if content:
                preview = content[:100].replace('\n', ' ')
                lines.append(f"  [{key:>16s}] {preview}...")
        lines.append("=" * 54)
        return "\n".join(lines)


# ──────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║      AUTOBIOGRAPHY — Push Memory Engine              ║")
    print("  ║  The agent's self-model pushes into context at start ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()
    print("  INSIGHT (Figueira): 'The agent will not call your")
    print("  memory tool. Push memory at session start.'")
    print()
    
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "test_autobiography_push.md")
    
    # ── Initial creation ──
    print("─" * 50)
    print("  [1] Initial creation")
    print("─" * 50)
    bio = Autobiography(path=tmp)
    print(f"  Created: {bio.path}")
    print(f"  Sections: {len(bio.sections)}")
    print()
    
    # ── Add some history ──
    bio.add_milestone(
        "RSI Stack — L1-L8 Complete",
        "Full recursive self-improvement stack: ReAct → MetaLoop → ToolForge → "
        "MSR → RSI Kernel → MetaKernel → OMC Talent Market → SelfModel"
    )
    bio.add_milestone(
        "Agent Evaluation Framework",
        "Optimal fingerprinting from climate science adapted for agent behavior attribution"
    )
    bio.add_milestone(
        "Immune Guardrail System",
        "3-layer immune-inspired guardrails (innate + adaptive + circuit breaker)"
    )
    bio.add_capability("Push Memory", "Self-model pushes into context at session start")
    bio._save()
    print("  Added 3 milestones + 1 capability")
    print()
    
    # ── RECORD A CORRECTION (failure as first-class) ──
    print("─" * 50)
    print("  [2] CORRECTION: Agent records a mistake mid-session")
    print("─" * 50)
    bio.correct(
        context="Building guardrail_bus.set_regime()",
        mistake="Called set_regime_factor twice — compounded scaling",
        cause="Forgot that factor multiplies CURRENT limits, not defaults",
        lesson="Always call set_regime('low_vol') first to reset defaults, "
               "then set the desired regime"
    )
    print("  ✅ Correction recorded as first-class lesson")
    print()
    
    # ── GENERATE PRE-WARM (push) ──
    print("─" * 50)
    print("  [3] generate_prewarm() — the push block")
    print("      (~500 tokens, ready for system prompt injection)")
    print("─" * 50)
    print()
    prewarm = bio.generate_prewarm(session_context={
        "continuity": "Next step: implement Breaktruth #14 vault publication"
    })
    token_count = len(prewarm.split())
    print(prewarm)
    print(f"\n  Token count: ~{token_count}")
    print()
    
    # ── Verify cache ──
    print("─" * 50)
    print("  [4] Cache verification")
    print("─" * 50)
    cached = Autobiography.load_prewarm_from_cache()
    if cached:
        print(f"  ✅ .memory_prewarm.json cache created")
        print(f"  Size: {len(cached)} chars")
    else:
        print("  ❌ Cache not created")
    print()
    
    # ── Status ──
    print("─" * 50)
    print("  STATUS")
    print("─" * 50)
    print(bio.status())
    print()
    
    # ── Compare pull vs push ──
    print("=" * 50)
    print("  PULL vs PUSH MEMORY")
    print("=" * 50)
    print()
    print("  Before (PULL):       After (PUSH):")
    print("  ──────────────       ─────────────")
    print("  to_summary() called   generate_prewarm() auto-injected")
    print("  by skill              at session start")
    print("  Agent must 'remember  Agent reads it because")
    print("  to call memory tool'  it's already in context")
    print("  Failures = raw events Failures = first-class lessons")
    print("  No continuity         Continuity from session context")
    print()
    print("  The difference: the agent doesn't need to remember.")
    print("  Memory is pushed at the one moment the agent")
    print("  is GUARANTEED to look: session start.")
    print("=" * 50)
    
    # Cleanup
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == '__main__':
    main()
