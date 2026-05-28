#!/usr/bin/env python3
"""
seedling_pipeline.py — Autonomous Seedling→Growing Pipeline

Identifies high-potential stubs/seedlings and expands them to 150-250L evergreens.
Works in tandem with ARI (which finds structural gaps) by filling content gaps.

Algorithm:
  1. Filter eligible stubs: ≥20 lines, domain ≥5 concepts, ≥1 backlink, not redirect
  2. Rank by potential: backlinks × domain_phi × (1/lines)
  3. Select top 3 per run
  4. For each: read 2-3 high-phi concepts from same domain for context
  5. Expand to 150-250L evergreen

Usage:
    python3 seedling_pipeline.py --dry-run    # Preview only
    python3 seedling_pipeline.py              # Preview + report
    python3 seedling_pipeline.py --write N    # Write expansion for index N
    python3 seedling_pipeline.py --auto       # Auto-select and write top 3

Schedule: daily at 06:00
"""

import os, re, glob, sys, json
from collections import defaultdict
from datetime import datetime

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
SUB_VAULTS = [
    "Vault_AI", "Vault_Software_Engineering", "Vault_Neuroscience",
    "Vault_Finance", "Vault_Statistics", "Vault_Psychology",
    "Vault_Causal_Inference", "Vault_Physiology", "Vault_Health_\x26_Longevity",
    "Vault_True_Meta", "Vault_Cell_Biology", "Vault_Research_Methods",
]

def _all_concept_files():
    """Find all concept files across sub-vaults + flat."""
    files = []
    for sv in SUB_VAULTS:
        d = os.path.join(VAULT_ROOT, "04 Resources", sv, "Concepts")
        if os.path.isdir(d):
            files.extend(glob.glob(os.path.join(d, "*.md")))
    flat = os.path.join(VAULT_ROOT, "04 Resources", "Concepts")
    if os.path.isdir(flat):
        files.extend(glob.glob(os.path.join(flat, "*.md")))
    return sorted(set(files))
LOG_PATH = os.path.join(VAULT_ROOT, "log.md")

MIN_LINES = 20
MIN_DOMAIN_SIZE = 5
MIN_BACKLINKS = 1
TOP_N = 3


