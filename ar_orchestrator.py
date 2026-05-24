#!/usr/bin/env python3
"""
ar_orchestrator.py — Master AutoResearch Orchestrator

Runs the full AutoResearch pipeline on schedule:
  1. Phase 1: AR vault concept optimization (ariauthor)
  2. Phase 2: AR tool optimization (toolautor) — if tools pending
  3. Phase 3: AR RSI coupling optimization (rsi_autor) — weekly

Usage:
  python3 ar_orchestrator.py --mode nightly   # Phase 1: 50 experiments
  python3 ar_orchestrator.py --mode weekly    # All phases
  python3 ar_orchestrator.py --mode demo      # Phase 1: 5 experiments
"""

import os, sys, json, subprocess, time
from datetime import datetime

COGNOSCOPE = os.path.expanduser("~/cognoscope")
sys.path.insert(0, COGNOSCOPE)

from autoresearch import (
    Mutator, Metric, AutoResearchLoop, AutoResearchConfig,
    AutoResearchResult, save_ar_report, format_ar_result
)

EXPERIMENTS_DIR = os.path.join(COGNOSCOPE, "autoresearch_experiments")
VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
DEFAULT_MAX_EXPERIMENTS = 30
NIGHTLY_EXPERIMENTS = 50


def run_phase1(max_experiments: int = DEFAULT_MAX_EXPERIMENTS) -> list[dict]:
    """
    Phase 1: AR on vault concepts.
    
    Picks concept notes from vault and runs AR optimization loop.
    If ARI has predictions targeting existing concepts, uses those.
    Otherwise picks high-value concepts randomly.
    """
    from ariauthor import VaultMutator, VaultMetric
    from ari_engine import GraphLoader, AnomalyDetector
    
    print(f"\n{'='*60}")
    print(f"  PHASE 1: VAULT OPTIMIZATION ({max_experiments} exp)")
    print(f"{'='*60}")
    
    loader = GraphLoader()
    detector = AnomalyDetector(loader)
    
    # Find ARI predictions that target existing concepts
    candidates = []
    for p in detector.predictions:
        path = os.path.join(CONCEPTS_DIR, f"{p.predicted_title}.md")
        if os.path.exists(path):
            candidates.append((p, path))
    
    if not candidates:
        # Fallback: pick from recently edited / high-value concepts
        print("  No ARI predictions target existing concepts.")
        print("  Falling back to random concept optimization.")
        
        # Pick stubs and seedlings — they need the most improvement
        all_notes = []
        for fname in os.listdir(CONCEPTS_DIR):
            if not fname.endswith(".md") or fname == "AGENTS.md":
                continue
            fpath = os.path.join(CONCEPTS_DIR, fname)
            with open(fpath) as f:
                content = f.read(500)  # Read frontmatter
            if "status: stub" in content or "status: seedling" in content:
                all_notes.append(fpath)
            elif "status: growing" in content:
                all_notes.append(fpath)
        
        # Pick up to 3 notes
        import random
        random.shuffle(all_notes)
        candidates = [(None, path) for path in all_notes[:3]]
    
    results = []
    for pred, concept_path in candidates[:3]:  # Max 3 concepts per run
        title = os.path.splitext(os.path.basename(concept_path))[0]
        print(f"\n  Optimizing: {title}")
        
        mutator = VaultMutator()
        metric = VaultMetric()
        baseline = metric.evaluate(concept_path)
        
        loop = AutoResearchLoop(
            subject_name=title,
            file_path=concept_path,
            mutator=mutator,
            metric=metric,
            baseline=baseline,
        )
        result = loop.run()
        
        if result:
            save_ar_report(result)
            results.append({
                "subject": title,
                "experiments": result.total_experiments,
                "kept": result.kept_experiments,
                "improvement": result.metric_improvement_pct,
                "metric_from": result.metric_start,
                "metric_to": result.metric_end,
            })
    
    return results


