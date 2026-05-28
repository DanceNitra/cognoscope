"""
phi_audit.py — Compute vault integration metrics

Φ is Integrated Information Theory's measure of a system's
integration and differentiation. Here we compute a simplified
structural Φ for the vault's knowledge graph.

Metrics:
- Node Φ (integration): weighted combination of backlinks, outgoing
  links, and 2-hop reach. Higher = more central in connectome.
- Domain Φ (cohesion): how integrated each domain is (cross-links
  within domain / total links).
- Bridge density: cross-domain links / total links per node.
- Orphan count: nodes with zero backlinks (functional forgetting).
- Hub count: nodes with 3+ backlinks (high integration).
- Global Φ: mean node integration across the entire graph.

Usage:
  python3 phi_audit.py          # full audit
  python3 phi_audit.py --json   # JSON output for tool chaining
"""

import json, os, re, glob, sys
from collections import defaultdict

VAULT_PATH = os.path.expanduser("~/Obsidian Vault/04 Resources/Concepts")
SUB_VAULTS = [
    "Vault_AI", "Vault_Software_Engineering", "Vault_Neuroscience",
    "Vault_Finance", "Vault_Statistics", "Vault_Psychology",
    "Vault_Causal_Inference", "Vault_Physiology", "Vault_Health_&_Longevity",
    "Vault_True_Meta", "Vault_Cell_Biology", "Vault_Research_Methods", ]


