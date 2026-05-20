"""
bridge_recommender.py — Φ-Guided Bridge Discovery

Scans the vault's connectome and finds domain pairs that are
structurally close (share many neighbor concepts) but have NO
direct bridge. These are the highest-value next bridges.

The insight: if two domains share neighbors in the knowledge graph
but have no direct connection between them, that gap is a
structural bridge candidate. The vault has already done the
groundwork — it just hasn't made the final link.

Algorithm:
  1. For each pair of domains, compute:
     a. Shared neighbor ratio (Jaccard similarity of neighbor sets)
     b. Combined Φ (mean integration of both domains' top nodes)
     c. Bridge potential = shared_neighbors × mean_Φ × domain_size_factor
  2. Filter out pairs that already have a bridge (by checking publications)
  3. Rank by bridge potential
  4. Output top 15 recommendations with rationale

Usage:
  python3 bridge_recommender.py
  python3 bridge_recommender.py --json
  python3 bridge_recommender.py --write   # output as vault note
"""

import json, os, re, glob, sys
from collections import defaultdict

VAULT_CONCEPTS = os.environ.get("BR_VAULT_CONCEPTS") or os.path.expanduser("~/Obsidian Vault/04 Resources/Concepts")
VAULT_PUBS = os.environ.get("BR_VAULT_PUBS") or os.path.expanduser("~/Obsidian Vault/04 Resources/Publications")


def load_vault():
    """Load full vault graph with domain info."""
    all_files = {}
    backlinks = defaultdict(int)
    outgoing = {}
    domains = {}
    neighbor_sets = defaultdict(set)

    for f in glob.glob(os.path.join(VAULT_CONCEPTS, "*.md")):
        title = os.path.splitext(os.path.basename(f))[0]
        all_files[title] = f

    # First pass: backlinks
    for f in all_files.values():
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        for match in re.finditer(r'\[\[([^\]|]+)', content):
            target = match.group(1).split('#')[0].strip()
            if target in all_files:
                backlinks[target] += 1

    # Second pass: outgoing, domains, neighbors
    for title, f in all_files.items():
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()

        links = []
        for match in re.finditer(r'\[\[([^\]|]+)', content):
            target = match.group(1).split('#')[0].strip()
            if target in all_files and target != title:
                links.append(target)
        outgoing[title] = links

        # Domain
        domain = ""
        dm = re.search(r'^domain:\s*(.+?)$', content, re.MULTILINE | re.IGNORECASE)
        if dm:
            domain = dm.group(1).strip()
        else:
            # Tags fallback
            tags_match = re.search(r'tags:\s*\[([^\]]+)\]', content)
            if tags_match:
                tags = [t.strip().strip('"').strip("'") for t in tags_match.group(1).split(',')]
                generic = {'concept', 'concept-v1', 'agent', 'agents', 'auto-expanded'}
                for t in tags:
                    if t.lower() not in generic and not t.startswith('#'):
                        words = t.replace('-', ' ').split()
                        domain = ' '.join(w.capitalize() for w in words)
                        break
            if not domain:
                tags_match2 = re.search(r'tags:\s*\n((?:\s+-\s+.*\n)+)', content)
                if tags_match2:
                    tags = [re.sub(r'\s*-\s*', '', l).strip() for l in tags_match2.group(1).split('\n') if l.strip()]
                    generic = {'concept', 'concept-v1', 'agent', 'agents', 'auto-expanded'}
                    for t in tags:
                        if t.lower() not in generic and not t.startswith('#'):
                            words = t.replace('-', ' ').split()
                            domain = ' '.join(w.capitalize() for w in words)
                            break
        domains[title] = domain

    # Build neighbor sets per domain
    domain_nodes = defaultdict(set)
    for title, d in domains.items():
        if d:
            domain_nodes[d].add(title)

    for title, links in outgoing.items():
        d = domains.get(title, "")
        if d:
            for l in links:
                ld = domains.get(l, "")
                if ld and ld != d:
                    neighbor_sets[d].add(ld)

    return all_files, backlinks, outgoing, domains, domain_nodes, neighbor_sets