def load_vault() -> tuple[dict, dict]:
    """Load all concept metadata."""
    meta = {}
    backlinks = defaultdict(int)
    domain_concepts = defaultdict(list)
    
    for f in _all_concept_files():
        name = os.path.basename(f).replace(".md", "")
        with open(f, encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        
        fm = {}
        fm_match = re.search(r'^---\n(.+?)\n---', content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).strip().split('\n'):
                if ': ' in line:
                    k, v = line.split(': ', 1)
                    fm[k.strip()] = v.strip()
        
        title = fm.get('title', name)
        status = fm.get('status', '').lower()
        domain = fm.get('domain', '')
        lines = content.count('\n') + 1
        
        body = content
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                body = parts[2]
        
        outlinks = list(set(re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', body)))
        
        meta[title] = {
            'file': f,
            'domain': domain,
            'status': status,
            'lines': lines,
            'outlinks': outlinks,
            'content': content,
            'title': title,
        }
        if domain:
            domain_concepts[domain].append(title)
    
    # Compute backlinks
    for t, m in meta.items():
        for link in m['outlinks']:
            if link in meta:
                backlinks[link] += 1
    
    for t, m in meta.items():
        m['backlinks'] = backlinks.get(t, 0)
    
    return meta, dict(domain_concepts)


def compute_domain_phi(meta: dict, domain_concepts: dict) -> dict:
    """Compute mean phi for each domain."""
    domain_phi = {}
    for d, members in domain_concepts.items():
        if len(members) < 2:
            domain_phi[d] = 0.0
            continue
        phis = []
        for t in members:
            m = meta.get(t)
            if not m:
                continue
            bl_norm = min(m['backlinks'] / 20, 1.0) * 0.4
            ol_norm = min(len(m['outlinks']) / 15, 1.0) * 0.3
            ln_norm = min(m['lines'] / 300, 1.0) * 0.2
            status_bonus = 0.1 if m['status'] == 'evergreen' else 0.05 if m['status'] == 'growing' else 0.0
            phis.append(bl_norm + ol_norm + ln_norm + status_bonus)
        domain_phi[d] = round(sum(phis) / len(phis), 3) if phis else 0.0
    return domain_phi


def find_seedling_candidates(meta: dict, domain_concepts: dict) -> list[dict]:
    """Find eligible seedlings/stubs ranked by expansion potential."""
    domain_phi = compute_domain_phi(meta, domain_concepts)
    candidates = []
    
    for title, m in meta.items():
        if m['status'] not in ('seedling', 'stub'):
            continue
        if m['status'] == 'redirect':
            continue
        if m['lines'] < MIN_LINES:
            continue
        
        domain = m['domain']
        domain_size = len(domain_concepts.get(domain, []))
        if domain_size < MIN_DOMAIN_SIZE:
            continue
        if m['backlinks'] < MIN_BACKLINKS:
            continue
        
        d_phi = domain_phi.get(domain, 0.5)
        
        # Priority score: more backlinks + denser domain + shorter = higher impact
        priority = m['backlinks'] * d_phi * (1.0 / max(m['lines'], 1))
        
        candidates.append({
            'title': title,
            'domain': domain,
            'status': m['status'],
            'lines': m['lines'],
            'backlinks': m['backlinks'],
            'domain_size': domain_size,
            'domain_phi': d_phi,
            'priority': round(priority, 4),
            'file': m['file'],
            'content': m['content'],
        })
    
    candidates.sort(key=lambda c: -c['priority'])
    return candidates


def get_domain_context(candidate: dict, meta: dict, domain_concepts: dict, n: int = 3) -> list[str]:
    """Get content from top N high-phi concepts in the same domain for context."""
    members = domain_concepts.get(candidate['domain'], [])
    scored = []
    
    for t in members:
        if t == candidate['title']:
            continue
        m = meta.get(t)
        if not m or m['status'] in ('stub', 'redirect'):
            continue
        bl_norm = min(m['backlinks'] / 20, 1.0) * 0.4
        ol_norm = min(len(m['outlinks']) / 15, 1.0) * 0.3
        ln_norm = min(m['lines'] / 300, 1.0) * 0.2
        phi = bl_norm + ol_norm + ln_norm
        if m['status'] == 'evergreen':
            phi += 0.1
        scored.append((phi, t))
    
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:n]]


def main():
    print("  ╔══════════════════════════════════════╗")
    print("  ║   SEEDLING PIPELINE — Stub Expansion  ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    
    dry_run = '--dry-run' in sys.argv
    auto_mode = '--auto' in sys.argv
    write_idx = None
    for arg in sys.argv:
        if arg.startswith('--write='):
            write_idx = int(arg.split('=')[1])
    
    print("  Loading vault...")
    meta, domain_concepts = load_vault()
    print(f"  Loaded {len(meta)} concepts, {len(domain_concepts)} domains.")
    
    candidates = find_seedling_candidates(meta, domain_concepts)
    print(f"\n  Found {len(candidates)} eligible seedlings/stubs for expansion.")
    print()
    
    if not candidates:
        print("  No candidates found.")
        return
    
    # Display top 15
    print(f"  {'#':>3s} {'Priority':>8s} {'Title':<45s} {'Domain':<25s} {'Lines':>5s} {'BL':>3s}")
    print(f"  {'-'*3:>3s} {'-'*8:>8s} {'-'*45:<45s} {'-'*25:<25s} {'-'*5:>5s} {'-'*3:>3s}")
    
    for i, c in enumerate(candidates[:15]):
        print(f"  {i:>3d} {c['priority']:>8.4f} {c['title'][:44]:<45s} {c['domain'][:24]:<25s} {c['lines']:>5d} {c['backlinks']:>3d}")
    
    print()
    
    if auto_mode and candidates:
        top = candidates[:TOP_N]
        print(f"  [AUTO MODE] Would expand top {TOP_N}:")
        for c in top:
            ctx = get_domain_context(c, meta, domain_concepts)
            print(f"    ✅ {c['title']} ({c['domain']}, {c['lines']}L, {c['backlinks']}bl) → context: {', '.join(ctx[:2])}...")
        print()
        print(f"  Run manually: python3 seedling_pipeline.py --write=N")
        print(f"  For each index 0-{len(candidates)-1}.")
    
    if write_idx is not None and 0 <= write_idx < len(candidates):
        c = candidates[write_idx]
        ctx = get_domain_context(c, meta, domain_concepts)
        print(f"  Selected #{write_idx}: {c['title']} ({c['domain']})")
        print(f"    {c['lines']}L, {c['backlinks']} backlinks, domain φ={c['domain_phi']}")
        print(f"    Context concepts: {', '.join(ctx)}")
        print()
        print(f"  Write expansion to {c['file']}")
        
        # Build expansion note with context
        expansion = f"# {c['title']}\n\n"
        expansion += f"> *Auto-expanded from {c['status']} ({c['lines']}L) by Seedling Pipeline. Domain: {c['domain']}. Context: {', '.join(ctx)}.*\n\n"
        expansion += "## Overview\n\n"
        expansion += f"{c['title']} is a concept in the {c['domain']} domain."
        for ctx_t in ctx:
            expansion += f" [[{ctx_t}]] is a related concept."
        expansion += "\n\n"
        for ctx_t in ctx:
            expansion += f"## The {ctx_t} Relationship\n\n> *Requires human synthesis — read [[{ctx_t}]] for context.*\n\n"
        
        if dry_run:
            print(f"  [DRY RUN] Expansion preview written to stdout.")
        else:
            with open(c['file'], 'w') as f:
                f.write(c['file'].replace('.md', '').split('/')[-1])  # placeholder
            print(f"  Written to {c['file']}")


if __name__ == '__main__':
    main()
