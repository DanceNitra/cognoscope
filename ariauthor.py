#!/usr/bin/env python3
"""
ariauthor.py — Phase 1: AutoResearch for Vault Concept Optimization

The AutoResearch loop applied to vault concept notes.
ARI detects structural gaps — AR optimizes how we fill them.

How it works:
  1. ARI's AnomalyDetector identifies a concept gap (stub, missing bridge, etc.)
  2. AR takes the candidate concept and runs N experiments on its structure
  3. Each experiment: mutate the concept (add/remove sections, links, keywords)
  4. Evaluate vault metric (Φ gain, wikilink density, domain coverage)
  5. Binary keep/discard — keep only improvements
  6. Git commit each kept experiment
  7. After N experiments, best version is in the vault

Metrics used:
  - vault_phi: estimated Φ contribution (integration × size × cross-domain links)
  - wikilink_density: ratio of [[links]] to lines of content
  - domain_coverage: how many domains the concept touches
  - structure_score: presence of key sections (definition, mechanisms, related concepts)
"""

import os, sys, re, json, math, random
from datetime import datetime

# Add cognoscope to path
sys.path.insert(0, os.path.expanduser("~/cognoscope"))
from autoresearch import (
    Mutator, Metric, AutoResearchLoop, AutoResearchConfig,
    AutoResearchResult, save_ar_report, format_ar_result
)
from ari_engine import GraphLoader, AnomalyDetector, ConceptNode

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")


# ──────────────────────────────────────────────
# VAULT MUTATOR
# ──────────────────────────────────────────────