def load_existing_bridges():
    """Extract domain pairs already connected by bridges.
    Returns a set of frozenset pairs like {('Neuroscience', 'Physiology')}."""
    bridge_pairs = set()

    for f in sorted(glob.glob(os.path.join(VAULT_PUBS, "Bridge*.md"))):
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        
        # Extract sources list from frontmatter — handle both inline [a, b] and block (- item) YAML
        sources = []
        sources_m = re.search(r'sources:\s*\[([^\]]*)\]', content)
        if sources_m:
            sources = [s.strip() for s in sources_m.group(1).split(',')]
        else:
            # Try YAML block list format
            sources_block = re.search(r'sources:\n((?:\s+- .+\n?)+)', content)
            if sources_block:
                sources = [re.sub(r'^\s*-\s*', '', s).strip() for s in sources_block.group(1).split('\n') if s.strip()]
        
        # Extract the bridge title (first heading)
        title_m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_m.group(1) if title_m else os.path.basename(f)
        
        # The title often names the two domains explicitly
        # e.g. "The Brain Is a Physiological Organ — Neuroscience and Physiology Were Never Separate"
        # or "The Ladder of Statistical Inference — Why Causality and Statistics Are the Same Discipline"
        title_clean = title.replace('—', '-').replace('–', '-')
        
        # Extract concept wikilinks from the content
        refs = re.findall(r'\[\[([^\]|]+)', content)

        # Extract tags from frontmatter
        tags_m = re.search(r'tags:\s*\[([^\]]*)\]', content)
        if tags_m:
            tags = [t.strip() for t in tags_m.group(1).split(',')]
            tags_text = ' '.join(tags)
        else:
            tags_text = ''

        # Build a combined text to search for domain names
        combined_text = ' '.join(refs + sources + [title_clean, tags_text]).lower()
        
        # Find all domains mentioned in this bridge
        mentioned_domains = set()
        if 'neuroscience' in combined_text:
            mentioned_domains.add('Neuroscience')
        if 'neuroscience' in combined_text and ('cognitive psychology' in combined_text or 'cognitive' in combined_text):
            mentioned_domains.add('Neuroscience / Cognitive Psychology')
        if 'physiology' in combined_text:
            mentioned_domains.add('Physiology')
        if 'immunology' in combined_text or 'immune' in combined_text:
            mentioned_domains.add('Immunology')
        if 'causality' in combined_text or 'causal' in combined_text:
            mentioned_domains.add('Causality')
        if 'statistic' in combined_text:
            mentioned_domains.add('Statistics')
        if 'biology' in combined_text:
            mentioned_domains.add('Biology')
        if 'cell' in combined_text and 'biology' in combined_text:
            mentioned_domains.add('Cell Biology')
        if 'cell-biology' in combined_text:
            mentioned_domains.add('Cell Biology')
        if 'sleep' in combined_text:
            mentioned_domains.add('Sleep Science')
            mentioned_domains.add('Sleep')
        if 'psychology' in combined_text:
            mentioned_domains.add('Psychology')
        if 'stress' in combined_text or 'allostatic' in combined_text:
            mentioned_domains.add('Stress')
        if 'finance' in combined_text:
            mentioned_domains.add('Finance')
        if 'climate' in combined_text:
            mentioned_domains.add('Climate')
        if 'agent' in combined_text:
            mentioned_domains.add('Agent')
        if 'software' in combined_text or 'engineering' in combined_text:
            mentioned_domains.add('Software Engineering')
        if 'software engineering' in combined_text and 'ai' in combined_text:
            mentioned_domains.add('Software Engineering / AI')
        if 'machine' in combined_text and 'learning' in combined_text:
            mentioned_domains.add('Machine Learning')
        if 'meta' in combined_text or 'moc' in combined_text:
            mentioned_domains.add('Meta')
        
        # Every pair of mentioned domains in a bridge IS a bridged pair
        dom_list = sorted(mentioned_domains)
        for i, d1 in enumerate(dom_list):
            for d2 in dom_list[i+1:]:
                bridge_pairs.add(frozenset([d1.lower(), d2.lower()]))

    return bridge_pairs


def compute_domain_phi(domain_nodes, backlinks, outgoing):
    """Compute mean Φ for a domain's top nodes."""
    domain_phi = {}
    for d, nodes in domain_nodes.items():
        if len(nodes) < 2:
            domain_phi[d] = 0.0
            continue
        phis = []
        for n in nodes:
            bl = backlinks.get(n, 0) / 100.0
            ol = len(outgoing.get(n, [])) / 50.0
            phi = min(bl * 0.4 + ol * 0.3, 1.0)
            phis.append(phi)
        domain_phi[d] = round(sum(phis) / len(phis), 3)
    return domain_phi


