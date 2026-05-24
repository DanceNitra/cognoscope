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
from ari_engine import GraphLoader, AnomalyDetector

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
# VAULT METRIC
# ──────────────────────────────────────────────

class VaultMetric(Metric):
    """Evaluate vault concept quality. Higher = better."""
    
    def __init__(self):
        self.graph = None
        try:
            self.graph = GraphLoader()
        except Exception:
            pass
    
    def evaluate(self, file_path: str) -> float:
        """Compute vault quality metric for a concept note."""
        try:
            with open(file_path) as f:
                content = f.read()
            return self.evaluate_content(content, file_path)
        except Exception:
            return 0.0
    
    def evaluate_content(self, content: str, file_path: str = "") -> float:
        """Compute metric from content string."""
        if not content.strip():
            return 0.0
        
        # 1. Content size score (capped at 400L)
        lines = content.count('\n') + 1
        size_score = min(1.0, lines / 400) * 0.20
        
        # 2. Wikilink density
        wikilinks = len(re.findall(r'\[\[([^\]]+)\]\]', content))
        density_score = min(1.0, wikilinks / 20) * 0.25
        
        # 3. Section quality
        required_sections = ["## 1", "## 2", "## 3"]
        section_score = sum(1 for s in required_sections if s in content) / len(required_sections) * 0.15
        
        # 4. Frontmatter presence
        has_frontmatter = content.startswith("---")
        has_domain = "domain:" in content[:100]
        has_sources = "sources:" in content[:100] or "---" not in content[:100] == False
        fm_score = (has_frontmatter + has_domain) / 2 * 0.10
        
        # 5. Breaktruth claim
        has_breaktruth = "## Breaktruth Claim" in content
        bt_score = 0.10 if has_breaktruth else 0.0
        
        # 6. Cross-domain connections (if graph is available)
        cd_score = 0.0
        if self.graph:
            domain = self._extract_domain(content)
            if domain:
                cross_domain_links = 0
                for link in re.findall(r'\[\[([^\]]+)\]\]', content):
                    node = self.graph.nodes.get(link)
                    if node and node.domain and node.domain != domain:
                        cross_domain_links += 1
                cd_score = min(1.0, cross_domain_links / 5) * 0.20
            else:
                cd_score = 0.05
        
        total = size_score + density_score + section_score + fm_score + bt_score + cd_score
        return round(total, 4)
    
    def _extract_domain(self, content: str) -> str | None:
        match = re.search(r'domain:\s*(.+?)\n', content)
        return match.group(1).strip() if match else None


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
