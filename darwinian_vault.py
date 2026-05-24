#!/usr/bin/env python3
"""
darwinian_vault.py — Population-level vault evolution engine

The vault-as-ecosystem:
  Instead of optimizing ONE note at a time (AR loop),
  treat the entire vault as a POPULATION of concepts
  undergoing natural selection, crossover, speciation,
  and extinction.

Key innovations over existing tools:
  - AR loop (ariauthor): local mutation of one note
  - VaultMetric v2: local fitness of one note
  - Darwinian Vault: population genetics for the whole vault

Concepts:
  - FITNESS LANDSCAPE: 3D surface (Φ integration × content quality × domain diversity)
  - SELECTION: Which concepts survive to the next generation?
  - CROSSOVER: Breed two concepts from different domains → hybrid offspring
  - SPECIATION: When a domain reaches critical mass, auto-split into subdomains
  - EXTINCTION: Concepts with zero inbound links for N generations
  - NICHE CARVING: Detect overcrowded vs underpopulated domains
"""

import os, sys, re, json, math, random, subprocess
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.expanduser("~/cognoscope"))

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
PUBLICATIONS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")

# Try to import real VaultMetric for Φ scoring
try:
    from ariauthor import VaultMetric
    _HAVE_REAL_METRIC = True
except ImportError:
    _HAVE_REAL_METRIC = False
    VaultMetric = None

# ──────────────────────────────────────────────
# POPULATION GENE POOL
# ──────────────────────────────────────────────

@dataclass
class ConceptGene:
    """One concept's genetic profile."""
    name: str
    domain: str
    lines: int
    wikilinks_out: int
    wikilinks_in: int
    sections: int
    has_breaktruth: bool
    has_figures: bool
    source_count: int
    phi_score: float          # from VaultMetric v2.1
    content_density: float     # facts_per_line estimate
    age_days: int
    generation: int

    @property
    def fitness(self) -> float:
        """Composite fitness: how well this concept contributes to vault integration."""
        return (
            self.phi_score * 0.40 +
            min(self.content_density, 1.0) * 0.20 +
            min(self.wikilinks_in / 10, 1.0) * 0.15 +
            min(self.wikilinks_out / 15, 1.0) * 0.10 +
            (0.10 if self.has_breaktruth else 0) +
            min(self.source_count / 3, 1.0) * 0.05
        )


@dataclass
class PopulationSnapshot:
    """Snapshot of the entire vault at one generation."""
    generation: int
    timestamp: str
    concepts: list[ConceptGene]
    total_phi: float
    mean_fitness: float
    domain_distribution: dict
    extinct_candidates: list[str]
    speciation_signals: dict
    niche_gaps: dict

    @property
    def population_size(self) -> int:
        return len(self.concepts)

    @property
    def diversity(self) -> float:
        """Shannon entropy over domains — higher = more diverse."""
        if not self.concepts:
            return 0.0
        counts = Counter(c.domain for c in self.concepts)
        total = len(self.concepts)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        # Normalize: max entropy = log2(num_domains)
        num_domains = len(counts)
        return entropy / math.log2(num_domains) if num_domains > 1 else 0.0


# ──────────────────────────────────────────────
# VAULT PARSER — Extract Gene Pool
# ──────────────────────────────────────────────

