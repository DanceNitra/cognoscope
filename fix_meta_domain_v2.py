#!/usr/bin/env python3
"""
fix_meta_domain_v2.py — Phase A: Meta Domain Cleanup v2

Smart cleanup:
1. Delete: stubs (<40 lines, 0 links, status stub/redirect) — pure junk
2. Classify: real content (>40 lines or with content) into proper domains
3. Keep: True Meta (vault architecture, tools, quality)
"""

import os, re, glob, sys, shutil
from collections import defaultdict

VAULT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS = os.path.join(VAULT, "04 Resources/Concepts")
BACKUP = os.path.join(VAULT, "05 Archives/Meta Cleanup 2026-05-27")

DRY_RUN = "--dry-run" in sys.argv or "-n" in sys.argv

os.makedirs(BACKUP, exist_ok=True)


def parse_frontmatter(content: str) -> dict:
    fm = {}
    m = re.search(r'^---\n(.+?)\n---', content, re.DOTALL)
    if m:
        for line in m.group(1).split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                fm[k.strip()] = v.strip().strip('"\'')
    return fm


def classify_real(name: str, title: str, content: str, lines: int, links: int) -> str | None:
    """Classify a real concept. Returns domain or None for True Meta."""
    nl = name.lower()
    tl = title.lower()
    combined = nl + " " + tl
    content_lower = content.lower()
    
    # ── True Meta — vault infrastructure ──
    true_meta_patterns = [
        "moc", "second brain", "knowledge management", "zettelkasten",
        "digital garden", "para", "information architecture", "evergreen",
        "note taking", "spaced repetition", "obsidian", "vault evolution",
        "publications moc", "index", "log.md", "template", "convention",
        "taxonomy", "classification", "three-layer", "workflow",
        "vault 2.0", "recursive layered", "meta", "maps of content",
        "progressive summarization", "wikilinks", "links", "note-taking",
        "digital twin", "learning", "disaster recovery", "agents.md"
    ]
    for p in true_meta_patterns:
        if p in combined:
            return "True Meta"
    
    # ── Domain classification ──
    
    if any(kw in combined for kw in [
        "ai ", "artificial intelligence", "deep learning", "machine learning",
        "llm", "transformer", "neural network", "reinforcement learning",
        "deepseek", "inference optimization", "prompt engineering",
        "rag", "agentic", "vector database", "quantization",
        "fine-tuning", "training", "model context protocol", "mcp",
        "attention mechanism", "token", "embedding"
    ]):
        return "AI"
    
    if any(kw in combined for kw in [
        "finance", "trading", "position sizing", "regime detection",
        "portfolio", "market", "stock", "option", "volatility",
        "risk management", "drawdown", "sharpe", "kelly",
        "backtest", "crypto", "bitcoin", "solana"
    ]):
        return "Finance"
    
    if any(kw in combined for kw in [
        "neuroscience", "brain", "neuron", "synapse", "cortex",
        "prefrontal", "amygdala", "hippocampus", "dopamine",
        "serotonin", "neurotransmitter", "neuroplasticity",
        "sleep", "circadian", "chronobiology", "glymphatic",
        "memory consolidation", "predictive processing",
        "free energy", "active inference", "bayesian brain"
    ]):
        return "Neuroscience"
    
    if any(kw in combined for kw in [
        "psychology", "cognitive", "behavioral", "emotion",
        "decision fatigue", "loss aversion", "prospect theory",
        "anchoring", "mental model", "cognitive bias",
        "heuristic", "adhd", "depression", "anxiety",
        "stress", "rumination", "personality"
    ]):
        return "Psychology"
    
    if any(kw in combined for kw in [
        "software", "engineering", "architecture", "microservice",
        "api", "database", "testing", "deployment", "devops",
        "kubernetes", "docker", "container", "protocol",
        "typescript", "javascript", "python", "algorithm",
        "cybersecurity", "terminal", "cron", "automation",
        "actor model", "concurrency", "auto ml", "automl"
    ]):
        return "Software Engineering"
    
    if any(kw in combined for kw in [
        "cell biology", "mitochondria", "autophagy", "apoptosis",
        "proteostasis", "stem cell", "senescence", "senolytics",
        "epigenetics", "methylation", "histone", "ampk",
        "cerebrospinal", "brown adipose", "interstitial fluid"
    ]):
        return "Cell Biology"
    
    if any(kw in combined for kw in [
        "health", "longevity", "medicine", "disease", "diagnosis",
        "clinical", "pharmacology", "nutrition", "diet", "exercise",
        "inflammation", "immune", "aging", "yamanaka",
        "multiple sclerosis"
    ]):
        return "Health & Longevity"
    
    if any(kw in combined for kw in [
        "statistics", "bayesian", "frequentist", "hypothesis",
        "p-value", "regression", "correlation", "causal inference",
        "measurement", "reliability", "validity"
    ]):
        return "Statistics"
    
    if any(kw in combined for kw in [
        "complexity", "emergence", "self-organization",
        "phase transition", "dynamical system", "attractor",
        "bifurcation", "chaos", "network science",
        "agriculture", "climate", "energy sustainability"
    ]):
        return "Complexity Science"
    
    if any(kw in combined for kw in [
        "mathematics", "category theory", "topology", "algebra",
        "calculus", "probability", "formal foundations",
        "lambda calculus", "type theory"
    ]):
        return "Formal Foundations"
    
    if any(kw in combined for kw in [
        "philosophy", "epistemology", "ontology", "metaphysics",
        "consciousness", "geopolitics", "global governance",
        "energy sustainability", "communication",
        "addictive loop", "addiction"
    ]):
        return "Philosophy / Social Sciences"
    
    if any(kw in combined for kw in [
        "research methods", "methodology", "research", "discovery pipeline"
    ]):
        return "Research Methods"
    
    return None  # Unknown — keep in Meta for manual review


