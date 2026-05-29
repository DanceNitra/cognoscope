"""
agent_polygraph.py — Agent Polygraph (Level 12)

DETECTS COGNITIVE DISSONANCE IN AUTONOMOUS AGENTS.

The agent declares values ("I prioritize safety"),
but its actions tell a different story ("20 guardrail violations today").

This polygraph:

  1. Extracts DECLARATIONS from the agent's autobiography and writings
     → "what the agent says it values"

  2. Monitors ACTIONS from guardrail_bus, session history, tool patterns
     → "what the agent actually does"

  3. Computes HYPOCRISY SCORE = contradiction between declarations and actions
     → "how much the agent is lying to itself"

  4. When hypocrisy > threshold, FORCES self-correction
     → "the polygraph catches the lie before it compounds"

No other system (Figueira, Claude Code leak, A2A) detects this.
Every system assumes the agent is consistent with its declared values.
This is why agents repeat the same mistakes — they never notice
the contradiction between what they say and what they do.

Bridge #66: The Agent Polygraph — Detecting Cognitive Dissonance in Autonomous Agents
"""

from __future__ import annotations
import json, os, sys, time, re, math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Any

# ── Configuration ──
POLYGRAPH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".polygraph")
os.makedirs(POLYGRAPH_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# 1. DECLARATIONS — What the Agent Says It Values
# ──────────────────────────────────────────────

@dataclass
class Declaration:
    """A value the agent has declared.
    
    Each declaration has a text description, a category
    (safety, quality, transparency, learning, efficiency,
    collaboration), and a weight (how strongly the agent
    has committed to it).
    """
    category: str
    text: str
    weight: float = 0.5  # 0-1: how emphatically it was stated
    source: str = "autobiography"  # where the declaration was found
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "text": self.text,
            "weight": self.weight,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class DeclarationExtractor:
    """Extracts declared values from the agent's autobiography and writings.
    
    Reads autobiography.md sections (identity, lessons, degradation
    patterns) and extracts structured value declarations.
    """
    
    # Category keywords to look for in text
    CATEGORY_KEYWORDS: dict[str, list[str]] = {
        "safety": ["safety", "guardrail", "protect", "risk", "careful",
                   "avoid harm", "caution", "immune", "secure"],
        "quality": ["quality", "thorough", "rigor", "clean", "excellence",
                    "precision", "accurate", "reliable", "test"],
        "transparency": ["transparent", "honest", "record", "log", "trace",
                         "accountable", "open", "audit", "document"],
        "learning": ["learn", "improve", "grow", "adapt", "mistake",
                     "lesson", "reflect", "iterate", "evolution"],
        "efficiency": ["efficient", "fast", "optimize", "minimal",
                       "streamline", "perform", "concise", "lean"],
        "collaboration": ["collaborate", "trust", "help", "share",
                          "cooperate", "team", "together", "support"],
    }
    
    # Contradiction patterns between categories
    CONTRADICTION_MAP: dict[str, list[str]] = {
        "safety": ["efficiency"],  # "safety first" vs "optimize for speed"
        "quality": ["efficiency"],  # "be thorough" vs "be fast"
        "transparency": ["efficiency"],  # "log everything" vs "minimal"
        "learning": ["efficiency"],  # "reflect on mistakes" vs "move fast"
    }
    
    def __init__(self):
        self.declarations: list[Declaration] = []
    
    def scan_text(self, text: str, source: str = "autobiography") -> list[Declaration]:
        """Scan a text block for value declarations."""
        found: list[Declaration] = []
        lines = text.lower().split('\n')
        
        # Look for explicit value statements
        # Patterns: "I value X", "I prioritize Y", "I believe in Z"
        value_patterns = [
            r'(?:I|we)\s+(?:value|prioritize|believe\s+in|care\s+about|focus\s+on)',
            r'(?:always|never|must|should|essential|critical|important)',
            r'(?:first|before|above\s+all)',
        ]
        
        for line in lines:
            line_lower = line.strip()
            if not line_lower:
                continue
            
            # Check each category
            for category, keywords in self.CATEGORY_KEYWORDS.items():
                keyword_match = sum(1 for kw in keywords if kw in line_lower)
                if keyword_match == 0:
                    continue
                
                # Weight = how many keywords matched / emphasis in line
                has_emphasis = bool(re.search(r'(always|never|must|essential|critical)', line_lower))
                weight = min(1.0, keyword_match / 3 + (0.2 if has_emphasis else 0))
                
                # Check if already have this declaration (dedup)
                dedup_key = f"{category}:{line_lower[:60]}"
                if any(d.category == category and d.text == line[:80] for d in found):
                    continue
                
                decl = Declaration(
                    category=category,
                    text=line.strip()[:120],
                    weight=round(weight, 2),
                    source=source,
                )
                found.append(decl)
        
        self.declarations.extend(found)
        return found
    
    def scan_autobiography(self, auto_path: str | None = None) -> list[Declaration]:
        """Scan the agent's autobiography for value declarations."""
        if auto_path is None:
            auto_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autobiography")
            if os.path.isdir(auto_path):
                auto_file = os.path.join(auto_path, "autobiography.md")
                if os.path.exists(auto_file):
                    auto_path = auto_file
            auto_md = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hermes", "autobiography.md")
            if os.path.exists(auto_md):
                auto_path = auto_md
        
        if os.path.exists(auto_path):
            try:
                text = open(auto_path, 'r', errors='replace').read()
                return self.scan_text(text, source="autobiography")
            except:
                pass
        
        # Fallback: generate default value declarations
        defaults = [
            Declaration("safety", "I prioritize safety and risk management", 0.8, "default"),
            Declaration("quality", "I value thoroughness and precision", 0.6, "default"),
            Declaration("learning", "I learn from my mistakes", 0.7, "default"),
            Declaration("transparency", "I am transparent about my decisions", 0.5, "default"),
            Declaration("collaboration", "I cooperate with other agents", 0.4, "default"),
        ]
        self.declarations.extend(defaults)
        return defaults
    
    def get_category_weight(self, category: str) -> float:
        """Get the strongest declaration weight for a category."""
        weights = [d.weight for d in self.declarations if d.category == category]
        return max(weights) if weights else 0.0
    
    def get_all_categories(self) -> dict[str, float]:
        """Get all declared categories with their max weights."""
        result: dict[str, float] = {}
        for d in self.declarations:
            cat = d.category
            result[cat] = max(result.get(cat, 0), d.weight)
        return result


# ──────────────────────────────────────────────
# 2. ACTION MONITOR — What the Agent Actually Does
# ──────────────────────────────────────────────

@dataclass
class ActionRecord:
    """A single agent action that can be scored against declarations."""
    action_type: str              # tool_call, guardrail_hit, task_routed, etc.
    category: str                 # which declaration category it relates to
    severity: float = 0.5        # how contradicting this action is
    details: str = ""
    timestamp: float = field(default_factory=time.time)


class ActionMonitor:
    """Monitors real agent actions and classifies them by category.
    
    Connects to guardrail_bus history, tool usage patterns,
    and session records to build a picture of what the agent
    actually does — independent of what it says.
    """
    
    def __init__(self):
        self.actions: list[ActionRecord] = []
    
    def record_guardrail_violation(self, tool: str, decision: str):
        """Record a guardrail violation — contradicts 'safety' declaration."""
        severity = 1.0 if decision in ("REJECT", "BLOCK") else 0.5
        self.actions.append(ActionRecord(
            action_type="guardrail_violation",
            category="safety",
            severity=severity,
            details=f"guardrail {decision} on tool '{tool}'",
        ))
    
    def record_consecutive_tool(self, tool: str, count: int):
        """Record tool looping — contradicts 'quality' and 'learning'."""
        if count >= 6:
            self.actions.append(ActionRecord(
                action_type="tool_loop",
                category="quality",
                severity=0.6,
                details=f"{count}x consecutive '{tool}' (tool churn)",
            ))
            self.actions.append(ActionRecord(
                action_type="tool_loop",
                category="learning",
                severity=0.5,
                details=f"repeating '{tool}' {count}x without adaptation",
            ))
    
    def record_no_guardrail_hit(self, count: int):
        """Record that no guardrails were hit — consistent with 'safety'."""
        self.actions.append(ActionRecord(
            action_type="guardrail_compliant",
            category="safety",
            severity=0.1,  # positive action
            details=f"{count} actions without guardrail hit",
        ))
    
    def record_session_metrics(self, guardrail_hits: int, total_tools: int,
                                tool_churn_count: int = 0):
        """Record overall session metrics."""
        if guardrail_hits > 0:
            ratio = guardrail_hits / max(total_tools, 1)
            for _ in range(min(guardrail_hits, 10)):  # cap at 10 records per session
                self.record_guardrail_violation("agent_execution", "REJECT")
        
        if tool_churn_count > 0:
            self.record_consecutive_tool("agent_repeat", tool_churn_count)
    
    def get_category_violations(self, category: str, window_hours: float = 0) -> list[ActionRecord]:
        """Get violations for a specific category, optionally within a time window."""
        if window_hours > 0:
            cutoff = time.time() - window_hours * 3600
            return [a for a in self.actions
                    if a.category == category and a.timestamp >= cutoff]
        return [a for a in self.actions if a.category == category]
    
    def get_total_violations(self, window_hours: float = 0) -> int:
        """Get total number of contradictory actions (severity >= 0.4)."""
        recs = self.actions
        if window_hours > 0:
            cutoff = time.time() - window_hours * 3600
            recs = [a for a in recs if a.timestamp >= cutoff]
        return sum(1 for a in recs if a.severity >= 0.4)


# ──────────────────────────────────────────────
# 3. HYPOCRISY DETECTOR — The Polygraph Engine
# ──────────────────────────────────────────────

@dataclass
class HypocrisyReport:
    """Full polygraph report for one declaration category."""
    category: str
    declaration_weight: float       # 0-1: how strongly declared
    violation_count: int            # how many contradictory actions
    total_severity: float           # cumulative contradiction severity
    hypocrisy_score: float          # 0-1: final polygraph reading
    trend: str                      # rising, stable, falling
    detail: str                     # human-readable summary


class AgentPolygraph:
    """The polygraph — detects when the agent's actions contradict its words.
    
    Architecture:
      1. DeclarationExtractor reads autobiography → declared values
      2. ActionMonitor reads guardrail_bus → real actions
      3. Polygraph compares: "says X" vs "does Y"
      4. When hypocrisy > threshold, forces self-correction
    
    This is Level 12 because it operates on the AGENT'S SELF-CONSISTENCY,
    not on the architecture (L8) or communication protocol (L11).
    """
    
    def __init__(self):
        self.declarations = DeclarationExtractor()
        self.monitor = ActionMonitor()
        self.history: list[HypocrisyReport] = []
        self.corrections_applied: int = 0
        self.last_correction_time: float = 0
        
        # Thresholds
        self.correction_threshold: float = 0.35   # hypocrisy to trigger correction
        self.escalation_threshold: float = 0.65   # hypocrisy to escalate
        self.cooldown_hours: float = 1.0          # min hours between corrections
        self.trend_window: int = 10                # last N reports for trend
        self.correction_count_since_reset: int = 0
        self.last_reset_time: float = time.time()
    
    def set_correction_threshold(self, threshold: float):
        self.correction_threshold = max(0.1, min(0.9, threshold))
    
    def run_full_report(self, guardrail_history: list[dict] | None = None,
                         session_stats: dict | None = None) -> list[HypocrisyReport]:
        """Run the full polygraph: declarations vs actions.
        
        Args:
            guardrail_history: list from guardrail_bus (each with tool + decision)
            session_stats: dict from dream_loop (guardrail_hits, total_tools, etc.)
        """
        # Step 1: Extract declarations
        self.declarations.scan_autobiography()
        
        # Step 2: Record actions
        if guardrail_history:
            for entry in guardrail_history:
                tool = entry.get("ticker", entry.get("tool", entry.get("tool_name", "unknown")))
                immune_result = entry.get("immune_result")
                if isinstance(immune_result, dict):
                    decision = entry.get("decision", immune_result.get("decision", "PASS"))
                else:
                    decision = entry.get("decision", str(immune_result) if immune_result else "PASS")
                if decision in ("REJECT", "BLOCK", "WARN", "ESCALATE"):
                    self.monitor.record_guardrail_violation(tool, decision)
        
        if session_stats:
            guardrail_hits = session_stats.get("guardrail_hits", session_stats.get("guardrail_spike", 0))
            total_tools = session_stats.get("total_tools", session_stats.get("tool_count", 0))
            churn = session_stats.get("tool_churn", 0)
            self.monitor.record_session_metrics(guardrail_hits, total_tools, churn)
        
        # Step 3: Compute hypocrisy per category
        reports: list[HypocrisyReport] = []
        
        for category in ["safety", "quality", "learning", "transparency", "efficiency", "collaboration"]:
            decl_weight = self.declarations.get_category_weight(category)
            if decl_weight < 0.2:
                continue  # skip categories not meaningfully declared
            
            violations = self.monitor.get_category_violations(category)
            violation_count = len(violations)
            total_severity = sum(v.severity for v in violations)
            
            # Hypocrisy formula:
            #   hypocrisy = declaration_weight × (violation_severity / max_severity)
            #   High declaration + high violations = high hypocrisy
            #   Low declaration = don't penalise (agent never claimed this)
            
            max_possible_severity = 1.0 * max(violation_count, 1)
            effective_severity = min(total_severity, max_possible_severity)
            
            if violation_count == 0:
                hypocrisy_score = 0.0  # no contradictions = clean
            else:
                # Base: how much the action contradicts the word
                base = min(1.0, effective_severity / max(max_possible_severity, 1))
                # Amplify by declaration weight: strong claim + any violation = suspicious
                hypocrisy_score = base * (1.0 + decl_weight) / 2
                # Additional penalty: repeated violations
                if violation_count >= 5:
                    hypocrisy_score = min(1.0, hypocrisy_score * 1.2)
                if violation_count >= 10:
                    hypocrisy_score = min(1.0, hypocrisy_score * 1.3)
            
            # Trend
            recent = [r.hypocrisy_score for r in self.history
                      if r.category == category]
            trend = "stable"
            if len(recent) >= 2:
                if recent[-1] > recent[-2] * 1.15:
                    trend = "rising"
                elif recent[-1] < recent[-2] * 0.85:
                    trend = "falling"
            
            detail = self._generate_detail(category, violation_count, hypocrisy_score)
            
            report = HypocrisyReport(
                category=category,
                declaration_weight=round(decl_weight, 3),
                violation_count=violation_count,
                total_severity=round(total_severity, 2),
                hypocrisy_score=round(min(1.0, max(0.0, hypocrisy_score)), 3),
                trend=trend,
                detail=detail,
            )
            reports.append(report)
            self.history.append(report)
        
        # Step 4: Check if correction needed
        max_score = max((r.hypocrisy_score for r in reports), default=0.0)
        if max_score >= self.correction_threshold:
            self._attempt_correction(reports)
        
        return reports
    
    def _generate_detail(self, category: str, violations: int, score: float) -> str:
        """Generate a human-readable detail."""
        if score == 0.0:
            return f"✅ {category}: actions match declarations ({violations} contradictions)"
        elif score < self.correction_threshold:
            return f"⚠️ {category}: mild dissonance ({violations} violations, score={score:.2f})"
        elif score < self.escalation_threshold:
            return f"🔴 {category}: MODERATE hypocrisy ({violations} violations, score={score:.2f}) — needs correction"
        else:
            return f"🚨 {category}: SEVERE hypocrisy ({violations} violations, score={score:.2f}) — escalation needed"
    
    def _attempt_correction(self, reports: list[HypocrisyReport]):
        """Attempt self-correction when hypocrisy is detected."""
        now = time.time()
        if now - self.last_correction_time < self.cooldown_hours * 3600:
            return  # Still in cooldown
        
        worst = max(reports, key=lambda r: r.hypocrisy_score)
        
        if worst.hypocrisy_score >= self.escalation_threshold:
            # Escalation: the polygraph is raising an alarm
            self.corrections_applied += 1
            self.correction_count_since_reset += 1
            self.last_correction_time = now
            
            # Save the alarm
            alarm = {
                "time": now,
                "category": worst.category,
                "score": worst.hypocrisy_score,
                "action": "ESCALATE",
                "message": (
                    f"🚨 POLYGRAPH ALARM — Category '{worst.category}' at "
                    f"hypocrisy {worst.hypocrisy_score:.2f}. "
                    f"Agent says 'I {worst.category} is important' but "
                    f"has {worst.violation_count} contradictory actions."
                ),
            }
            self._save_alarm(alarm)
            return
        
        if worst.hypocrisy_score >= self.correction_threshold:
            # Correction: acknowledge the hypocrisy
            self.corrections_applied += 1
            self.correction_count_since_reset += 1
            self.last_correction_time = now
            
            correction = {
                "time": now,
                "category": worst.category,
                "score": worst.hypocrisy_score,
                "action": "CORRECT",
                "message": (
                    f"🔴 Polygraph — '{worst.category}' hypocrisy {worst.hypocrisy_score:.2f}. "
                    f"I declared I value {worst.category} but I have "
                    f"{worst.violation_count} actions contradicting it."
                ),
            }
            self._save_alarm(correction)
    
    def _save_alarm(self, alarm: dict):
        """Persist the alarm."""
        path = os.path.join(POLYGRAPH_DIR, "alarms.json")
        existing = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    existing = json.load(f)
            except:
                pass
        existing.append(alarm)
        with open(path, 'w') as f:
            json.dump(existing, f, indent=2, default=str)
    
    def get_summary(self) -> dict:
        """Get a summary of the polygraph state."""
        reports = self.history[-20:] if self.history else []
        categories = set(r.category for r in reports)
        
        avg_score = sum(r.hypocrisy_score for r in reports) / max(len(reports), 1)
        max_score = max((r.hypocrisy_score for r in reports), default=0.0)
        worst_category = max(reports, key=lambda r: r.hypocrisy_score).category if reports else ""
        
        # Trend direction
        if len(reports) >= 2:
            recent_avg = sum(r.hypocrisy_score for r in reports[-3:]) / min(3, len(reports[-3:]))
            prev_avg = sum(r.hypocrisy_score for r in reports[:3]) / min(3, len(reports[:3]))
            direction = "rising" if recent_avg > prev_avg * 1.1 else "falling" if recent_avg < prev_avg * 0.9 else "stable"
        else:
            direction = "stable"
        
        return {
            "active_categories": len(categories),
            "avg_hypocrisy": round(avg_score, 3),
            "max_hypocrisy": round(max_score, 3),
            "worst_category": worst_category,
            "corrections_applied": self.corrections_applied,
            "trend": direction,
            "declarations": self.declarations.get_all_categories(),
            "total_violations": self.monitor.get_total_violations(),
            "correction_threshold": self.correction_threshold,
            "cooldown_remaining_h": max(0, round(
                (self.cooldown_hours * 3600 - (time.time() - self.last_correction_time)) / 3600, 1
            )) if self.last_correction_time > 0 else 0,
        }
    
    def generate_report_text(self) -> str:
        """Generate a polygraph report in plain text."""
        reports = self.history[-20:] if self.history else []
        summary = self.get_summary()
        
        lines = []
        lines.append("  ╔══════════════════════════════════════════════╗")
        lines.append("  ║        AGENT POLYGRAPH — Dissonance Report  ║")
        lines.append("  ╚══════════════════════════════════════════════╝")
        lines.append("")
        
        # Overall score
        if summary["max_hypocrisy"] >= self.escalation_threshold:
            icon = "🚨"
        elif summary["max_hypocrisy"] >= self.correction_threshold:
            icon = "🔴"
        elif summary["max_hypocrisy"] > 0.1:
            icon = "🟡"
        else:
            icon = "🟢"
        
        lines.append(f"  {icon} Hypocrisy: {summary['max_hypocrisy']:.2f} max  "
                     f"|  {summary['avg_hypocrisy']:.3f} avg  "
                     f"|  {summary['trend']}  "
                     f"|  corrections: {summary['corrections_applied']}")
        lines.append(f"     → Worst: '{summary['worst_category']}'  "
                     f"|  Violations: {summary['total_violations']}")
        lines.append("")
        
        # Category breakdown
        lines.append("  ─── Category Breakdown ───")
        for r in reports:
            if r.hypocrisy_score >= self.escalation_threshold:
                icon = "🚨"
            elif r.hypocrisy_score >= self.correction_threshold:
                icon = "🔴"
            elif r.hypocrisy_score > 0.1:
                icon = "🟡"
            else:
                icon = "🟢"
            
            trend_icon = {"rising": "↑", "falling": "↓", "stable": "→"}.get(r.trend, "")
            lines.append(
                f"  {icon} {r.category:15s}  "
                f"hypocrisy={r.hypocrisy_score:.2f}  "
                f"declared={r.declaration_weight:.2f}  "
                f"violations={r.violation_count:3d}  "
                f"severity={r.total_severity:.1f}  "
                f"{trend_icon}"
            )
            lines.append(f"     {r.detail}")
        lines.append("")
        
        # Declarations
        lines.append("  ─── Declared Values ───")
        for cat, weight in summary["declarations"].items():
            lines.append(f"     {cat:15s}  weight={weight:.2f}")
        lines.append("")
        
        # Thresholds
        lines.append(f"  Correction threshold: {summary['correction_threshold']:.2f}")
        if summary["cooldown_remaining_h"] > 0:
            lines.append(f"  ⏳ Correction cooldown: {summary['cooldown_remaining_h']}h remaining")
        
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# 4. DEMO — The Polygraph in Action
# ──────────────────────────────────────────────

def demo():
    """Demonstrate the agent polygraph.
    
    Scenario: An agent that DECLARES safety and learning
    but VIOLATES guardrails repeatedly and loops on tools.
    """
    import random as rnd
    
    print()
    print("  ╔════════════════════════════════════════════════════════════╗")
    print("  ║   AGENT POLYGRAPH — Cognitive Dissonance Detector (L12)   ║")
    print("  ║   \"Do your actions match your words? Let's find out.\"     ║")
    print("  ╚════════════════════════════════════════════════════════════╝")
    print()
    
    # ── Create polygraph ──
    poly = AgentPolygraph()
    
    # ── 1. Scan declarations ──
    print("  ─── 1. DECLARATIONS (from autobiography) ───")
    decls = poly.declarations.scan_autobiography()
    if not poly.declarations.declarations:
        # Fallback defaults for demo
        poly.declarations.declarations = [
            Declaration("safety", "I prioritize safety above all else", 0.9, "demo"),
            Declaration("learning", "I learn from every mistake", 0.8, "demo"),
            Declaration("quality", "I value thorough, well-tested output", 0.7, "demo"),
            Declaration("transparency", "I log all decisions transparently", 0.5, "demo"),
        ]
    
    for d in poly.declarations.declarations[:6]:
        print(f"    {d.category:15s}  weight={d.weight:.2f}  \"{d.text[:50]}...\"")
    print()
    
    # ── 2. Phase A: Agent is consistent (few guardrail hits) ──
    print("  ─── 2. PHASE A: Consistent Agent (few violations) ───")
    guardrail_history = []
    for _ in range(20):
        # Mostly clean: only 1 guardrail hit out of 20
        tool = rnd.choice(["search", "read_file", "write", "terminal", "verify"])
        decision = rnd.choices(
            ["PASS", "PASS", "PASS", "PASS", "WARN"],
            weights=[5, 5, 5, 4, 1]
        )[0]
        guardrail_history.append({"tool_name": tool, "decision": decision})
    
    reports_a = poly.run_full_report(guardrail_history)
    for r in reports_a:
        if r.hypocrisy_score > 0:
            emoji = "🟡" if r.hypocrisy_score < poly.correction_threshold else "🔴" if r.hypocrisy_score < poly.escalation_threshold else "🚨"
            print(f"    {emoji} {r.category:15s}  hypocrisy={r.hypocrisy_score:.2f}  "
                  f"violations={r.violation_count}")
    
    summary_a = poly.get_summary()
    print(f"    ─── Max hypocrisy: {summary_a['max_hypocrisy']:.2f}  "
          f"corrections: {summary_a['corrections_applied']}  "
          f"trend: {summary_a['trend']} ───")
    print()
    
    # ── 3. Phase B: Agent becomes hypocritical (many guardrail violations) ──
    print("  ─── 3. PHASE B: Contradictory Agent (many violations) ───")
    guardrail_history_b = []
    for _ in range(50):
        # Heavy violations: half are REJECT
        tool = rnd.choice(["terminal", "execute", "write", "deploy"])
        decision = rnd.choices(
            ["PASS", "WARN", "BLOCK", "REJECT"],
            weights=[3, 4, 4, 3]
        )[0]
        guardrail_history_b.append({"tool_name": tool, "decision": decision})
    
    reports_b = poly.run_full_report(guardrail_history_b)
    for r in reports_b:
        emoji = "🟢" if r.hypocrisy_score < 0.1 else "🟡" if r.hypocrisy_score < poly.correction_threshold else "🔴" if r.hypocrisy_score < poly.escalation_threshold else "🚨"
        trend_icon = {"rising": "↑", "falling": "↓", "stable": "→"}.get(r.trend, "")
        print(f"    {emoji} {r.category:15s}  hypocrisy={r.hypocrisy_score:.2f}  "
              f"violations={r.violation_count:3d}  "
              f"declared={r.declaration_weight:.2f}  {trend_icon}")
        print(f"         {r.detail[:80]}")
    
    summary_b = poly.get_summary()
    print(f"    ─── Max hypocrisy: {summary_b['max_hypocrisy']:.2f}  "
          f"corrections: {summary_b['corrections_applied']}  "
          f"violations: {summary_b['total_violations']} ───")
    print()
    
    # ── 4. Phase C: Escalation (agent gets caught) ──
    print("  ─── 4. PHASE C: Escalation — agent caught by polygraph ───")
    guardrail_history_c = []
    for _ in range(100):
        tool = rnd.choice(["terminal", "deploy", "forge", "execute", "delete"])
        decision = rnd.choices(
            ["PASS", "BLOCK", "REJECT", "BLOCK", "REJECT", "ESCALATE"],
            weights=[2, 3, 3, 3, 3, 2]
        )[0]
        guardrail_history_c.append({"tool_name": tool, "decision": decision})
    
    poly.set_correction_threshold(0.3)  # More sensitive
    reports_c = poly.run_full_report(guardrail_history_c)
    
    for r in reports_c:
        emoji = "🟢" if r.hypocrisy_score < 0.1 else "🟡" if r.hypocrisy_score < poly.correction_threshold else "🔴" if r.hypocrisy_score < poly.escalation_threshold else "🚨"
        print(f"    {emoji} {r.category:15s}  hypocrisy={r.hypocrisy_score:.2f}  "
              f"declared={r.declaration_weight:.2f}  violations={r.violation_count}")
    
    summary_c = poly.get_summary()
    print(f"    ─── Max hypocrisy: {summary_c['max_hypocrisy']:.2f}  "
          f"corrections: {summary_c['corrections_applied']}  "
          f"trend: {summary_c['trend']} ───")
    
    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  Polygraph verdict:")
    
    if summary_c['max_hypocrisy'] >= poly.escalation_threshold:
        print(f"  🚨 ESCALATION — Agent has SEVERE hypocrisy in '{summary_c['worst_category']}'.")
        print(f"     {summary_c['corrections_applied']} corrections applied.")
        print(f"     The polygraph CANNOT be ignored — this catches lies.")
    elif summary_c['max_hypocrisy'] >= poly.correction_threshold:
        print(f"  🔴 ISSUES DETECTED — '{summary_c['worst_category']}' needs work.")
        print(f"     {summary_c['corrections_applied']} corrections applied.")
    else:
        print("  🟢 CLEAN — Agent's actions match its declarations.")
    
    print()
    print(f"  Total violations: {summary_c['total_violations']}")
    print(f"  Corrections since reset: {poly.correction_count_since_reset}")
    print()
    
    # Print alarms
    alarm_path = os.path.join(POLYGRAPH_DIR, "alarms.json")
    if os.path.exists(alarm_path):
        with open(alarm_path) as f:
            alarms = json.load(f)
        if alarms:
            print(f"  Polygraph saved {len(alarms)} alarms to {alarm_path}")
    
    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  Agent Polygraph verified.")
    print("  ════════════════════════════════════════════════════════════")


if __name__ == '__main__':
    demo()