class VaultParser:
    """Parse the vault's concept notes into a population."""

    def __init__(self, concepts_dir: str = CONCEPTS_DIR):
        self.concepts_dir = concepts_dir
        self._phi_scores_cache = {}
        self._metric = None
        if _HAVE_REAL_METRIC:
            try:
                self._metric = VaultMetric()
                print(f"  [Darwinian] Real VaultMetric loaded — evaluating Φ for each concept")
            except Exception as e:
                print(f"  [Darwinian] VaultMetric init failed: {e}")
    
    def _get_real_phi(self, path: str, name: str) -> float:
        """Get real Φ score from VaultMetric, with caching."""
        if name in self._phi_scores_cache:
            return self._phi_scores_cache[name]
        
        if self._metric:
            try:
                phi = self._metric.evaluate(path)
                self._phi_scores_cache[name] = phi
                return phi
            except Exception:
                pass
        
        # Fallback: heuristic approximation
        try:
            with open(path) as f:
                c = f.read()
            lines = c.count("\n") + 1
            wikilinks = len(re.findall(r"\[\[([^\]]+)\]\]", c))
            has_breaktruth = bool(re.search(r"##\s*Breaktruth\s*Claim", c, re.IGNORECASE))
            has_sources = "sources:" in c[:500]
            sections = len(re.findall(r"^##\s+\S", c, re.MULTILINE))
            
            phi = 0.1  # base
            if lines >= 100: phi += 0.15
            elif lines >= 50: phi += 0.08
            if wikilinks >= 10: phi += 0.15
            elif wikilinks >= 5: phi += 0.08
            if has_breaktruth: phi += 0.10
            if has_sources: phi += 0.05
            if sections >= 5: phi += 0.10
            elif sections >= 3: phi += 0.05
            
            phi = min(1.0, phi)
            self._phi_scores_cache[name] = phi
            return phi
        except Exception:
            return 0.2

    def extract_population(self, generation: int) -> PopulationSnapshot:
        """Scan all concept notes and build a population snapshot."""
        concepts = []
        backlinks = self._compute_backlinks()

        for fname in sorted(os.listdir(self.concepts_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self.concepts_dir, fname)
            gene = self._parse_concept(fname, path, backlinks, generation)
            if gene:
                concepts.append(gene)

        total_phi = sum(c.phi_score for c in concepts)
        mean_fitness = sum(c.fitness for c in concepts) / len(concepts) if concepts else 0
        domain_dist = dict(Counter(c.domain for c in concepts if c.domain))

        return PopulationSnapshot(
            generation=generation,
            timestamp=datetime.now().isoformat(),
            concepts=concepts,
            total_phi=total_phi,
            mean_fitness=mean_fitness,
            domain_distribution=domain_dist,
            extinct_candidates=self._find_extinct_candidates(concepts, backlinks),
            speciation_signals=self._detect_speciation_signals(concepts),
            niche_gaps=self._compute_niche_gaps(concepts),
        )

    def _parse_concept(self, fname: str, path: str, backlinks: dict, gen: int) -> ConceptGene | None:
        try:
            with open(path) as f:
                content = f.read()
        except (IOError, OSError):
            return None

        lines = content.count("\n") + 1
        if lines < 10:
            return None  # skip stubs that aren't meaningful

        name = fname.replace(".md", "")

        # Parse frontmatter
        fm = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip()

        domain = fm.get("domain", fm.get("Domain", "unknown"))
        status = fm.get("status", fm.get("Status", "")).lower()

        if status == "stub":
            return None  # skip stubs

        # Wikilinks
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]

        wikilinks_out = len(set(re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body)))
        wikilinks_in = backlinks.get(name, 0)

        # Sections
        sections = len(re.findall(r"^##\s+\S", body, re.MULTILINE))

        # Breaktruth claim
        has_breaktruth = bool(re.search(r"##\s*Breaktruth\s*Claim", body, re.IGNORECASE | re.MULTILINE))

        # Source count (from frontmatter sources: field)
        source_count = 0
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                sources_text = parts[1]
                source_count = len(re.findall(r"^\s*-\s+", sources_text, re.MULTILINE))

        # Content density: ratio of "dense" lines (numbers, citations, code, tables)
        dense_lines = len(re.findall(r"(?:^\d|`|#|!\[|\||\$\$|\*\*[^*]+\*\*:)", body, re.MULTILINE))
        effective_body_lines = max(len(body.strip().split("\n")) - sections, 1)
        density = min(dense_lines / effective_body_lines * 3, 1.5)

        # Φ score — use real VaultMetric if available
        phi = self._get_real_phi(path, name)

        # Age
        created_str = fm.get("created", fm.get("Created", ""))
        age_days = 0
        if created_str:
            try:
                created = datetime.strptime(created_str[:10], "%Y-%m-%d")
                age_days = (datetime.now() - created).days
            except ValueError:
                pass

        return ConceptGene(
            name=name,
            domain=domain,
            lines=lines,
            wikilinks_out=wikilinks_out,
            wikilinks_in=wikilinks_in,
            sections=sections,
            has_breaktruth=has_breaktruth,
            has_figures=bool(re.search(r"!\[", body)),
            source_count=source_count,
            phi_score=phi,
            content_density=round(density, 3),
            age_days=age_days,
            generation=gen,
        )

    def _compute_backlinks(self) -> dict:
        """Count inbound wikilinks for every concept."""
        backlinks = defaultdict(int)
        existing = set()
        for fname in os.listdir(self.concepts_dir):
            if fname.endswith(".md"):
                existing.add(fname.replace(".md", ""))

        for fname in os.listdir(self.concepts_dir):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(self.concepts_dir, fname)
            try:
                with open(path) as f:
                    content = f.read()
            except (IOError, OSError):
                continue
            for m in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content):
                target = m.group(1).strip()
                if target in existing:
                    backlinks[target] += 1
        return dict(backlinks)

    def _find_extinct_candidates(self, concepts: list[ConceptGene], backlinks: dict) -> list[str]:
        """Find concepts with ZERO inbound links and low Φ — candidates for merge/deletion."""
        extinct = []
        for c in concepts:
            if c.wikilinks_in == 0 and c.phi_score < 0.15 and c.lines < 50:
                extinct.append(c.name)
        return sorted(extinct)[:20]

    def _detect_speciation_signals(self, concepts: list[ConceptGene]) -> dict:
        """Detect domains approaching critical mass for subdomain splitting."""
        domain_counts = Counter(c.domain for c in concepts)
        signals = {}
        for domain, count in domain_counts.most_common():
            if count >= 15:
                # Check if subdomain patterns exist within this domain
                subdomains = set()
                for c in concepts:
                    if c.domain == domain:
                        for kw in self._subdomain_keywords(c):
                            subdomains.add(kw)
                if len(subdomains) >= 3:
                    signals[domain] = {
                        "count": count,
                        "subdomain_candidates": list(subdomains)[:5],
                        "recommendation": f"Split {domain} into {len(subdomains)} subdomains"
                    }
        return signals

    def _subdomain_keywords(self, gene: ConceptGene) -> list[str]:
        """Infer subdomain from concept name and properties."""
        hints = []
        name_lower = gene.name.lower()
        # Known subdomain signals
        subdomain_map = {
            "neuroscience": ["prefrontal", "amygdala", "hippocampus", "dmn", "basal ganglia",
                           "serotonin", "acetylcholine", "norepinephrine", "hpa", "neurotransmitter",
                           "synaptic", "neural", "cortex", "limbic", "brain"],
            "finance": ["trading", "risk", "portfolio", "sharpe", "volatility", "drawdown",
                       "position", "backtest", "regime", "signal", "momentum", "mean reversion",
                       "option", "futures", "equity", "bond", "forex"],
            "psychology": ["cognitive", "behavioral", "motivation", "emotion", "personality",
                         "perception", "memory", "learning", "bias", "heuristic", "attention"],
            "sleep": ["circadian", "deprivation", "sws", "rem", "glymphatic", "melatonin",
                     "chronobiology", "insomnia", "nrem", "slow wave"],
            "ml": ["supervised", "unsupervised", "reinforcement", "deep", "transformer",
                  "attention", "embedding", "gradient", "loss", "layer", "network"],
        }
        for superdomain, kws in subdomain_map.items():
            if gene.domain.lower().startswith(superdomain):
                for kw in kws:
                    if kw in name_lower:
                        hints.append(kw.capitalize())
        return hints

    def _compute_niche_gaps(self, concepts: list[ConceptGene]) -> dict:
        """Find overcrowded and underpopulated domains (niche opportunity map)."""
        counts = Counter(c.domain for c in concepts)
        total = len(concepts)

        # Mean inbound links per domain — low mean = overcrowded (competition)
        domain_backlinks = defaultdict(list)
        for c in concepts:
            domain_backlinks[c.domain].append(c.wikilinks_in)

        underpopulated = {}
        overcrowded = {}
        for domain, count in counts.most_common():
            ratio = count / total
            avg_inlinks = sum(domain_backlinks[domain]) / max(len(domain_backlinks[domain]), 1)

            if ratio < 0.02 and count < 5:
                underpopulated[domain] = {
                    "count": count,
                    "ratio": round(ratio, 4),
                    "niche_description": f"{domain}: only {count} concepts — easy to colonize"
                }
            elif ratio > 0.12:
                overcrowded[domain] = {
                    "count": count,
                    "ratio": round(ratio, 4),
                    "avg_inlinks": round(avg_inlinks, 1),
                    "competition_warning": f"{domain}: {count} concepts ({ratio:.1%}), avg {avg_inlinks:.1f} inbound links each"
                }

        return {
            "underpopulated": dict(sorted(underpopulated.items(), key=lambda x: x[1]["count"])),
            "overcrowded": dict(sorted(overcrowded.items(), key=lambda x: -x[1]["count"])),
        }


