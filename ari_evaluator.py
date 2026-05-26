#!/usr/bin/env python3
"""
ari_evaluator.py — ARI Feedback Loop Evaluator

Closes the ARI feedback loop:
  ARI predicts → evaluator validates → ARI learns

Reads ARI predictions from JSON (ari_engine.py --json), auto-validates
each prediction, and feeds outcomes back into ari_memory.json so ARI
never re-predicts the same thing.

Usage (from cron):
    cd ~/cognoscope && python3 ari_engine.py --json | python3 ari_evaluator.py

Schedule: 0 5 * * * (05:00, after darwinian heal + vault health)
"""

import sys, json, os, re, glob, time
from datetime import datetime
from collections import defaultdict

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
PUBS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")
ARI_DIR = os.path.join(VAULT_ROOT, "04 Resources/ARI")
ARI_MEMORY_PATH = os.path.join(ARI_DIR, "ari_memory.json")
LOG_PATH = os.path.join(VAULT_ROOT, "log.md")

MIN_CONFIDENCE = 0.4
MIN_DOMAIN_SIZE = 5
MIN_STALE_GROWTH = 3


# ──────────────────────────────────────────────
# VAULT LOADERS
# ──────────────────────────────────────────────

def load_existing_concepts() -> set[str]:
    """Return set of all existing concept titles (lowercase)."""
    titles = set()
    for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
        name = os.path.basename(f).replace(".md", "")
        titles.add(name.lower())
        # Also check YAML title
        with open(f, encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        m = re.search(r'^title:\s*(.+)$', content, re.MULTILINE)
        if m:
            titles.add(m.group(1).strip().lower())
        # Check aliases
        alias_section = re.search(r'aliases:\s*\n((?:\s+- .+\n?)+)', content)
        if alias_section:
            for line in alias_section.group(1).strip().split('\n'):
                alias = re.sub(r'^\s*-\s*', '', line).strip().strip("'\"")
                if alias:
                    titles.add(alias.lower())
    return titles


def load_existing_bridge_pairs() -> set[frozenset]:
    """Return set of frozenset domain pairs already bridged."""
    pairs = set()
    for f in glob.glob(os.path.join(PUBS_DIR, "Bridge*.md")):
        with open(f, encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        # Extract domain frontmatter
        m = re.search(r'^domain:\s*(.+)$', content, re.MULTILINE)
        if m:
            domain = m.group(1).strip().lower()
            parts = [p.strip() for p in domain.split('/') if p.strip()]
            # Normalise: the domain field on bridge pubs is like "Finance / Complexity Science"
            # We want to split by / and create all pairs
            if len(parts) >= 2:
                pairs.add(frozenset([p.lower() for p in parts]))
        # Also extract from title: "Finance × Complexity Science"
        title_m = re.search(r'^# (.+)$', content, re.MULTILINE)
        if title_m:
            title = title_m.group(1)
            # Look for × or — or — pattern
            x_match = re.search(r'(\w[\w\s]+?)\s*[×x]\s*(\w[\w\s]+?)', title)
            if x_match:
                a = x_match.group(1).strip().lower()
                b = x_match.group(2).strip().lower()
                pairs.add(frozenset([a, b]))
    return pairs


def load_domain_sizes() -> dict[str, int]:
    """Return dict of domain -> concept count."""
    sizes = defaultdict(int)
    for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
        with open(f, encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        m = re.search(r'^domain:\s*(.+)$', content, re.MULTILINE)
        if m:
            sizes[m.group(1).strip()] += 1
    return dict(sizes)


def load_ari_memory() -> list[dict]:
    """Load existing ARI memory."""
    if os.path.exists(ARI_MEMORY_PATH):
        try:
            with open(ARI_MEMORY_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_ari_memory(entries: list[dict]):
    """Save entries to ari_memory.json (keep last 500)."""
    os.makedirs(os.path.dirname(ARI_MEMORY_PATH), exist_ok=True)
    with open(ARI_MEMORY_PATH, 'w') as f:
        json.dump(entries[-500:], f, indent=2)


def fuzzy_title_match(predicted_title: str, existing_titles: set[str]) -> str | None:
    """
    Check if a predicted concept already exists under a different name.
    Uses several fuzzy strategies:
    1. Exact match (lowercase)
    2. Substring match
    3. Word-overlap ≥ 60%
    """
    pl = predicted_title.lower().strip()
    
    # Exact match
    if pl in existing_titles:
        return pl
    
    # Substring match: predicted title exists WITHIN an existing concept?
    # e.g. "Gradient Descent and..." already exists as "Gradient Descent"
    for t in existing_titles:
        if pl in t or t in pl:
            return t
    
    # Word overlap: common words in predicted vs existing
    pred_words = set(pl.split())
    for t in existing_titles:
        existing_words = set(t.split())
        if len(pred_words) > 0 and len(existing_words) > 0:
            overlap = len(pred_words & existing_words)
            max_len = max(len(pred_words), len(existing_words))
            if max_len > 0 and overlap / max_len >= 0.6:
                return t
    
    return None


# ──────────────────────────────────────────────
# VALIDATION
# ──────────────────────────────────────────────

def validate_prediction(pred: dict, existing_titles: set[str],
                        existing_bridges: set[frozenset],
                        domain_sizes: dict[str, int]) -> dict:
    """
    Validate a single ARI prediction.
    Returns dict with: accepted (bool), reason (str), details (dict).
    """
    predicted_title = pred.get('predicted_title', '')
    predicted_domain = pred.get('predicted_domain', '')
    source_domain = pred.get('source_domain', '')
    target_domain = pred.get('target_domain', '')
    confidence = pred.get('confidence', 0.0)
    pred_type = pred.get('type', 'unknown')
    
    checks = []
    failures = []
    
    # Check 1: Does concept already exist?
    match = fuzzy_title_match(predicted_title, existing_titles)
    if match:
        checks.append(f"ALREADY EXISTS as '{match}'")
        failures.append("exists")
    else:
        checks.append("title appears new ✓")
    
    # Check 2: Does domain pair already have a bridge?
    # Normalise domain names for bridge matching
    if predicted_domain:
        domain_parts = [p.strip().lower() for p in predicted_domain.split('/') if p.strip()]
        for bp in existing_bridges:
            # Check if any bridge pair covers these domains
            normalized_parts = []
            for dp in domain_parts:
                for ep in bp:
                    if dp in ep or ep in dp:
                        normalized_parts.append(ep)
            if len(normalized_parts) >= 2:
                checks.append(f"ALREADY BRIDGED (pair matches existing bridge)")
                failures.append("bridged")
                break
        else:
            checks.append("no existing bridge ✓")
    
    # Check 3: Is predicted domain ≥ 5 concepts?
    if predicted_domain:
        for part in predicted_domain.split('/'):
            part = part.strip()
            if part:
                size = domain_sizes.get(part, 0)
                if size < MIN_DOMAIN_SIZE and size > 0:
                    checks.append(f"domain '{part}' only {size} concepts (< {MIN_DOMAIN_SIZE})")
                    failures.append("small_domain")
                    break
        else:
            checks.append("domain size ≥ 5 ✓")
    
    # Check 4: Is confidence ≥ 0.4?
    if confidence < MIN_CONFIDENCE:
        checks.append(f"low confidence {confidence:.2f} (< {MIN_CONFIDENCE})")
        failures.append("low_confidence")
    else:
        checks.append(f"confidence {confidence:.2f} ✓")
    
    accepted = len(failures) == 0
    
    return {
        "accepted": accepted,
        "reason": "; ".join(checks),
        "failures": failures,
        "confidence": confidence,
        "pred_type": pred_type,
        "source_domain": source_domain,
        "target_domain": target_domain,
        "predicted_domain": predicted_domain,
    }


# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────

def append_to_log(n_accepted: int, n_rejected: int, n_skipped: int,
                  accepted_titles: list[str], rejected_reasons: dict):
    """Append evaluation summary to vault log.md."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    entry = f"\n## [{date_str}] ari_evaluator\n"
    entry += f"ARI predictions evaluated: {n_accepted} accepted, {n_rejected} rejected, {n_skipped} skipped\n\n"
    
    if accepted_titles:
        entry += "**Accepted:**\n"
        for t in accepted_titles:
            entry += f"- {t}\n"
        entry += "\n"
    
    if rejected_reasons:
        entry += "**Rejected:**\n"
        for reason, count in sorted(rejected_reasons.items()):
            entry += f"- {reason}: {count}\n"
        entry += "\n"
    
    # Read existing log, append
    try:
        with open(LOG_PATH) as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "# Vault Log\n\n"
    
    with open(LOG_PATH, 'w') as f:
        f.write(log_content.rstrip() + entry)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print("  ╔══════════════════════════════════════╗")
    print("  ║   ARI EVALUATOR — Feedback Loop      ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    
    # Read ARI predictions from stdin (JSON from ari_engine.py --json)
    try:
        predictions = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[ARI_EVAL] ERROR: invalid JSON from stdin: {e}")
        print("[ARI_EVAL] Usage: python3 ari_engine.py --json | python3 ari_evaluator.py")
        sys.exit(1)
    
    if not predictions:
        print("[ARI_EVAL] No predictions to evaluate.")
        return
    
    print(f"[ARI_EVAL] Loaded {len(predictions)} ARI predictions.")
    
    # Load vault state
    print("[ARI_EVAL] Loading vault state...")
    existing_titles = load_existing_concepts()
    existing_bridges = load_existing_bridge_pairs()
    domain_sizes = load_domain_sizes()
    ari_memory = load_ari_memory()
    
    print(f"[ARI_EVAL] {len(existing_titles)} existing concepts")
    print(f"[ARI_EVAL] {len(existing_bridges)} existing bridge pairs")
    print(f"[ARI_EVAL] {len(ari_memory)} ARI memory entries")
    print()
    
    # Evaluate each prediction
    accepted = []
    rejected = []
    skipped = []  # already in memory
    
    new_memory_entries = []
    rejected_reasons = {}
    
    for pred in predictions:
        predicted_title = pred.get('predicted_title', '')
        source_domain = pred.get('source_domain', '')
        target_domain = pred.get('target_domain', '')
        pred_type = pred.get('type', '')
        confidence = pred.get('confidence', 0.0)
        novelty = pred.get('novelty_score', 0.0)
        phi_impact = pred.get('phi_impact', 0.0)
        
        # Skip if already in ARI memory (stale-pair check)
        already_in_memory = False
        for entry in ari_memory:
            src_l = entry.get('source_domain', '').lower()
            tgt_l = entry.get('target_domain', '').lower()
            if entry.get('predicted_title', '').lower() == predicted_title.lower():
                already_in_memory = True
                break
            # Also check if same domain pair was done
            if (src_l == source_domain.lower() and tgt_l == target_domain.lower()) or \
               (src_l == target_domain.lower() and tgt_l == source_domain.lower()):
                already_in_memory = True
                break
        
        if already_in_memory:
            skipped.append(predicted_title)
            continue
        
        # Validate
        result = validate_prediction(pred, existing_titles, existing_bridges, domain_sizes)
        
        # Build memory entry
        memory_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "accepted" if result["accepted"] else "rejected",
            "predicted_title": predicted_title,
            "detector_type": pred_type if pred_type else result["pred_type"],
            "source_domain": source_domain,
            "target_domain": target_domain,
            "source_concept_count": domain_sizes.get(source_domain, 0),
            "target_concept_count": domain_sizes.get(target_domain, 0),
            "confidence": confidence,
            "novelty_score": novelty,
            "phi_impact": phi_impact,
            "accepted": result["accepted"],
            "validation_reason": result["reason"],
            "validation_failures": result["failures"],
        }
        new_memory_entries.append(memory_entry)
        
        if result["accepted"]:
            accepted.append(predicted_title)
            print(f"  ✅ ACCEPTED: {predicted_title[:55]:55s} [{result['pred_type']}]")
        else:
            rejected.append(predicted_title)
            reason = result['failures'][0] if result['failures'] else 'unknown'
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
            print(f"  ❌ REJECTED: {predicted_title[:55]:55s} → {result['reason'][:60]}")
    
    print()
    print(f"[ARI_EVAL] Results: {len(accepted)} accepted, {len(rejected)} rejected, {len(skipped)} skipped")
    
    # Save to ARI memory
    if new_memory_entries:
        combined = ari_memory + new_memory_entries
        save_ari_memory(combined)
        print(f"[ARI_EVAL] Saved {len(new_memory_entries)} new entries to ARI memory.")
    
    # Log to vault
    append_to_log(
        n_accepted=len(accepted),
        n_rejected=len(rejected),
        n_skipped=len(skipped),
        accepted_titles=accepted,
        rejected_reasons=rejected_reasons,
    )
    print(f"[ARI_EVAL] Logged to vault log.md.")
    
    # Print summary
    print()
    print("  ═══ EVALUATION SUMMARY ═══")
    print(f"  Total predictions:  {len(predictions)}")
    print(f"  ✅ Accepted:        {len(accepted)}")
    print(f"  ❌ Rejected:        {len(rejected)}")
    print(f"  ⏭️  Skipped (mem):  {len(skipped)}")
    if rejected_reasons:
        print()
        print("  Rejection breakdown:")
        for reason, count in sorted(rejected_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")
    if accepted:
        print()
        print("  Accepted predictions (will be suppressed next cycle):")
        for t in accepted:
            print(f"    ✅ {t[:70]}")


if __name__ == '__main__':
    main()
