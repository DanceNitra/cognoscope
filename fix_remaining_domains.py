#!/usr/bin/env python3
"""Fix remaining uncategorised concepts and normalise lowercase domains."""
import os, re, glob

CONCEPTS_DIR = os.path.expanduser("~/Obsidian Vault/04 Resources/Concepts")

# 1. Fix remaining 4 uncategorised
fixes = {
    "Attention & Resource Allocation — The Isomorphic Routing Problem Across Cognition, AI, and Finance": "Psychology",
    "Control Theory as Universal Bridge — Feedback Architecture Across Physiology, Engineering, and Trading": "Control Theory",
    "Personal Knowledge Digital Twin": "Meta",
    "Test-Time Compute Scaling": "AI",
}

for fname, domain in fixes.items():
    fpath = os.path.join(CONCEPTS_DIR, fname + ".md")
    if not os.path.isfile(fpath):
        print(f"NOT FOUND: {fname}")
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'domain:' in content:
        content = re.sub(r'^domain:.*', f'domain: {domain}', content, flags=re.MULTILINE)
    else:
        content = content.replace('---\n', f'---\ndomain: {domain}\n', 1)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"FIXED: {fname} -> {domain}")

# 2. Normalise lowercase/misspelled domains
pairs = [
    ("ai", "AI"), ("finance", "Finance"), 
    ("physiology", "Physiology"), ("statistics", "Statistics"),
    ("cell-biology", "Cell Biology"), ("software-engineering", "Software Engineering"),
    ("sleep-science", "Sleep / Neuroscience"),
]

for old, new in pairs:
    count = 0
    for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
        try:
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            # Match domain: old or domain: "old"
            pattern = re.compile(r'^domain:\s*("?"' + re.escape(old) + r'"?)', re.MULTILINE)
            if pattern.search(content):
                content = re.sub(r'^domain:\s*("?"' + re.escape(old) + r'"?)', f'domain: {new}', content, flags=re.MULTILINE)
                with open(f, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                count += 1
        except:
            pass
    if count:
        print(f"NORMALISED: {old} -> {new} ({count} files)")

# 3. Check for Neuroscience/Psychology lowercase
for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
    try:
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        # Check for lowercase domain that should be capitalised
        domain_match = re.search(r'^domain:\s*(.+)$', content, re.MULTILINE)
        if domain_match:
            domain_val = domain_match.group(1).strip().strip('"')
            # Known proper name mappings
            proper_map = {
                "neuroscience": "Neuroscience",
                "psychology": "Psychology",
                "cell-biology": "Cell Biology",
                "software-engineering": "Software Engineering",
            }
            if domain_val in proper_map:
                proper = proper_map[domain_val]
                content = re.sub(r'^domain:\s*("?"' + re.escape(domain_val) + r'"?)', f'domain: {proper}', content, flags=re.MULTILINE)
                with open(f, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                print(f"NORMALISED: {domain_val} -> {proper} in {os.path.basename(f)}")
    except:
        pass

print("\nDone. Now running verification...")