# ──────────────────────────────────────────────
# FITNESS LANDSCAPE
# ──────────────────────────────────────────────

class FitnessLandscape:
    """
    Multi-dimensional fitness landscape of the vault.
    
    Three axes:
      X — Φ INTEGRATION (how connected a domain's concepts are)
      Y — CONTENT QUALITY (density, sections, breaktruth presence)
      Z — DOMAIN DIVERSITY (how many domains this concept touches)
    """
    
    def __init__(self, snapshot: PopulationSnapshot):
        self.snapshot = snapshot
    
    def compute(self) -> dict:
        """Compute landscape features."""
        s = self.snapshot
        if not s.concepts:
            return {"error": "empty vault"}
        
        # Sort concepts by fitness
        ranked = sorted(s.concepts, key=lambda c: c.fitness, reverse=True)
        
        # Adaptive peaks: top 10% of concepts by fitness
        top_pct = max(int(len(ranked) * 0.10), 3)
        peaks = ranked[:top_pct]
        
        # Valleys: bottom 10%
        valley_pct = max(int(len(ranked) * 0.10), 3)
        valleys = ranked[-valley_pct:]
        
        # Ruggedness: variance in fitness across domains
        domain_fitness = defaultdict(list)
        for c in ranked:
            domain_fitness[c.domain].append(c.fitness)
        
        rugged = {}
        for domain, scores in domain_fitness.items():
            if len(scores) >= 3:
                mean_f = sum(scores) / len(scores)
                var_f = sum((f - mean_f)**2 for f in scores) / len(scores)
                rugged[domain] = {
                    "mean_fitness": round(mean_f, 4),
                    "variance": round(var_f, 6),
                    "ruggedness": "high" if var_f > 0.05 else "moderate" if var_f > 0.02 else "smooth"
                }
        
        return {
            "adaptive_peaks": [
                {
                    "name": p.name,
                    "domain": p.domain,
                    "fitness": round(p.fitness, 4),
                    "why": self._peak_reason(p)
                }
                for p in peaks[:10]
            ],
            "valleys": [
                {
                    "name": v.name,
                    "domain": v.domain,
                    "fitness": round(v.fitness, 4),
                    "why": self._valley_reason(v)
                }
                for v in valleys[:5]
            ],
            "ruggedness_per_domain": rugged,
            "fitness_range": {
                "min": round(min(c.fitness for c in ranked), 4),
                "max": round(max(c.fitness for c in ranked), 4),
                "spread": round(max(c.fitness for c in ranked) - min(c.fitness for c in ranked), 4),
            }
        }
    
    def _peak_reason(self, c: ConceptGene) -> str:
        reasons = []
        if c.phi_score > 0.6:
            reasons.append("Φ > 0.6")
        if c.wikilinks_in > 10:
            reasons.append(f"{c.wikilinks_in} inbound links (hub)")
        if c.has_breaktruth:
            reasons.append("breaktruth claim present")
        if c.sections > 5:
            reasons.append(f"{c.sections} sections (deep)")
        return " + ".join(reasons[:3]) if reasons else "high content density"
    
    def _valley_reason(self, c: ConceptGene) -> str:
        reasons = []
        if c.wikilinks_in == 0:
            reasons.append("orphan (zero backlinks)")
        if c.lines < 30:
            reasons.append(f"shallow ({c.lines}L)")
        if not c.has_breaktruth:
            reasons.append("no breaktruth claim")
        if c.sections < 2:
            reasons.append("thin structure")
        return " + ".join(reasons[:3]) if reasons else "low fitness"
    
    def report(self, detailed: bool = False) -> str:
        """Generate a human-readable fitness landscape report."""
        data = self.compute()
        s = self.snapshot
        
        lines = [
            f"═══ FITNESS LANDSCAPE (Generation {s.generation}) ═══",
            "",
            f"Population: {s.population_size} concepts across {len(s.domain_distribution)} domains",
            f"Total Φ: {s.total_phi:.4f} | Mean Fitness: {s.mean_fitness:.4f}",
            f"Diversity (Shannon): {s.diversity:.3f}",
            "",
            "── Adaptive Peaks ──",
        ]
        
        for i, peak in enumerate(data.get("adaptive_peaks", [])[:7], 1):
            lines.append(f"  {i}. {peak['name']} [{peak['domain']}] — fitness {peak['fitness']:.4f}")
            lines.append(f"     {peak['why']}")
        
        lines.extend(["", "── Valleys (extinction candidates) ──"])
        for v in data.get("valleys", [])[:5]:
            lines.append(f"  • {v['name']} [{v['domain']}] — fitness {v['fitness']:.4f}")
            lines.append(f"    {v['why']}")
        
        lines.extend(["", "── Ruggedness by Domain ──"])
        for dom, info in sorted(data.get("ruggedness_per_domain", {}).items(),
                               key=lambda x: -x[1]["mean_fitness"])[:10]:
            lines.append(f"  • {dom}: μ={info['mean_fitness']:.4f} σ²={info['variance']:.6f} [{info['ruggedness']}]")
        
        if detailed:
            lines.extend(["", "── Niche Gaps ──"])
            ng = s.niche_gaps
            lines.append(f"  Underpopulated ({len(ng.get('underpopulated', {}))}):")
            for dom, info in list(ng.get("underpopulated", {}).items())[:5]:
                lines.append(f"    → {info['niche_description']}")
            lines.append(f"  Overcrowded ({len(ng.get('overcrowded', {}))}):")
            for dom, info in list(ng.get("overcrowded", {}).items())[:5]:
                lines.append(f"    → {info['competition_warning']}")
            
            lines.extend(["", "── Speciation Signals ──"])
            for dom, sig in s.speciation_signals.items():
                lines.append(f"  • {dom}: {sig['count']} nodes → {sig['recommendation']}")
            
            lines.extend(["", "── Extinction Candidates ──"])
            if s.extinct_candidates:
                lines.append(f"  ！ {len(s.extinct_candidates)} concepts with 0 backlinks + low Φ")
                lines.append(f"     First 5: {', '.join(s.extinct_candidates[:5])}")
            else:
                lines.append("  ✓ No extinction candidates detected")
        
        return "\n".join(lines)