def load_graph():
    """Load vault graph and compute all metrics."""
    all_files = {}
    backlinks = defaultdict(int)
    outgoing = defaultdict(list)
    domains = {}
    note_sizes = {}

    concepts_root = os.path.expanduser("~/Obsidian Vault/04 Resources")
    concept_files = []
    # Flat concepts
    flat_dir = os.path.join(concepts_root, "Concepts")
    if os.path.isdir(flat_dir):
        concept_files.extend(glob.glob(os.path.join(flat_dir, "*.md")))
    # Sub-vaults
    for sv in SUB_VAULTS:
        sv_dir = os.path.join(concepts_root, sv, "Concepts")
        if os.path.isdir(sv_dir):
            concept_files.extend(glob.glob(os.path.join(sv_dir, "*.md")))
    for f in sorted(set(concept_files)):
        title = os.path.splitext(os.path.basename(f))[0]
        all_files[title] = f

    # First pass: compute backlinks
    for f in all_files.values():
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        for match in re.finditer(r'\[\[([^\]|]+)', content):
            target = match.group(1).split('#')[0].strip()
            if target in all_files:
                backlinks[target] += 1

    # Second pass: compute outgoing links and domains
    for title, f in all_files.items():
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()

        links = []
        for match in re.finditer(r'\[\[([^\]|]+)', content):
            target = match.group(1).split('#')[0].strip()
            if target in all_files and target != title:
                links.append(target)
        outgoing[title] = links

        # Domain extraction
        domain = ""
        dm = re.search(r'^domain:\s*(.+?)$', content, re.MULTILINE | re.IGNORECASE)
        if dm:
            domain = dm.group(1).strip()
        else:
            # Fall back to tags
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

        # File size
        note_sizes[title] = os.path.getsize(f)

    # Node Φ (integration score)
    node_phi = {}
    max_bl = max(backlinks.values()) if backlinks else 1
    for title in all_files:
        bl = backlinks.get(title, 0) / max(1, max_bl)
        ol = len(outgoing.get(title, [])) / 50.0  # normalized
        # 2-hop reach
        visited = {title}
        frontier = outgoing.get(title, [])
        two_hop = set()
        for n in frontier:
            if n in visited:
                continue
            visited.add(n)
            two_hop.add(n)
            for n2 in outgoing.get(n, []):
                if n2 not in visited and n2 != title:
                    two_hop.add(n2)
        reach = len(two_hop) / max(1, len(all_files)) * 10  # normalized ~0-1
        node_phi[title] = round(bl * 0.4 + min(ol, 1.0) * 0.3 + min(reach, 1.0) * 0.3, 3)

    # Domain Φ (cohesion)
    domain_nodes = defaultdict(list)
    for title, d in domains.items():
        if d:
            domain_nodes[d].append(title)

    domain_cohesion = {}
    for dname, nodes in domain_nodes.items():
        if len(nodes) < 2:
            domain_cohesion[dname] = 0.0
            continue
        internal_links = 0
        total_links = 0
        for n in nodes:
            for link in outgoing.get(n, []):
                total_links += 1
                if link in nodes:
                    internal_links += 1
        cohesion = internal_links / max(total_links, 1)
        domain_cohesion[dname] = round(cohesion, 3)

    # Cross-domain bridge density per node
    bridge_density = {}
    for title in all_files:
        links = outgoing.get(title, [])
        if not links:
            bridge_density[title] = 0.0
            continue
        same_domain = sum(1 for l in links if domains.get(l) == domains.get(title))
        cross = len(links) - same_domain
        bridge_density[title] = round(cross / len(links), 3)

    # Orphans (zero backlinks)
    orphans = [t for t in all_files if backlinks.get(t, 0) == 0]

    # Hubs (high backlinks)
    hub_threshold = max(2, int(sum(backlinks.values()) / max(1, len(all_files))))
    hubs = [(backlinks.get(t, 0), len(outgoing.get(t, [])), t) for t in all_files
             if backlinks.get(t, 0) >= min(5, hub_threshold)]
    hubs.sort(reverse=True)

    # Top integrated nodes
    top_integrated = sorted(node_phi.items(), key=lambda x: -x[1])[:30]

    return {
        "total_notes": len(all_files),
        "total_links": sum(len(v) for v in outgoing.values()),
        "domains": len([d for d in domain_nodes if d]),
        "orphans": len(orphans),
        "orphan_list": orphans[:20],
        "hubs": len(hubs),
        "hub_list": [{"node": t, "backlinks": bl, "outgoing": ol}
                     for bl, ol, t in hubs[:20]],
        "avg_backlinks": round(sum(backlinks.values()) / max(1, len(all_files)), 1),
        "avg_outgoing": round(sum(len(v) for v in outgoing.values()) / max(1, len(all_files)), 1),
        "median_phi": round(sorted(node_phi.values())[len(node_phi)//2], 3),
        "mean_phi": round(sum(node_phi.values()) / max(1, len(node_phi)), 3),
        "top_phi": top_integrated,
        "domain_cohesion": sorted(domain_cohesion.items(), key=lambda x: -x[1])[:15],
        "domain_node_counts": [(d, len(ns)) for d, ns in
                               sorted(domain_nodes.items(), key=lambda x: -len(x[1]))[:15]],
        "top_bridge_density": sorted(bridge_density.items(), key=lambda x: -x[1])[:15],
    }


def main():
    data = load_graph()

    if "--json" in sys.argv:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║     Φ AUDIT — Vault Integration Metrics         ║")
    print("  ║     The vault's connectome, measured.            ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

    # ── Global metrics ──
    print("  ═══ GLOBAL METRICS ═══")
    print(f"  Total concept notes:         {data['total_notes']}")
    print(f"  Total wikilinks:             {data['total_links']}")
    print(f"  Distinct domains:            {data['domains']}")
    print(f"  Average backlinks/note:      {data['avg_backlinks']}")
    print(f"  Average outgoing links/note: {data['avg_outgoing']}")
    print(f"  Mean node Φ:                 {data['mean_phi']}")
    print(f"  Median node Φ:               {data['median_phi']}")
    print(f"  Hubs (5+ backlinks):         {data['hubs']}")
    print(f"  Orphans (0 backlinks):       {data['orphans']}")
    print()

    # ── Top integrated nodes ──
    print("  ═══ TOP 20 HIGHEST-Φ NODES (most integrated) ═══")
    print(f"  {'Φ':>6} {'NODE'}")
    print(f"  {'─'*50}")
    for title, phi in data["top_phi"][:20]:
        print(f"  {phi:>6.3f}  {title}")
    print()

    # ── Domain cohesion ──
    print("  ═══ DOMAIN COHESION (top 15) ═══")
    print("        (internal links / total links — higher = more insular)")
    print(f"  {'COHESION':>8} {'NODES':>6}  {'DOMAIN'}")
    print(f"  {'─'*50}")
    domain_meta = {d: c for d, c in data["domain_node_counts"]}
    for dname, cohesion in data["domain_cohesion"]:
        nnodes = domain_meta.get(dname, 0)
        bar = "█" * int(cohesion * 30)
        print(f"  {cohesion:>8.2f} {nnodes:>6}  {bar} {dname}")

    # ── Lowest cohesion domains ──
    all_dc = sorted(data["domain_cohesion"], key=lambda x: x[1])
    print()
    print("  ═══ LEAST COHESIVE DOMAINS (least internal integration) ═══")
    for dname, cohesion in all_dc[:10]:
        nnodes = domain_meta.get(dname, 0)
        if nnodes >= 2:
            print(f"  {cohesion:>8.2f} {nnodes:>6}  {dname}")

    # ── Bridge agents ──
    print()
    print("  ═══ TOP 15 BRIDGE AGENTS (highest cross-domain link ratio) ═══")
    print("        (cross-domain links / total links — higher = more bridging)")
    print(f"  {'BRIDGE Φ':>8}  {'NODE'}")
    print(f"  {'─'*50}")
    for title, bd in data["top_bridge_density"][:15]:
        n = outgoing_count.get(title, 0) if 'outgoing_count' in dir() else 0
        print(f"  {bd:>8.3f}  {title}")

    # ── Orphan details ──
    print()
    print("  ═══ ORPHAN NOTES (zero backlinks — functional forgetting) ═══")
    for o in data["orphan_list"][:15]:
        print(f"  • {o}")
    if data["orphans"] > 15:
        print(f"  ... and {data['orphans'] - 15} more")
    print()

    # ── Interpretation ──
    print("  ═══ INTERPRETATION ═══")
    phi = data["mean_phi"]
    if phi > 0.15:
        print(f"  HIGH INTEGRATION (Φ={phi:.3f}): The vault's connectome is")
        print("  richly interconnected. New connections (bridges) will")
        print("  find fertile ground — most nodes are reachable and")
        print("  cross-domain links are common.")
    elif phi > 0.08:
        print(f"  MODERATE INTEGRATION (Φ={phi:.3f}): The vault is connected")
        print("  but has room for denser cross-linking.")
    else:
        print(f"  LOW INTEGRATION (Φ={phi:.3f}): Many isolated clusters.")
        print("  Bridge-writing will have high impact.")

    if data["orphans"] > 20:
        print()
        print(f"  {data['orphans']} orphan notes suggests significant")
        print("  functional forgetting. Consider linking orphans to hub")
        print("  nodes or archiving them (VaultAgent prediction #5).")

    print()
    print("  ══════════════════════════════════════════════════════")
    print("  Bridge #67 prediction: Mean Φ should increase with")
    print("  each new bridge written. Run this audit again after")
    print("  Bridge #68 to verify.")
    print("  ══════════════════════════════════════════════════════")


if __name__ == '__main__':
    # Need outgoing_count for bridge density display
    from phi_audit import load_graph
    data = load_graph()
    # Compute outgoing_count globally for the main function
    import glob, os, re
    from collections import defaultdict
    outgoing_count = {}
    all_files = {}
    concepts_root = os.path.expanduser("~/Obsidian Vault/04 Resources")
    concept_files = []
    flat_dir = os.path.join(concepts_root, "Concepts")
    if os.path.isdir(flat_dir):
        concept_files.extend(glob.glob(os.path.join(flat_dir, "*.md")))
    for sv in SUB_VAULTS:
        sv_dir = os.path.join(concepts_root, sv, "Concepts")
        if os.path.isdir(sv_dir):
            concept_files.extend(glob.glob(os.path.join(sv_dir, "*.md")))
    for f in sorted(set(concept_files)):
        title = os.path.splitext(os.path.basename(f))[0]
        all_files[title] = f
    for title, f in all_files.items():
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        links = []
        for match in re.finditer(r'\[\[([^\]|]+)', content):
            target = match.group(1).split('#')[0].strip()
            if target in all_files and target != title:
                links.append(target)
        outgoing_count[title] = len(links)
    main()
