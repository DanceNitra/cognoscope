#!/usr/bin/env python3
"""
domain_assigner.py — Batch-categorize all uncategorised vault concepts.

Reads every concept .md, classifies by keyword/tags/links, patches frontmatter,
fills stub concepts with minimal evergreen content.
"""
import os, re, sys, glob, time
from collections import defaultdict, Counter

VAULT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT, "04 Resources/Concepts")

# ── Domain Keyword Signatures ──
# Each domain has: keyword patterns, tag patterns, link-to patterns
DOMAIN_SIGNATURES = {
    "AI": {
        "kw": ["artificial intelligence", "llm", "large language model", "foundation model", 
               "transformer", "gpt", "neural network", "deep learning", "machine learning",
               "attention mechanism", "token", "embedding", "multimodal", "nlp",
               "natural language", "computer vision", "object detection", "segmentation",
               "reinforcement learning", "diffusion model", "generative", "rag",
               "retrieval augmented", "fine-tuning", "pretraining", "self-supervised",
               "contrastive learning", "backpropagation", "gradient descent", "loss function",
               "activation function", "convolutional", "recurrent", "lstm", "rnn",
               "cnn", "transformer architecture", "clip", "sam", "yolo", "unet",
               "faster r-cnn", "detr", "sora", "alphafold", "autonomous vehicle",
               "robotics", "slam", "lidar", "sensor fusion", "speech recognition",
               "autonomous systems", "embodied ai", "ai safety", "alignment",
               "constitutional ai", "rlhf", "chain-of-thought", "reasoning",
               "world model", "agent", "tool calling", "multi-agent", "swarm intelligence",
               "autonomous agent", "recursive self-improvement", "rsi"],
        "tags": ["ai", "machine-learning", "deep-learning"],
        "link_to": ["AI", "Machine Learning", "Deep Learning"],
    },
    "AI / Systems Engineering": {
        "kw": ["agent architecture", "agent development", "agent workflow", "agent evaluation",
               "agent memory", "agent observability", "agent safety", "agent guardrail",
               "agent testing", "agent tool", "tool calling", "toolforge", "hermes agent",
               "agent skill", "agent deployment", "agent monitoring", "guardrail",
               "nine-layer", "agentic system", "agent pipeline", "recovery engine",
               "react pattern", "agent loop", "action selection", "memory hierarchy for agent"],
        "tags": ["agents", "guardrails"],
        "link_to": ["Hermes Agent", "Agent Architecture Patterns", "Agent Safety & Guardrails"],
    },
    "Causal Inference": {
        "kw": ["causal inference", "causal discovery", "causal forest", "causal",
               "backdoor criterion", "frontdoor criterion", "do-calculus", "sutva",
               "instrumental variable", "counterfactual", "potential outcome",
               "directed acyclic graph", "dag", "confounding", "collider", "mediation",
               "mendelian randomization", "treatment effect", "ate", "att", "cate",
               "propensity score", "matching", "difference-in-differences",
               "regression discontinuity", "simpson", "selection bias", "positivity",
               "identification", "d-separation", "pearl", "structural equation"],
        "tags": ["causality", "causal-inference"],
        "link_to": ["Causal Inference", "Causal Discovery", "Causal Reasoning", "Backdoor Criterion"],
    },
    "Statistics": {
        "kw": ["statistics", "probability", "bayesian inference", "bayes", "bootstrap",
               "hypothesis test", "p-value", "confidence interval", "anova", "regression",
               "logistic regression", "linear regression", "correlation", "covariance",
               "standard deviation", "variance", "distribution", "normal distribution",
               "markov chain monte carlo", "mcmc", "bayesian network", "markov random field",
               "random variable", "expectation", "likelihood", "maximum likelihood",
               "prior", "posterior", "statistical power", "effect size", "sample size",
               "contingency table", "chi-square", "t-test", "nonparametric",
               "survival analysis", "cox model", "kaplan-meier", "hazard"],
        "tags": ["statistics", "bayesian"],
        "link_to": ["Statistics", "Bayesian Inference", "Hypothesis Testing"],
    },
    "Finance": {
        "kw": ["finance", "trading", "stock", "market", "portfolio", "option", "future",
               "swap", "derivative", "fixed income", "bond", "credit", "yield", "spread",
               "asset", "equity", "commodity", "currency", "fx", "volatility", "risk",
               "sharpe", "sortino", "drawdown", "alpha", "beta", "factor", "momentum",
               "mean reversion", "arbitrage", "hedging", "liquidity", "order book",
               "market microstructure", "backtest", "execution", "tca", "vwap",
               "implementation shortfall", "market making", "market impact",
               "behavioral finance", "disposition effect", "herding", "anomaly detection",
               "crypto", "blockchain", "defi", "bitcoin", "ethereum", "smart contract",
               "treasury", "inflation", "macro", "carry", "cross-asset",
               "algorithmic trading", "high-frequency", "hft", "regime detection",
               "cointegrated", "pair trade", "risk parity", "capital market"],
        "tags": ["finance"],
        "link_to": ["Finance", "Algorithmic Trading", "Backtesting Methodology"],
    },
    "Neuroscience": {
        "kw": ["neuroscience", "brain", "neuron", "synapse", "neurotransmitter",
               "acetylcholine", "dopamine", "serotonin", "gaba", "glutamate",
               "noradrenaline", "adrenaline", "cortisol", "hippocampus", "amygdala",
               "prefrontal cortex", "pfc", "thalamus", "hypothalamus", "cerebellum",
               "brain stem", "cortex", "neural", "neuroplasticity", "synaptic plasticity",
               "ltp", "long-term potentiation", "glia", "astrocytes", "microglia",
               "oligodendrocyte", "myelin", "axon", "dendrite", "action potential",
               "membrane potential", "neurogenesis", "brain-derived", "bdnf",
               "alzheimer", "parkinson", "neurodegenerative", "epilepsy", "seizure",
               "traumatic brain injury", "concussion", "cte", "blood-brain barrier",
               "neuroimaging", "fmri", "eeg", "meg", "consciousness", "cognition",
               "cognitive function", "memory", "working memory", "long-term memory",
               "declarative memory", "procedural memory", "emotional memory",
               "neurobiology", "neuropharmacology"],
        "tags": ["neuroscience", "neurobiology"],
        "link_to": ["Neuroscience", "Hippocampus", "Neuroplasticity"],
    },
    "Psychology": {
        "kw": ["psychology", "cognitive", "behavioral", "mental", "emotion", "anxiety",
               "depression", "addiction", "stress", "trauma", "ptsd", "ocd", "adhd",
               "autism", "personality", "motivation", "decision making", "judgment",
               "heuristic", "bias", "cognitive bias", "attention", "memory",
               "learning", "expertise", "deliberate practice", "flow", "mindfulness",
               "grit", "resilience", "self-regulation", "emotion regulation",
               "dual process", "system 1", "system 2", "cognitive load",
               "chunking", "mental model", "belief", "attitude", "social",
               "interpersonal", "group", "leadership", "communication",
               "cognitive psychology", "behavioral economics", "nudge",
               "attention residue", "cognitive dissonance"],
        "tags": ["psychology"],
        "link_to": ["Cognitive Psychology", "Decision Making", "Cognitive Bias"],
    },
    "Sleep / Neuroscience": {
        "kw": ["sleep", "circadian", "chronotype", "melatonin", "adenosine", "insomnia",
               "sleep apnea", "narcolepsy", "nrem", "rem", "slow wave", "sleep spindle",
               "glymphatic", "cbt-i", "sleep hygiene", "light therapy", "chronotherapy",
               "social jetlag", "shift work", "delayed sleep phase", "jet lag",
               "clock gene", "per3", "suprachiasmatic", "scn", "entrainment",
               "sleep deprivation", "sleep architecture", "memory consolidation",
               "sleep pressure", "homeostatic sleep", "blue light",
               "seasonal affective", "sad", "circadian disruption"],
        "tags": ["sleep", "chronobiology", "sleep-science"],
        "link_to": ["Sleep", "Circadian Rhythm", "Glymphatic System"],
    },
    "Physiology": {
        "kw": ["physiology", "homeostasis", "allostasis", "hpa axis", "autonomic",
               "sympathetic", "parasympathetic", "blood pressure", "heart rate",
               "heart rate variability", "hrv", "stress response", "cortisol",
               "adrenal", "thyroid", "endocrine", "hormone", "metabolism",
               "metabolic", "glucose", "insulin", "pancreas", "kidney", "renal",
               "liver", "hepatic", "digestion", "gut", "microbiome", "appetite",
               "ghrelin", "leptin", "thermoregulation", "core body temperature",
               "fever", "inflammation", "immune", "exercise", "fitness",
               "cardio", "cardiovascular", "pulmonary", "respiratory",
               "muscle", "skeletal", "bone", "joint", "aging", "longevity",
               "oxidative stress", "mitochondrial", "autophagy", "senescence",
               "caloric restriction", "nutrition", "diet", "micronutrient",
               "macronutrient", "vitamin", "mineral", "electrolyte", "fluid balance",
               "acid-base", "ph", "blood", "oxygen", "carbon dioxide"],
        "tags": ["physiology", "endocrine"],
        "link_to": ["Physiology", "Homeostasis", "Allostatic Load"],
    },
    "Software Engineering": {
        "kw": ["software engineering", "programming", "code", "api", "rest", "grpc",
               "microservices", "monolith", "architecture", "design pattern", "solid",
               "clean architecture", "hexagonal", "domain-driven", "ddd", "tdd",
               "test-driven", "ci/cd", "continuous integration", "continuous deployment",
               "devops", "docker", "kubernetes", "container", "orchestration",
               "terraform", "infrastructure as code", "cloud computing", "aws", "azure",
               "gcp", "serverless", "lambda", "function", "database", "sql", "nosql",
               "cache", "redis", "message queue", "kafka", "event-driven", "caching",
               "load balancing", "proxy", "gateway", "version control", "git",
               "github", "monorepo", "functional programming", "object-oriented",
               "oop", "immutable", "immutability", "concurrency", "parallel",
               "distributed system", "consensus", "cap theorem", "cohesion",
               "coupling", "refactoring", "dependency injection", "inversion of control",
               "python", "javascript", "typescript", "rust", "go", "c++", "java",
               "linux", "unix", "bash", "shell", "scripting", "debugging",
               "monitoring", "observability", "logging", "tracing", "metrics",
               "scalability", "performance", "optimization", "testing",
               "unit test", "integration test", "e2e", "end-to-end"],
        "tags": ["software-engineering", "architecture"],
        "link_to": ["Software Engineering", "Clean Architecture", "Functional Programming"],
    },
    "Meta": {
        "kw": ["moc", "map of content", "index", "template", "gateway", "note taking",
               "zettelkasten", "second brain", "personal knowledge", "pkm",
               "knowledge management", "information architecture", "digital garden",
               "evergreen note", "fleeting note", "progressive summarization",
               "para method", "p.a.r.a", "spaced repetition", "knowledge graph",
               "ontology", "taxonomy", "vault", "obsidian", "workflow",
               "productivity", "system", "dashboard", "log", "handoff",
               "restart", "session", "migration", "backup", "disaster recovery"],
        "tags": ["meta", "system"],
        "link_to": ["MOC", "Zettelkasten", "Index"],
    },
    "Complexity Science": {
        "kw": ["complexity", "complex system", "emergence", "self-organization",
               "network science", "graph theory", "tipping point", "phase transition",
               "feedback loop", "nonlinear", "dynamical system", "chaos",
               "butterfly effect", "power law", "scale-free", "small world",
               "agent-based", "simulation", "cybernetics", "second-order cybernetics",
               "systems thinking", "information theory", "entropy"],
        "tags": ["complexity", "emergence", "systems-thinking"],
        "link_to": ["Complexity Science", "Emergence", "Cybernetics"],
    },
    "Philosophy": {
        "kw": ["philosophy", "epistemology", "ontology", "metaphysics", "ethics",
               "logic", "consciousness", "mind", "phenomenology", "free will",
               "determinism", "rationality", "knowledge", "truth", "belief",
               "moral", "value", "justice", "fairness", "diplomacy", "power",
               "geopolitics", "global governance", "security dilemma",
               "international relations", "soft power", "military strategy",
               "thucydides trap", "deterrence"],
        "tags": ["philosophy"],
        "link_to": ["Philosophy of Mind", "Ethics", "Epistemology"],
    },
    "Immunology": {
        "kw": ["immune", "immunology", "immunity", "antibody", "antigen", "cytokine",
               "t cell", "b cell", "natural killer", "macrophage", "dendritic cell",
               "inflammation", "inflammaging", "autoimmune", "allergy", "asthma",
               "vaccine", "immunotherapy", "checkpoint inhibitor", "cancer immunotherapy",
               "complement system", "mhc", "major histocompatibility", "immunosenescence",
               "immune function", "adaptive immune", "innate immune"],
        "tags": ["immunology"],
        "link_to": ["Immunology", "Adaptive Immune System", "Complement System"],
    },
    "Cell Biology": {
        "kw": ["cell", "cellular", "mitochondria", "mitochondrial", "apoptosis",
               "programmed cell death", "autophagy", "senescence", "cellular senescence",
               "dna", "rna", "transcription", "translation", "protein folding",
               "protein", "gene", "genome", "chromosome", "epigenetic", "epigenetics",
               "signaling pathway", "signal transduction", "receptor", "ligand",
               "membrane", "organelle", "nucleus", "cytoplasm", "endoplasmic reticulum",
               "golgi", "lysosome", "peroxisome", "cytoskeleton", "stem cell",
               "differentiation", "proliferation", "cell cycle", "cell division",
               "mitosis", "meiosis", "crispr", "gene editing", "synthetic biology"],
        "tags": ["cell-biology"],
        "link_to": ["Cell Biology", "Mitochondrial Biology", "Apoptosis"],
    },
    "Genomics": {
        "kw": ["genomics", "genome", "gene", "dna sequencing", "whole genome",
               "exome", "gwas", "genome-wide", "snps", "variant", "mutation",
               "polymorphism", "allele", "genotype", "phenotype", "heritability",
               "polygenic risk", "pharmacogenomics", "transcriptomics", "rnaseq",
               "epigenomics", "chip-seq", "bioinformatics", "biostatistics",
               "mendelian randomization", "crispr-cas9", "gene therapy",
               "precision medicine", "personalized medicine"],
        "tags": ["genomics"],
        "link_to": ["Genomics", "GWAS", "CRISPR-Cas9 Gene Editing"],
    },
    "Longevity": {
        "kw": ["longevity", "aging", "age-related", "lifespan", "healthspan",
               "caloric restriction", "dietary restriction", "intermittent fasting",
               "time-restricted eating", "senolytic", "senomorphic", "sasp",
               "hallmarks of aging", "geroscience", "epigenetic clock", "biological age",
               "telomere", "telomerase", "yamanaka factor", "reprogramming",
               "regenerative medicine", "stem cell therapy", "stem cell",
               "anti-aging", "age reversal", "longevity science",
               "nad+", "sirtuin", "mtor", "ampk", "igf-1", "growth hormone"],
        "tags": ["longevity", "aging"],
        "link_to": ["Longevity Science", "Hallmarks of Aging", "Caloric Restriction"],
    },
    "Research Methods": {
        "kw": ["research method", "study design", "cohort study", "case-control",
               "randomized controlled trial", "rct", "clinical trial", "trial",
               "observational study", "longitudinal", "cross-sectional", "survey",
               "meta-analysis", "systematic review", "evidence-based", "replication",
               "power analysis", "sample size", "missing data", "measurement error",
               "validity", "reliability", "generalizability", "transportability",
               "research design", "confirmation bias", "publication bias",
               "registered report", "open science", "reproducibility"],
        "tags": ["research-methods"],
        "link_to": ["Research Methods", "Cohort Study", "Causal Inference"],
    },
    "Health": {
        "kw": ["health", "wellness", "well-being", "self-care", "burnout",
               "mental health", "physical health", "disease prevention",
               "public health", "epidemiology", "medicine", "medical",
               "diagnosis", "treatment", "therapy", "clinical", "patient",
               "doctor", "hospital", "pharmaceutical", "drug", "prescription",
               "biomedical", "biomedicine", "biotechnology"],
        "tags": ["health"],
        "link_to": ["Health", "Biomedical Science"],
    },
    "Economics": {
        "kw": ["economic", "economics", "market", "microeconomics", "macroeconomics",
               "supply and demand", "incentive", "game theory", "mechanism design",
               "auction", "bargaining", "trade", "global trade", "business cycle",
               "recession", "inflation", "deflation", "monetary policy", "fiscal policy",
               "central bank", "interest rate", "employment", "gdp", "growth",
               "development", "inequality", "poverty", "welfare", "regulation",
               "competition", "monopoly", "oligopoly", "externalities", "public good",
               "market failure", "information asymmetry", "principal-agent",
               "adverse selection", "moral hazard", "signaling"],
        "tags": ["economics"],
        "link_to": ["Game Theory", "Economics", "Mechanism Design"],
    },
    "Productivity": {
        "kw": ["productivity", "deep work", "time management", "focus", "attention",
               "flow", "habit", "routine", "discipline", "willpower",
               "procrastination", "goal setting", "project management",
               "task management", "gtd", "getting things done", "eisenhower",
               "pomodoro", "energy management", "efficiency", "effectiveness"],
        "tags": ["productivity"],
        "link_to": ["Deep Work", "Attention Economy", "Decision Making"],
    },
    "Control Theory": {
        "kw": ["control theory", "feedback control", "pid controller", "pid",
               "state space", "transfer function", "stability", "lyapunov",
               "optimal control", "model predictive", "mpc", "adaptive control",
               "robust control", "feedback loop", "regulation", "servo",
               "homeostasis", "cybernetics", "kalman filter"],
        "tags": [],
        "link_to": ["Control Theory", "Homeostasis", "Feedback Loops"],
    },
}

