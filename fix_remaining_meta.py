#!/usr/bin/env python3
"""
fix_remaining_meta.py — Final pass: handle 88 remaining Meta concepts.

Rules:
1. Already True Meta (52) → keep as is
2. Session logs / handoffs → Meta - Sessions
3. Stub MOCs (empty) → archive (delete)
4. Bridge stubs → archive
5. Known domain mappings → reclassify
6. Everything else → manual review list

Usage:
    python3 fix_remaining_meta.py --dry-run
    python3 fix_remaining_meta.py
"""

import os, re, glob, sys, shutil

VAULT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS = os.path.join(VAULT, "04 Resources/Concepts")
BACKUP = os.path.join(VAULT, "05 Archives/Meta Cleanup 2026-05-27")

DRY_RUN = "--dry-run" in sys.argv

# Explicit mapping: name → domain or special action
# None means "keep as True Meta"
# 'ARCHIVE' means delete (move to backup)
DOMAIN_MAP = {
    # ── Session logs / handoffs → Meta - Sessions ──
    "Hermes Coding Session Log 2026-05-06": "Meta - Sessions",
    "Hermes Coding Session Log 2026-05-06 Afternoon": "Meta - Sessions",
    "Cross-Session Agent Memory — Why Agent Loops Repeat and": "Meta - Sessions",
    "Cognoscope Validation Against Real Hermes Session Data": "Meta - Sessions",
    "Team Run Report 2026-05-06": "Meta - Sessions",
    "Phase 3 Execution Report": "Meta - Sessions",
    "SDEAS Phase 18 — Execution Infrastructure (gstack Fusio": "Meta - Sessions",
    "SDEAS Phase 6 — Self-Modifying Agent": "Meta - Sessions",
    "SDEAS Phase Integration Map": "Meta - Sessions",
    "SDEAS Roadmap": "Meta - Sessions",
    "Autonomous AI Self-Learning Deep Research Synthesis": "Meta - Sessions",
    "Self-Rewriting Programs — Runtime Code Modification for": "Meta - Sessions",
    "Stigmergic Self-Awareness — How Agents Coordinate by Re": "Meta - Sessions",
    "The Autobiography — Why Every Agent Needs a Self-Model": "Meta - Sessions",
    "The Disposition Effect as a Reinforcement Learning Fail": "Meta - Sessions",
    "The Aggregation Problem — Lord's Paradox × Complexity S": "Meta - Sessions",
    "NotebookLM Deep Queries 2026-05-05": "Meta - Sessions",
    
    # ── Stub MOCs → ARCHIVE (empty auto-generated) ──
    "Areas MOC": "ARCHIVE",
    "Biology MOC": "ARCHIVE",
    "Cell Biology MOC": "ARCHIVE",
    "Concepts MOC": "ARCHIVE",
    "Design Patterns MOC": "ARCHIVE",
    "Longevity MOC": "ARCHIVE",
    "Machine Learning MOC": "ARCHIVE",
    "Medicine MOC": "ARCHIVE",
    "Meta MOC": "ARCHIVE",
    "Neuroscience MOC": "ARCHIVE",
    "Physiology MOC": "ARCHIVE",
    "Psychology MOC": "ARCHIVE",
    "Research MOC": "ARCHIVE",
    "Research Methods MOC": "ARCHIVE",
    "Sleep Science MOC": "ARCHIVE",
    "Statistics MOC": "ARCHIVE",
    "04 Resources MOC": "ARCHIVE",
    "AI Agents MOC": "ARCHIVE",
    "Agent Engineering MOC": "ARCHIVE",
    "Resources MOC": "ARCHIVE",
    "Projects Active MOC": "ARCHIVE",
    "MOC": "ARCHIVE",
    "moc": "ARCHIVE",
    "atomic-note": "ARCHIVE",
    "index": "ARCHIVE",
    "system-dashboard": "ARCHIVE",
    "AGENTS": "ARCHIVE",
    
    # ── Bridge redirects/stubs → ARCHIVE (real bridges in Publications/) ──
    "Bridge 67 — Vault as Self": "True Meta",  # Important bridge redirect
    "Bridge 48 — Climate Adaptation as a Multi-Agent Co": "ARCHIVE",
    "Bridge #108 — The Chart Is Not a Drawing, It's an": "ARCHIVE",
    "Bridge #53 — FEP as Unification of Athena Stack": "ARCHIVE",
    "Bridge #90": "ARCHIVE",
    
    # ── Known domain mappings ──
    "Causal Strategy Validation Pattern": "Causal Inference",
    "Crisis Management": "Psychology",
    "Heatwave Response": "Meta - Sessions",
    "LiDAR": "Software Engineering",
    "Licensing": "Meta - Sessions",
    "Message Queues": "Software Engineering",
    "Neurobiology of Agent Memory Systems": "AI",
    "Personal Knowledge Management": "True Meta",
    "Publication Hierarchy & Reading Guide": "True Meta",
    "SASP": "True Meta",
    "Test Automation Suite": "Software Engineering",
    "Concepts Cluster": "True Meta",
    "Deep Evolution Plan 2026-05-27": "True Meta",
    "Fleeting Notes": "True Meta",
    "Home": "True Meta",
    "Idea Index": "True Meta",
    "Map of Content (MOC)": "True Meta",
    "Note": "True Meta",
    "Note-Taking": "True Meta",
    "Note Taking": "True Meta",
    "Orphans": "True Meta",
    "Progressive Summarization": "True Meta",
    "Topic": "True Meta",
    "Wikilinks": "True Meta",
    "wikilinks": "True Meta",
    "Links": "True Meta",
    "links": "True Meta",
}