def run_phase2() -> list[dict]:
    """
    Phase 2: AR on synthesized/queued tools.
    Checks for tools pending optimization.
    """
    print(f"\n{'='*60}")
    print(f"  PHASE 2: TOOL OPTIMIZATION")
    print(f"{'='*60}")
    
    results = []
    pending_path = os.path.expanduser("~/.hermes/autoresearch/pending_tools.json")
    
    if not os.path.exists(pending_path):
        print("  No pending tools. Skipping Phase 2.")
        return results
    
    with open(pending_path) as f:
        pending = json.load(f)
    
    for tool in pending[:3]:  # Max 3 tools per run
        print(f"\n  Optimizing tool: {tool['name']}")
        try:
            subprocess.run([
                sys.executable, os.path.join(COGNOSCOPE, "toolautor.py"),
                "--synthesize", tool["description"],
                "--tool-name", tool["name"]
            ], check=True, timeout=120)
            results.append({"name": tool["name"], "status": "optimized"})
        except Exception as e:
            results.append({"name": tool["name"], "status": f"failed: {e}"})
    
    # Clear pending
    os.remove(pending_path)
    
    return results


def run_phase3() -> list[dict]:
    """
    Phase 3: AR on RSI coupling config.
    """
    print(f"\n{'='*60}")
    print(f"  PHASE 3: RSI COUPLING OPTIMIZATION")
    print(f"{'='*60}")
    
    results = []
    
    try:
        from rsi_autor import run_ar_on_coupling
        result = run_ar_on_coupling()
        if result:
            results.append({
                "phase": "RSI Coupling",
                "experiments": result.total_experiments,
                "kept": result.kept_experiments,
                "improvement": result.metric_improvement_pct,
            })
    except Exception as e:
        print(f"  Phase 3 failed: {e}")
    
    return results


def save_run_log(mode: str, results: dict, duration: float):
    """Save run log for delivery."""
    log = {
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
        "duration_sec": duration,
        "phase1": results.get("phase1", []),
        "phase2": results.get("phase2", []),
        "phase3": results.get("phase3", []),
    }
    
    log_dir = os.path.join(EXPERIMENTS_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    path = os.path.join(log_dir, f"ar_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(log, f, indent=2)
    
    return log


def format_report(log: dict) -> str:
    """Format AR run report for delivery."""
    lines = []
    lines.append(f"## 🤖 AutoResearch Run [{log['mode']}]")
    lines.append(f"Duration: {log['duration_sec']:.1f}s")
    
    p1 = log.get("phase1", [])
    if p1:
        lines.append(f"\n**Phase 1: Vault Optimization**")
        for r in p1:
            imp = r.get("improvement", 0)
            sign = "+" if imp >= 0 else ""
            lines.append(f"- {r['subject']}: {r.get('metric_from', 0):.4f} → {r.get('metric_to', 0):.4f} ({sign}{imp:.1f}%), {r.get('kept', 0)}/{r.get('experiments', 0)} kept")
    
    p2 = log.get("phase2", [])
    if p2:
        lines.append(f"\n**Phase 2: Tool Optimization**")
        for r in p2:
            lines.append(f"- {r.get('name', '?')}: {r.get('status', '?')}")
    
    p3 = log.get("phase3", [])
    if p3:
        lines.append(f"\n**Phase 3: RSI Coupling**")
        for r in p3:
            lines.append(f"- {r.get('phase', '?')}: {r.get('improvement', 0):+.1f}%, {r.get('kept', 0)}/{r.get('experiments', 0)} kept")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AutoResearch Orchestrator")
    parser.add_argument("--mode", choices=["demo", "nightly", "weekly"], default="demo")
    args = parser.parse_args()
    
    start = time.time()
    log_data = {"mode": args.mode, "phase1": [], "phase2": [], "phase3": []}
    
    if args.mode == "demo":
        # Quick test: 10 experiments on one concept
        results = run_phase1(10)
        log_data["phase1"] = results
    
    elif args.mode == "nightly":
        # Full nightly: 50 experiments on vault concepts
        log_data["phase1"] = run_phase1(NIGHTLY_EXPERIMENTS)
        log_data["phase2"] = run_phase2()
    
    elif args.mode == "weekly":
        # Full weekly: all phases
        log_data["phase1"] = run_phase1(NIGHTLY_EXPERIMENTS)
        log_data["phase2"] = run_phase2()
        log_data["phase3"] = run_phase3()
    
    duration = time.time() - start
    log_data["duration_sec"] = duration
    save_run_log(args.mode, log_data, duration)
    
    report = format_report(log_data)
    print(f"\n{report}")
    
    return report


if __name__ == "__main__":
    report = main()
