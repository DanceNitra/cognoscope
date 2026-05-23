#!/usr/bin/env python3
"""Final fix: last 6 uncategorised + lowercase domains."""
import os, re, glob

CONCEPTS_DIR = os.path.expanduser("~/Obsidian Vault/04 Resources/Concepts")

# Fix remaining uncategorised by title matching
fixes = {
    "The Addictive Loop": "Psychology",
    "The Social Mirror": "AI / Systems Engineering",
    "Advanced Options: Exotics": "Finance",
    "The Vol Surface: Local, Stochastic, Rough Vol": "Finance",
    "Test-Time Compute Scaling": "AI",
}

for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
    with open(f, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    
    # Get title from frontmatter or filename
    title_m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', content, re.MULTILINE)
    if title_m:
        title = title_m.group(1).strip()
    else:
        title = os.path.splitext(os.path.basename(f))[0]
    
    if title in fixes:
        domain = fixes[title]
        if "domain:" in content:
            content = re.sub(r"^domain:.*", f"domain: {domain}", content, flags=re.MULTILINE)
        else:
            content = content.replace("---\n", f"---\ndomain: {domain}\n", 1)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"FIXED: {title} -> {domain}")

# Fix the weird one with many A's
for f in glob.glob(os.path.join(CONCEPTS_DIR, "A A*.md")):
    print(f"Found weird file: {os.path.basename(f)}")
    with open(f, "r", encoding="utf-8") as fh:
        content = fh.read()
    if "domain:" not in content or re.search(r"domain: (General|Uncategorised)", content):
        if "domain:" in content:
            content = re.sub(r"^domain:.*", "domain: Meta", content, flags=re.MULTILINE)
        else:
            content = content.replace("---\n", "---\ndomain: Meta\n", 1)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"FIXED: weird file -> Meta")

# Normalise lowercase domains in ALL files
lcase_map = {
    "physiology": "Physiology",
    "statistics": "Statistics",
    "finance": "Finance",
    "neuroscience": "Neuroscience",
    "psychology": "Psychology",
    "cell-biology": "Cell Biology",
}

counts = {}
for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
    with open(f, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    for lower, proper in lcase_map.items():
        pattern = r'^domain:\s*("?' + re.escape(lower) + r'"?)\s*$'
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"domain: {proper}", content, flags=re.MULTILINE)
            counts[lower] = counts.get(lower, 0) + 1
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(content)

for lower, count in sorted(counts.items()):
    print(f"NORMALISED: {lower} -> {lcase_map[lower]} ({count} files)")

print("\nDone. All remaining fixes applied.")
