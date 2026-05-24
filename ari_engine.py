#!/usr/bin/env python3
"""
ARI — Autonomous Research Intelligence
Layer 1: Node Prediction Module

Scans the vault's concept graph for structural anomalies and predicts
missing concept notes that the graph itself implies should exist.

Detection strategies:
  1. Asymmetric edges — domain A links to B heavily, B barely links back
  2. Dangling senders — concepts with high out-links and near-zero in-links
  3. Missing triads — A→B→C exists but no direct A→C path
  4. Bridge potential — domains with shared neighbors but no existing bridge
  5. Stub isolation — low-backlink concepts that need structural integration

Usage:
    python3 ari_engine.py --scan           # Full scan, print predictions
    python3 ari_engine.py --top-n 10       # Top 10 predictions
    python3 ari_engine.py --prediction N   # Show one prediction in detail
    python3 ari_engine.py --write N        # Auto-write the predicted node
"""

import os, re, glob, json, math, random
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, Counter
from typing import Any

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
PUBS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")
ARI_DIR = os.path.join(VAULT_ROOT, "04 Resources/ARI")
DISTILLED_DIR = os.path.join(VAULT_ROOT, "04 Resources/Distilled")
ARI_MEMORY_PATH = os.path.join(ARI_DIR, "ari_memory.json")
os.makedirs(ARI_DIR, exist_ok=True)


# ──────────────────────────────────────────────
# GRAPH LOADER
# ──────────────────────────────────────────────

@dataclass
class ConceptNode:
    file: str
    title: str
    status: str              # evergreen, growing, seedling, stub
    domain: str              # from frontmatter
    tags: list[str]          # from frontmatter
    aliases: list[str]       # from frontmatter
    lines: int
    wikilinks_out: list[str]  # [[links]] pointing from this note
    wikilinks_in: int         # count of notes linking TO this one
    has_sources: bool
    date: str
    phi_estimate: float = 0.0  # placeholder — computed below