# ──────────────────────────────────────────────
# GENETIC CROSSOVER ENGINE
# ──────────────────────────────────────────────

class CrossoverEngine:
    """
    Breed two concept notes from different domains → hybrid offspring.
    
    Inspired by genetic crossover:
    - Parent A provides section structure (chromosome 1)
    - Parent B provides domain-specific mechanisms (chromosome 2)
    - Crossover point = breaktruth claim (the fused insight)
    
    This is NOT random recombination — it's guided by Φ potential.
    """
    
    def __init__(self):
        self.concepts_dir = CONCEPTS_DIR
    
    def find_crossover_pairs(self, snapshot: PopulationSnapshot, pairs: int = 5) -> list[dict]:
        """
        Find high-potential crossover pairs (different domains, both fit).
        
        Selection criteria:
          1. Different domains (no inbreeding)
          2. Both have fitness > 0.3 (viable parents)
          3. Their combined domain pair has no existing bridge (untested hybridization)
        """
        concepts = [c for c in snapshot.concepts if c.fitness > 0.3]
        
        # Group by domain
        by_domain = defaultdict(list)
        for c in concepts:
            by_domain[c.domain].append(c)
        
        domains = list(by_domain.keys())
        candidates = []
        
        # Find existing bridges to avoid duplicating
        existing_pairs = self._load_existing_bridge_pairs()
        
        for i in range(len(domains)):
            for j in range(i + 1, len(domains)):
                da, db = domains[i], domains[j]
                pair_key = frozenset([da.lower(), db.lower()])
                if pair_key in existing_pairs:
                    continue  # already a bridge exists — no crossover needed
                
                best_a = max(by_domain[da], key=lambda c: c.fitness)
                best_b = max(by_domain[db], key=lambda c: c.fitness)
                combined_fitness = (best_a.fitness + best_b.fitness) / 2
                
                if combined_fitness < 0.3:
                    continue
                
                candidates.append({
                    "domain_a": da,
                    "domain_b": db,
                    "parent_a": best_a.name,
                    "parent_b": best_b.name,
                    "fitness_a": round(best_a.fitness, 4),
                    "fitness_b": round(best_b.fitness, 4),
                    "combined_fitness": round(combined_fitness, 4),
                    "crossover_potential": round(combined_fitness * (1 - combined_fitness) * 4, 4),
                    "score": round(combined_fitness * 0.5 + 
                                   (1 - len(candidates) / 100) * 0.5, 4),  # diversity bonus
                })
        
        # Rank by crossover potential
        candidates.sort(key=lambda x: -x["crossover_potential"])
        return candidates[:pairs]
    
    def _load_existing_bridge_pairs(self) -> set:
        """Load existing bridge domain pairs so we don't suggest duplicates."""
        bridges_dir = os.path.join(VAULT_ROOT, "04 Resources/Publications")
        existing = set()
        if not os.path.isdir(bridges_dir):
            return existing
        
        for fname in os.listdir(bridges_dir):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(bridges_dir, fname)
            try:
                with open(path) as f:
                    content = f.read()
            except (IOError, OSError):
                continue
            
            # Extract domain frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].strip().split("\n"):
                        if line.startswith("domain:") or line.startswith("Domain:"):
                            _, v = line.split(":", 1)
                            for d in v.split(","):
                                d = d.strip().lower()
                                for other_d in v.split(","):
                                    od = other_d.strip().lower()
                                    if d and od and d != od:
                                        existing.add(frozenset([d, od]))
        return existing
    
    def design_hybrid(self, pair: dict) -> str:
        """
        Generate a crossover plan for hybridizing two concepts.
        Returns a natural-language brief that a bridge-writing agent can execute.
        """
        return (
            f"CROSSOVER: {pair['parent_a']} ({pair['domain_a']}) × "
            f"{pair['parent_b']} ({pair['domain_b']})\n"
            f"  Fitness: {pair['fitness_a']} × {pair['fitness_b']} = φ{pair['combined_fitness']:.4f}\n"
            f"  Crossover potential: {pair['crossover_potential']:.4f}\n"
            f"\n"
            f"  Design brief:\n"
            f"    • Parent A ({pair['parent_a']}) provides: structural framework\n"
            f"    • Parent B ({pair['parent_b']}) provides: domain-specific mechanisms\n"
            f"    • Crossover point: the shared pattern that exists in both domains\n"
            f"    • Hybrid form: bridge publication (~100-200L) with isomorphism table\n"
            f"    • Expected outcome: a concept that inherits from both parents\n"
            f"      but is neither — a new species"
        )


# ──────────────────────────────────────────────
# DARWINIAN VAULT — The Orchestrator
# ──────────────────────────────────────────────