class VaultMutator(Mutator):
    """
    Generates mutations of a vault concept note.
    
    Mutation strategies:
      a. Add/reorder sections (structural mutation)
      b. Add/remove wikilinks (connection mutation)
      c. Deepen existing sections (content mutation)
      d. Add breaktruth claim (edge mutation)
    """
    
    MUTATION_TYPES = [
        "add_wikilinks",
        "add_breaktruth",
        "add_domain_connection",
        "restructure_sections",
        "deepen_existing",
    ]
    
    def __init__(self):
        self.graph = None
        self._load_graph()
    
    def _load_graph(self):
        """Load vault graph for domain-aware mutations."""
        try:
            self.graph = GraphLoader()  # __init__ calls _load()
        except Exception as e:
            print(f"  Graph load failed: {e}")
            self.graph = None
    
    def mutate(self, file_path: str, content: str, experiment_id: int, history: list) -> tuple[str, str]:
        """
        Mutate a vault concept note.
        Returns (new_content, mutation_log).
        """
        mutation_type = random.choice(self.MUTATION_TYPES)
        
        parsers = {m: getattr(self, f"_{m}", None) for m in self.MUTATION_TYPES}
        parser = parsers.get(mutation_type)
        
        if parser and callable(parser):
            return parser(content, file_path)
        
        # Fallback: just return unchanged
        return content, "no-op"
    
    def _add_wikilinks(self, content: str, file_path: str) -> tuple[str, str]:
        """Add 2-5 new wikilinks to the concept from the vault graph."""
        if not self.graph:
            return content, "no-op (no graph)"
        
        # Parse current wikilinks
        current_links = set(re.findall(r'\[\[([^\]]+)\]\]', content))
        
        # Get the concept's domain
        domain = self._extract_domain(content)
        
        # Find unlinked concepts in related domains
        candidates = []
        for node in self.graph.nodes.values():
            if node.title not in current_links and node.domain and node.lines >= 50:
                # Prioritize cross-domain links (higher Φ impact)
                if domain and node.domain != domain:
                    candidates.append((node, 1.5))  # cross-domain bonus
                else:
                    candidates.append((node, 1.0))
        
        if not candidates:
            return content, "no-op (no candidates)"
        
        # Pick 2-5 random candidates weighted by cross-domain bonus
        weights = [w for _, w in candidates]
        n_links = min(random.randint(2, 5), len(candidates))
        selected = random.choices([n for n, _ in candidates], weights=weights, k=n_links)
        
        # Insert wikilinks in the "Related Concepts" section
        related_section = "\n\n## Related Concepts\n\n"
        for node in selected:
            related_section += f"- [[{node.title}]]\n"
        
        # Append before breaktruth or at end
        if "## Breaktruth Claim" in content:
            new_content = content.replace(
                "## Breaktruth Claim",
                related_section + "\n## Breaktruth Claim"
            )
        else:
            new_content = content + related_section
        
        titles = [n.title for n in selected]
        return new_content, f"add wikilinks: {', '.join(titles[:3])} (+{n_links})"
    
    def _add_breaktruth(self, content: str, file_path: str) -> tuple[str, str]:
        """Add or improve the breaktruth claim section."""
        if "## Breaktruth Claim" in content:
            return content, "no-op (already has breaktruth)"
        
        # Extract title from frontmatter
        title_match = re.search(r'title:\s*"?(.+?)"?\n', content)
        title = title_match.group(1).strip('"') if title_match else "this concept"
        
        breaktruth = (
            f"\n\n## Breaktruth Claim\n\n"
            f"> **{title} reveals that {self._generate_breaktruth_claim(content)}**\n"
        )
        
        new_content = content + breaktruth
        return new_content, "add breaktruth claim"
    
    def _generate_breaktruth_claim(self, content: str) -> str:
        """Generate a generic but plausible breaktruth claim."""
        templates = [
            "the fundamental architecture is shared across domains, not invented within each one",
            "what we thought were separate mechanisms are actually the same process at different scales",
            "the boundary between the two domains is an artifact of academic history, not nature",
            "the same control architecture appears wherever a system persists in a changing environment",
            "the isomorphism between these domains is evidence of a deeper invariant, not a coincidence",
        ]
        return random.choice(templates)
    
    def _add_domain_connection(self, content: str, file_path: str) -> tuple[str, str]:
        """Add a paragraph connecting the concept to a different domain."""
        if not self.graph:
            return content, "no-op (no graph)"
        
        domain = self._extract_domain(content)
        if not domain:
            return content, "no-op (no domain)"
        
        # Find a related domain
        related_domains = []
        for d, nodes in self.graph.domains.items():
            if d != domain and len(nodes) >= 3:
                related_domains.append(d)
        
        if not related_domains:
            return content, "no-op (no related domains)"
        
        target_domain = random.choice(related_domains)
        sample_concepts = self.graph.domains.get(target_domain, [])[:3]
        concept_refs = " and ".join(f"[[{c}]]" for c in sample_concepts)
        
        # Find a good spot to insert — before "Related Concepts" or at end
        connection_para = (
            f"\n\n### Connection to {target_domain}\n\n"
            f"The mechanisms described here have direct parallels in {target_domain}. "
            f"Notably, {concept_refs} exhibit structurally similar dynamics. "
            f"This suggests a deeper organizing principle that unifies {domain} and {target_domain} — "
            f"a cross-domain invariant worth exploring systematically."
        )
        
        if "## Related Concepts" in content:
            new_content = content.replace(
                "## Related Concepts",
                f"---\n{connection_para}\n\n## Related Concepts"
            )
        else:
            new_content = content + connection_para
        
        return new_content, f"add {target_domain} connection"
    
    def _restructure_sections(self, content: str, file_path: str) -> tuple[str, str]:
        """Reorder or rename sections for better flow."""
        # Simple: ensure common sections exist
        required = ["## Definition", "## Overview", "## Related"]
        added = []
        new_content = content
        
        for section in required:
            if section not in new_content:
                # Add at appropriate position
                if section == "## Definition":
                    # Add after frontmatter
                    new_content = new_content + f"\n\n{section}\n\nThis concept explores the fundamental principles underlying its domain.\n"
                elif section == "## Overview":
                    new_content = new_content + f"\n\n{section}\n\nThis concept connects multiple domains through shared structural patterns.\n"
                elif "## Related" in section:
                    new_content = new_content + f"\n\n{section} Concepts\n\n"
                added.append(section)
        
        if added:
            return new_content, f"add sections: {', '.join(a.replace('## ', '') for a in added)}"
        return content, "no-op (all sections present)"
    
    def _deepen_existing(self, content: str, file_path: str) -> tuple[str, str]:
        """Deepen the longest existing section with additional detail."""
        # Find current sections
        sections = re.split(r'\n## ', content)
        if len(sections) <= 2:
            return content, "no-op (too few sections)"
        
        # Pick a non-definition, non-related section to deepen
        candidates = [(i, s) for i, s in enumerate(sections) 
                      if not s.startswith("Definition") and not s.startswith("Related")
                      and not s.startswith("Breaktruth")]
        if not candidates:
            return content, "no-op (no candidates)"
        
        idx, section = random.choice(candidates)
        header = section.split('\n')[0].strip() if '\n' in section else section.strip()
        
        # Add a speculative paragraph
        speculation = (
            f"\n\n### Implications for Future Research\n\n"
            f"The relationship between {header.lower()} and adjacent phenomena suggests "
            f"several open questions. Future work should investigate whether these patterns "
            f"generalize across the broader domain and what boundary conditions constrain them. "
            f"Cross-domain validation remains the most promising path to establishing "
            f"the robustness of these findings."
        )
        
        new_section = section + speculation
        new_sections = sections.copy()
        new_sections[idx] = new_section
        new_content = "## ".join(new_sections)
        
        return new_content, f"deepen {header}"
    
    def _extract_domain(self, content: str) -> str | None:
        """Extract domain from frontmatter."""
        match = re.search(r'domain:\s*(.+?)\n', content)
        return match.group(1).strip() if match else None
    
    def _extract_title(self, content: str) -> str:
        """Extract title from frontmatter."""
        match = re.search(r'title:\s*"?(.+?)"?\n', content)
        return match.group(1).strip().strip('"') if match else "Untitled"


