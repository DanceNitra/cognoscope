#!/usr/bin/env python3
"""
fix_meta_domain.py — Phase A: Meta Domain Cleanup

Reklasifikuje 319 konceptov v Meta doméne do správnych domén.
Rules-based classifier podľa názvu, obsahu a cesty.
"""

import os, re, glob, sys
from collections import defaultdict

VAULT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS = os.path.join(VAULT, "04 Resources/Concepts")
PUBS = os.path.join(VAULT, "04 Resources/Publications")
META_90 = os.path.join(VAULT, "90 Meta")
PROJECTS = os.path.join(VAULT, "02 Projects")
SESSIONS = os.path.join(VAULT, "04 Sessions")
RESEARCH = os.path.join(VAULT, "04 Resources/Research")
ARI_DIR = os.path.join(VAULT, "04 Resources/ARI")
ANALYSIS = os.path.join(VAULT, "04 Resources/Analysis")

DRY_RUN = "--dry-run" in sys.argv or "-n" in sys.argv

# ── Classification rules ──

def classify_by_name(name: str, content: str, filepath: str) -> str | None:
    """Return proper domain or None if should stay Meta."""
    nl = name.lower()
    
    # Path-based: files that should NOT be in Concepts/
    rel = os.path.relpath(filepath, VAULT)
    if rel.startswith("04 Resources/Publications"):
        return None  # These are bridges, not concepts — stay as-is
    if rel.startswith("04 Resources/ARI") or rel.startswith("04 Resources/Analysis"):
        return None  # ARI outputs — stay
    
    # Bridge notes in Concepts/ (auto-generated redirects)
    if name.startswith("Bridge"):
        return None
    
    # Session handoffs
    if "session" in nl and ("handoff" in nl or "2026" in nl):
        return "Meta - Sessions"
    
    # Vault architecture — TRUE Meta
    true_meta_keywords = [
        "agents.md", "vault", "index.md", "moc", "second brain",
        "knowledge management", "zettelkasten", "digital garden",
        "para method", "information architecture", "evergreen",
        "note taking", "spaced repetition", "obsidian",
        "agenda", "lint", "health check", "log.md",
        "template", "convention", "taxonomy", "classification",
        "three-layer", "p.a.r.a", "workflow"
    ]
    for kw in true_meta_keywords:
        if kw in nl:
            return "True Meta"
    
    # Agent architecture — True Meta
    agent_keywords = [
        "archivist", "researcher", "synthesizer", "reviewer",
        "swarm orchestrator", "agent memory", "agent architecture",
        "autonomous agent", "agent factory", "agent skill",
        "agent testing", "agent development", "agent safety"
    ]
    for kw in agent_keywords:
        if kw in nl:
            return "True Meta"
    
    # AI / ML concepts wrongly classified as Meta
    ai_keywords = [
        "ai agent", "artificial intelligence", "deep learning",
        "machine learning", "llm", "transformer", "neural network",
        "reinforcement learning", "deepseek", "claude", "hermes",
        "token", "embedding", "attention mechanism", "mcp",
        "model context protocol", "inference optimization",
        "prompt engineering", "rag", "retrieval augmented",
        "agentic", "vector database", "quantization",
        "fine-tuning", "lora", "training", "inference"
    ]
    for kw in ai_keywords:
        if kw in nl:
            return "AI"
    
    # Finance/Trading
    finance_keywords = [
        "finance", "trading", "position sizing", "regime detection",
        "portfolio", "market", "stock", "spy", "option",
        "volatility", "risk management", "drawdown",
        "sharpe", "kelly", "backtest", "signal",
        "crypto", "bitcoin", "blockchain"
    ]
    for kw in finance_keywords:
        if kw in nl:
            return "Finance"
    
    # Neuroscience
    neuro_keywords = [
        "neuroscience", "brain", "neuron", "synapse", "cortex",
        "prefrontal", "amygdala", "hippocampus", "striatum",
        "dopamine", "serotonin", "norepinephrine", "acetylcholine",
        "gaba", "glutamate", "neurotransmitter", "neuroplasticity",
        "sleep", "circadian", "chronobiology", "glymphatic",
        "memory consolidation", "ltp", "ltd", "stdp",
        "predictive processing", "free energy", "active inference",
        "bayesian brain", "precision weighting"
    ]
    for kw in neuro_keywords:
        if kw in nl:
            return "Neuroscience"
    
    # Psychology
    psych_keywords = [
        "psychology", "cognitive", "behavioral", "emotion",
        "decision fatigue", "loss aversion", "prospect theory",
        "anchoring", "mental model", "cognitive bias",
        "heuristic", "thinking fast", "system 1", "system 2",
        "ego depletion", "rumination", "adhd", "depression",
        "anxiety", "stress", "trauma", "personality"
    ]
    for kw in psych_keywords:
        if kw in nl:
            return "Psychology"
    
    # Cell Biology
    cell_keywords = [
        "cell biology", "mitochondria", "autophagy", "apoptosis",
        "proteostasis", "dna repair", "stem cell", "senescence",
        "senolytics", "membrane", "organelle", "nucleus",
        "epigenetics", "methylation", "histone"
    ]
    for kw in cell_keywords:
        if kw in nl:
            return "Cell Biology"
    
    # Health / Longevity / Medicine
    health_keywords = [
        "health", "longevity", "medicine", "disease", "diagnosis",
        "clinical", "patient", "therapy", "drug", "pharmacology",
        "nutrition", "diet", "exercise", "inflammation",
        "immune", "vaccine", "aging", "yamanaka"
    ]
    for kw in health_keywords:
        if kw in nl:
            return "Health & Longevity"
    
    # Statistics
    stats_keywords = [
        "statistics", "bayesian", "frequentist", "hypothesis test",
        "p-value", "regression", "correlation", "causal inference",
        "potential outcome", "do-calculus", "confounding",
        "measurement", "reliability", "validity"
    ]
    for kw in stats_keywords:
        if kw in nl:
            return "Statistics"
    
    # Complexity / Systems
    complex_keywords = [
        "complexity", "emergence", "self-organization", "phase transition",
        "dynamical system", "attractor", "bifurcation", "chaos",
        "network science", "scale-free", "power law"
    ]
    for kw in complex_keywords:
        if kw in nl:
            return "Complexity Science"
    
    # Software Engineering
    se_keywords = [
        "software", "engineering", "architecture", "microservice",
        "api", "database", "testing", "deployment", "devops",
        "kubernetes", "docker", "container", "ci/cd",
        "monolith", "distributed", "protocol", "typescript",
        "javascript", "python", "git", "algorithm"
    ]
    for kw in se_keywords:
        if kw in nl:
            return "Software Engineering"
    
    # Mathematics / Formal
    math_keywords = [
        "mathematics", "category theory", "topology", "algebra",
        "calculus", "probability", "formal foundations",
        "lambda calculus", "type theory", "set theory"
    ]
    for kw in math_keywords:
        if kw in nl:
            return "Formal Foundations"
    
    # Philosophy
    phil_keywords = [
        "philosophy", "epistemology", "ontology", "metaphysics",
        "phenomenology", "consciousness", "qualia"
    ]
    for kw in phil_keywords:
        if kw in nl:
            return "Philosophy"
    
    return None  # Stay Meta


