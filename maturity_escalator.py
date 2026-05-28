#!/usr/bin/env python3
"""
maturity_escalator.py — Concept Maturity Escalator ("Natural Killer Cell")

Scans the vault for low-phi-but-high-content concepts (100+ lines, ≤3 backlinks,
domain size ≥ 5) and automatically injects cross-references to high-phi
neighbors in the same domain. This is the vault's "natural killer cell" —
it doesn't write new content, it just connects what already exists.

Usage:
    python3 maturity_escalator.py               # Run scan + inject
    python3 maturity_escalator.py --dry-run     # Preview only
    python3 maturity_escalator.py --report      # Full report

Schedule: daily at 04:00 (between vault health at 00:00 and ARI eval at 05:00)
"""

import os, re, glob, sys
from collections import defaultdict, Counter
from datetime import datetime

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
SUB_VAULTS = [
    "Vault_AI", "Vault_Software_Engineering", "Vault_Neuroscience",
    "Vault_Finance", "Vault_Statistics", "Vault_Psychology",
    "Vault_Causal_Inference", "Vault_Physiology", "Vault_Health_&_Longevity",
    "Vault_True_Meta", "Vault_Cell_Biology", "Vault_Research_Methods",
]

def _all_concept_files():
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

MAX_NEW_LINKS = 5
MIN_LINES = 100
MAX_BACKLINKS = 3
MIN_DOMAIN_SIZE = 5


# ──────────────────────────────────────────────
# VAULT LOADER
# ──────────────────────────────────────────────

def load_vault() -> tuple[dict, dict, dict]:
    """Load all concepts with metadata.
    Returns: (titles_to_files, concept_metadata, domain_backlinks)
    """
    files = {}
    meta = {}
    backlinks = defaultdict(int)
    domain_concepts = defaultdict(list)
    
    for f in _all_concept_files():
        name = os.path.basename(f).replace(".md", "")
        with open(f, encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        
        # Frontmatter
        fm = {}
        fm_match = re.search(r'^---\n(.+?)\n---', content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).strip().split('\n'):
                if ': ' in line:
                    k, v = line.split(': ', 1)
                    fm[k.strip()] = v.strip()
        
        title = fm.get('title', name)
        domain = fm.get('domain', '')
        status = fm.get('status', '').lower()
        lines = content.count('\n') + 1
        
        # Wikilinks
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
        }
        files[title] = f
        if domain:
            domain_concepts[domain].append(title)
    
    # Compute backlinks
    for t, m in meta.items():
        for link in m['outlinks']:
            # Resolve alias: if link points to non-existent concept, skip
            if link in meta:
                backlinks[link] += 1
    
    # Attach backlinks to meta
    for t, m in meta.items():
        m['backlinks'] = backlinks.get(t, 0)
    
    return files, meta, domain_concepts


def compute_phi(m: dict) -> float:
    """Simple phi estimate for ranking."""
    backlinks_norm = min(m['backlinks'] / 20, 1.0) * 0.4
    outlinks_norm = min(len(m['outlinks']) / 15, 1.0) * 0.3
    lines_norm = min(m['lines'] / 300, 1.0) * 0.2
    status_bonus = 0.1 if m['status'] == 'evergreen' else 0.05 if m['status'] == 'growing' else 0.0
    return round(backlinks_norm + outlinks_norm + lines_norm + status_bonus, 3)


# ──────────────────────────────────────────────
# CANDIDATE DETECTION
# ──────────────────────────────────────────────

def find_low_phi_high_content(meta: dict, domain_concepts: dict) -> list[dict]:
    """Find concepts with low integration despite having content."""
    candidates = []
    
    for title, m in meta.items():
        domain = m['domain']
        domain_size = len(domain_concepts.get(domain, []))
        
        # Skip stubs, redirects, seedlings without content
        if m['status'] in ('stub', 'redirect'):
            continue
        if m['lines'] < MIN_LINES:
            continue
        if m['backlinks'] > MAX_BACKLINKS:
            continue
        if domain_size < MIN_DOMAIN_SIZE:
            continue
        
        phi = compute_phi(m)
        
        # Low phi relative to size — good candidate
        if phi < 0.25:
            candidates.append({
                'title': title,
                'domain': domain,
                'lines': m['lines'],
                'backlinks': m['backlinks'],
                'outlinks': len(m['outlinks']),
                'phi': phi,
                'domain_size': domain_size,
                'file': m['file'],
                'content': m['content'],
            })
    
    # Sort by phi (lowest first = most need)
    candidates.sort(key=lambda c: c['phi'])
    return candidates


