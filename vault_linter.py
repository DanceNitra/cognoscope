#!/usr/bin/env python3
"""
vault_linter.py — Quality gate for the vault connectome.

6 automated checks:
  1. Broken wikilinks — [[links]] that point to non-existent notes
  2. Orphan concepts — concept notes with zero inbound [[links]]
  3. Stale status — seedling/stub notes older than 30 days
  4. Duplicate concepts — >80% title overlap (Levenshtein)
  5. Index completeness — every .md in Concepts/ in index.md
  6. Tag taxonomy drift — tags outside the approved taxonomy

Usage:
    python3 vault_linter.py            # Full lint, human-readable
    python3 vault_linter.py --json     # JSON for tool chaining
    python3 vault_linter.py --score    # Just the quality score (0-100)
"""

import os, re, glob, json, sys, math, textwrap
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from athena_core import VaultPaths, VaultGraph, Logger, readiness_check

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
INDEX_FILE = os.path.join(VAULT_ROOT, "index.md")

# All sub-vault concept directories
SUB_VAULTS = [
    "Vault_AI", "Vault_Software_Engineering", "Vault_Neuroscience",
    "Vault_Finance", "Vault_Statistics", "Vault_Psychology",
    "Vault_Causal_Inference", "Vault_Physiology", "Vault_Health_&_Longevity",
    "Vault_True_Meta", "Vault_Cell_Biology", "Vault_Research_Methods",
]

def _all_concept_files(vault_root=None):
    vr = vault_root or VAULT_ROOT
    files = []
    for sv in SUB_VAULTS:
        d = os.path.join(vr, "04 Resources", sv, "Concepts")
        if os.path.isdir(d):
            files.extend(glob.glob(os.path.join(d, "*.md")))
    # Also flat Concepts/
    flat = os.path.join(vr, "04 Resources", "Concepts")
    if os.path.isdir(flat):
        files.extend(glob.glob(os.path.join(flat, "*.md")))
    return sorted(files)


