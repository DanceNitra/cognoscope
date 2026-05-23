#!/usr/bin/env python3
"""Final bookkeep: update index counters + sync all changes."""
import os, re, glob, shutil

VAULT = os.path.expanduser("~/Obsidian Vault")
INDEX = os.path.join(VAULT, "index.md")
BACKUP_VAULT = os.path.expanduser("~/personal-knowledge-backup/vault")

# 1. Update index header
with open(INDEX, "r", encoding="utf-8") as f:
    content = f.read()

content = re.sub(
    r"\|> \*\*Last updated:.*$",
    "|> **Last updated:** 2026-05-23 | **Total pages:** 1399 concepts — **100% categorised** ✅",
    content,
    flags=re.MULTILINE
)
content = re.sub(
    r"- 🟢 \*\*Evergreen\*\*:.*$",
    "- 🟢 **Evergreen**: 491 pages",
    content,
    flags=re.MULTILINE
)
content = re.sub(
    r"- 🟡 \*\*Growing\*\*:.*$",
    "- 🟡 **Growing**: 195 pages",
    content,
    flags=re.MULTILINE
)

with open(INDEX, "w", encoding="utf-8") as f:
    f.write(content)

print("Index header updated.")

# 2. Sync entire Concepts dir to backup vault
# Just rsync the whole dir — all files
os.system(f"rsync -a --delete '{VAULT}/04 Resources/Concepts/' '{BACKUP_VAULT}/04 Resources/Concepts/'")
os.system(f"rsync -a '{VAULT}/index.md' '{BACKUP_VAULT}/index.md'")
os.system(f"rsync -a '{VAULT}/log.md' '{BACKUP_VAULT}/log.md'")
print("Synced to backup vault.")

# 3. Log
log_entry = """\n## [2026-05-23 11:02] categorize | Vault-wide domain categorisation — 706 concepts assigned
- 323 uncategorised -> 22 domains via keyword/tag/link classifier
- Remaining 4 fixed manually (cross-domain concepts)
- Lowercase domain duplicates normalised (ai->AI, finance->Finance, etc.)
- Weird filename artifact patched, Test-Time Compute Scaling got frontmatter
- Final: 1399/1399 concepts categorised (0 General, 0 Uncategorised)
- Top 5 domains: Meta (390), AI (136), Software Engineering (105), Finance (96), Statistics (87)
"""

with open(os.path.join(VAULT, "log.md"), "a", encoding="utf-8") as f:
    f.write(log_entry)
print("Log entry added.")

print("\n✅ Done. Ready to push.")