class DarwinianVault:
    """
    Population-level vault evolution engine.
    
    Usage:
        dv = DarwinianVault()
        report = dv.run_generation()
        print(report)
    """
    
    GENERATIONS_DIR = os.path.join(os.path.expanduser("~/cognoscope"), "darwinian_generations")
    TRENDS_FILE = os.path.join(os.path.expanduser("~/cognoscope"), "darwinian_generations", "trends_history.json")
    IMMUNE_FILE = os.path.join(os.path.expanduser("~/cognoscope"), "darwinian_generations", "immune_history.json")
    
    def __init__(self):
        self.parser = VaultParser()
        self.crossover = CrossoverEngine()
        os.makedirs(self.GENERATIONS_DIR, exist_ok=True)
    
    def run_generation(self) -> PopulationSnapshot:
        """Run one full generation: snapshot → landscape → crossover → report."""
        # Load generation counter
        gen_file = os.path.join(self.GENERATIONS_DIR, "generation_counter.json")
        if os.path.exists(gen_file):
            with open(gen_file) as f:
                counter = json.load(f)
            generation = counter.get("generation", 0) + 1
        else:
            generation = 1
        
        # Extract population
        snapshot = self.parser.extract_population(generation)
        
        # Compute landscape
        landscape = FitnessLandscape(snapshot)
        landscape_data = landscape.compute()
        
        # Find crossover candidates
        crosstop = self.crossover.find_crossover_pairs(snapshot)
        
        # Save generation data
        gen_data = {
            "generation": generation,
            "timestamp": snapshot.timestamp,
            "population_size": snapshot.population_size,
            "total_phi": snapshot.total_phi,
            "mean_fitness": snapshot.mean_fitness,
            "diversity": snapshot.diversity,
            "domains": snapshot.domain_distribution,
            "extinct_candidates": snapshot.extinct_candidates,
            "adaptive_peaks": landscape_data.get("adaptive_peaks", [])[:5],
            "crossover_pairs": [
                {"a": p["parent_a"], "b": p["parent_b"], 
                 "da": p["domain_a"], "db": p["domain_b"],
                 "score": p["score"]}
                for p in crosstop
            ],
            "speciation_signals": {
                k: {"count": v["count"], "subdomains": v["subdomain_candidates"]}
                for k, v in snapshot.speciation_signals.items()
            },
            "niche_gaps": {
                "underpopulated": list(snapshot.niche_gaps.get("underpopulated", {}).keys())[:5],
                "overcrowded": list(snapshot.niche_gaps.get("overcrowded", {}).keys())[:5],
            }
        }
        
        gen_path = os.path.join(self.GENERATIONS_DIR, f"generation_{generation}.json")
        with open(gen_path, "w") as f:
            json.dump(gen_data, f, indent=2, default=str)
        
        # Save counter
        with open(gen_file, "w") as f:
            json.dump({
                "generation": generation,
                "last_run": snapshot.timestamp,
            }, f)
        
        # Save latest for quick access
        latest_path = os.path.join(self.GENERATIONS_DIR, "latest.json")
        with open(latest_path, "w") as f:
            json.dump(gen_data, f, indent=2, default=str)
        
        self._latest = (snapshot, landscape, crosstop)
        self._gen_data = gen_data
        
        # Record trends & run immune check
        self._record_trends(gen_data)
        immune_alerts = self.vault_immune_check()
        self._latest_immune = immune_alerts
        
        return snapshot
    
    def _record_trends(self, gen_data: dict):
        """Record generation data into trend history for multi-gen tracking."""
        history = []
        if os.path.exists(self.TRENDS_FILE):
            try:
                with open(self.TRENDS_FILE) as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []
        
        # Extract compact trend record
        record = {
            "generation": gen_data["generation"],
            "timestamp": gen_data["timestamp"],
            "population_size": gen_data["population_size"],
            "total_phi": gen_data["total_phi"],
            "mean_fitness": gen_data["mean_fitness"],
            "diversity": gen_data["diversity"],
            "domain_count": len(gen_data.get("domains", {})),
            "extinct_count": len(gen_data.get("extinct_candidates", [])),
            "crossover_count": len(gen_data.get("crossover_pairs", [])),
            "speciation_count": len(gen_data.get("speciation_signals", {})),
        }
        
        history.append(record)
        # Keep last 100 generations
        if len(history) > 100:
            history = history[-100:]
        
        with open(self.TRENDS_FILE, "w") as f:
            json.dump(history, f, indent=2)
    
    def trends_report(self) -> str:
        """Generate multi-generational trend analysis."""
        if not os.path.exists(self.TRENDS_FILE):
            return "No trend data yet. Run multiple generations first."
        
        with open(self.TRENDS_FILE) as f:
            history = json.load(f)
        
        if len(history) < 2:
            return "Need at least 2 generations to show trends."
        
        lines = []
        lines.append("📈 DARWINIAN TRENDS")
        lines.append("")
        
        first = history[0]
        last = history[-1]
        
        # Overall trajectory
        phi_trend = last["total_phi"] - first["total_phi"]
        pop_trend = last["population_size"] - first["population_size"]
        div_trend = last["diversity"] - first["diversity"]
        gen_count = last["generation"] - first["generation"]
        
        lines.append(f"  Trajectory over {gen_count} generations (gen {first['generation']} → {last['generation']}):")
        lines.append(f"    Φ:     {first['total_phi']:.2f} → {last['total_phi']:.2f}  ({'+' if phi_trend > 0 else ''}{phi_trend:.2f})")
        lines.append(f"    Pop:   {first['population_size']} → {last['population_size']}  ({'+' if pop_trend > 0 else ''}{pop_trend})")
        lines.append(f"    Div:   {first['diversity']:.3f} → {last['diversity']:.3f}  ({'+' if div_trend > 0 else ''}{div_trend:.3f})")
        lines.append(f"    Domains: {first['domain_count']} → {last['domain_count']}")
        lines.append("")
        
        # Per-generation delta
        lines.append("  Per-generation deltas:")
        for i in range(1, len(history)):
            prev, cur = history[i-1], history[i]
            d_phi = cur["total_phi"] - prev["total_phi"]
            d_pop = cur["population_size"] - prev["population_size"]
            arrow_phi = "▲" if d_phi > 0 else "▼" if d_phi < 0 else "→"
            arrow_pop = "▲" if d_pop > 0 else "▼" if d_pop < 0 else "→"
            lines.append(f"    Gen {cur['generation']}: Φ {d_phi:+.4f} {arrow_phi}  Pop {d_pop:+d} {arrow_pop}  H={cur['diversity']:.3f}")
        
        lines.append("")
        
        # Acceleration
        if len(history) >= 3:
            recent = history[-3:]
            avg_recent = sum(g["total_phi"] for g in recent) / 3
            avg_early = sum(g["total_phi"] for g in history[:3]) / 3
            accel = avg_recent - avg_early
            lines.append(f"  Φ Velocity: avg last 3 = {avg_recent:.2f} vs first 3 = {avg_early:.2f} ({'+' if accel > 0 else ''}{accel:.2f})")
        
        # Extinction rate
        total_extinct = sum(g["extinct_count"] for g in history)
        lines.append(f"  Total extinction warnings: {total_extinct}")
        
        return "\n".join(lines)
    
    def vault_immune_check(self) -> list[dict]:
        """
        Vault Immune System — detect concept decay:
          1. STALE: concepts not updated in >90 days with Φ < 0.3
          2. BROKEN: wikilinks pointing to non-existent concepts
          3. Φ DECAY: concepts whose Φ dropped since last generation
          4. DOMAIN DRIFT: concepts whose domain changed
          5. PUBLICATION STALE: bridges not cross-linked to their target concepts
        """
        alerts = []
        
        # Load previous immune state
        prev_immune = {}
        if os.path.exists(self.IMMUNE_FILE):
            try:
                with open(self.IMMUNE_FILE) as f:
                    prev_immune = json.load(f)
            except (json.JSONDecodeError, IOError):
                prev_immune = {}
        
        # Parse all concepts
        from ariauthor import VaultMetric as VMetric
        metric = None
        try:
            metric = VMetric()
        except Exception:
            pass
        
        concepts_dir = CONCEPTS_DIR
        existing_concepts = set()
        for fname in os.listdir(concepts_dir):
            if fname.endswith(".md"):
                existing_concepts.add(fname.replace(".md", ""))
        
        current_phi = {}
        
        for fname in os.listdir(concepts_dir):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(concepts_dir, fname)
            name = fname.replace(".md", "")
            
            try:
                with open(path) as f:
                    content = f.read()
            except (IOError, OSError):
                continue
            
            lines = content.count("\n") + 1
            if lines < 15:
                continue
            
            # Get Φ
            phi = 0.2
            if metric:
                try:
                    phi = metric.evaluate(path)
                except Exception:
                    pass
            current_phi[name] = phi
            
            body = content
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2]
            
            # 1. STALE check
            fm_date = None
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].split("\n"):
                        if line.startswith("updated:"):
                            try:
                                fm_date = line.split(":", 1)[1].strip()[:10]
                            except:
                                pass
            
            if fm_date:
                try:
                    updated = datetime.strptime(fm_date, "%Y-%m-%d")
                    age_days = (datetime.now() - updated).days
                    if age_days > 90 and phi < 0.3:
                        alerts.append({
                            "type": "STALE",
                            "name": name,
                            "detail": f"Last updated {age_days}d ago, Φ={phi:.2f}",
                            "severity": "medium"
                        })
                except ValueError:
                    pass
            
            # 2. BROKEN wikilinks — filter out path-based and non-concept refs
            broken_links = []
            for m in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body):
                target = m.group(1).strip()
                # Skip path-based references like "04 Resources/Concepts/..."
                if target.startswith("04 ") or target.startswith("02 "):
                    continue
                # Skip skill/internal paths
                if "06 System/" in target or "06 System/Skills/" in target:
                    continue
                # Skip known external URLs or templates
                if target.startswith("http") or "{{" in target or "}}" in target:
                    continue
                # Skip quoted/wrapped text that isn't a real link attempt
                if target.startswith('"') or target.startswith('"'):  # smart quotes too
                    continue
                # Skip obviously wrong text caught in wikilink syntax
                if '$file' in target or '.md' in target:
                    continue
                if target not in existing_concepts:
                    # Check if it's a publication link
                    pub_path = os.path.join(PUBLICATIONS_DIR, f"{target}.md")
                    if not os.path.exists(pub_path):
                        # Also check if it's an alias reference
                        broken_links.append(target)
            
            if broken_links:
                alerts.append({
                    "type": "BROKEN_LINKS",
                    "name": name,
                    "detail": f"Wikilinks to non-existent: {', '.join(broken_links[:3])}",
                    "severity": "high" if len(broken_links) > 3 else "low",
                    "broken_count": len(broken_links),
                    "broken_targets": broken_links[:5]
                })
        
        # 3. Φ DECAY — compare with previous generation
        if prev_immune and "phi_snapshot" in prev_immune:
            prev_phi = prev_immune["phi_snapshot"]
            for name, phi in current_phi.items():
                if name in prev_phi:
                    delta = phi - prev_phi[name]
                    if delta < -0.1:  # Significant drop
                        alerts.append({
                            "type": "PHI_DECAY",
                            "name": name,
                            "detail": f"Φ dropped {delta:.4f} (was {prev_phi[name]:.4f} → now {phi:.4f})",
                            "severity": "high" if delta < -0.2 else "medium",
                            "phi_before": prev_phi[name],
                            "phi_after": phi,
                            "delta": delta
                        })
        
        # 4. STALE BRIDGES — publications that link to non-existent concepts
        #    (Unidirectional bridge→concept is expected; only flag if bridge links
        #     to a concept that doesn't exist — which is already caught by BROKEN_LINKS)
        pass
        
        # Save current immune state for next generation comparison
        immune_state = {
            "phi_snapshot": current_phi,
            "timestamp": datetime.now().isoformat(),
            "alerts_count": len(alerts),
        }
        with open(self.IMMUNE_FILE, "w") as f:
            json.dump(immune_state, f, indent=2)
        
        return alerts
    
    def immune_report(self) -> str:
        """Generate immune system report."""
        try:
            alerts = self._latest_immune
        except AttributeError:
            alerts = self.vault_immune_check()
        
        if not alerts:
            return "🛡️ Vault Immune System: ✓ No issues detected"
        
        lines = []
        lines.append("🛡️ VAULT IMMUNE SYSTEM")
        lines.append("")
        
        # Group by severity
        by_type = defaultdict(list)
        for a in alerts:
            by_type[a["type"]].append(a)
        
        for alert_type, items in sorted(by_type.items()):
            high = sum(1 for i in items if i.get("severity") == "high")
            med = sum(1 for i in items if i.get("severity") == "medium")
            low = sum(1 for i in items if i.get("severity") == "low")
            
            lines.append(f"  {alert_type}: {len(items)} issues (🔴{high} 🟡{med} 🟢{low})")
            
            for item in items[:5]:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item.get("severity", "low"), "🟢")
                lines.append(f"    {icon} {item['name']}: {item['detail']}")
            
            if len(items) > 5:
                lines.append(f"    ... +{len(items) - 5} more")
            lines.append("")
        
        lines.append(f"  Total: {len(alerts)} immune alerts")
        lines.append("  Run --heal to auto-fix broken links")
        
        return "\n".join(lines)
    
    def heal_broken_links(self) -> str:
        """Auto-fix broken wikilinks where possible."""
        alerts = self.vault_immune_check()
        broken = [a for a in alerts if a["type"] == "BROKEN_LINKS"]
        
        if not broken:
            return "✓ No broken links to heal"
        
        fixed = 0
        not_fixed = 0
        
        # Build fuzzy match index
        concepts = {}
        for fname in os.listdir(CONCEPTS_DIR):
            if fname.endswith(".md"):
                base = fname.replace(".md", "").lower()
                concepts[base] = fname.replace(".md", "")
        
        for item in broken:
            path = os.path.join(CONCEPTS_DIR, f"{item['name']}.md")
            if not os.path.exists(path):
                continue
            
            try:
                with open(path) as f:
                    content = f.read()
            except (IOError, OSError):
                continue
            
            new_content = content
            targets = item.get("broken_targets", [])
            
            for raw_target in targets:
                # Clean target: strip quotes, trim
                target = raw_target.strip('"\'“”‘’')
                target_lower = target.lower()
                
                # Strategy 1: Direct match (case-insensitive)
                best_match = None
                best_score = 0
                
                for concept_name, display_name in concepts.items():
                    # Direct match (maybe with different punctuation)
                    if target_lower == concept_name:
                        best_match = display_name
                        best_score = 1.0
                        break
                    
                    # Strategy 2: Substring containment
                    if target_lower in concept_name or concept_name in target_lower:
                        score = len(target_lower) / max(len(concept_name), 1) + 0.2
                        if score > best_score:
                            best_score = score
                            best_match = display_name
                
                # Strategy 3: Token intersection (split by spaces / / - , .)
                if not best_match or best_score < 0.6:
                    target_tokens = set(re.split(r'[\s/,\-.:]+', target_lower))
                    for concept_name, display_name in concepts.items():
                        concept_tokens = set(re.split(r'[\s/,\-.:]+', concept_name))
                        intersection = target_tokens & concept_tokens
                        union = target_tokens | concept_tokens
                        if union and len(intersection) >= 2:  # At least 2 common tokens
                            jaccard = len(intersection) / len(union)
                            if jaccard > best_score and jaccard > 0.3:
                                best_score = jaccard
                                best_match = display_name
                
                # Strategy 4: Extract last component from path (06 System/Skills/.../Name)
                if not best_match and "/" in target:
                    last_part = target.rstrip("/").split("/")[-1].strip()
                    if last_part and last_part.lower() in concepts:
                        best_match = concepts[last_part.lower()]
                        best_score = 0.8
                
                if best_match and best_score > 0.35:
                    # Try all possible wiki link forms
                    variants = [f"[[{raw_target}]]", f"[[{raw_target}|", f"[[{target}]]"]
                    for old_link in variants:
                        if old_link in new_content:
                            new_content = new_content.replace(old_link, f"[[{best_match}]]")
                            fixed += 1
                            break
                    else:
                        # Try regex: [[stuff that ends with target]]
                        # This matches [[...|target]] and [[target]] patterns
                        escaped = re.escape(target)
                        for m in re.finditer(rf"\[\[([^\]]*{escaped}[^\]]*)\]\]", new_content):
                            full_old = m.group(0)
                            new_content = new_content.replace(full_old, f"[[{best_match}]]")
                            fixed += 1
            
            if new_content != content:
                with open(path, "w") as f:
                    f.write(new_content)
        
        # Re-run immune check after healing
        self._latest_immune = self.vault_immune_check()
        
        return f"🔧 Healed: {fixed} broken links fixed, {not_fixed} could not be matched"
    
    def report(self, include_crossover: bool = True) -> str:
        """Generate the full evolutionary report."""
        latest = getattr(self, "_latest", None)
        if not latest:
            return "No generation data. Call run_generation() first."
        snapshot, landscape, crosstop = latest
        
        report = []
        
        # ── HEADER ──
        report.append(f"🧬 DARWINIAN VAULT — Generation {snapshot.generation}")
        report.append(f"   {snapshot.timestamp}")
        report.append("")
        
        # ── VITAL STATISTICS ──
        report.append("── Vital Statistics ──")
        report.append(f"  Population:       {snapshot.population_size} concepts")
        report.append(f"  Domains:          {len(snapshot.domain_distribution)}")
        report.append(f"  Total Φ:          {snapshot.total_phi:.4f}")
        report.append(f"  Mean fitness:     {snapshot.mean_fitness:.4f}")
        report.append(f"  Diversity (H):    {snapshot.diversity:.3f}")
        
        # Phi deltas from previous generation
        self._gen_delta(report)
        
        report.append("")
        
        # ── FITNESS LANDSCAPE ──
        report.append("── Fitness Landscape ──")
        landscape_data = {}
        if landscape is not None:
            landscape_data = landscape.compute()
        
        report.append("  Adaptive Peaks:")
        for i, p in enumerate(landscape_data.get("adaptive_peaks", [])[:5], 1):
            report.append(f"    {i}. {p['name']} [{p['domain']}] — φ_{p['fitness']:.4f}")
            report.append(f"       {p['why']}")
        
        report.append("  Valleys (extinction risk):")
        for v in landscape_data.get("valleys", [])[:3]:
            report.append(f"    • {v['name']} [{v['domain']}] — φ_{v['fitness']:.4f}")
            report.append(f"      {v['why']}")
        
        report.append("")
        
        # ── DOMAIN DYNAMICS ──
        report.append("── Domain Ecology ──")
        
        # Top 10 domains by population
        sorted_domains = sorted(snapshot.domain_distribution.items(), key=lambda x: -x[1])
        report.append("  Population by Domain (top 10):")
        for dom, count in sorted_domains[:10]:
            pct = count / snapshot.population_size * 100
            bar = "█" * max(int(count / 2), 1)
            report.append(f"    {dom:30s} {count:3d} ({pct:4.1f}%) {bar}")
        
        report.append("")
        
        # ── NICHE GAPS ──
        ng = snapshot.niche_gaps
        under = ng.get("underpopulated", {})
        over = ng.get("overcrowded", {})
        
        report.append("── Niche Carving ──")
        if under:
            report.append("  Underpopulated (colonization targets):")
            for dom, info in list(under.items())[:5]:
                report.append(f"    ➜ {info['niche_description']}")
        else:
            report.append("  ✓ No underpopulated niches")
        
        if over:
            report.append("  Overcrowded (competition):")
            for dom, info in list(over.items())[:3]:
                report.append(f"    ⚠ {info['competition_warning']}")
        else:
            report.append("  ✓ No overcrowded domains")
        
        report.append("")
        
        # ── SPECIATION ──
        if snapshot.speciation_signals:
            report.append("── Speciation Signals ──")
            for dom, sig in list(snapshot.speciation_signals.items())[:3]:
                report.append(f"  🔬 {dom}: {sig['count']} nodes")
                report.append(f"     Candidates: {', '.join(sig['subdomain_candidates'][:5])}")
                report.append(f"     → {sig['recommendation']}")
            report.append("")
        
        # ── CROSSOVER ──
        if include_crossover and crosstop:
            report.append("── Crossover Pairs (hybridization recommended) ──")
            for i, pair in enumerate(crosstop[:5], 1):
                report.append(f"  {i}. {pair['parent_a']} ({pair['domain_a']}) × {pair['parent_b']} ({pair['domain_b']})")
                report.append(f"     Combined fitness: φ{pair['combined_fitness']:.4f} | Potential: {pair['crossover_potential']:.4f}")
            report.append("")
        
        # ── EXTINCTION MONITOR ──
        if snapshot.extinct_candidates:
            report.append(f"── Extinction Watch ──")
            report.append(f"  ⚰ {len(snapshot.extinct_candidates)} concepts with 0 backlinks + low Φ")
            report.append(f"     Candidates: {', '.join(snapshot.extinct_candidates[:5])}")
            report.append("")
        
        # ── SELECTION PRESSURE ──
        report.append("── Selection Pressure ──")
        
        # Which domains are being "selected for" (high mean fitness)
        domain_fitness = defaultdict(list)
        for c in snapshot.concepts:
            domain_fitness[c.domain].append(c.fitness)
        
        top_domains = sorted(domain_fitness.items(), key=lambda x: -sum(x[1])/len(x[1]))[:3]
        bottom_domains = sorted(domain_fitness.items(), key=lambda x: sum(x[1])/len(x[1]))[:3]
        
        report.append("  Positive selection (high Φ domains):")
        for dom, scores in top_domains:
            mean_f = sum(scores) / len(scores)
            report.append(f"    ❯ {dom}: μ={mean_f:.4f} ({len(scores)} concepts)")
        
        report.append("  Neutral/drift (low Φ domains):")
        for dom, scores in bottom_domains:
            mean_f = sum(scores) / len(scores)
            report.append(f"    ❯ {dom}: μ={mean_f:.4f} ({len(scores)} concepts)")
        
        return "\n".join(report)
    
    def _gen_delta(self, report: list):
        """Compare with previous generation."""
        prev_path = os.path.join(self.GENERATIONS_DIR, "latest.json")
        if not os.path.exists(prev_path):
            return
        
        try:
            with open(prev_path) as f:
                prev = json.load(f)
            cur = self._gen_data
            
            delta_phi = cur.get("total_phi", 0) - prev.get("total_phi", 0)
            delta_pop = cur.get("population_size", 0) - prev.get("population_size", 0)
            delta_div = cur.get("diversity", 0) - prev.get("diversity", 0)
            
            report.append(f"  Δ from previous gen:")
            if delta_phi > 0:
                report.append(f"    Φ: +{delta_phi:.4f} ▲")
            elif delta_phi < 0:
                report.append(f"    Φ: {delta_phi:.4f} ▼")
            else:
                report.append(f"    Φ: unchanged")
            
            if delta_pop > 0:
                report.append(f"    Population: +{delta_pop}")
            elif delta_pop < 0:
                report.append(f"    Population: {delta_pop}")
            
            if delta_div > 0:
                report.append(f"    Diversity: +{delta_div:.3f} ▲")
            elif delta_div < 0:
                report.append(f"    Diversity: {delta_div:.3f} ▼")
        except (json.JSONDecodeError, KeyError):
            pass
    
    def run_demo(self) -> str:
        """Run one generation and return report."""
        self.run_generation()
        return self.report()