def find_crossref_targets(candidate: dict, meta: dict,
                           domain_concepts: dict) -> list[str]:
    """Find high-phi neighbors in the same domain to link to."""
    domain = candidate['domain']
    domain_members = domain_concepts.get(domain, [])
    existing_links = set(candidate.get('content', '').lower())
    
    # Score each domain member by phi
    scored = []
    for t in domain_members:
        if t == candidate['title']:
            continue
        m = meta.get(t)
        if not m:
            continue
        
        # Skip if already linked
        link_ref = t.lower()
        if f'[[{link_ref}' in existing_links or f'[[{t}' in existing_links:
            continue
        
        phi = compute_phi(m)
        scored.append((phi, t, m))
    
    # Return top N by phi
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:MAX_NEW_LINKS]]


# ──────────────────────────────────────────────
# INJECTION
# ──────────────────────────────────────────────

def inject_crossrefs(filepath: str, targets: list[str],
                     candidate_title: str) -> tuple[bool, str]:
    """Inject [[wikilinks]] into the Related section."""
    with open(filepath) as f:
        content = f.read()
    
    original = content
    link_lines = '\n'.join(f'- [[{t}]]' for t in targets)
    
    # Try to find an existing ## Related or similar section
    related_pattern = re.search(r'(## Related .+\n)', content, re.DOTALL)
    if related_pattern:
        # Append to existing Related section
        new_section = related_pattern.group(1).rstrip() + '\n' + link_lines + '\n'
        content = content.replace(related_pattern.group(1), new_section)
    else:
        # Append at the end of file
        content = content.rstrip() + f'\n\n## Related\n\n{link_lines}\n'
    
    if content == original:
        return False, "no change"
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    return True, f"injected {len(targets)} crossrefs: {', '.join(targets[:3])}..."


# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────

def append_to_log(injected: list[dict], skipped: list[dict]):
    """Log to vault log.md."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    entry = f"\n## [{date_str}] maturity_escalator\n"
    entry += f"Concepts escalated: {len(injected)} injected, {len(skipped)} skipped\n\n"
    
    if injected:
        entry += "**Injected cross-references:**\n"
        for c in injected:
            entry += f"- {c['title']} ({c['domain']}, φ={c['phi']}) → {c['link_count']} new links\n"
        entry += "\n"
    
    if skipped:
        entry += "**Skipped (no candidates found):**\n"
        for c in skipped[:5]:
            entry += f"- {c['title']} ({c['domain']}, φ={c['phi']}) — {c['reason']}\n"
        if len(skipped) > 5:
            entry += f"  ... and {len(skipped)-5} more\n"
    
    try:
        with open(LOG_PATH) as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "# Vault Log\n\n"
    
    with open(LOG_PATH, 'w') as f:
        f.write(log_content.rstrip() + entry)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print("  ╔══════════════════════════════════════╗")
    print("  ║   MATURITY ESCALATOR — Natural Killer ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("  [DRY RUN MODE — no changes will be made]")
        print()
    
    print("  Loading vault...")
    files, meta, domain_concepts = load_vault()
    print(f"  Loaded {len(meta)} concepts, {len(domain_concepts)} domains.")
    
    candidates = find_low_phi_high_content(meta, domain_concepts)
    print(f"\n  Found {len(candidates)} low-phi-high-content candidates.")
    print()
    
    if not candidates:
        print("  No candidates to escalate.")
        return
    
    # Process top 10 candidates
    processed = 0
    injected = []
    skipped = []
    
    for c in candidates[:10]:
        targets = find_crossref_targets(c, meta, domain_concepts)
        
        if not targets:
            skipped.append({
                'title': c['title'],
                'domain': c['domain'],
                'phi': c['phi'],
                'reason': 'no suitable targets'
            })
            print(f"  ⏭️  {c['title'][:40]:40s} [{c['domain']:20s}] φ={c['phi']:.3f} — no targets")
            continue
        
        if dry_run:
            print(f"  📝 {c['title'][:40]:40s} [{c['domain']:20s}] φ={c['phi']:.3f} → {len(targets)} targets: {', '.join(targets[:3])}...")
            processed += 1
            injected.append({
                'title': c['title'],
                'domain': c['domain'],
                'phi': c['phi'],
                'link_count': len(targets),
            })
        else:
            success, msg = inject_crossrefs(c['file'], targets, c['title'])
            if success:
                processed += 1
                injected.append({
                    'title': c['title'],
                    'domain': c['domain'],
                    'phi': c['phi'],
                    'link_count': len(targets),
                })
                print(f"  ✅ {c['title'][:40]:40s} [{c['domain']:20s}] φ={c['phi']:.3f} → +{len(targets)} links")
            else:
                skipped.append({
                    'title': c['title'],
                    'domain': c['domain'],
                    'phi': c['phi'],
                    'reason': msg
                })
                print(f"  ⏭️  {c['title'][:40]:40s} [{c['domain']:20s}] φ={c['phi']:.3f} — {msg}")
    
    print(f"\n  ═══ SUMMARY ═══")
    print(f"  Processed: {processed}")
    print(f"  Injected:  {len(injected)}")
    print(f"  Skipped:   {len(skipped)}")
    
    if not dry_run and injected:
        append_to_log(injected, skipped)
        print(f"  Logged to vault log.md.")


if __name__ == '__main__':
    main()