def should_delete(name: str, title: str, lines: int, status: str, links: int, content: str) -> bool:
    """Check if this is pure junk that should be deleted."""
    nl = name.lower()
    tl = title.lower()
    
    # Auto-generated stubs that match the pattern
    is_auto_stub = status in ('stub', 'redirect') and lines <= 35
    
    # Bridge stubs with no real content (auto-generated)
    if name.startswith("Bridge") and is_auto_stub and links <= 1:
        return True
    
    # Auto-generated ARI stubs
    if name.startswith("ARI") and is_auto_stub:
        return True
    
    # Section stubs (auto-generated §N fragments)
    if '§' in name and is_auto_stub:
        return True
    
    # Coordinates/sizes (auto-generated excalidraw or code stubs)
    coord_patterns = [r'^\d+,\s*\d+$', r'^\d+$', r'^".+"$', r"^'.+'$"]
    for pat in coord_patterns:
        if re.match(pat, name):
            return True
    
    # Auto-generated synthesis/plan stubs (date-based or machine-generated)
    date_patterns = [
        r'^\d{4}-\d{2}-\d{2}$',           # 2026-05-06
        r'^PUB-\w+',                       # PUB-MCPMQ1
        r'^.*Deep Research Synthesis',     # auto-generated synthesis
        r'^autonomous.*report',            # auto-generated report
        r'^autonomous.*roadmap',           # auto-generated
        r'^.*synthesis.*2026',             # auto-generated
        r'^2026.*strategic.*intelligence', # auto-generated
    ]
    for pat in date_patterns:
        if re.search(pat, nl):
            return True
    
    # Excalidraw diagrams
    if name.endswith('.excalidraw') and is_auto_stub:
        return True
    
    # MOC redirects / empty MOCs
    if (name.endswith('MOC') or ' MOC' in name) and is_auto_stub and links <= 1:
        return True
    
    # AGENTS redirect
    if name == 'AGENTS' and is_auto_stub:
        return True
    
    # Auto-generated template stubs with boilerplate "Auto-generated stub"
    if 'Auto-generated stub' in content and is_auto_stub:
        return True
    
    return False