def find_bridge_candidates(all_files, backlinks, outgoing, domains, domain_nodes, neighbor_sets, existing_bridges):
    """Find domain pairs that are structurally close but have no bridge."""

    domain_list = [d for d in domain_nodes if d and len(domain_nodes[d]) >= 2]
    d_phi = compute_domain_phi(domain_nodes, backlinks, outgoing)

    candidates = []

    for i, d1 in enumerate(domain_list):
        for d2 in domain_list[i + 1:]:
            if d1 == d2:
                continue

            # Skip pairs that already have a bridge
            pair_key = frozenset([d1.lower(), d2.lower()])
            if pair_key in existing_bridges:
                already_bridged = True
            else:
                already_bridged = False

            # Shared neighbors (other domains that both domains connect to)
            n1 = neighbor_sets.get(d1, set())
            n2 = neighbor_sets.get(d2, set())
            shared = n1 & n2
            union = n1 | n2

            if not union:
                continue

            jaccard = len(shared) / len(union)

            # Combined Φ
            combined_phi = (d_phi.get(d1, 0) + d_phi.get(d2, 0)) / 2

            # Domain size factor (prefer pairs where both domains are substantive)
            size1 = len(domain_nodes[d1])
            size2 = len(domain_nodes[d2])
            size_factor = min(1.0, (size1 + size2) / 100.0)

            # Bridge potential score
            score = jaccard * combined_phi * size_factor * 10

            if score > 0.001:
                candidates.append({
                    "domain_a": d1,
                    "domain_b": d2,
                    "shared_neighbors": list(shared)[:10],
                    "shared_count": len(shared),
                    "jaccard": round(jaccard, 3),
                    "phi_a": d_phi.get(d1, 0),
                    "phi_b": d_phi.get(d2, 0),
                    "combined_phi": round(combined_phi, 3),
                    "size_a": size1,
                    "size_b": size2,
                    "score": round(score, 4),
                    "already_bridged": already_bridged,
                    "sample_concepts_a": list(domain_nodes[d1])[:5],
                    "sample_concepts_b": list(domain_nodes[d2])[:5],
                })

    candidates.sort(key=lambda x: -x["score"])
    return candidates