# ──────────────────────────────────────────────
# VAULT METRIC v2 — Kvalita, nie kvantita
# ──────────────────────────────────────────────

class VaultMetric(Metric):
    """Evaluate vault concept quality. Higher = better.
    
    v2 changes:
    1. Deep reading: measures factual density vs generic filler
    2. Cross-domain meaningfulness: filters noise links via graph relevance
    3. Φ contribution delta: how much this concept increases vault-wide integration
    """
    
    GENERIC_PATTERNS = [
        r'This concept explores',
        r'The mechanisms described here',
        r'This suggests a deeper',
        r'Notably,',
        r'This relationship suggests',
        r'Future work should',
        r'This is worth exploring',
        r'The relationship between',
        r'adjacent phenomena suggests',
        r'This reveals that',
        r'the fundamental architecture is shared',
        r'what we thought were separate',
        r'the boundary between',
        r'an artifact of academic history',
        r'the same control architecture',
        r'the isomorphism between',
        r'is evidence of a deeper',
        r'not a coincidence',
    ]
    
    # Cross-domain link pairs that vault already validates as meaningful
    # (populated from existing high-quality cross-domain references in vault)
    MEANINGFUL_PAIRS = {
        ('Neuroscience', 'Psychology'): True,
        ('Neuroscience', 'AI'): True,
        ('Neuroscience', 'Sleep'): True,
        ('Neuroscience', 'Philosophy'): True,
        ('Psychology', 'Philosophy'): True,
        ('Psychology', 'Neuroscience'): True,
        ('Psychology', 'AI'): True,
        ('AI', 'Neuroscience'): True,
        ('AI', 'Psychology'): True,
        ('AI', 'Philosophy'): True,
        ('AI', 'Software Engineering'): True,
        ('Finance', 'Economics'): True,
        ('Finance', 'Psychology'): True,
        ('Finance', 'Neuroscience'): True,
        ('Trading', 'Finance'): True,
        ('Trading', 'Psychology'): True,
        ('Causal Inference', 'Statistics'): True,
        ('Causal Inference', 'AI'): True,
        ('Statistics', 'Causal Inference'): True,
        ('Sleep', 'Neuroscience'): True,
        ('Sleep', 'Psychology'): True,
        ('Sleep', 'Physiology'): True,
        ('Cell Biology', 'Physiology'): True,
        ('Cell Biology', 'Longevity'): True,
        ('Cell Biology', 'Neuroscience'): True,
        ('Physiology', 'Neuroscience'): True,
        ('Physiology', 'Sleep'): True,
        ('Longevity', 'Cell Biology'): True,
        ('Longevity', 'Physiology'): True,
        ('Philosophy', 'Neuroscience'): True,
        ('Philosophy', 'Psychology'): True,
        ('Philosophy', 'AI'): True,
        ('Software Engineering', 'AI'): True,
        ('Software Engineering', 'Neuroscience'): True,
        ('Software Engineering', 'Philosophy'): True,
        ('Economics', 'Finance'): True,
        ('Economics', 'Psychology'): True,
        ('Complexity Science', 'Neuroscience'): True,
        ('Complexity Science', 'Finance'): True,
        ('Complexity Science', 'AI'): True,
        ('Immunology', 'Neuroscience'): True,
        ('Immunology', 'Cell Biology'): True,
        ('Immunology', 'Longevity'): True,
        ('Meta', 'AI'): True,
        ('Meta', 'Neuroscience'): True,
        ('Meta', 'Philosophy'): True,
    }
    
    # Domains that almost never form meaningful cross-domain links
    NOISE_DOMAINS = {
        'Blockchain', 'Crypto', 'NFT', 'Web3', 'Metaverse',
        'Solana', 'Bitcoin', 'Ethereum', 'DeFi',
    }
    
    def __init__(self):
        self.graph = None
        try:
            self.graph = GraphLoader()
            self._build_meaningful_pairs()
        except Exception:
            pass
    
    def _build_meaningful_pairs(self):
        """Auto-extend MEANINGFUL_PAIRS from existing vault cross-links."""
        if not self.graph:
            return
        for (d1, d2), count in self.graph.domain_pairs.items():
            if count >= 3:  # At least 3 existing vault notes cross-link these domains
                key = (d1, d2)
                self.MEANINGFUL_PAIRS[key] = True
                self.MEANINGFUL_PAIRS[(d2, d1)] = True
    
    def evaluate(self, file_path: str) -> float:
        """Compute vault quality metric for a concept note."""
        try:
            with open(file_path) as f:
                content = f.read()
            return self.evaluate_content(content, file_path)
        except Exception:
            return 0.0
    
    def _extract_domain(self, content: str) -> str | None:
        match = re.search(r'domain:\s*(.+?)$', content, re.MULTILINE)
        return match.group(1).strip() if match else None
    
    def evaluate_content(self, content: str, file_path: str = "") -> float:
        """Compute metric from content string.
        
        Scoring breakdown:
          1. Substantive content (0.25) — deep reading: facts vs filler
          2. Quality wikilinks (0.25) — meaningful + domain-relevant, penalises noise
          3. Structure quality (0.15) — numbered sections with actual depth
          4. Φ contribution (0.20) — how much this increases vault integration
          5. Frontmatter + breaktruth (0.15) — baseline requirements
        
        Max: 1.0 (theoretical ceiling)
        Good evergreen: 0.50-0.75
        Excellent evergreen: 0.75-0.90
        Outstanding (rare): 0.90+
        """
        if not content.strip():
            return 0.0
        
        lines = content.count('\n') + 1
        domain = self._extract_domain(content)
        
        # ── 1. SUBSTANTIVE CONTENT (0.25) ──
        deep_score = self._score_deep_reading(content, lines)
        
        # ── 2. QUALITY WIKILINKS (0.25) ──
        link_score = self._score_wikilinks(content, domain)
        
        # ── 3. STRUCTURE QUALITY (0.15) ──
        structure_score = self._score_structure(content)
        
        # ── 4. Φ CONTRIBUTION (0.20) ──
        phi_score = self._score_phi_contribution(content, file_path, domain)
        
        # ── 5. BASELINE (0.15) ──
        baseline_score = self._score_baseline(content)
        
        total = (deep_score * 0.25 + link_score * 0.25 + structure_score * 0.15
                 + phi_score * 0.20 + baseline_score * 0.15)
        
        return round(min(1.0, total), 4)
    
    # ──────────────────────────────────────────
    # 1. DEEP READING METRIC
    # ──────────────────────────────────────────
    
    def _score_deep_reading(self, content: str, lines: int) -> float:
        """Measure substantive content density vs generic filler.
        
        v2.1: increased floor for AR-tuned content (sections + references count)
        """
        score = 0.0
        
        # 1a. GENERIC FILLER PENALTY
        generic_count = 0
        for pattern in self.GENERIC_PATTERNS:
            generic_count += len(re.findall(pattern, content, re.IGNORECASE))
        
        generic_penalty = min(0.5, generic_count * 0.05)
        
        # 1b. SPECIFIC CONTENT (numbers, data, citations)
        has_numbers = bool(re.search(r'\d+[%×±]|\b\d{3,}\b', content))
        has_citations_paren = bool(re.search(r'\([A-Z][a-z]+.*?\d{4}\)', content))
        has_citations_bracket = bool(re.search(r'\[\d+[^}\]]*\]', content))
        has_tables = bool(re.search(r'\|.*\|.*\|', content))
        has_formulas = bool(re.search(r'\$.*\$|\\[a-zA-Z]+', content))
        
        specificity_score = (
            0.15 * has_numbers +
            0.15 * has_citations_paren +
            0.10 * has_citations_bracket +
            0.10 * has_tables +
            0.10 * has_formulas
        )
        
        # 1c. SUBSTANTIVE SENTENCES — count paragraphs with real claims
        substantive_clues = [
            ' is the ', ' refers to ', ' defined as ',
            ' demonstrates ', ' shows that ', ' found that ',
            ' because ', ' therefore ', ' however ',
            ' Specifically, ', ' For example, ', ' Importantly, ',
            'mechanism', 'pathway', 'circuit', 'process',
            'theory', 'hypothesis', 'evidence', 'data',
            'region', 'system', 'network', 'architecture',
        ]
        
        sentences = content.split('. ')
        substantive_sentences = sum(
            1 for s in sentences if any(clue.lower() in s.lower() for clue in substantive_clues)
        )
        total_sentences = max(1, len(sentences))
        density_ratio = min(1.0, substantive_sentences / max(1, total_sentences) * 2)
        
        # 1d. SECTION DEPTH — paragraphs (5+ lines) in sections
        sections = re.split(r'\n## ', content)
        deep_sections = sum(1 for s in sections[1:] if len(s.split('\n')) >= 5)
        depth_ratio = min(1.0, deep_sections / max(1, len(sections) - 1))
        
        # 1e. CONTENT LENGTH BONUS — reward substantive length (not just presence)
        length_bonus = min(0.2, lines / 1000 * 0.2)
        
        score = (specificity_score * 0.3 + density_ratio * 0.25 + depth_ratio * 0.25 
                 + length_bonus - generic_penalty)
        
        # Floor based on content presence
        base = 0.05 if lines >= 10 else 0.0
        has_frontmatter = content.startswith('---')
        if has_frontmatter and lines >= 15:
            base = 0.15
        
        return max(base, min(1.0, score))
    
    # ──────────────────────────────────────────
    # 2. QUALITY WIKILINKS METRIC
    # ──────────────────────────────────────────
    
    def _score_wikilinks(self, content: str, domain: str | None) -> float:
        """Measure wikilink quality vs noise.
        
        Rewards:
          - Cross-domain links to MEANINGFUL_PAIRS domains
          - Links to high-Φ concepts (well-integrated)
          - Bidirectional references (link exists both ways)
        
        Penalises:
          - Links to NOISE_DOMAINS (crypto, blockchain, etc.)
          - Generic self-links (same domain without real connection)
          - Links to stubs (low-value targets)
        """
        wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)
        if not wikilinks:
            return 0.0
        
        if not self.graph:
            # Fallback without graph: just count unique
            return min(1.0, len(set(wikilinks)) / 15) * 0.5
        
        total_score = 0.0
        meaningful_count = 0
        noise_count = 0
        
        for link_text in wikilinks:
            node = self.graph.nodes.get(link_text)
            if not node:
                continue
            
            link_domain = node.domain
            
            # Check if link is meaningful
            if domain and link_domain and domain != link_domain:
                # Cross-domain link
                pair = (domain, link_domain)
                if pair in self.MEANINGFUL_PAIRS:
                    meaningful_count += 1
                    # Bonus for high-Φ targets
                    total_score += 0.12 * min(1.0, node.phi_estimate * 3)
                elif link_domain in self.NOISE_DOMAINS:
                    noise_count += 1
                    total_score -= 0.20  # Penalty for noise
                elif node.lines >= 100:
                    # Unknown but substantive cross-domain link = potential discovery
                    meaningful_count += 0.5
                    total_score += 0.06
            elif domain and link_domain and domain == link_domain:
                # Same-domain link: useful if target is high-Φ
                if node.phi_estimate >= 0.5:
                    total_score += 0.06
                elif node.lines >= 50:
                    total_score += 0.03
            else:
                # Unknown domain link
                if node.phi_estimate >= 0.3:
                    total_score += 0.04
        
        # Normalise by total links (but reward meaningful links)
        total_links = max(1, len(wikilinks))
        noise_penalty = min(0.5, noise_count * 0.15)
        meaningful_bonus = min(0.3, meaningful_count * 0.05)
        
        normalised = (total_score / total_links * 2) + meaningful_bonus - noise_penalty
        
        return max(0.0, min(1.0, normalised))
    
    # ──────────────────────────────────────────
    # 3. STRUCTURE QUALITY
    # ──────────────────────────────────────────
    
    def _score_structure(self, content: str) -> float:
        """Measure structure quality beyond just 'has sections'.
        
        Rewards:
          - Numbered sections with depth (not just headers)
          - Tables with content
          - Code blocks or formulas
          - Consistent formatting
        """
        score = 0.0
        
        # Numbered sections (## 1, ## 2, ## 3...)
        sections = re.findall(r'^## \d+\.', content, re.MULTILINE)
        section_depth = min(1.0, len(sections) / 5) * 0.30
        score += section_depth
        
        # Tables (markdown tables with content)
        tables = re.findall(r'^\|.*\|$', content, re.MULTILINE)
        table_score = min(1.0, len(tables) / 15) * 0.25
        score += table_score
        
        # Code blocks
        has_code = '```' in content
        score += 0.10 if has_code else 0.0
        
        # Formulas (LaTeX math)
        has_formulas = bool(re.search(r'\$.*\$', content))
        score += 0.10 if has_formulas else 0.0
        
        # Consistent paragraph length (penalty for single-line sections)
        paragraphs = [p for p in content.split('\n\n') if len(p.strip()) > 0]
        shallow_paras = sum(1 for p in paragraphs if 1 < len(p.split('\n')) <= 2 and not p.startswith('|'))
        shallow_ratio = shallow_paras / max(1, len(paragraphs))
        depth_penalty = shallow_ratio * 0.15
        
        score -= depth_penalty
        
        return max(0.0, min(1.0, score))
    
    # ──────────────────────────────────────────
    # 4. Φ CONTRIBUTION DELTA
    # ──────────────────────────────────────────
    
    def _score_phi_contribution(self, content: str, file_path: str, 
                                  domain: str | None) -> float:
        """Measure how much this concept contributes to vault-wide integration.
        
        Φ contribution = how many NEW connections this concept makes
        between domains that were previously not connected.
        
        Metrics:
          a. Links to high-Φ vault concepts
          b. Creates new cross-domain edges (novel connections)
          c. Bridges domains that had zero existing links
        
        Without graph: fallback to link diversity.
        """
        if not self.graph:
            # Fallback: unique domains linked
            wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)
            domains_linked = set()
            for link in wikilinks:
                node = self.graph.nodes.get(link) if self.graph else None
                if node and node.domain:
                    domains_linked.add(node.domain)
            return min(1.0, len(domains_linked) / 4) * 0.5 + 0.1
        
        wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)
        total_domains = len(set(
            self.graph.nodes.get(l, ConceptNode(file='', title=l, status='unknown',
                                   domain='Unknown', tags=[], aliases=[],
                                   lines=0, wikilinks_out=[], wikilinks_in=0,
                                   has_sources=False, date='', phi_estimate=0.0)).domain
            for l in wikilinks if self.graph.nodes.get(l)
        ))
        
        # Reward linking to high-Φ concepts
        phi_sum = sum(
            max(0, self.graph.nodes[l].phi_estimate if l in self.graph.nodes else 0.0)
            for l in wikilinks if self.graph.nodes.get(l)
        ) if wikilinks else 0
        avg_target_phi = phi_sum / max(1, len(wikilinks))
        
        # Reward domain diversity
        domain_diversity = min(1.0, total_domains / 4) * 0.5
        
        # Reward high-quality targets
        target_quality = min(1.0, avg_target_phi * 3) * 0.3
        
        # Novelty bonus: if concept creates EDGES between domains
        # that had no previous connection in vault (requires full analysis)
        novelty = 0.0
        if file_path:
            novelty = self._estimate_novelty(content, file_path, domain, wikilinks)
        
        return min(1.0, domain_diversity + target_quality + novelty)
    
    def _estimate_novelty(self, content: str, file_path: str,
                           domain: str | None, wikilinks: list[str]) -> float:
        """Estimate novelty: does this concept make new cross-domain links?"""
        if not self.graph or not domain:
            return 0.0
        
        if not wikilinks:
            return 0.0
        
        # Count cross-domain links that are to well-integrated targets
        cross_integrated = 0
        total_cross = 0
        
        for link in set(wikilinks):
            node = self.graph.nodes.get(link)
            if node and node.domain and node.domain != domain:
                total_cross += 1
                if node.phi_estimate >= 0.6:  # High-Φ concept
                    cross_integrated += 1
        
        if total_cross == 0:
            return 0.0
        
        # Fraction of cross-links to high-value targets
        ratio = cross_integrated / max(1, total_cross)
        return ratio * 0.2
    
    # ──────────────────────────────────────────
    # 5. BASELINE
    # ──────────────────────────────────────────
    
    def _score_baseline(self, content: str) -> float:
        """Check baseline vault requirements."""
        score = 0.0
        
        # Frontmatter
        has_fm = content.startswith('---')
        has_domain = 'domain:' in content[:100]
        has_sources = 'sources:' in content[:200]
        
        fm_score = (
            0.10 * has_fm +
            0.10 * has_domain +
            0.10 * has_sources
        )
        score += fm_score
        
        # Breaktruth claim
        if '## Breaktruth Claim' in content:
            score += 0.15
        elif '## Breaktruth' in content:
            score += 0.10
        
        # Title (should be meaningful, not generic)
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            if len(title) >= 5 and not title.startswith('Auto-generated'):
                score += 0.10
        
        # Status: evergreen bonus
        if 'status: evergreen' in content[:200]:
            score += 0.10
        
        # Minimum length
        lines = content.count('\n') + 1
        if 100 <= lines <= 500:
            score += 0.10
        elif lines > 500:
            score += 0.05  # Very long notes may need splitting
        
        return min(1.0, score)


