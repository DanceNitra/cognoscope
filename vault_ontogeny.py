#!/usr/bin/env python3
"""
vault_ontogeny.py — Vault Ontogeny & Age Pyramid

Tracks the vault's lifecycle: stubs → seedlings → growing → evergreens.
Produces visualisations and metrics about concept maturity, age distribution,
and lifecycle velocity.

Inspired by:
  - Population age pyramids (demographics)
  - Forest succession ecology (stages of growth)
  - Software maturity models (concept → proven)

Reports:
  1. Age Pyramid: how many concepts at each lifecycle stage
  2. Velocity: how fast stubs transition to evergreens
  3. Cohort Analysis: which domains have the oldest/youngest concepts
  4. Lifecycle Flow: where the vault is gaining/losing mass
  5. Maturity Gap: difference between domain importance and concept maturity
"""

import os, sys, re, json
from datetime import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass

sys.path.insert(0, os.path.expanduser("~/cognoscope"))

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
ONTOLOGY_DIR = os.path.join(os.path.expanduser("~/cognoscope"), "ontogeny")
os.makedirs(ONTOLOGY_DIR, exist_ok=True)

# Lifecycle stages with numeric maturity score
LIFECYCLE = {
    "stub": 0.0,
    "seedling": 0.25,
    "growing": 0.5,
    "evergreen": 1.0,
}

LIFECYCLE_ORDER = ["stub", "seedling", "growing", "evergreen"]


@dataclass
class ConceptProfile:
    """Profile of one concept's lifecycle status."""
    name: str
    domain: str
    status: str           # stub/seedling/growing/evergreen
    lines: int
    age_days: int         # days since created
    last_update_days: int  # days since last updated
    sections: int
    wikilinks_out: int
    wikilinks_in: int
    has_breaktruth: bool
    has_sources: bool
    maturity_score: float  # 0.0-1.0 computed


@dataclass
class OntogenySnapshot:
    """Full ontogeny picture of the vault."""
    timestamp: str
    total_concepts: int
    stage_distribution: dict[str, int]
    domain_maturity: dict[str, float]
    age_pyramid: dict[str, list[ConceptProfile]]
    velocity: dict       # transitions between stages
    oldest: list[ConceptProfile]
    newest: list[ConceptProfile]
    maturity_gaps: list[dict]