class GraphLoader:
    """Load all concept notes and build the wikilink graph."""

    def __init__(self):
        self.nodes: dict[str, ConceptNode] = {}  # title → node
        self.domains: dict[str, list[str]] = defaultdict(list)  # domain → titles
        self.domain_pairs: dict[tuple[str, str], int] = Counter()
        self._load()

    def _load(self):
        for f in sorted(glob.glob(os.path.join(CONCEPTS_DIR, "*.md"))):
            fn = os.path.basename(f)
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                raw = fh.read()

            # Parse frontmatter
            fm = re.search(r'^---\n(.*?)\n---', raw, re.DOTALL)
            metadata = {}
            if fm:
                for line in fm.group(1).strip().split('\n'):
                    if ': ' in line:
                        key, val = line.split(': ', 1)
                        metadata[key.strip()] = val.strip()

            title = fn.replace('.md', '')
            title_match = re.search(r'^# (.+)$', raw, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
            # Also check YAML title
            yt = metadata.get('title', '')
            if yt:
                title = yt

            status = metadata.get('status', 'unknown').strip('# ')
            domain = metadata.get('domain', 'General')

            # Tags
            tags_str = metadata.get('tags', '')
            tags = []
            if tags_str.startswith('['):
                tags = [t.strip().strip("'\"") for t in tags_str.strip('[]').split(',') if t.strip()]
            elif tags_str.startswith('#'):
                tags = [t.strip('# ') for t in tags_str.split() if t.startswith('#')]
            elif tags_str:
                tags = [tags_str]

            # Aliases
            aliases_raw = raw.split('---')[1] if '---' in raw else ''
            aliases = list(set(re.findall(r'aliases:\n(\s+- .+\n?)+', raw)))
            # simpler: find lines starting with "  - "
            alias_list = []
            in_alias = False
            for line in raw.split('\n'):
                if line.startswith('aliases:'):
                    in_alias = True
                    continue
                if in_alias:
                    m = re.match(r'\s*-\s*(.+)$', line)
                    if m:
                        alias_list.append(m.group(1).strip().strip("'\""))
                    elif not line.strip().startswith('-'):
                        in_alias = False
            aliases = alias_list

            # Extract wikilinks
            wikilinks_out = list(set(re.findall(r'\[\[([^\]]+?)(?:\|[^\]]+)?\]\]', raw)))
            # Remove self-references
            wikilinks_out = [w for w in wikilinks_out if w != title]

            lines = len(raw.split('\n'))
            has_sources = bool(re.search(r'(?:^|\\n)sources:', raw, re.MULTILINE))
            date = metadata.get('date', metadata.get('created', ''))

            node = ConceptNode(
                file=os.path.join(CONCEPTS_DIR, fn), title=title, status=status, domain=domain,
                tags=tags, aliases=aliases, lines=lines,
                wikilinks_out=wikilinks_out, wikilinks_in=0,
                has_sources=has_sources, date=date
            )
            self.nodes[title] = node
            self.domains[domain].append(title)

        # Compute in-links (who links to whom)
        title_to_title = {}
        for t, node in self.nodes.items():
            title_to_title[t] = t
            for alias in node.aliases:
                title_to_title[alias] = t

        for node in self.nodes.values():
            for link in node.wikilinks_out:
                # Resolve alias
                target = title_to_title.get(link, link)
                if target in self.nodes:
                    self.nodes[target].wikilinks_in += 1

        # Compute domain cross-links
        for node in self.nodes.values():
            for link in node.wikilinks_out:
                target = title_to_title.get(link, link)
                if target in self.nodes:
                    td = self.nodes[target].domain
                    pair = tuple(sorted([node.domain, td]))
                    if node.domain != td:
                        self.domain_pairs[pair] += 1

        # Phi estimate: normalized integration
        max_in = max((n.wikilinks_in for n in self.nodes.values()), default=1)
        max_out = max((len(n.wikilinks_out) for n in self.nodes.values()), default=1)
        max_lines = max((n.lines for n in self.nodes.values()), default=1)
        for node in self.nodes.values():
            in_norm = node.wikilinks_in / max_in
            out_norm = len(node.wikilinks_out) / max_out
            line_norm = node.lines / max_lines
            # Phi ≈ combined integration: receives links + sends links + substance
            node.phi_estimate = round((in_norm * 0.5 + out_norm * 0.3 + line_norm * 0.2), 3)

        self._log(f"Loaded {len(self.nodes)} concepts, {len(self.domains)} domains")

    def _log(self, msg):
        print(f"[ARI] {msg}")


# ──────────────────────────────────────────────
# ANOMALY DETECTORS
# ──────────────────────────────────────────────

@dataclass
class Prediction:
    id: int
    type: str                 # asymmetric, dangling, missing_triad, bridge_gap, stub_isolation
    confidence: float         # 0-1
    source_domain: str
    target_domain: str
    predicted_title: str
    predicted_domain: str
    evidence: str
    suggested_structure: list[str]  # suggested sections
    suggested_sources: list[str]
    phi_impact: float         # estimated Φ gain
    novelty_score: float      # 0-1
    already_exists: bool = False


class AnomalyDetector:
    """Find structural gaps in the concept graph."""

    def __init__(self, graph: GraphLoader):
        self.graph = graph
        self.predictions: list[Prediction] = []
        self._detect()
        self._rank()

    def _detect(self):
        pid = 0
        pid = self._detect_asymmetric_edges(pid)
        pid = self._detect_dangling_senders(pid)
        pid = self._detect_missing_triads(pid)
        pid = self._detect_bridge_gaps(pid)
        pid = self._detect_stub_isolation(pid)
        pid = self._detect_multi_hop_chains(pid)
        print(f"[ARI] Generated {pid} predictions")

    def _detect_asymmetric_edges(self, start_id):
        """
        Strategy 1: Asymmetric edges.
        Domain A has N concepts linking to Domain B.
        Domain B has M concepts linking to Domain A.
        If N >> M and both domains are substantive, predict a missing
        concept in Domain B that synthesizes the A→B connections.
        """
        # Load persistent ARI memory for stale-pair dedup
        ari_memory = self._load_ari_memory()

        # Count cross-domain link pairs
        cross_counts = {}
        for node in self.graph.nodes.values():
            for link in node.wikilinks_out:
                target = self.graph.nodes.get(link)
                if target and target.domain != node.domain:
                    key = (node.domain, target.domain)
                    if key not in cross_counts:
                        cross_counts[key] = {'out': 0, 'from': []}
                    cross_counts[key]['out'] += 1
                    cross_counts[key]['from'].append(node.title)

        pid = start_id
        for (dom_a, dom_b), data in cross_counts.items():
            rev_key = (dom_b, dom_a)
            rev_data = cross_counts.get(rev_key, {'out': 0, 'from': []})
            forward = data['out']
            backward = rev_data['out']

            # Skip if this domain pair was already written and neither domain grew
            if self._is_domain_pair_stale(dom_a, dom_b, ari_memory):
                continue

            # Asymmetry: at least 3:1 ratio and minimum 3 forward links
            if forward >= 3 and backward == 0:
                # Domain A has concepts linking to B, but nothing links back
                # The missing concept should be in Domain A, synthesizing B's perspective
                domain_size_a = len(self.graph.domains.get(dom_a, []))
                domain_size_b = len(self.graph.domains.get(dom_b, []))

                if domain_size_a >= 2 and domain_size_b >= 2:
                    from_concepts = data.get('from', [])[:5]
                    evidence = (
                        f"Domain {dom_a} has {forward} concepts linking to domain {dom_b}, "
                        f"but {dom_b} has 0 concepts linking back. "
                        f"Missing concept in {dom_a} should synthesize the {dom_b}→{dom_a} perspective. "
                        f"Sources: {', '.join(from_concepts[:3])}"
                    )

                    # Infer the predicted domain (the one that should RECEIVE the reciprocal links)
                    pred_domain = dom_a  # The domain that has senders but no receive back
                    pred_title = self._generate_asymmetric_title(dom_a, dom_b, from_concepts)

                    # Estimate Φ impact
                    phi_impact = min(0.05, forward * 0.005)

                    pred = Prediction(
                        id=pid, type='asymmetric',
                        confidence=min(0.9, forward * 0.12),
                        source_domain=dom_b, target_domain=dom_a,
                        predicted_title=pred_title,
                        predicted_domain=pred_domain,
                        evidence=evidence,
                        suggested_structure=[
                            f"The {dom_b} Perspective on {dom_a}",
                            "Key Mechanisms Transferred Across Domains",
                            "Empirical Support",
                            "Implications for Practice"
                        ],
                        suggested_sources=from_concepts,
                        phi_impact=phi_impact,
                        novelty_score=min(0.95, forward * 0.08)
                    )
                    self.predictions.append(pred)
                    pid += 1

        return pid

    def _detect_dangling_senders(self, start_id):
        """
        Strategy 2: Dangling senders.
        Concepts with high outbound links (giving knowledge) but very few
        inbound links (not being referenced back). These are concepts that
        contribute to the graph but aren't structurally integrated.
        """
        pid = start_id
        candidates = []
        for node in self.graph.nodes.values():
            out = len(node.wikilinks_out)
            if out >= 8 and node.wikilinks_in <= 2 and node.lines >= 150:
                candidates.append(node)

        candidates.sort(key=lambda n: -len(n.wikilinks_out))
        for node in candidates[:5]:
            evidence = (
                f"'{node.title}' ({node.domain}) sends {len(node.wikilinks_out)} wikilinks "
                f"but receives only {node.wikilinks_in} backlinks. "
                f"It contributes knowledge but isn't structurally integrated. "
                f"Concepts from {node.wikilinks_out[:5]} link to it — "
                f"reciprocal notes should exist."
            )

            pred = Prediction(
                id=pid, type='dangling',
                confidence=min(0.85, len(node.wikilinks_out) * 0.08),
                source_domain=node.domain,
                target_domain=node.domain,
                predicted_title=f"{node.title} — Integration and Reciprocity",
                predicted_domain=node.domain,
                evidence=evidence,
                suggested_structure=[
                    f"Concepts That Link to {node.title}",
                    "Synthesizing the Reciprocal Relationship",
                    "Practical Applications",
                    "Open Questions"
                ],
                suggested_sources=[node.title],
                phi_impact=min(0.03, len(node.wikilinks_out) * 0.003),
                novelty_score=0.5
            )
            self.predictions.append(pred)
            pid += 1

        return pid

    def _detect_missing_triads(self, start_id):
        """
        Strategy 3: Missing triads.
        If A links to B and B links to C, but there is no direct A→C link,
        the graph suggests a missing connection. The most triad-rich
        domains produce the strongest predictions.
        """
        pid = start_id
        # Build link matrix
        link_matrix = {}
        for node in self.graph.nodes.values():
            for link in node.wikilinks_out:
                target = self.graph.nodes.get(link)
                if target:
                    link_matrix[(node.title, target.title)] = True

        triads_found = []
        # Sample triads — check high-backlink concepts as B
        hubs = sorted(self.graph.nodes.values(), key=lambda n: -n.wikilinks_in)[:30]
        for hub in hubs:
            # Find concepts that link TO hub
            inbound = []
            outbound = []
            for node in self.graph.nodes.values():
                if link_matrix.get((node.title, hub.title)):
                    inbound.append(node)
                if link_matrix.get((hub.title, node.title)):
                    outbound.append(node)

            for a in inbound[:10]:
                for c in outbound[:10]:
                    if a.title != c.title and not link_matrix.get((a.title, c.title)):
                        if a.domain != c.domain:
                            triads_found.append((a, hub, c))

        # Score triads
        scored = []
        for a, hub, c in triads_found:
            score = (a.phi_estimate + hub.phi_estimate + c.phi_estimate) / 3
            scored.append((score, a, hub, c))

        scored.sort(key=lambda x: -x[0])

        for score, a, hub, c in scored[:5]:
            evidence = (
                f"Triad gap: '{a.title}' ({a.domain}) → '{hub.title}' → "
                f"'{c.title}' ({c.domain}). "
                f"A direct '{a.title}' → '{c.title}' link does not exist "
                f"but the graph implies it should, "
                f"bridging {a.domain} and {c.domain} through {hub.domain}."
            )

            pred = Prediction(
                id=pid, type='missing_triad',
                confidence=min(0.8, score * 1.5),
                source_domain=a.domain,
                target_domain=c.domain,
                predicted_title=f"{a.title} and {c.title} — The Hidden Connection Through {hub.title}",
                predicted_domain=f"{a.domain} / {c.domain}",
                evidence=evidence,
                suggested_structure=[
                    f"How {hub.title} Mediates {a.domain} and {c.domain}",
                    f"The Structural Isomorphism",
                    "Empirical Evidence",
                    "Practical Applications",
                    "Open Questions"
                ],
                suggested_sources=[a.title, hub.title, c.title],
                phi_impact=min(0.04, score * 0.05),
                novelty_score=min(0.9, score * 1.2)
            )
            self.predictions.append(pred)
            pid += 1

        return pid

    def _load_ari_memory(self) -> list[dict]:
        """Load persistent ARI memory — tracks every completed prediction."""
        if os.path.exists(ARI_MEMORY_PATH):
            try:
                with open(ARI_MEMORY_PATH, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_ari_memory(self, entry: dict):
        """Append one entry to persistent ARI memory."""
        mem = self._load_ari_memory()
        mem.append(entry)
        with open(ARI_MEMORY_PATH, 'w') as f:
            json.dump(mem, f, indent=2)

    def _is_domain_pair_stale(self, dom_a: str, dom_b: str, memory: list[dict]) -> bool:
        """Check if a domain pair was already bridged and the domains haven't grown."""
        for entry in memory:
            if entry.get('type') not in ('bridge_gap', 'asymmetric', 'missing_triad'):
                continue
            src = entry.get('source_domain', '').lower()
            tgt = entry.get('target_domain', '').lower()
            dom_a_lower = dom_a.lower()
            dom_b_lower = dom_b.lower()
            if {src, tgt} == {dom_a_lower, dom_b_lower}:
                # Check if concept count changed in either domain
                old_count_a = entry.get('source_concept_count', 0) if src == dom_a_lower else entry.get('target_concept_count', 0)
                old_count_b = entry.get('target_concept_count', 0) if src == dom_a_lower else entry.get('source_concept_count', 0)
                new_count_a = len(self.graph.domains.get(dom_a, []))
                new_count_b = len(self.graph.domains.get(dom_b, []))
                # Skip if neither domain grew by >= 2 concepts since last write
                if new_count_a <= old_count_a + 1 and new_count_b <= old_count_b + 1:
                    return True
        return False

    def _detect_bridge_gaps(self, start_id):
        """
        Strategy 4: Bridge gaps via domain neighbor analysis.
        If two domains share many neighbor domains but have no bridge between them,
        predict a bridge publication. Reuses logic from the bridge recommender.
        """
        pid = start_id
        # Load persistent memory
        ari_memory = self._load_ari_memory()

        # Compute domain neighbor sets
        domain_neighbors = defaultdict(set)
        for node in self.graph.nodes.values():
            for link in node.wikilinks_out:
                target = self.graph.nodes.get(link)
                if target and target.domain != node.domain:
                    domain_neighbors[node.domain].add(target.domain)

        # Already bridged domains — check ALL output locations + memory
        already_bridged_titles = set()
        already_bridged_domain_pairs = set()
        already_bridged_keywords = {}  # domain_keyword -> set of paired domains

        # Collect already-bridged from files
        for dirpath in [PUBS_DIR, ARI_DIR, DISTILLED_DIR]:
            if not os.path.isdir(dirpath):
                continue
            for f in glob.glob(os.path.join(dirpath, "*.md")):
                with open(f, encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                # Read domain frontmatter
                doms = re.findall(r'^domain: (.+)$', content, re.MULTILINE)
                for d in doms:
                    parts = [p.strip().lower() for p in d.split('/')]
                    if len(parts) >= 2:
                        already_bridged_domain_pairs.add(tuple(sorted(parts[:2])))
                # Read title for exact-title check
                t = re.search(r'^title: "(.+)"', content, re.MULTILINE)
                if t:
                    already_bridged_titles.add(t.group(1).strip().lower())
                # Content-based: extract domain keywords from title
                title_text = content[:500].lower()
                # Also check for × separator pattern (domain × domain)
                x_pairs = re.findall(r'(\w[\w\s/]+?)\s*[×x&]\s*(\w[\w\s/]+?)', title_text[:300])
                for a, b in x_pairs:
                    a_key = re.sub(r'[^a-z0-9]', '', a.strip().lower())
                    b_key = re.sub(r'[^a-z0-9]', '', b.strip().lower())
                    if a_key and b_key:
                        already_bridged_domain_pairs.add(tuple(sorted([a_key, b_key])))

        # Score all domain pairs
        all_domains = list(self.graph.domains.keys())
        scored_pairs = []
        for i, d1 in enumerate(all_domains):
            for d2 in all_domains[i+1:]:
                if d1 == d2:
                    continue
                n1 = domain_neighbors.get(d1, set())
                n2 = domain_neighbors.get(d2, set())
                shared = n1 & n2
                if len(shared) < 3:
                    continue
                # Check if already bridged
                d1_lower = d1.lower()
                d2_lower = d2.lower()
                pair = tuple(sorted([d1_lower, d2_lower]))
                if pair in already_bridged_domain_pairs:
                    continue
                # Also check via keyword matching: do any existing pub titles
                # contain BOTH domain names (simplified)?
                d1_key = re.sub(r'[^a-z0-9]', '', d1_lower)
                d2_key = re.sub(r'[^a-z0-9]', '', d2_lower)
                bridged_via_keywords = False
                for existing_pair in list(already_bridged_domain_pairs):
                    a, b = existing_pair
                    # Check if the existing bridge domain pair corresponds
                    if (d1_key in a or a in d1_key) and (d2_key in b or b in d2_key):
                        bridged_via_keywords = True
                        break
                    if (d1_key in b or b in d1_key) and (d2_key in a or a in d2_key):
                        bridged_via_keywords = True
                        break
                if bridged_via_keywords:
                    continue

                # Check persistent ARI memory — skip if already written and domains haven't grown
                if self._is_domain_pair_stale(d1, d2, ari_memory):
                    continue

                jaccard = len(shared) / max(1, len(n1 | n2))
                size_factor = min(1.0, (len(self.graph.domains[d1]) * len(self.graph.domains[d2])) / 100)
                score = jaccard * len(shared) * size_factor

                scored_pairs.append((score, d1, d2, shared))

        scored_pairs.sort(reverse=True)

        for score, d1, d2, shared in scored_pairs[:3]:
            shared_str = ', '.join(sorted(list(shared))[:6])

            # Generate varied title
            bridge_titles = [
                f"Why {d1} Is {d2} — The Structural Isomorphism Uncovered by the Graph",
                f"What {d1} Knows About {d2} That {d2} Doesn't Know About Itself",
                f"The Bridge Between {d1} and {d2}: What the Vault Found in Its Own Structure",
                f"{d1} and {d2} Are the Same System — Here Is Why",
                f"Missing Link: Why {d1} Needs a Bridge to {d2}",
            ]
            # Pick title that hasn't been used yet
            title = None
            for t in bridge_titles:
                if t.lower() not in already_bridged_titles:
                    title = t
                    break
            if title is None:
                title = f"{d1} × {d2} — The Cross-Domain Bridge"

            evidence = (
                f"Bridge gap: '{d1}' and '{d2}' share "
                f"{len(shared)} neighbor domains ({shared_str}) "
                f"but no bridge publication exists between them. "
                f"Score: {score:.3f}"
            )

            # Compute actual variance in φ
            dom1_size = len(self.graph.domains.get(d1, []))
            dom2_size = len(self.graph.domains.get(d2, []))
            phi_variance = min(0.08, max(0.02, score * 0.08 + (dom1_size * dom2_size) / 10000 * 0.02))

            pred = Prediction(
                id=pid, type='bridge_gap',
                confidence=min(0.9, score * 2),
                source_domain=d1, target_domain=d2,
                predicted_title=title,
                predicted_domain=f"{d1} / {d2}",
                evidence=evidence,
                suggested_structure=[
                    "The Shared Terrain",
                    f"The {d1} Perspective on {d2}",
                    f"The {d2} Perspective on {d1}",
                    "The Common Architecture",
                    "Implications for Practice"
                ],
                suggested_sources=list(shared)[:5],
                phi_impact=phi_variance,
                novelty_score=min(0.85, score * 1.5)
            )
            self.predictions.append(pred)
            pid += 1

        return pid

    def _detect_stub_isolation(self, start_id):
        """
        Strategy 5: Stub isolation.
        Low-backlink concepts in otherwise dense domains — nodes that exist
        but aren't structurally integrated. These need expansion and reconnection.
        """
        pid = start_id
        candidates = []
        for node in self.graph.nodes.values():
            if node.wikilinks_in <= 3 and len(node.wikilinks_out) <= 4 and node.lines >= 100:
                # Low integration despite having content
                domain_size = len(self.graph.domains.get(node.domain, []))
                if domain_size >= 5:
                    candidates.append((node, domain_size))

        candidates.sort(key=lambda x: x[1])  # Sort by domain size

        for node, dom_size in candidates[:5]:
            evidence = (
                f"'{node.title}' ({node.domain}) has only {node.wikilinks_in} backlinks "
                f"and {len(node.wikilinks_out)} outlinks despite {node.lines} lines of content "
                f"in a domain with {dom_size} concepts. "
                f"Needs structural integration into the domain's core network."
            )

            pred = Prediction(
                id=pid, type='stub_isolation',
                confidence=0.6,
                source_domain=node.domain,
                target_domain=node.domain,
                predicted_title=f"{node.title} — Domain Integration and Cross-Referencing",
                predicted_domain=node.domain,
                evidence=evidence,
                suggested_structure=[
                    f"{node.title} in the Context of {node.domain}",
                    "Related Concepts and Relationships",
                    "Connections to Other Domains",
                    "Unresolved Questions"
                ],
                suggested_sources=[node.title],
                phi_impact=0.02,
                novelty_score=0.35
            )
            self.predictions.append(pred)
            pid += 1

        return pid

    def _detect_multi_hop_chains(self, start_id):
        """
        Strategy 6: Multi-hop reasoning chains.
        Chains predictions across detectors: dangling sender -> missing triad -> bridge gap.
        One prediction's output becomes the next prediction's input context.

        Algorithm:
        1. Find the top dangling sender (high out-links, low in-links, >= 100L)
        2. Trace its most-linked concept -> find a missing triad through it
        3. If the triad spans two domains -> score as a bridge_gap with pre-filled evidence
        4. The chain is a SINGLE prediction that carries the full reasoning path
        """
        pid = start_id

        # Step 1: Find top dangling senders
        dangling = []
        for node in self.graph.nodes.values():
            out = len(node.wikilinks_out)
            if out >= 6 and node.wikilinks_in <= 3 and node.lines >= 100:
                dangling.append(node)
        dangling.sort(key=lambda n: -len(n.wikilinks_out))
        if not dangling:
            return pid

        top_dangler = dangling[0]

        # Step 2: Which of its outbound links is a hub (most inbound links)?
        top_links = []
        for link in top_dangler.wikilinks_out:
            target = self.graph.nodes.get(link)
            if target and target.title != top_dangler.title:
                top_links.append((target.wikilinks_in, target))
        top_links.sort(key=lambda x: -x[0])
        if not top_links:
            return pid

        hub = top_links[0][1]

        # Step 3: Find concepts linking TO hub but NOT to top_dangler (missing triad)
        missing_candidates = []
        for node in self.graph.nodes.values():
            if node.title == top_dangler.title or node.title == hub.title:
                continue
            links_to_hub = hub.title in node.wikilinks_out
            links_to_dangler = top_dangler.title in node.wikilinks_out
            if links_to_hub and not links_to_dangler and node.domain != hub.domain:
                missing_candidates.append(node)

        if not missing_candidates:
            return pid

        best_c = sorted(missing_candidates,
                        key=lambda n: len(n.wikilinks_out) + n.wikilinks_in * 2,
                        reverse=True)[0]

        evidence = (
            f"Multi-hop chain: '{top_dangler.title}' ({top_dangler.domain}) is a dangling sender "
            f"({len(top_dangler.wikilinks_out)} out, {top_dangler.wikilinks_in} in) -> "
            f"its top destination '{hub.title}' ({hub.domain}) is a hub "
            f"({hub.wikilinks_in} backlinks) -> "
            f"'{best_c.title}' ({best_c.domain}) links to the hub but not to the dangler. "
            f"The chain implies: A->B->C exists, A->C missing. "
            f"Writing the A->C concept would close the loop and integrate '{top_dangler.title}' "
            f"into the network."
        )

        chain_confidence = min(0.85,
            0.3 + len(top_dangler.wikilinks_out) * 0.03 + hub.wikilinks_in * 0.01)

        pred = Prediction(
            id=pid, type='multi_hop_chain',
            confidence=chain_confidence,
            source_domain=top_dangler.domain,
            target_domain=best_c.domain,
            predicted_title=f"{top_dangler.title} and {best_c.title} -- Closing the Loop Through {hub.title}",
            predicted_domain=f"{top_dangler.domain} / {best_c.domain}",
            evidence=evidence,
            suggested_structure=[
                f"The Chain: {top_dangler.title} -> {hub.title} -> {best_c.title}",
                f"Why {top_dangler.title} Needs a Link to {best_c.title}",
                "What the Graph Reveals About the Missing Connection",
                "Implications for Domain Integration",
                "Related Concepts That Complete the Loop"
            ],
            suggested_sources=[top_dangler.title, hub.title, best_c.title],
            phi_impact=min(0.06, chain_confidence * 0.07),
            novelty_score=min(0.9, chain_confidence * 1.1)
        )
        self.predictions.append(pred)
        pid += 1

        return pid

    def _generate_asymmetric_title(self, dom_a, dom_b, from_concepts):
        """Generate a plausible title for a missing reciprocal concept."""
        templates = [
            f"Why {dom_b} Needs {dom_a} — The Missing Reciprocity",
            f"{dom_b} Through the Lens of {dom_a}",
            f"What {dom_a} Knows About {dom_b} That {dom_b} Doesn't Know About Itself",
            f"The {dom_a} Foundation of {dom_b}",
            f"{dom_b} Is {dom_a} — A Structural Convergence",
        ]
        # Pick based on hash of the pair for consistency
        idx = hash((dom_a, dom_b)) % len(templates)
        return templates[idx]

    def _rank(self):
        """Rank predictions by composite score combining confidence, novelty, and phi_impact."""
        for pred in self.predictions:
            pred.confidence = min(1.0, pred.confidence)
            pred.novelty_score = min(1.0, pred.novelty_score)
            pred.phi_impact = min(0.1, pred.phi_impact)

        self.predictions.sort(
            key=lambda p: (p.confidence * 0.4 + p.novelty_score * 0.35 + p.phi_impact * 10 * 0.25),
            reverse=True
        )

        # Check for duplicates against existing concepts
        existing = set(self.graph.nodes.keys())
        for pred in self.predictions:
            if pred.predicted_title in existing:
                pred.already_exists = True

    def report(self, n: int = 15) -> str:
        """Print top N predictions."""
        lines = []
        lines.append("=" * 72)
        lines.append("  ARI — AUTONOMOUS RESEARCH INTELLIGENCE — PREDICTIONS")
        lines.append("=" * 72)
        lines.append(f"\n  Active predictions: {len(self.predictions)}\n")

        lines.append(f"  {'#':>3s}  {'Conf':>5s}  {'Novelty':>7s}  {'Φ±':>5s}  {'Type':<18s}  {'Prediction':<40s}")
        lines.append("  " + "-" * 90)

        valid = [p for p in self.predictions if not p.already_exists][:n]
        for i, pred in enumerate(valid):
            score = pred.confidence * 0.4 + pred.novelty_score * 0.35 + pred.phi_impact * 10 * 0.25
            type_icon = {
                'asymmetric': '⟷',
                'dangling': '↴',
                'missing_triad': '△',
                'bridge_gap': '⧉',
                'stub_isolation': '○',
            }.get(pred.type, '?')

            lines.append(
                f"  {i+1:>3d}. {score:.3f}  "
                f"{pred.confidence:.2f}-{pred.novelty_score:.2f}  "
                f"+{pred.phi_impact:.3f}  "
                f"{type_icon} {pred.type:<16s} "
                f"{pred.predicted_title[:38]:<38s}"
            )
            lines.append(f"       {pred.evidence[:90]}")
            lines.append(f"       → Write to: {pred.predicted_domain}")

        lines.append(f"\n  Detectors: asymmetric | dangling | missing_triad | bridge_gap | stub_isolation")
        lines.append(f"  {len(self.predictions)} total, {len(valid)} actionable")
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ARI — Autonomous Research Intelligence")
    parser.add_argument('--scan', action='store_true', help='Full scan and report')
    parser.add_argument('--top-n', type=int, default=10, help='Show top N predictions')
    parser.add_argument('--prediction', type=int, help='Show details for prediction N')
    parser.add_argument('--write', type=int, help='Write prediction N as a concept note')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    graph = GraphLoader()
    detector = AnomalyDetector(graph)

    if args.json:
        # Export predictions as JSON
        output = []
        for pred in detector.predictions:
            if pred.already_exists:
                continue
            output.append({
                'id': pred.id,
                'type': pred.type,
                'confidence': pred.confidence,
                'novelty_score': pred.novelty_score,
                'phi_impact': pred.phi_impact,
                'predicted_title': pred.predicted_title,
                'predicted_domain': pred.predicted_domain,
                'evidence': pred.evidence,
            })
        print(json.dumps(output, indent=2))
    elif args.prediction is not None:
        valid = [p for p in detector.predictions if not p.already_exists]
        if 0 <= args.prediction < len(valid):
            p = valid[args.prediction]
            print(f"PREDICTION #{args.prediction}")
            print(f"  Type: {p.type}")
            print(f"  Title: {p.predicted_title}")
            print(f"  Domain: {p.predicted_domain}")
            print(f"  Confidence: {p.confidence:.3f}")
            print(f"  Novelty: {p.novelty_score:.3f}")
            print(f"  Φ Impact: +{p.phi_impact:.3f}")
            print(f"  Evidence: {p.evidence}")
            print(f"  Suggested Structure:")
            for s in p.suggested_structure:
                print(f"    - {s}")
            print(f"  Suggested Sources:")
            for s in p.suggested_sources:
                print(f"    - [[{s}]]")
        else:
            print(f"Invalid prediction index {args.prediction}. Max: {len(valid)-1}")
    elif args.write is not None:
        valid = [p for p in detector.predictions if not p.already_exists]
        if 0 <= args.write < len(valid):
            p = valid[args.write]

            # Build frontmatter
            date_str = datetime.now().strftime('%Y-%m-%d')
            content = "---\n"
            content += f"title: \"{p.predicted_title}\"\n"
            content += f"status: growing\n"
            content += f"domain: {p.predicted_domain}\n"
            content += f"tags:\n"
            content += f"  - concept\n"
            content += f"  - ari-predicted\n"
            content += f"  - ari-{p.type}\n"
            content += f"  - auto-discovered\n"
            content += f"created: {date_str}\n"
            content += f"ari_confidence: {p.confidence:.2f}\n"
            content += f"ari_type: {p.type}\n"
            content += f"sources:\n"
            for s in p.suggested_sources:
                content += f"  - [[{s}]]\n"
            content += "---\n\n"
            content += f"# {p.predicted_title}\n\n"
            content += "> *ARI-predicted concept note. " + p.evidence + "*\n\n"
            content += "---\n\n"

            for section in p.suggested_structure:
                content += f"## {section}\n\n"
                content += "> *This section was predicted by ARI but requires human synthesis.*\n\n"
                content += "- Predicted content area\n"
                content += "- Requires evidence from sources\n"
                content += "- Cross-reference with related concepts\n\n"
                content += "---\n\n"

            content += f"*Auto-generated by ARI on {date_str}. "
            content += f"Confidence: {p.confidence:.0%}. Type: {p.type}. "
            content += f"Phi impact estimate: +{p.phi_impact:.3f}.*\n"

            # Sanitize filename
            safe_title = re.sub(r'[^\w\s-]', '', p.predicted_title).strip().replace(' ', '_')[:80]
            path = os.path.join(ARI_DIR, f"ARI_{date_str}_{safe_title}.md")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Written: {path}")
        else:
            print(f"Invalid prediction index {args.write}. Max: {len(valid)-1}")
    else:
        print(detector.report(args.top_n))


if __name__ == '__main__':
    main()