def update_domain_in_file(filepath: str, new_domain: str) -> bool:
    """Update domain in frontmatter. Returns True if changed."""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    
    # Check current domain
    m = re.search(r'^domain:\s*Meta', content, re.MULTILINE)
    if not m:
        return False  # Not Meta, skip
    
    # Replace domain: Meta with domain: NewDomain
    new_content = re.sub(
        r'^(domain:\s*)Meta\b',
        f'\\1{new_domain}',
        content,
        count=1
    )
    
    if new_content == content:
        return False
    
    if not DRY_RUN:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
    return True


def main():
    print(f"  ╔══════════════════════════════════════╗")
    print(f"  ║   META DOMAIN CLEANUP — Phase A      ║")
    print(f"  ╚══════════════════════════════════════╝")
    print()
    if DRY_RUN:
        print("  [DRY RUN MODE — no changes will be made]")
    print()
    
    # Scan all concept files
    all_concepts = []
    for f in glob.glob(os.path.join(CONCEPTS, "*.md")):
        with open(f, encoding='utf-8') as fh:
            content = fh.read()
        name = os.path.basename(f).replace('.md', '')
        
        # Check if Meta domain
        if not re.search(r'^domain:\s*Meta\b', content, re.MULTILINE):
            continue
        
        all_concepts.append((name, f, content))
    
    print(f"  Found {len(all_concepts)} concepts with domain: Meta")
    print()
    
    # Classify
    classified = defaultdict(list)
    unclassified = []
    true_meta = []
    
    for name, filepath, content in all_concepts:
        domain = classify_by_name(name, content, filepath)
        if domain is None or domain == "True Meta":
            if domain == "True Meta":
                true_meta.append((name, filepath))
            else:
                unclassified.append((name, filepath))
        else:
            classified[domain].append((name, filepath))
    
    print("  === CLASSIFIED === ")
    for domain, items in sorted(classified.items(), key=lambda x: -len(x[1])):
        print(f"  {domain}: {len(items)} concepts")
    print(f"\n  === TRUE META (staying) === ")
    print(f"  {len(true_meta)} concepts")
    print(f"\n  === UNCLASSIFIED (need manual review) === ")
    print(f"  {len(unclassified)} concepts")
    for name, fp in unclassified[:20]:
        print(f"  - {name}")
    if len(unclassified) > 20:
        print(f"  ... and {len(unclassified)-20} more")
    print()
    
    # Apply changes
    if not DRY_RUN:
        total_changed = 0
        for domain, items in classified.items():
            for name, filepath in items:
                if update_domain_in_file(filepath, domain):
                    total_changed += 1
        print(f"  Applied changes to {total_changed} files.")
    else:
        total = sum(len(items) for items in classified.values())
        print(f"  Would change {total} files ({total} classified + 0 unclassified).")


if __name__ == "__main__":
    main()