def main():
    print(f"  ╔══════════════════════════════════════╗")
    print(f"  ║   META DOMAIN CLEANUP v2 — Phase A   ║")
    print(f"  ╚══════════════════════════════════════╝")
    print()
    if DRY_RUN:
        print("  [DRY RUN MODE — no changes will be made]")
    print()
    
    # Scan
    all_meta = []
    for f in sorted(glob.glob(os.path.join(CONCEPTS, "*.md"))):
        with open(f, encoding='utf-8') as fh:
            content = fh.read()
        if not re.search(r'^domain:\s*Meta\b', content, re.MULTILINE):
            continue
        
        name = os.path.basename(f).replace('.md', '')
        lines = len(content.splitlines())
        fm = parse_frontmatter(content)
        title = fm.get('title', name)
        status = fm.get('status', 'unknown')
        links = len(re.findall(r'\[\[.+?\]\]', content))
        
        all_meta.append((name, title, lines, status, links, f, content))
    
    print(f"  Found {len(all_meta)} concepts with domain: Meta")
    print()
    
    # Classify
    to_delete = []      # Junk stubs
    to_classify = []    # Real concepts to reclassify
    true_meta = []      # Keep as True Meta
    unknown = []        # Need manual review
    
    for name, title, lines, status, links, filepath, content in all_meta:
        # Delete criteria: auto-generated junk
        if should_delete(name, title, lines, status, links, content):
            to_delete.append((name, title, lines, status, links, filepath))
            continue
        
        # Try to classify
        domain = classify_real(name, title, content, lines, links)
        if domain == "True Meta":
            true_meta.append((name, title, lines, status, links, filepath))
        elif domain:
            to_classify.append((name, title, lines, status, links, filepath, domain))
        else:
            unknown.append((name, title, lines, status, links, filepath))
    
    # Report
    print(f"  === TO DELETE (junk stubs) === ")
    print(f"  {len(to_delete)} files")
    for name, title, lines, status, links, fp in to_delete[:20]:
        print(f"  - {name[:45]:45s} | {status:10s} | {lines:3d}L | {links} links")
    if len(to_delete) > 20:
        print(f"  ... and {len(to_delete)-20} more")
    print()
    
    print(f"  === TO CLASSIFY === ")
    by_domain = defaultdict(list)
    for name, title, lines, status, links, fp, domain in to_classify:
        by_domain[domain].append((name, title, lines, status, links, fp))
    for domain, items in sorted(by_domain.items(), key=lambda x: -len(x[1])):
        print(f"  {domain}: {len(items)} files")
        for name, title, lines, status, links, fp in items:
            print(f"    {name[:50]:50s} | {lines:3d}L | {status:10s} | {links} links")
    print()
    
    print(f"  === TRUE META (keeping) === ")
    print(f"  {len(true_meta)} files")
    for name, title, lines, status, links, fp in sorted(true_meta, key=lambda x: -x[2])[:15]:
        print(f"  {name[:50]:50s} | {lines:3d}L | {status:10s} | {links} links")
    if len(true_meta) > 15:
        print(f"  ... and {len(true_meta)-15} more")
    print()
    
    print(f"  === UNKNOWN (needs manual review) === ")
    print(f"  {len(unknown)} files")
    for name, title, lines, status, links, fp in unknown[:15]:
        print(f"  {name[:50]:50s} | {title[:40]:40s} | {lines:3d}L | {status:10s} | {links} links")
    if len(unknown) > 15:
        print(f"  ... and {len(unknown)-15} more")
    print()
    
    # ── Apply changes ──
    if not DRY_RUN:
        # Delete junk stubs
        for name, title, lines, status, links, filepath in to_delete:
            shutil.move(filepath, os.path.join(BACKUP, os.path.basename(filepath)))
        
        # Reclassify real concepts
        classified_count = 0
        for name, title, lines, status, links, filepath, domain in to_classify:
            with open(filepath, encoding='utf-8') as f:
                content = f.read()
            new_content = re.sub(
                r'^(domain:\s*)Meta\b',
                f'\\1{domain}',
                content,
                count=1,
                flags=re.MULTILINE
            )
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                classified_count += 1
        
        # Update True Meta domain to differentiate
        for name, title, lines, status, links, filepath in true_meta:
            with open(filepath, encoding='utf-8') as f:
                content = f.read()
            new_content = re.sub(
                r'^(domain:\s*)Meta\b',
                f'\\1True Meta',
                content,
                count=1
            )
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
        
        print(f"  === APPLIED ===")
        print(f"  Deleted: {len(to_delete)} (moved to Archives/Meta Cleanup)")
        print(f"  Classified: {classified_count}")
        print(f"  True Meta: {len(true_meta)} (domain: True Meta)")
        print(f"  Remaining unknown: {len(unknown)} (stayed as Meta for review)")
    else:
        print(f"  === WOULD APPLY ===")
        print(f"  Delete: {len(to_delete)} (move to archives)")
        print(f"  Classify: {len(to_classify)} (update domain)")
        print(f"  True Meta: {len(true_meta)} (domain: True Meta)")
        print(f"  Manual review: {len(unknown)}")


if __name__ == "__main__":
    main()