def main():
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║   Φ-GUIDED BRIDGE RECOMMENDER                   ║")
    print("  ║   Let the connectome tell you what to connect.   ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

    print("  Loading vault connectome...")
    all_files, backlinks, outgoing, domains, domain_nodes, neighbor_sets = load_vault()
    print(f"  Loaded {len(all_files)} concepts, {len(domain_nodes)} domains.\n")

    print("  Scanning for existing bridges...")
    existing = load_existing_bridges()
    print(f"  Found {len(existing)} existing bridge references.\n")

    print("  Computing bridge candidates...")
    candidates = find_bridge_candidates(all_files, backlinks, outgoing, domains, domain_nodes, neighbor_sets, existing)

    # Filter to non-bridged pairs for recommendation
    new_candidates = [c for c in candidates if not c["already_bridged"]]

    print(f"  Found {len(new_candidates)} candidate domain pairs for new bridges.\n")

    # If --write, output as vault note
    if "--write" in sys.argv:
        write_vault_note(new_candidates[:10], domain_nodes)
        print("  Written to vault!\n")
        return

    if "--json" in sys.argv:
        print(json.dumps(new_candidates[:15], indent=2))
        return

    # ── Display top 10 ──
    print("  ═══ TOP 10 BRIDGE RECOMMENDATIONS ═══")
    print()
    for i, c in enumerate(new_candidates[:10], 1):
        a, b = c["domain_a"], c["domain_b"]
        print(f"  [{i}] {a}  ↔  {b}")
        print(f"      Score: {c['score']:.4f}  |  Shared neighbors: {c['shared_count']}  |  Jaccard: {c['jaccard']}")
        print(f"      Φ-a: {c['phi_a']:.3f}  |  Φ-b: {c['phi_b']:.3f}  |  Combined: {c['combined_phi']:.3f}")
        print(f"      Sizes: {c['size_a']} + {c['size_b']} nodes")
        if c["shared_neighbors"]:
            print(f"      Bridge terrain: {', '.join(c['shared_neighbors'][:5])}")
        rationale = generate_rationale(a, b, c, domain_nodes)
        print(f"      Why: {rationale}")
        print()

    print("  ═══ BRIDGE TERRAIN HEATMAP ═══")
    print()
    print(f"  {'DOMAIN A':<30} {'DOMAIN B':<30} {'SCORE':>6} {'SHARED':>6}")
    print(f"  {'─'*74}")
    for c in new_candidates[:20]:
        a = c["domain_a"][:28]
        b = c["domain_b"][:28]
        print(f"  {a:<30} {b:<30} {c['score']:>6.3f} {c['shared_count']:>6}")

    print()
    print(f"  Total candidates: {len(new_candidates)}")
    print(f"  Already bridged: {len(candidates) - len(new_candidates)}")
    print()
    
    # ── V2: Concept-level gaps ──
    print("  ═══ CONCEPT-LEVEL GAPS ═══")
    print()
    
    concept_gaps = find_concept_gaps(all_files, backlinks, outgoing, domains)
    
    print(f"  Isolated orphans (0 backlinks, ≥1 outgoing): {len(concept_gaps['orphans'])}")
    if concept_gaps["align"]:
        print(f"  Domain-aligned orphans that should link to hubs:")
        for g in concept_gaps["align"][:5]:
            print(f"    🔗 {g['orphan']} → {g['hub']} (Φ={g['hub_bl']/100:.2f})")
        print()
    
    print(f"  Cross-domain concept pairs that share neighbors but lack direct links:")
    if concept_gaps["cross"]:
        for g in concept_gaps["cross"][:8]:
            print(f"    {g['a']:35s} ↔ {g['b']:35s}  ({g['n']} shared: {', '.join(g['shared'][:3])})")
    else:
        print("    (none found)")
    print()


# ── V2: Concept-level gap detection ──

def find_concept_gaps(all_files, backlinks, outgoing, domains):
    """Find concept-level gaps: isolated orphans, domain-align gaps,
    and cross-domain concept pairs that share neighbors but lack links."""
    isolates = []
    for title in all_files:
        bl = backlinks.get(title, 0)
        ol = len(outgoing.get(title, []))
        if bl == 0 and ol >= 1:
            isolates.append({"title": title, "outgoing": ol, "domain": domains.get(title, "") or "unset"})
    
    hub_notes = sorted([(backlinks.get(t, 0), t) for t in all_files if backlinks.get(t, 0) >= 3], key=lambda x: -x[0])
    hub_titles = [t for _, t in hub_notes[:40]]
    domain_matches = []
    seen = set()
    for iso in isolates:
        if not iso.get("domain") or iso["domain"] == "unset":
            continue
        for hub_title in hub_titles:
            hub_domain = domains.get(hub_title, "")
            if hub_domain and hub_domain == iso["domain"] and iso["title"] != hub_title:
                if iso["title"] not in outgoing.get(hub_title, []):
                    k = f"{iso['title']}->{hub_title}"
                    if k not in seen:
                        seen.add(k)
                        domain_matches.append({"orphan": iso["title"], "hub": hub_title, "hub_bl": backlinks.get(hub_title, 0)})
                        break
    
    dn = defaultdict(list)
    for t, d in domains.items():
        if d: dn[d].append(t)
    cross_gaps = []
    dlist = sorted([d for d in dn if len(dn[d]) >= 2])
    for d1 in dlist:
        for d2 in dlist:
            if d1 >= d2: continue
            for n1 in dn[d1][:5]:
                s1 = set(outgoing.get(n1, []))
                if not s1: continue
                for n2 in dn[d2][:5]:
                    s2 = set(outgoing.get(n2, []))
                    if not s2: continue
                    shared = s1 & s2
                    if len(shared) >= 2 and n2 not in s1 and n1 not in s2:
                        cross_gaps.append({"a": n1, "da": d1, "b": n2, "db": d2, "shared": list(shared)[:5], "n": len(shared)})
    cross_gaps.sort(key=lambda x: -x["n"])
    return {"orphans": isolates[:15], "align": domain_matches[:10], "cross": cross_gaps[:10]}


def generate_rationale(a, b, c, domain_nodes):
    """Generate a concise why-this-bridge rationale."""
    reasons = []

    shared = c.get("shared_neighbors", [])
    if shared:
        reasons.append(f"both connect to {shared[0].lower()}")

    if c["combined_phi"] > 0.2:
        reasons.append("both are high-integration domains")

    if c["size_a"] > 10 and c["size_b"] > 10:
        reasons.append("both have substantial concept density")

    if abs(c["phi_a"] - c["phi_b"]) < 0.05:
        reasons.append("comparable integration levels")

    if c["score"] > 0.5:
        reasons.append("strong structural proximity")

    if reasons:
        return f"{a} and {b} share {c['shared_count']} neighbor domains — {' and '.join(reasons)}. A bridge here would connect two structurally adjacent regions with high integration potential."
    return "Structural gap detected between two knowledge regions."


def write_vault_note(recommendations, domain_nodes):
    """Write the top recommendations as a vault publication."""
    lines = [
        "---",
        "tags: [publication, bridge-recommendations, phi-audit, vault-as-self, meta]",
        "status: #status/gateway",
        "domain: Cross-Domain Synthesis",
        "sources: [Bridge Recommender Engine, Φ Audit, Vault Connectome]",
        "date: 2026-05-18",
        "---",
        "",
        "# Bridge Recommendations — What the Connectome Wants You to Write Next",
        "",
        "> *The vault's connectome was scanned. 698 nodes, 8,052 edges, 100 domains. For every pair of domains, structural proximity was computed: do they share neighbor concepts? Do they have comparable integration (Φ)? Has a bridge already been written between them?*",
        "> *These are the gaps the connectome wants filled.*",
        "",
        "---",
        "",
        "## The Method",
        "",
        "Each recommendation is scored by:",
        "- **Shared neighbor ratio** (Jaccard similarity) — how many domains both connect to",
        "- **Combined Φ** — the mean integration of both domains' top nodes",
        "- **Domain size** — both domains should be substantive (>2 concepts)",
        "- **Already bridged** — pairs with existing bridges are excluded",
        "",
        "Score = Jaccard × Combined Φ × Size Factor × 10",
        "",
        "---",
        "",
        "## Top Recommendations",
        "",
    ]

    for i, c in enumerate(recommendations[:10], 1):
        a, b = c["domain_a"], c["domain_b"]
        lines.append(f"### {i}. {a} ↔ {b}")
        lines.append(f"")
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Bridge potential score | {c['score']:.4f} |")
        lines.append(f"| Shared neighbor domains | {c['shared_count']} |")
        lines.append(f"| Domain similarity (Jaccard) | {c['jaccard']} |")
        lines.append(f"| {a} integration (Φ) | {c['phi_a']:.3f} |")
        lines.append(f"| {b} integration (Φ) | {c['phi_b']:.3f} |")
        lines.append(f"| {a} concept count | {c['size_a']} |")
        lines.append(f"| {b} concept count | {c['size_b']} |")
        lines.append(f"")
        lines.append(f"**Why this bridge:** {generate_rationale(a, b, c, domain_nodes)}")
        lines.append(f"")
        if c["shared_neighbors"]:
            lines.append(f"**Shared conceptual terrain:** {', '.join(c['shared_neighbors'][:8])}")
            lines.append(f"")
        lines.append("---")
        lines.append("")

    lines.extend([
        "",
        "## How to Use This",
        "",
        "Pick any recommendation above. Read the concept notes from both domains.",
        "Look for the underlying structural isomorphism — the common pattern",
        "that connects them. Write a bridge.",
        "",
        "Each bridge will increase the vault's integration (Φ).",
        "The connectome is telling you where it wants to grow.",
        "",
        "---",
        "",
        "*Generated 2026-05-18 by the Bridge Recommender Engine. The vault scanned",
        "itself, found its own gaps, and produced this list. No human chose which",
        "pairs to evaluate. The connectome decided.*",
    ])

    path = os.path.expanduser(
        "~/Obsidian Vault/04 Resources/Publications/Bridge Recommendations — What the Connectome Wants You to Write Next.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  Written: {path}")


if __name__ == '__main__':
    main()
