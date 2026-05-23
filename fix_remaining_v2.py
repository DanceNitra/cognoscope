#!/usr/bin/env python3
"""Fix the remaining uncategorised concepts by their actual filenames."""
import os, re, glob

CONCEPTS_DIR = os.path.expanduser("~/Obsidian Vault/04 Resources/Concepts")

# These files need their domain set (filenames from what's actually on disk)
fix_files = {
    "Attention & Resource Allocation — The Isomorphic Routing Problem.md": "Psychology",
    "Control Theory as Universal Bridge.md": "Control Theory",
    "Personal Knowledge Digital Twin.md": "Meta",
}

for fname, domain in fix_files.items():
    fpath = os.path.join(CONCEPTS_DIR, fname)
    if not os.path.isfile(fpath):
        print(f"NOT FOUND: {fname}")
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    if "domain:" in content:
        content = re.sub(r"^domain:.*", f"domain: {domain}", content, flags=re.MULTILINE)
    else:
        content = content.replace("---\n", f"---\ndomain: {domain}\n", 1)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"FIXED: {fname} -> {domain}")

# Also check for Personal Knowledge Digital Twin which might have a truncation
for f in glob.glob(os.path.join(CONCEPTS_DIR, "*Personal*Digital*")):
    print(f"Found alt: {os.path.basename(f)}")
    with open(f, "r", encoding="utf-8") as fh:
        c = fh.read()
    if not re.search(r"domain:", c) or re.search(r"domain: (General|Uncategorised)", c):
        if "domain:" in c:
            c = re.sub(r"^domain:.*", "domain: Meta", c, flags=re.MULTILINE)
        else:
            c = c.replace("---\n", "---\ndomain: Meta\n", 1)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(c)
        print(f"FIXED: {os.path.basename(f)} -> Meta")

print("\nAll remaining fixes applied.")