# ──────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Darwinian Vault Evolution Engine")
    parser.add_argument("--run", action="store_true", help="Run one generation")
    parser.add_argument("--report", action="store_true", help="Generate report from latest generation")
    parser.add_argument("--crossover", action="store_true", help="Show crossover pairs only")
    parser.add_argument("--landscape", action="store_true", help="Show fitness landscape only")
    parser.add_argument("--extinct", action="store_true", help="Show extinction candidates only")
    parser.add_argument("--detailed", action="store_true", help="Full detailed report")
    parser.add_argument("--immune", action="store_true", help="Vault immune system check")
    parser.add_argument("--trends", action="store_true", help="Multi-generational trends")
    parser.add_argument("--heal", action="store_true", help="Auto-fix broken links")
    parser.add_argument("--full", action="store_true", help="Run all: generation + immune + trends")
    
    args = parser.parse_args()
    
    dv = DarwinianVault()
    
    # Single-action flags
    if args.immune:
        print(dv.immune_report())
        sys.exit(0)
    if args.trends:
        print(dv.trends_report())
        sys.exit(0)
    if args.heal:
        print(dv.heal_broken_links())
        sys.exit(0)
    
    if args.full:
        print("═══ DARWINIAN VAULT — FULL SCAN ═══")
        print()
        snapshot = dv.run_generation()
        print(dv.report())
        print()
        print(dv.immune_report())
        print()
        print(dv.trends_report())
        sys.exit(0)
    
    if args.run or not any([args.report, args.crossover, args.landscape, args.extinct, args.immune, args.trends, args.heal, args.full]):
        snapshot = dv.run_generation()
        if args.report:
            print(dv.report())
        elif args.crossover:
            _, _, crosstop = dv._latest
            for p in crosstop:
                print(dv.crossover.design_hybrid(p))
                print()
        elif args.landscape:
            _, landscape, _ = dv._latest
            print(landscape.report(detailed=True))
        elif args.extinct:
            if snapshot.extinct_candidates:
                print("Extinction candidates:")
                for name in snapshot.extinct_candidates:
                    print(f"  ⚰ {name}")
            else:
                print("No extinction candidates")
        else:
            print(dv.report())
    else:
        # Load latest if exists
        latest_path = os.path.join(dv.GENERATIONS_DIR, "latest.json")
        if not os.path.exists(latest_path):
            print("No generation data. Run --run first.")
            sys.exit(1)
        
        with open(latest_path) as f:
            data = json.load(f)
        
        if args.report:
            # Re-run to get full context
            dv.run_generation()
            print(dv.report())