# ──────────────────────────────────────────────
# ARI → AR INTEGRATION
# ──────────────────────────────────────────────

def run_ar_on_ari_prediction(prediction_id: int | None = None):
    """
    Run AutoResearch on an ARI prediction.
    
    If prediction_id is None, runs on the top ARI prediction.
    """
    from ari_engine import GraphLoader, AnomalyDetector
    
    loader = GraphLoader()
    
    detector = AnomalyDetector(loader)
    
    predictions = detector.predictions
    if not predictions:
        print("No ARI predictions found")
        return None
    
    if prediction_id is not None:
        pred = next((p for p in predictions if p.id == prediction_id), None)
        if not pred:
            print(f"Prediction {prediction_id} not found")
            return None
    else:
        # Use top prediction that targets an existing concept
        valid_preds = [p for p in predictions if os.path.exists(
            os.path.join(CONCEPTS_DIR, f"{p.predicted_title}.md"))]
        if not valid_preds:
            print("No predictions targeting existing concepts")
            return None
        pred = valid_preds[0]
    
    print(f"\nARI Prediction: {pred.predicted_title}")
    print(f"  Type: {pred.type}")
    print(f"  Confidence: {pred.confidence:.2f}")
    print(f"  Source: {pred.source_domain} → Target: {pred.target_domain}")
    
    # Check if target concept exists
    concept_path = os.path.join(CONCEPTS_DIR, f"{pred.predicted_title}.md")
    
    if os.path.exists(concept_path):
        # Concept exists — optimize it
        print(f"\n  Target exists. Running AR optimization...")
        mutator = VaultMutator()
        metric = VaultMetric()
        baseline = metric.evaluate(concept_path)
        
        loop = AutoResearchLoop(
            subject_name=pred.predicted_title,
            file_path=concept_path,
            mutator=mutator,
            metric=metric,
            baseline=baseline,
        )
        result = loop.run()
        save_ar_report(result)
        return result
    else:
        # Concept doesn't exist — need to create it first, then optimize
        print(f"\n  Target doesn't exist. Created via ARI writer.")
        return None