# Concepts that are already True Meta (domain already set)
ALREADY_TRUE_META = [
    "PKS Disaster Recovery Guide", "Learning", "Vault 2.0 — Recursive Layered Architecture",
    "Digital Twin", "Second Brain", "Information Architecture",
    "Maps of Content as Self-Model", "Publications MOC — All Bridges",
    "Digital Garden", "Vault Evolution Cycle", "Obsidian",
    "Zettelkasten", "PARA Method", "P.A.R.A Method",
    "Knowledge Management", "Evergreen", "Evergreen Notes",
    "Spaced Repetition", "Maps of Content", "Meta",
    "Zettelkasten and Obsidian Workflow", "AI Agents Self-Learning Deep Research",
]

# Filepath patterns for archive
def matches_archive(name: str) -> bool:
    nl = name.lower()
    # stub MOC patterns
    if nl.endswith(' moc') or nl == 'moc' or nl == 'index' or nl == 'system-dashboard':
        return True
    if name in ('atomic-note', 'AGENTS', '04 Resources MOC', 'AI Agents MOC',
                'Agent Engineering MOC', 'Resources MOC', 'Projects Active MOC',
                'Machine Learning MOC', 'Cell Biology MOC'):
        return True
    return False


def main():
    print(f"  ╔══════════════════════════════════════╗")
    print(f"  ║   FINAL META CLEANUP                 ║")
    print(f"  ╚══════════════════════════════════════╝")
    if DRY_RUN:
        print("  [DRY RUN]\n")
    
    # Scan remaining Meta
    meta_files = []
    for f in sorted(glob.glob(os.path.join(CONCEPTS, "*.md"))):
        with open(f, encoding='utf-8') as fh:
            content = fh.read(500)
        if not re.search(r'^domain:\s*Meta\b', content, re.MULTILINE):
            continue
        name = os.path.basename(f).replace('.md', '')
        lines = len(content.splitlines())
        meta_files.append((name, lines, f))
    
    print(f"  Found {len(meta_files)} remaining Meta files.\n")
    
    # Categorize
    results = {'archive': [], 'session': [], 'classify': [], 'keep': []}
    unknown = []
    
    for name, lines, fpath in meta_files:
        # Already True Meta from first pass — skip
        if name in ALREADY_TRUE_META:
            results['keep'].append((name, lines, 'already True Meta'))
            continue
        
        if name in DOMAIN_MAP:
            action = DOMAIN_MAP[name]
            if action == 'ARCHIVE':
                results['archive'].append((name, lines, fpath))
            elif action == 'True Meta':
                results['keep'].append((name, lines, 'True Meta'))
            elif action == 'Meta - Sessions':
                results['session'].append((name, lines, fpath, action))
            else:
                results['classify'].append((name, lines, fpath, action))
        else:
            unknown.append((name, lines, fpath))
    
    # Report
    print(f"  ARCHIVE ({len(results['archive'])}):")
    for n, l, fp in sorted(results['archive']):
        print(f"    {n[:55]:55s} | {l:3d}L")
    
    print(f"\n  → META - SESSIONS ({len(results['session'])}):")
    for n, l, fp, d in sorted(results['session']):
        print(f"    {n[:55]:55s} | {l:3d}L → {d}")
    
    print(f"\n  → CLASSIFY ({len(results['classify'])}):")
    for n, l, fp, d in sorted(results['classify']):
        print(f"    {n[:55]:55s} | {l:3d}L → {d}")
    
    print(f"\n  KEEP ({len(results['keep'])}):")
    for n, l, reason in sorted(results['keep']):
        print(f"    {n[:55]:55s} | {l:3d}L | {reason}")
    
    print(f"\n  UNKNOWN ({len(unknown)}):")
    for n, l, fp in sorted(unknown):
        print(f"    {n[:55]:55s} | {l:3d}L")
    
    total_handled = sum(len(v) for v in results.values())
    print(f"\n  Handled: {total_handled}, Unknown: {len(unknown)}")
    
    # Apply
    if not DRY_RUN:
        # Archive
        for n, l, fp in results['archive']:
            shutil.move(fp, os.path.join(BACKUP, os.path.basename(fp)))
        
        # Move to Session
        for n, l, fp, d in results['session']:
            with open(fp, encoding='utf-8') as f:
                content = f.read()
            new_content = re.sub(r'^(domain:\s*)Meta\b', f'\\1{d}', content, count=1, flags=re.MULTILINE)
            if new_content != content:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(new_content)
        
        # Classify
        for n, l, fp, d in results['classify']:
            with open(fp, encoding='utf-8') as f:
                content = f.read()
            new_content = re.sub(r'^(domain:\s*)Meta\b', f'\\1{d}', content, count=1, flags=re.MULTILINE)
            if new_content != content:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(new_content)
        
        print(f"\n  Applied!")
        print(f"  Archived: {len(results['archive'])}")
        print(f"  Moved to Sessions: {len(results['session'])}")
        print(f"  Classified: {len(results['classify'])}")
        print(f"  Remain: {len(unknown)} (need manual review)")


if __name__ == "__main__":
    main()
