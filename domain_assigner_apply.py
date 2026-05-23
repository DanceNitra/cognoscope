#!/usr/bin/env python3
"""
domain_assigner_apply.py — Phase 2: Apply domain assignments to vault files.
Reads /tmp/domain_assignments.txt, patches frontmatter, fills stubs.
"""
import os, re, sys, glob

VAULT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT, "04 Resources/Concepts")

# Load assignment log
assignments = {}
with open("/tmp/domain_assignments.txt") as f:
    for line in f:
        line = line.strip()
        if " | " in line:
            domain, title = line.split(" | ", 1)
            domain = domain.strip()
            title = title.strip()
            assignments[title] = domain

print(f"Loaded {len(assignments)} assignments")

# Domain-specific stub definitions
STUBS = {
    "AI": "Artificial Intelligence concerns systems that perceive, reason, learn, and act. It encompasses machine learning, deep learning, NLP, computer vision, robotics, and reasoning systems.",
    "Finance": "Finance concerns the management of money, assets, and risk across markets, instruments, and institutions. Core areas: trading, portfolio management, derivatives, and risk.",
    "Software Engineering": "Software engineering is the systematic design, development, testing, and maintenance of software systems using engineering principles and best practices.",
    "Causal Inference": "Causal inference is the set of statistical methods for determining cause-effect relationships from observational or experimental data.",
    "Neuroscience": "Neuroscience is the scientific study of the nervous system across multiple scales from molecules and cells to circuits, systems, and behaviour.",
    "Psychology": "Psychology is the scientific study of mind and behaviour, covering cognition, emotion, motivation, personality, social interaction, and mental health.",
    "Physiology": "Physiology studies the normal functions of living organisms and their parts how cells, tissues, organs, and systems work and are regulated.",
    "Statistics": "Statistics is the science of collecting, analyzing, interpreting, and presenting data. It provides the mathematical foundation for inference, estimation, and hypothesis testing.",
    "Complexity Science": "Complexity science studies systems with many interacting components that exhibit emergent behaviour, self-organization, and non-linear dynamics.",
    "Philosophy": "Philosophy examines fundamental questions about existence, knowledge, values, reason, mind, and language through rational argument and critical analysis.",
    "Cell Biology": "Cell biology studies the structure, function, and behavior of cells the fundamental units of life.",
    "Economics": "Economics studies the production, distribution, and consumption of goods and services, analyzing how individuals, firms, and societies allocate scarce resources.",
    "AI / Systems Engineering": "AI Systems Engineering is the discipline of designing, building, and operating autonomous AI systems: agent architectures, guardrails, evaluation, and monitoring.",
    "Meta": "Meta concepts describe the structure, methodology, and navigation of the vault itself including knowledge management frameworks, organization systems, and workflow patterns.",
    "Health": "Health encompasses physical, mental, and social well-being, along with the medical and public health systems that maintain or restore it.",
    "Longevity": "Longevity science studies the biological mechanisms of aging and interventions to extend healthy lifespan from caloric restriction to senolytics to epigenetic reprogramming.",
    "Genomics": "Genomics is the study of whole genomes their structure, function, evolution, and mapping using high-throughput sequencing and computational analysis.",
    "Immunology": "Immunology studies the immune system: how it defends against pathogens, distinguishes self from non-self, and can malfunction in autoimmune disease.",
    "Sleep / Neuroscience": "Sleep neuroscience studies sleep as a neurobiological phenomenon its regulation by circadian and homeostatic processes, its architecture, and its functions.",
    "Research Methods": "Research methods are the systematic frameworks, study designs, and analytical approaches used to conduct valid and reproducible scientific research.",
    "Productivity": "Productivity studies how to maximize output per unit of input through time management, focus, habit formation, and workflow optimisation.",
    "Control Theory": "Control theory studies how to make dynamic systems behave in desired ways using feedback or feedforward control from thermostats to autonomous vehicles.",
}


def parse_frontmatter(content):
    """Return (frontmatter_dict, body, raw_frontmatter_str)."""
    fm = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not fm:
        return {}, content, ""
    result = {}
    for line in fm.group(1).strip().split("\n"):
        if ": " in line:
            key, val = line.split(": ", 1)
            result[key.strip()] = val.strip()
    body = content[fm.end():].strip()
    return result, body, fm.group(0)

stats = {"patched": 0, "stubs_filled": 0, "errors": 0, "new_domains": {}}

for title, domain in assignments.items():
    fpath = os.path.join(CONCEPTS_DIR, title + ".md")
    if not os.path.isfile(fpath):
        for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
            bare = os.path.splitext(os.path.basename(f))[0]
            if bare.lower() == title.lower():
                fpath = f
                break
        if not os.path.isfile(fpath):
            stats["errors"] += 1
            continue

    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except:
        stats["errors"] += 1
        continue

    fm, body, raw_fm = parse_frontmatter(content)
    current_domain = fm.get("domain", "")

    if current_domain in ("General", "Uncategorised", "", "General / Uncategorised"):
        # Patch frontmatter
        new_fm = raw_fm
        if "domain:" in raw_fm:
            new_fm = re.sub(r"^domain:.*$", f"domain: {domain}", raw_fm, flags=re.MULTILINE)
        else:
            lines = raw_fm.split("\n")
            inserted = False
            for i, line in enumerate(lines):
                if line.startswith("tags:") and not inserted:
                    lines.insert(i, f"domain: {domain}")
                    inserted = True
                    break
            if not inserted:
                lines.insert(-1, f"domain: {domain}")
            new_fm = "\n".join(lines)

        new_content = content.replace(raw_fm, new_fm)

        # Check if it's a stub (status stub or very short)
        status = fm.get("status", "")
        lines_count = len(content.splitlines())

        if status in ("stub", "seedling") and lines_count < 25 and domain in STUBS and domain != "Meta":
            # Create minimal content
            header_end = new_content.find("# ", 4)
            if header_end >= 0:
                newline_end = new_content.find("\n", header_end)
                if newline_end >= 0:
                    new_body_start = newline_end + 1
                else:
                    new_body_start = header_end + 2
            else:
                # Find second ---
                count = 0
                pos = 0
                while count < 2:
                    pos = new_content.find("---", pos)
                    if pos < 0:
                        break
                    count += 1
                    pos += 3
                new_body_start = pos if count >= 2 else len(new_content)

            stub_text = f"""\n\n## Core Definition\n\n{STUBS[domain]}\n\n## Key Aspects\n\nThis concept belongs to the **{domain}** domain. It was categorised during a vault-wide sweep of previously unassigned concepts.\n\n## Related Concepts\n- Links to be expanded during vault development.\n"""
            new_content = new_content[:new_body_start] + stub_text
            stats["stubs_filled"] += 1

        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write(new_content)

        stats["patched"] += 1
        stats["new_domains"][domain] = stats["new_domains"].get(domain, 0) + 1

print(f"\nResults:")
print(f"  Patched (domain assigned): {stats['patched']}")
print(f"  Stubs filled with content: {stats['stubs_filled']}")
print(f"  Errors:                     {stats['errors']}")
print(f"\nDomain distribution of newly assigned:")
for d, c in sorted(stats["new_domains"].items(), key=lambda x: -x[1]):
    print(f"  {d:40s} {c:3d}")