def ar_batch_from_ari(n_best: int = 3):
    """Run AR on the top N ARI predictions."""
    from ari_engine import GraphLoader, AnomalyDetector
    
    loader = GraphLoader()
    loader.load_all()
    
    detector = AnomalyDetector(loader)
    detector.run_all()
    
    predictions = detector.predictions[:n_best]
    
    results = []
    for pred in predictions:
        result = run_ar_on_ari_prediction(pred.id)
        if result:
            results.append(result)
    
    return results


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def demo():
    """Demo: run AR on an existing concept note."""
    test_file = os.path.join(CONCEPTS_DIR, "Synaptic Plasticity.md")
    if not os.path.exists(test_file):
        test_file = None
        for fname in os.listdir(CONCEPTS_DIR):
            if fname.endswith(".md") and fname != "AGENTS.md":
                test_file = os.path.join(CONCEPTS_DIR, fname)
                break
    
    if not test_file:
        print("No concept files found")
        return
    
    title = os.path.splitext(os.path.basename(test_file))[0]
    print(f"\nDemo: Running AR on {title}")
    
    mutator = VaultMutator()
    metric = VaultMetric()
    baseline = metric.evaluate(test_file)
    
    config = AutoResearchConfig(
        max_experiments=10,  # small demo
        time_budget_sec=30,
    )
    
    loop = AutoResearchLoop(
        subject_name=title,
        file_path=test_file,
        mutator=mutator,
        metric=metric,
        config=config,
        baseline=baseline,
    )
    result = loop.run()
    save_ar_report(result)
    
    print(format_ar_result(result))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ARI AutoResearch Phase 1")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--ari-top", type=int, default=0, 
                        help="Run AR on top N ARI predictions")
    parser.add_argument("--prediction", type=int, default=None,
                        help="Run AR on specific ARI prediction")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.prediction:
        run_ar_on_ari_prediction(args.prediction)
    elif args.ari_top:
        ar_batch_from_ari(args.ari_top)
    else:
        print("Usage: python3 ariauthor.py --demo")
        print("       python3 ariauthor.py --ari-top 3")
        print("       python3 ariauthor.py --prediction 0")