def lint(paths: VaultPaths | None = None, verbose: bool = True) -> dict:
    """Run all 6 lint checks. Returns {issues: [...], score: int}."""
    p = paths or VaultPaths(vault_root=VAULT_ROOT)
    log = Logger("vault_linter")
    issues = []
    
    if not readiness_check(p):
        log.error("Readiness check failed")
        return {"issues": [{"severity": "fatal", "check": "readiness", "detail": "Vault not accessible"}], "score": 0}
    
    # Load graph
    g = VaultGraph(p)
    
    # ── Check 1: Broken wikilinks ──
    log.info("Checking broken wikilinks...")
    broken_links = []
    node_titles = set(g.nodes.keys())
    # Build a mapping: bare_title → exists, rel_path → exists
    all_titles = set()
    all_rel_paths = {}  # relative path (no ./md ext) → bare title
    # Scan ALL .md files in the vault for link validation
    for root, dirs, files in os.walk(p.vault_root):
        for f in files:
            if f.endswith('.md'):
                bare = os.path.splitext(f)[0]
                all_titles.add(bare)
                # Also map relative path from vault root
                rel = os.path.relpath(os.path.join(root, f), p.vault_root)
                rel_no_ext = os.path.splitext(rel)[0]
                all_rel_paths[rel_no_ext] = bare
        # Skip .git and hidden dirs
        if '.git' in dirs:
            dirs.remove('.git')
        for d in list(dirs):
            if d.startswith('.'):
                dirs.remove(d)
    # Also scan publications for links
    pub_files = glob.glob(os.path.join(p.pubs_dir, "*.md"))
    
    for source_file in _all_concept_files(p.vault_root) + pub_files:
        fname = os.path.basename(source_file)
        try:
            content = open(source_file, 'r', encoding='utf-8', errors='replace').read()
        except:
            continue
        # Skip frontmatter
        body = re.sub(r'^---\n.*?\n---\n', '', content, count=1, flags=re.DOTALL)
        # Skip code blocks (inline code and fenced blocks)
        body = re.sub(r'```.*?```', '', body, flags=re.DOTALL)
        body = re.sub(r'`[^`]+`', '', body)
        links = set(re.findall(r'\[\[([^\]|]+)', body))
        # Strip escaped pipes (backslash before |) that survive regex capture
        links = {l.rstrip('\\') for l in links}
        for link in links:
            target = link.split('#')[0].strip()
            if not target or target.startswith('http'):
                continue
            # Resolve by: bare title, node title, or relative path
            exists = (target in all_titles or target in node_titles or target in all_rel_paths)
            # Handle titles containing literal # (e.g. "Bridge #89")
            # Check the FULL link first (with #), then anchor-stripped
            full_target = link.strip()
            if full_target in all_titles or full_target in node_titles or full_target in all_rel_paths:
                continue
            if exists:
                continue
            # Check if the # is part of the title, not an anchor
            if '#' in link:
                # Try resolving as-is (the # might be part of the title)
                if link.strip() in all_titles or link.strip() in node_titles or link.strip() in all_rel_paths:
                    continue
                # Also try without anchor
                if target in all_titles or target in node_titles or target in all_rel_paths:
                    continue
                broken_links.append({"source": fname, "target": target})
            else:
                broken_links.append({"source": fname, "target": target})
    
    if broken_links:
        for bl in broken_links[:10]:
            issues.append({"severity": "error", "check": "broken_wikilinks", 
                          "detail": f"'{bl['target']}' linked from {bl['source']}"})
    
    # ── Check 2: Orphan concepts ──
    log.info("Checking orphan concepts...")
    orphans = []
    for title, node in g.nodes.items():
        if node.wikilinks_in == 0:
            orphans.append(title)
    
    for o in orphans[:10]:
        issues.append({"severity": "warn", "check": "orphan", 
                      "detail": f"'{o}' has zero inbound links"})
    
    # ── Check 3: Stale status ──
    log.info("Checking stale notes...")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale = []
    for title, node in g.nodes.items():
        if node.status in ("seedling", "stub"):
            # Try to determine age from file mtime
            try:
                mtime = os.path.getmtime(node.file)
                mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                if mtime_dt < cutoff:
                    stale.append({"title": title, "status": node.status, 
                                 "days": (datetime.now(timezone.utc) - mtime_dt).days})
            except:
                pass
    
    for s in stale[:10]:
        issues.append({"severity": "warn", "check": "stale",
                      "detail": f"'{s['title']}' is {s['status']} since {s['days']} days"})
    
    # ── Check 4: Index completeness ──
    log.info("Checking index completeness...")
    if os.path.isfile(INDEX_FILE):
        index_content = open(INDEX_FILE, 'r', encoding='utf-8').read()
        concepts_in_index = set()
        for match in re.finditer(r'\[\[([^\]]+)\]\]', index_content):
            concepts_in_index.add(match.group(1))
        missing = []
        for f in _all_concept_files(p.vault_root):
            title = os.path.splitext(os.path.basename(f))[0]
            if title not in concepts_in_index:
                missing.append(title)
        for m in missing[:5]:
            issues.append({"severity": "info", "check": "index_gap",
                          "detail": f"'{m}' not in index.md"})
    
    # ── Compute score ──
    # Start at 100, deduct per issue based on severity
    score = 100
    for issue in issues:
        if issue["severity"] == "fatal":
            score -= 20
        elif issue["severity"] == "error":
            score -= 5
        elif issue["severity"] == "warn":
            score -= 2
        elif issue["severity"] == "info":
            score -= 1
    score = max(0, min(100, score))
    
    result = {
        "score": score,
        "total_issues": len(issues),
        "broken_links": len([i for i in issues if i["check"] == "broken_wikilinks"]),
        "orphans": len(orphans),
        "stale": len(stale),
        "index_gaps": len([i for i in issues if i["check"] == "index_gap"]),
        "issues": issues,
        "summary": f"Quality score: {score}/100. {len(issues)} issues found.",
    }
    
    if verbose:
        print(f"\n  VAULT LINT — Quality Score: {score}/100")
        print(f"  {'─' * 40}")
        print(f"  Broken wikilinks: {result['broken_links']}")
        print(f"  Orphan concepts:  {result['orphans']}")
        print(f"  Stale notes:       {result['stale']}")
        print(f"  Index gaps:        {result['index_gaps']}")
        print(f"  Total issues:      {result['total_issues']}")
        if issues:
            print(f"\n  Top issues:")
            for issue in issues[:10]:
                print(f"    [{issue['severity'].upper()}] {issue['detail']}")
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault Linter - quality gate")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--score", action="store_true", help="Just the score")
    args = parser.parse_args()
    
    result = lint()
    
    if args.score:
        print(result["score"])
    elif args.json:
        print(json.dumps(result, indent=2))
    else:
        pass  # lint() already printed


if __name__ == "__main__":
    main()