# Stub template — minimal evergreen placeholder
STUB_TEMPLATE = """\
---
title: {title}
aliases:
  - {alias}
status: stub
domain: {domain}
tags:
  - concept
  - {domain_tag}
created: 2026-05-23
updated: 2026-05-23
---

# {title}

> *Auto-categorised concept — placeholder.*

This concept note was auto-assigned to **{domain}** as part of the vault-wide domain categorisation sweep. It was previously uncategorised.

## Core Definition

{definition}

## Related Concepts
- {links}
"""


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body)."""
    fm = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not fm:
        return {}, content
    result = {}
    for line in fm.group(1).strip().split('\n'):
        if ': ' in line:
            key, val = line.split(': ', 1)
            result[key.strip()] = val.strip()
    body = content[fm.end():].strip()
    return result, body


def get_existing_domains() -> dict[str, str]:
    """Build a title → domain map from all classified concepts."""
    result = {}
    for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        fm, _ = parse_frontmatter(content)
        title = os.path.splitext(os.path.basename(f))[0]
        # Try YAML title
        yt = fm.get('title', '')
        if yt:
            if yt.startswith('"') and yt.endswith('"'):
                yt = yt[1:-1]
            title = yt
        domain = fm.get('domain', 'General')
        if domain in ('General', 'Uncategorised', ''):
            result[title] = None
        else:
            result[title] = domain
    return result


def get_domain_for_concept(title: str, content: str, existing: dict[str, str]) -> str:
    """Classify a concept to its best domain."""
    fm, body = parse_frontmatter(content)
    body_lower = body.lower() + title.lower()
    
    # Check existing links — what domains do linked concepts belong to?
    links = set(re.findall(r'\[\[([^\]|]+)', body))
    linked_domains = Counter()
    for link in links:
        target = link.split('#')[0].strip().rstrip('\\')
        if target in existing and existing[target]:
            linked_domains[existing[target]] += 1
    
    # Score each domain
    scores = {}
    for domain, sig in DOMAIN_SIGNATURES.items():
        score = 0
        
        # Keyword matches (weighted by position in content)
        for kw in sig["kw"]:
            if kw.lower() in body_lower:
                score += 2
            # Check in title specifically (higher weight)
            if kw.lower() in title.lower():
                score += 5
        
        # Tag matches
        fm_tags = fm.get('tags', '')
        for tag in sig["tags"]:
            if tag in fm_tags:
                score += 10
        
        # Link analysis
        if sig["link_to"]:
            for l in sig["link_to"]:
                if l in links:
                    score += 5
        
        # Linked domain bonus
        for ld, count in linked_domains.items():
            if ld == domain or (ld.lower() == domain.lower()):
                score += 3 * count
        
        if score > 0:
            scores[domain] = score
    
    # Also check link_to domains — if concept links to Finance concepts, it's probably finance
    for domain, sig in DOMAIN_SIGNATURES.items():
        for l in sig["link_to"]:
            if l in links:
                if domain not in scores:
                    scores[domain] = 0
                scores[domain] += 3
    
    if not scores:
        # Fallback: check first paragraph for any domain keyword
        first_para = body.split('\n\n')[0].lower() if '\n\n' in body else body[:200].lower()
        best_domain = "General"
        best_score = 0
        for domain, sig in DOMAIN_SIGNATURES.items():
            for kw in sig["kw"]:
                if kw.lower() in first_para:
                    score = 1
                    if score > best_score:
                        best_score = score
                        best_domain = domain
        if best_domain != "General":
            return best_domain
        return "General"  # truly unclassifiable
    
    return max(scores, key=scores.get)


def generate_stub_content(title: str, domain: str) -> str:
    """Generate minimal 30-50 line stub content."""
    # Simple domain-specific definitions
    definitions = {
        "AI": "A field of computer science focused on creating systems that can perform tasks requiring human-like intelligence, including learning, reasoning, and perception.",
        "Statistics": "The discipline that concerns the collection, organization, analysis, interpretation, and presentation of data.",
        "Finance": "The study and management of money, investments, and financial instruments including markets, institutions, and risk.",
        "Neuroscience": "The scientific study of the nervous system — its structure, function, development, and pathology.",
        "Psychology": "The scientific study of the mind and behaviour, encompassing conscious and unconscious phenomena including feelings and thoughts.",
        "Software Engineering": "The systematic application of engineering approaches to the design, development, testing, and maintenance of software.",
        "Causal Inference": "The set of statistical methods and frameworks for determining whether and how one variable causally affects another.",
        "Sleep / Neuroscience": "The study of sleep as a neurobiological phenomenon: its regulation, architecture, function, and disorders.",
        "Physiology": "The branch of biology concerned with the normal functions of living organisms and their parts.",
        "Meta": "A meta-concept describing vault structure, navigation, methodology, and knowledge management practices.",
        "Complexity Science": "The study of complex systems — networks of many interacting components exhibiting emergent behaviour not predictable from individual parts.",
        "Philosophy": "The study of fundamental questions about existence, knowledge, values, reason, mind, and language.",
        "Immunology": "The study of the immune system — its structure, function, disorders, and therapeutic manipulation.",
        "Cell Biology": "The study of cell structure, function, and behaviour — the basic unit of life.",
        "Genomics": "The study of whole genomes — their structure, function, evolution, and mapping.",
        "Longevity": "The interdisciplinary science of extending healthy lifespan through understanding the mechanisms of aging.",
        "Research Methods": "The systematic frameworks, study designs, and analytical approaches used to conduct scientific research.",
        "Health": "The state of physical, mental, and social well-being, and the systems that maintain or restore it.",
        "AI / Systems Engineering": "The discipline of designing, building, and operating autonomous AI systems — agent architectures, guardrails, evaluation, and deployment.",
        "Economics": "The social science concerned with the production, distribution, and consumption of goods and services.",
        "Productivity": "The study and practice of maximising output per unit of input — time management, focus, habits, and workflow optimisation.",
        "Control Theory": "The mathematical study of how to make dynamic systems behave in a desired way using feedback or feedforward control.",
    }
    
    if domain == "General":
        definition = "A concept that requires further analysis for accurate domain classification."
    else:
        definition = definitions.get(domain, f"A concept within the domain of {domain}.")
    
    domain_tag = domain.lower().replace(" / ", "-").replace(" ", "-").replace("/", "-")
    
    body_lines = [
        f"# {title}\n",
        f"\n> *Auto-categorised concept — placeholder for **{domain}**.*\n",
        f"\n## Core Definition\n",
        f"\n{definition}\n",
        f"\n## Key Aspects\n",
        f"\nThis concept belongs to the **{domain}** domain. It was categorised",
        f"during a vault-wide sweep of previously unassigned concepts.\n",
        f"\n## Related Concepts\n",
        f"- Links to be added during vault expansion.\n",
        f"\n## Sources\n",
        f"- *Placeholder — to be populated.*\n",
    ]
    
    return "\n".join(body_lines)


def main():
    print("=" * 60)
    print("  VAULT DOMAIN ASSIGNER")
    print("=" * 60)
    
    # Get existing domains
    print("\nLoading existing domain assignments...")
    existing = get_existing_domains()
    assigned = sum(1 for d in existing.values() if d)
    unassigned = sum(1 for d in existing.values() if not d)
    print(f"  Already assigned: {assigned}")
    print(f"  Uncategorised:    {unassigned}")
    
    uncategorised = [t for t, d in existing.items() if not d]
    
    # Classify each
    classified = {}
    for title in uncategorised:
        # Find the file
        fpath = os.path.join(CONCEPTS_DIR, title + ".md")
        if not os.path.isfile(fpath):
            # Try to find by searching
            found = False
            for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
                bare = os.path.splitext(os.path.basename(f))[0]
                if bare.lower() == title.lower():
                    fpath = f
                    found = True
                    break
            if not found:
                continue
        
        with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        
        domain = get_domain_for_concept(title, content, existing)
        classified[title] = (fpath, domain)
    
    # Report
    domain_counts = Counter(d for _, d in classified.values())
    print(f"\n{'─' * 60}")
    print("  CLASSIFICATION RESULTS")
    print(f"{'─' * 60}")
    for domain, count in domain_counts.most_common():
        print(f"  {domain:40s} {count:3d}")
    print(f"\n  Total classified: {len(classified)}")
    print(f"  Unmatched:        {len(uncategorised) - len(classified)}")
    
    # Write assignments
    with open("/tmp/domain_assignments.txt", 'w') as log:
        for title, (fpath, domain) in sorted(classified.items()):
            log.write(f"{domain:40s} | {title}\n")
    
    print(f"\nFull log: /tmp/domain_assignments.txt")


if __name__ == "__main__":
    main()
