"""bridge-recommender CLI — find structural knowledge gaps in any vault.

Usage:
  bridge-recommender scan PATH [--top N] [--json]
  bridge-recommender write PATH --gap N [--output FILE]
  bridge-recommender audit PATH
  bridge-recommender help
"""

import argparse
import json
import os
import sys

from .scanner import load_vault, load_existing_bridges, find_bridge_candidates, find_concept_gaps, generate_rationale


def main():
    parser = argparse.ArgumentParser(
        prog="bridge-recommender",
        description="Find structural knowledge gaps in any vault",
    )
    parser.add_argument("command", choices=["scan", "write", "audit", "help"], nargs="?", default="help")
    parser.add_argument("path", nargs="?", default=None, help="Path to your vault's Concepts directory")
    parser.add_argument("--top", type=int, default=10, help="Number of recommendations (default: 10)")
    parser.add_argument("--gap", type=int, default=1, help="Gap number to write (1-indexed)")
    parser.add_argument("--output", default=None, help="Output file for write command")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.command == "help" or not args.path:
        print(__doc__)
        return

    # Resolve vault path
    path = os.path.abspath(args.path)
    concepts_dir = path
    pubs_dir = os.path.join(os.path.dirname(path) if os.path.isfile(path) else path, "..", "Publications")
    if not os.path.isdir(concepts_dir):
        # Maybe they gave vault root — look for Concepts/
        if os.path.isdir(os.path.join(path, "04 Resources", "Concepts")):
            concepts_dir = os.path.join(path, "04 Resources", "Concepts")
            pubs_dir = os.path.join(path, "04 Resources", "Publications")
        else:
            print(f"Error: cannot find Concepts directory at {path}")
            sys.exit(1)

    # Set env vars for the scanner
    os.environ["BR_VAULT_CONCEPTS"] = concepts_dir
    if os.path.isdir(pubs_dir):
        os.environ["BR_VAULT_PUBS"] = pubs_dir

    # Run
    print(f"  Loading vault from {concepts_dir}...")
    all_files, backlinks, outgoing, domains, domain_nodes, neighbor_sets = load_vault()
    print(f"  Loaded {len(all_files)} concepts, {len(domain_nodes)} domains.")

    existing = load_existing_bridges()
    print(f"  Found {len(existing)} existing bridges.")

    candidates = find_bridge_candidates(all_files, backlinks, outgoing, domains, domain_nodes, neighbor_sets, existing)
    new_candidates = [c for c in candidates if not c.get("already_bridged")]

    if args.command == "scan":
        if args.json:
            print(json.dumps(new_candidates[:args.top], indent=2))
            return

        print(f"\n  ═══ TOP {args.top} BRIDGE RECOMMENDATIONS ═══\n")
        for i, c in enumerate(new_candidates[:args.top], 1):
            a, b = c["domain_a"], c["domain_b"]
            print(f"  [{i}] {a}  ↔  {b}")
            print(f"      Score: {c['score']:.4f}  |  Shared neighbors: {c['shared_count']}  |  Jaccard: {c['jaccard']:.3f}")
            print(f"      Φ-a: {c['phi_a']:.3f}  |  Φ-b: {c['phi_b']:.3f}  |  Combined: {c['combined_phi']:.3f}")
            print(f"      Sizes: {c['size_a']} + {c['size_b']} nodes")
            if c.get("shared_neighbors"):
                print(f"      Terrain: {', '.join(c['shared_neighbors'][:5])}")
            print(f"      Why: {generate_rationale(a, b, c, domain_nodes)}")
            print()

        print(f"  Total candidates: {len(new_candidates)}")
        print(f"  Already bridged: {len(existing)}")

        # Concept-level gaps
        gaps = find_concept_gaps(all_files, backlinks, outgoing, domains)
        print(f"\n  Concept gaps: {len(gaps['orphans'])} orphans, {len(gaps['cross'])} cross-domain pairs")

    elif args.command == "audit":
        print(f"\n  ═══ VAULT HEALTH AUDIT ═══\n")
        print(f"  Concepts:      {len(all_files)}")
        print(f"  Domains:       {len(domain_nodes)}")
        print(f"  Bridges:       {len(existing)}")
        print(f"  Candidates:    {len(new_candidates)}")
        gaps = find_concept_gaps(all_files, backlinks, outgoing, domains)
        print(f"  Orphans:       {len(gaps['orphans'])}")
        print(f"  Cross-domain:  {len(gaps['cross'])}")

        if new_candidates:
            print(f"\n  Best gap:      {new_candidates[0]['domain_a']} ↔ {new_candidates[0]['domain_b']} ({new_candidates[0]['score']:.4f})")

    elif args.command == "write":
        idx = args.gap - 1
        if idx < 0 or idx >= len(new_candidates):
            print(f"Error: gap #{args.gap} not found. Top gap is #1 ({new_candidates[0]['domain_a']} ↔ {new_candidates[0]['domain_b']})")
            sys.exit(1)

        c = new_candidates[idx]
        a, b = c["domain_a"], c["domain_b"]
        output = args.output or f"bridge_{a.replace('/', '_')}_x_{b.replace('/', '_')}.md"
        content = f"""---
tags: [publication, bridge, bridge-recommender]
status: draft
domain: Cross-Domain Synthesis
bridge-number: TBD
---

# Bridge: {a} × {b}

> **Recommended by the Φ-guided bridge recommender.**
> Score: {c['score']:.4f} | Shared neighbors: {c['shared_count']} | Jaccard: {c['jaccard']:.3f}
> Φ-{a}: {c['phi_a']:.3f} | Φ-{b}: {c['phi_b']:.3f}

## Terrain

{', '.join(c.get('shared_neighbors', [])[:10])}

## Thesis

The structural isomorphism between {a} and {b}...

## Mapping Table

| {a} Concept | {b} Concept | Shared Principle |
|---|---|---|
| ... | ... | ... |

## Falsifiable Predictions

1. ...
2. ...
3. ...
"""
        with open(output, 'w') as f:
            f.write(content)
        print(f"  Written: {output}")


if __name__ == "__main__":
    main()
