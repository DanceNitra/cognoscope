#!/usr/bin/env python3
"""
vault_quality_scorer.py — Layer 3 Quality Scoring

Computes quality scores for every concept in the vault:
  Q = 0.3·φ + 0.3·C + 0.2·(1 - δ/365) + 0.2·τ

Where:
  φ (phi) = integration — how connected
  C (confidence) = status-based (evergreen=1.0, growing=0.7, seedling=0.4, stub=0.2)
  δ (staleness) = days since last meaningful update
  τ (trust) = how many sessions cited this (≈ inbound links, normalised)

Outputs:
  - JSON report to stdout
  - Summary to vault log
  - Flags stale concepts (δ > 60) for review

Schedule: daily at 03:00 (after darwinian heal)
"""

import os, re, glob, json, sys
from datetime import datetime, timezone
from collections import defaultdict

VAULT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS = os.path.join(VAULT, "04 Resources/Concepts")
LOG_PATH = os.path.join(VAULT, "log.md")
OUTPUT_PATH = os.path.join(VAULT, "90 Meta/MOCs/vault_quality_report.json")

STALE_DAYS = 60
CRITICAL_STALE_DAYS = 120


def load_concepts() -> list[dict]:
    """Load all concepts with metadata."""
    results = []
    now = datetime.now(timezone.utc)

    for f in sorted(glob.glob(os.path.join(CONCEPTS, "*.md"))):
        with open(f, encoding='utf-8') as fh:
            content = fh.read()
        name = os.path.basename(f).replace(".md", "")
        lines = len(content.splitlines())

        # Frontmatter
        fm = {}
        fm_m = re.search(r'^---\n(.+?)\n---', content, re.DOTALL)
        if fm_m:
            for line in fm_m.group(1).split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip().strip('"\'')

        domain = fm.get('domain', 'Unknown')
        status = fm.get('status', 'unknown')
        updated = fm.get('updated', fm.get('date', ''))

        # Staleness
        staleness = None
        if updated:
            try:
                updated_dt = datetime.strptime(updated, "%Y-%m-%d")
                staleness = (now - updated_dt.replace(tzinfo=timezone.utc)).days
            except ValueError:
                pass

        if staleness is None:
            staleness = 365  # Unknown date → assume very stale

        # Inbound links (wikilinks from all concepts)
        inbound = len(re.findall(r'\[\[.*?' + re.escape(name) + r'.*?\]\]', content))

        # φ (phi) — integration score
        phi = min(1.0, inbound / 20)  # 20+ inbound = max phi

        # C (confidence) — based on status
        conf_map = {
            'evergreen': 1.0,
            'growing': 0.7,
            'seedling': 0.4,
            'stub': 0.2,
            'redirect': 0.1,
        }
        confidence = conf_map.get(status, 0.3)

        # τ (trust) — normalised inbound links
        trust = min(1.0, inbound / 10)

        # δ factor
        staleness_factor = max(0, 1.0 - staleness / 365)

        # Q overall
        Q = 0.3 * phi + 0.3 * confidence + 0.2 * staleness_factor + 0.2 * trust

        results.append({
            "name": name,
            "domain": domain,
            "status": status,
            "lines": lines,
            "inbound": inbound,
            "phi": round(phi, 3),
            "confidence": round(confidence, 3),
            "staleness_days": staleness,
            "staleness_factor": round(staleness_factor, 3),
            "trust": round(trust, 3),
            "Q": round(Q, 3),
        })

    return results


def main():
    print("  ╔══════════════════════════════════════╗")
    print("  ║   VAULT QUALITY SCORER — Layer 3     ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    concepts = load_concepts()
    print(f"  Scored {len(concepts)} concepts.\n")

    # Aggregate
    by_status = defaultdict(list)
    by_domain = defaultdict(list)
    stale = []
    critical = []

    for c in concepts:
        by_status[c['status']].append(c)
        by_domain[c['domain']].append(c)
        if c['staleness_days'] >= CRITICAL_STALE_DAYS:
            critical.append(c)
        elif c['staleness_days'] >= STALE_DAYS:
            stale.append(c)

    # Summary
    print("  === QUALITY SUMMARY === ")
    print(f"  Avg Q: {sum(c['Q'] for c in concepts)/len(concepts):.3f}")
    print(f"  Avg phi: {sum(c['phi'] for c in concepts)/len(concepts):.3f}")
    print(f"  Avg confidence: {sum(c['confidence'] for c in concepts)/len(concepts):.3f}")
    print(f"  Avg trust: {sum(c['trust'] for c in concepts)/len(concepts):.3f}")
    print()

    print("  === BY STATUS === ")
    for s in ['evergreen', 'growing', 'seedling', 'stub', 'redirect']:
        items = by_status.get(s, [])
        if items:
            avg_q = sum(c['Q'] for c in items) / len(items)
            print(f"  {s}: {len(items)} concepts, avg Q={avg_q:.3f}")
    print()

    print("  === STALE CONCEPTS (δ ≥ 60 days) === ")
    for c in sorted(stale + critical, key=lambda x: -x['staleness_days'])[:10]:
        marker = "⚠️" if c['staleness_days'] >= CRITICAL_STALE_DAYS else " "
        print(f"  {marker} {c['name'][:45]:45s} | δ={c['staleness_days']:3d}d | Q={c['Q']:.3f}")

    print(f"\n  Total stale: {len(stale)} | Critical: {len(critical)}\n")

    # Top/bottom by Q
    sorted_q = sorted(concepts, key=lambda x: -x['Q'])
    print("  === TOP 5 BY Q === ")
    for c in sorted_q[:5]:
        print(f"  {c['name'][:45]:45s} | Q={c['Q']:.3f} | φ={c['phi']:.3f} | τ={c['trust']:.3f}")

    print("\n  === BOTTOM 5 BY Q === ")
    for c in sorted_q[-5:]:
        print(f"  {c['name'][:45]:45s} | Q={c['Q']:.3f} | δ={c['staleness_days']:3d}d | {c['status']}")
    print()

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_concepts": len(concepts),
        "avg_Q": round(sum(c['Q'] for c in concepts) / len(concepts), 3),
        "stale_count": len(stale) + len(critical),
        "stale": [{"name": c['name'], "domain": c['domain'],
                    "staleness_days": c['staleness_days'], "Q": c['Q']}
                  for c in sorted(stale + critical, key=lambda x: -x['staleness_days'])],
        "concepts": sorted(concepts, key=lambda x: -x['Q']),
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to {OUTPUT_PATH}")

    # Append to log
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"\n## [{date_str}] quality_scorer\n"
    log_entry += f"Quality scored {len(concepts)} concepts. Avg Q={report['avg_Q']:.3f}. "
    log_entry += f"Stale: {len(stale)} | Critical: {len(critical)} | Top: {sorted_q[0]['name']} (Q={sorted_q[0]['Q']:.3f})\n"
    
    try:
        with open(LOG_PATH) as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "# Vault Log\n\n"
    with open(LOG_PATH, 'w') as f:
        f.write(log_content.rstrip() + log_entry)


if __name__ == "__main__":
    main()