class VaultOntogeny:
    """Analyze vault lifecycle and maturity."""

    def __init__(self, concepts_dir: str = CONCEPTS_DIR):
        self.concepts_dir = concepts_dir

    def scan(self) -> OntogenySnapshot:
        """Full ontogeny scan of the vault."""
        profiles = []
        now = datetime.now()

        for fname in sorted(os.listdir(self.concepts_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self.concepts_dir, fname)
            name = fname.replace(".md", "")

            try:
                with open(path) as f:
                    content = f.read()
            except (IOError, OSError):
                continue

            if not content.startswith("---"):
                continue

            lines = content.count("\n") + 1
            if lines < 10:
                continue

            # Parse frontmatter
            fm = {}
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip()

            status = fm.get("status", "unknown").lower()
            domain = fm.get("domain", "unknown")

            # Age
            created_str = fm.get("created", "")
            updated_str = fm.get("updated", "")
            age_days = 0
            last_update_days = 0

            if created_str:
                try:
                    created = datetime.strptime(created_str[:10], "%Y-%m-%d")
                    age_days = (now - created).days
                except ValueError:
                    pass

            if updated_str:
                try:
                    updated = datetime.strptime(updated_str[:10], "%Y-%m-%d")
                    last_update_days = (now - updated).days
                except ValueError:
                    pass

            # Body
            body = parts[2] if len(parts) >= 3 else content
            sections = len(re.findall(r"^##\s+\S", body, re.MULTILINE))
            wikilinks_out = len(set(re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body)))
            has_bt = bool(re.search(r"##\s*Breaktruth\s*Claim", body, re.IGNORECASE))
            has_src = "sources:" in content[:500]

            # Backlinks
            # (quick scan — not full backlink audit)
            wikilinks_in = 0

            # Maturity score
            score = LIFECYCLE.get(status, 0.0)
            if lines >= 100:
                score += 0.1
            if sections >= 5:
                score += 0.1
            if wikilinks_out >= 10:
                score += 0.1
            if wikilinks_out >= 5:
                score += 0.05
            if has_bt:
                score += 0.1
            if has_src:
                score += 0.05
            maturity_score = min(1.0, score)

            profiles.append(ConceptProfile(
                name=name, domain=domain, status=status,
                lines=lines, age_days=age_days, last_update_days=last_update_days,
                sections=sections, wikilinks_out=wikilinks_out,
                wikilinks_in=wikilinks_in, has_breaktruth=has_bt,
                has_sources=has_src, maturity_score=maturity_score,
            ))

        # Stage distribution
        stage_dist = Counter(p.status for p in profiles)
        stage_dist["unknown"] += sum(1 for p in profiles if p.status not in LIFECYCLE)

        # Domain maturity
        domain_scores = defaultdict(list)
        for p in profiles:
            domain_scores[p.domain].append(p.maturity_score)
        domain_mat = {d: sum(s)/len(s) for d, s in domain_scores.items() if len(s) >= 2}

        # Age pyramid by stage
        pyramid = {}
        for stage in LIFECYCLE_ORDER:
            pyramid[stage] = [p for p in profiles if p.status == stage]

        # Velocity (estimated from status × lines)
        velocity = {
            "stub_to_seedling": sum(1 for p in profiles if p.status == "seedling" and p.lines < 30),
            "seedling_to_growing": sum(1 for p in profiles if p.status == "growing" and p.lines < 80),
            "growing_to_evergreen": sum(1 for p in profiles if p.status == "evergreen" and p.lines < 100),
            "evergreen_mature": sum(1 for p in profiles if p.status == "evergreen" and p.lines >= 200),
        }

        # Oldest and newest
        sorted_by_age = sorted(profiles, key=lambda p: -p.age_days)
        sorted_by_new = sorted(profiles, key=lambda p: p.last_update_days)

        # Maturity gaps — important domains with low maturity
        important_domains = {
            "Finance": 0.7, "Neuroscience": 0.7, "Sleep": 0.7,
            "AI": 0.6, "Causal Inference": 0.7, "Psychology": 0.6,
            "Philosophy": 0.5, "Statistics": 0.6, "Software Engineering": 0.5,
        }
        maturity_gaps = []
        for dom, expected in important_domains.items():
            actual = domain_mat.get(dom, 0)
            if actual < expected:
                maturity_gaps.append({
                    "domain": dom,
                    "expected_maturity": expected,
                    "actual_maturity": round(actual, 3),
                    "gap": round(expected - actual, 3),
                    "concepts": sum(1 for p in profiles if p.domain == dom),
                })
        maturity_gaps.sort(key=lambda x: -x["gap"])

        return OntogenySnapshot(
            timestamp=datetime.now().isoformat(),
            total_concepts=len(profiles),
            stage_distribution=dict(stage_dist),
            domain_maturity=domain_mat,
            age_pyramid=pyramid,
            velocity=velocity,
            oldest=sorted_by_age[:10],
            newest=sorted_by_new[:10],
            maturity_gaps=maturity_gaps,
        )

    def report(self, snapshot: OntogenySnapshot = None) -> str:
        """Generate ontogeny report."""
        if snapshot is None:
            snapshot = self.scan()

        lines = []
        lines.append("🌱 VAULT ONTOGENY")
        lines.append(f"   {snapshot.timestamp}")
        lines.append("")

        # ── AGE PYRAMID ──
        lines.append("── Age Pyramid (Lifecycle Stages) ──")
        total = snapshot.total_concepts
        for stage in LIFECYCLE_ORDER:
            count = snapshot.stage_distribution.get(stage, 0)
            score = LIFECYCLE.get(stage, 0) * 100
            if total > 0:
                bar = "█" * max(int(count / max(total, 1) * 80), 1)
            else:
                bar = ""
            lines.append(f"  {stage:12s}  {count:4d} ({count/total*100:5.1f}%)  maturity: {score:.0f}%  {bar}")

        # Unknown
        unknown = snapshot.stage_distribution.get("unknown", 0)
        if unknown:
            lines.append(f"  {'unknown':12s}  {unknown:4d} ({unknown/total*100:5.1f}%)")

        lines.append(f"  {'─'*50}")
        lines.append(f"  {'TOTAL':12s}  {total:4d} (100%)")
        lines.append("")

        # ── VELOCITY ──
        lines.append("── Lifecycle Velocity ──")
        v = snapshot.velocity
        lines.append(f"  Stubs needing expansion:    {v['stub_to_seedling']}")
        lines.append(f"  Seedlings → growing ready:  {v['seedling_to_growing']}")
        lines.append(f"  Growing → evergreen ready:  {v['growing_to_evergreen']}")
        lines.append(f"  Mature evergreens:          {v['evergreen_mature']}")
        lines.append("")

        # ── DOMAIN MATURITY ──
        lines.append("── Domain Maturity ──")
        sorted_domains = sorted(snapshot.domain_maturity.items(), key=lambda x: -x[1])
        for dom, maturity in sorted_domains[:15]:
            bar = "█" * max(int(maturity * 30), 1)
            lines.append(f"  {dom:30s}  {maturity:.3f}  {bar}")
        lines.append("")

        # ── MATURITY GAPS ──
        if snapshot.maturity_gaps:
            lines.append("── Maturity Gaps (Important Domains Below Expected) ──")
            for gap in snapshot.maturity_gaps[:5]:
                bar = "█" * max(int((1 - gap["gap"]) * 30), 1)
                lines.append(f"  🔴 {gap['domain']:25s}  expected={gap['expected_maturity']:.1f}  actual={gap['actual_maturity']:.3f}  gap={gap['gap']:.3f}")
                lines.append(f"     {gap['concepts']} concepts")
            lines.append("")

        # ── OLDEST ──
        lines.append("── Oldest Concepts (Never Expanded) ──")
        for p in snapshot.oldest[:5]:
            lines.append(f"  📅 {p.name:35s}  {p.age_days:4d}d old  {p.status:10s}  {p.lines:4d}L")
        lines.append("")

        # ── MOST STALE ──
        stale = [p for p in snapshot.oldest if p.last_update_days > 30 and p.status != "evergreen"]
        if stale:
            lines.append("── Most Stale (Needing Attention) ──")
            for p in stale[:5]:
                lines.append(f"  ⏰ {p.name:35s}  created {p.age_days}d ago, last update {p.last_update_days}d ago")
            lines.append("")

        # ── MATURITY DISTRIBUTION ──
        lines.append("── Maturity Score Distribution ──")
        buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for p in ['ConceptProfile']:  # placeholder
            pass
        # Actually count
        all_profiles = []
        if snapshot.age_pyramid:
            for stage_list in snapshot.age_pyramid.values():
                all_profiles.extend(stage_list)
        for p in all_profiles:
            s = p.maturity_score
            if s < 0.2: buckets["0.0-0.2"] += 1
            elif s < 0.4: buckets["0.2-0.4"] += 1
            elif s < 0.6: buckets["0.4-0.6"] += 1
            elif s < 0.8: buckets["0.6-0.8"] += 1
            else: buckets["0.8-1.0"] += 1

        for bucket, count in buckets.items():
            if total > 0:
                bar = "█" * max(int(count / max(total, 1) * 60), 1)
            else:
                bar = ""
            lines.append(f"  {bucket:10s}  {count:4d} ({count/total*100:5.1f}%)  {bar}")

        return "\n".join(lines)

    def save(self, snapshot: OntogenySnapshot = None):
        """Save ontogeny snapshot to file."""
        if snapshot is None:
            snapshot = self.scan()
        
        data = {
            "timestamp": snapshot.timestamp,
            "total_concepts": snapshot.total_concepts,
            "stage_distribution": snapshot.stage_distribution,
            "domain_maturity": snapshot.domain_maturity,
            "velocity": snapshot.velocity,
            "maturity_gaps": snapshot.maturity_gaps,
        }
        
        path = os.path.join(ONTOLOGY_DIR, "latest_ontogeny.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        # Save history
        hist_path = os.path.join(ONTOLOGY_DIR, "ontogeny_history.json")
        history = []
        if os.path.exists(hist_path):
            try:
                with open(hist_path) as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []
        
        history.append({
            "timestamp": snapshot.timestamp,
            "total_concepts": snapshot.total_concepts,
            "evergreens": snapshot.stage_distribution.get("evergreen", 0),
            "growing": snapshot.stage_distribution.get("growing", 0),
            "seedlings": snapshot.stage_distribution.get("seedling", 0),
            "stubs": snapshot.stage_distribution.get("stub", 0),
            "mean_maturity": round(sum(
                p.maturity_score for stage_list in snapshot.age_pyramid.values()
                for p in stage_list
            ) / max(snapshot.total_concepts, 1), 4) if hasattr(snapshot, 'age_pyramid') else 0,
        })
        
        if len(history) > 50:
            history = history[-50:]
        
        with open(hist_path, "w") as f:
            json.dump(history, f, indent=2)

    def history_report(self) -> str:
        """Show ontogeny trajectory over time."""
        hist_path = os.path.join(ONTOLOGY_DIR, "ontogeny_history.json")
        if not os.path.exists(hist_path):
            return "No history yet. Run --scan first."
        
        with open(hist_path) as f:
            history = json.load(f)
        
        if len(history) < 2:
            return "Need at least 2 data points."
        
        lines = []
        lines.append("📊 VAULT ONTOGENY HISTORY")
        lines.append("")
        lines.append(f"  {len(history)} data points")
        lines.append("")
        
        first = history[0]
        last = history[-1]
        
        # Growth
        pop_growth = last["total_concepts"] - first["total_concepts"]
        eg_growth = last["evergreens"] - first["evergreens"]
        stub_change = last["stubs"] - first["stubs"]
        
        lines.append(f"  Population: {first['total_concepts']} → {last['total_concepts']}  ({'+' if pop_growth > 0 else ''}{pop_growth})")
        lines.append(f"  Evergreens:  {first['evergreens']} → {last['evergreens']}  ({'+' if eg_growth > 0 else ''}{eg_growth})")
        lines.append(f"  Stubs:       {first['stubs']} → {last['stubs']}  ({'+' if stub_change > 0 else ''}{stub_change})")
        
        lines.append("")
        lines.append("  Evolution per snapshot:")
        for h in history:
            lines.append(f"    {h['timestamp'][:10]}  pop={h['total_concepts']}  eg={h['evergreens']}  gr={h['growing']}  sd={h['seedlings']}  st={h['stubs']}")
        
        return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vault Ontogeny — Lifecycle & Maturity")
    parser.add_argument("--scan", action="store_true", help="Full ontogeny scan")
    parser.add_argument("--save", action="store_true", help="Scan + save to file")
    parser.add_argument("--history", action="store_true", help="Show ontogeny history")
    parser.add_argument("--gaps", action="store_true", help="Show maturity gaps only")
    
    args = parser.parse_args()
    
    onto = VaultOntogeny()
    
    if args.history:
        print(onto.history_report())
        sys.exit(0)
    
    if args.save or args.scan or not any([args.gaps]):
        snapshot = onto.scan()
        if args.save:
            onto.save(snapshot)
        
        if args.gaps:
            print("── Maturity Gaps ──")
            for gap in snapshot.maturity_gaps:
                print(f"  🔴 {gap['domain']:25s}  expected={gap['expected_maturity']:.1f}  actual={gap['actual_maturity']:.3f}  ({gap['concepts']} concepts)")
        elif args.scan:
            print(onto.report(snapshot))
        else:
            # Default: full report
            print(onto.report(snapshot))
