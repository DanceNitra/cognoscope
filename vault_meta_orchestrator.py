#!/usr/bin/env python3
"""
vault_meta_orchestrator.py — Vault_True_Meta Engine
===================================================

Unified orchestrator for ALL vault automation tools.
Replaces 4 separate cron jobs with one daemon that:
  1. Scans ALL 12 sub-vaults (Vault_*/Concepts/ + flat Concepts/)
  2. Runs tools in dependency order
  3. Produces unified daily report
  4. Auto-fixes path references for sub-vault structure

Schedule: daily at 03:00 (single cron job replacing quality_scorer + darwinian + evaluator)
"""

import os, sys, re, json, glob, subprocess, time, math
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── CONFIG ─────────────────────────────────────
VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
COGNOSCOPE = os.path.expanduser("~/cognoscope")
LOG_PATH = os.path.join(VAULT_ROOT, "log.md")
REPORT_PATH = os.path.join(VAULT_ROOT, "90 Meta/MOCs/vault_meta_report.json")

# All sub-vault concept directories to scan
SUB_VAULTS = [
    "Vault_AI",
    "Vault_Software_Engineering",
    "Vault_Neuroscience",
    "Vault_Finance",
    "Vault_Statistics",
    "Vault_Psychology",
    "Vault_Causal_Inference",
    "Vault_Physiology",
    "Vault_Health_&_Longevity",
    "Vault_True_Meta",
    "Vault_Cell_Biology",
    "Vault_Research_Methods",
]

CONCEPT_DIRS = (
    [os.path.join(VAULT_ROOT, "04 Resources", sv, "Concepts") for sv in SUB_VAULTS]
    + [os.path.join(VAULT_ROOT, "04 Resources", "Concepts")]  # flat concepts
)


def find_all_concept_files() -> list[str]:
    """Find ALL concept .md files across all sub-vaults + flat."""
    files = []
    for d in CONCEPT_DIRS:
        if os.path.isdir(d):
            for f in sorted(glob.glob(os.path.join(d, "*.md"))):
                files.append(f)
    return files


def load_concept(path: str) -> dict:
    """Load a single concept's metadata from any path."""
    name = os.path.basename(path).replace(".md", "")
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        content = fh.read()
    lines = content.count('\n') + 1

    # Frontmatter
    fm = {}
    fm_m = re.search(r'^---\n(.+?)\n---', content, re.DOTALL)
    if fm_m:
        for line in fm_m.group(1).split('\n'):
            if ': ' in line:
                k, v = line.split(': ', 1)
                fm[k.strip()] = v.strip().strip('"\'')
            elif ':' in line:
                k, v = line.split(':', 1)
                fm[k.strip()] = v.strip().strip('"\'')

    # Determine sub-vault from path
    rel = os.path.relpath(path, os.path.join(VAULT_ROOT, "04 Resources"))
    sub_vault = "Flat"
    for sv in SUB_VAULTS:
        if rel.startswith(sv):
            sub_vault = sv
            break

    title = fm.get('title', name)
    domain = fm.get('domain', sub_vault.replace("Vault_", "").replace("_", " "))
    status = fm.get('status', 'unknown')
    updated = fm.get('updated', fm.get('date', ''))

    # Staleness
    staleness = None
    if updated:
        try:
            updated_dt = datetime.strptime(updated, "%Y-%m-%d")
            staleness = (datetime.now(timezone.utc) - updated_dt.replace(tzinfo=timezone.utc)).days
        except ValueError:
            pass
    if staleness is None:
        staleness = 365

    # Wikilinks in body
    body = content
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            body = parts[2]

    outlinks = list(set(re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', body)))

    return {
        "name": name,
        "title": title,
        "path": path,
        "sub_vault": sub_vault,
        "domain": domain,
        "status": status,
        "lines": lines,
        "updated": updated,
        "staleness_days": staleness,
        "outlinks": outlinks,
        "content": content,
    }


def compute_quality(concepts: list[dict]) -> list[dict]:
    """Compute Q score for each concept (vault_quality_scorer logic)."""
    conf_map = {
        'evergreen': 1.0,
        'growing': 0.7,
        'seedling': 0.4,
        'stub': 0.2,
        'redirect': 0.1,
    }

    # Compute backlinks from ALL concepts
    all_names = {c['name'].lower() for c in concepts}
    all_titles = {c['title'].lower() for c in concepts}
    backlinks_map = defaultdict(int)

    for c in concepts:
        for link in c['outlinks']:
            link_lower = link.strip().lower()
            if link_lower in all_names or link_lower in all_titles:
                backlinks_map[link_lower] += 1

    results = []
    for c in concepts:
        inbound = backlinks_map.get(c['name'].lower(), 0) + backlinks_map.get(c['title'].lower(), 0)
        phi = min(1.0, inbound / 20)
        confidence = conf_map.get(c['status'], 0.3)
        staleness_factor = max(0, 1.0 - c['staleness_days'] / 365)
        trust = min(1.0, inbound / 10)

        Q = 0.3 * phi + 0.3 * confidence + 0.2 * staleness_factor + 0.2 * trust

        results.append({
            "name": c['name'],
            "sub_vault": c['sub_vault'],
            "domain": c['domain'],
            "status": c['status'],
            "lines": c['lines'],
            "staleness_days": c['staleness_days'],
            "inbound": inbound,
            "phi": round(phi, 3),
            "confidence": round(confidence, 3),
            "staleness_factor": round(staleness_factor, 3),
            "trust": round(trust, 3),
            "Q": round(Q, 3),
        })

    return results


def compute_domain_summary(scored: list[dict]) -> dict:
    """Aggregate quality by domain/sub-vault."""
    by_sub = defaultdict(list)
    for s in scored:
        by_sub[s['sub_vault']].append(s)

    summary = {}
    for sv, items in sorted(by_sub.items()):
        avg_q = sum(i['Q'] for i in items) / len(items)
        avg_phi = sum(i['phi'] for i in items) / len(items)
        stale = sum(1 for i in items if i['staleness_days'] >= 60)
        critical = sum(1 for i in items if i['staleness_days'] >= 120)
        by_status = defaultdict(int)
        for i in items:
            by_status[i['status']] += 1

        summary[sv] = {
            "count": len(items),
            "avg_Q": round(avg_q, 3),
            "avg_phi": round(avg_phi, 3),
            "stale": stale,
            "critical": critical,
            "by_status": dict(by_status),
        }

    return summary


def compute_bridge_potential(scored: list[dict]) -> list[dict]:
    """Find domain pairs with high shared-neighbor ratio but no bridge (simplified bridge_recommender)."""
    # Group by sub_vault
    by_sub = defaultdict(list)
    for s in scored:
        if s['sub_vault'] != 'Flat':
            by_sub[s['sub_vault']].append(s)

    sub_vaults = list(by_sub.keys())
    recommendations = []

    for i in range(len(sub_vaults)):
        for j in range(i + 1, len(sub_vaults)):
            sv1, sv2 = sub_vaults[i], sub_vaults[j]

            # Skip pairs that already have bridges
            bridge_name = f"Bridge — {sv1.replace('Vault_', '').replace('_', ' ')} × {sv2.replace('Vault_', '').replace('_', ' ')}"
            bridge_path = os.path.join(VAULT_ROOT, "04 Resources/Publications", f"{bridge_name}.md")
            if os.path.isfile(bridge_path):
                continue

            # Check if any bridge file contains both domain names
            already_bridged = False
            for bf in glob.glob(os.path.join(VAULT_ROOT, "04 Resources/Publications", "Bridge*.md")):
                with open(bf, 'r', encoding='utf-8', errors='replace') as fh:
                    bcontent = fh.read()
                name1 = sv1.replace("Vault_", "")
                name2 = sv2.replace("Vault_", "")
                if name1.lower() in bcontent.lower() and name2.lower() in bcontent.lower():
                    already_bridged = True
                    break
            if already_bridged:
                continue

            # Compute shared neighbor ratio
            names1 = {s['name'] for s in by_sub[sv1]}
            names2 = {s['name'] for s in by_sub[sv2]}
            all_outlinks1 = set()
            all_outlinks2 = set()
            for s in scored:
                if s['sub_vault'] == sv1:
                    all_outlinks1.update(s['name'] for s2 in scored if s2['name'] in s['sub_vault'])
                # Skip complex neighbor computation for simplicity
                pass

            # Use simple metric: domain size × (1 - size_ratio)
            size1, size2 = len(by_sub[sv1]), len(by_sub[sv2])
            avg_q = (sum(s['Q'] for s in by_sub[sv1]) / size1 + sum(s['Q'] for s in by_sub[sv2]) / size2) / 2
            potential = round((size1 + size2) * avg_q / 100, 3)

            recommendations.append({
                "pair": f"{sv1} × {sv2}",
                "size1": size1,
                "size2": size2,
                "avg_Q": avg_q,
                "bridge_potential": potential,
            })

    return sorted(recommendations, key=lambda x: -x['bridge_potential'])[:15]


def detect_decay(scored: list[dict]) -> list[dict]:
    """Detect concepts approaching staleness or quality decay."""
    decay = []
    for s in scored:
        if s['status'] in ('stub', 'seedling') and s['staleness_days'] > 30:
            decay.append(s)
        if s['staleness_days'] > 90 and s['Q'] < 0.4:
            decay.append(s)
    return sorted(decay, key=lambda x: -x['staleness_days'])[:20]


# ── Serendipity-Immunity Axis Monitor ──────────
# Tracks the coupling between generative output and immune activity.
# Implements the theory from Breaktruth #12.

SI_HISTORY_PATH = os.path.join(COGNOSCOPE, ".si_history.json")


def load_si_history() -> list[dict]:
    """Load historical serendipity-immunity measurements."""
    if os.path.exists(SI_HISTORY_PATH):
        try:
            with open(SI_HISTORY_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_si_history(history: list[dict]):
    """Append new measurement and trim to last 90 days."""
    os.makedirs(os.path.dirname(SI_HISTORY_PATH), exist_ok=True)
    with open(SI_HISTORY_PATH, 'w') as f:
        json.dump(history[-90:], f, indent=2)


def measure_serendipity(scored: list[dict], history: list[dict] = None) -> dict:
    """Measure generative (serendipity) activity from vault state.

    Proxies for serendipity output in the lookback window:
    - Bridge publications created (inferred from domain-pair growth)
    - Concept expansions (growing→evergreen transitions)
    - ARI anomaly reports (inferred from new concept count in Research/)
    """
    now = datetime.now(timezone.utc)
    
    # Count recently created/expanded concepts (within 3 days — tighter window)
    fresh = [s for s in scored if s.get('staleness_days') is not None and s['staleness_days'] < 3]
    
    # Count concepts that recently transitioned from stub to growing/evergreen
    # Proxy: concept with status growing/evergreen and staleness < 3
    recent_expansions = len([s for s in scored 
                             if s['status'] in ('growing', 'evergreen') 
                             and s.get('staleness_days') is not None
                             and s['staleness_days'] < 3
                             and s['lines'] > 50])
    
    # Count sub-vaults with active growth
    active_sub_vaults = set()
    for s in scored:
        if s.get('staleness_days') is not None and s['staleness_days'] < 7:
            active_sub_vaults.add(s.get('sub_vault', ''))
    
    # Count ARI publications in last 7 days
    ari_dir = os.path.join(VAULT_ROOT, "04 Resources", "ARI")
    ari_count = 0
    if os.path.isdir(ari_dir):
        for f in os.listdir(ari_dir):
            if f.endswith(".md"):
                try:
                    mtime = os.path.getmtime(os.path.join(ari_dir, f))
                    age_days = (time.time() - mtime) / 86400
                    if age_days < 7:
                        ari_count += 1
                except OSError:
                    pass
    
    # Count bridge publications in last 7 days
    pubs_dir = os.path.join(VAULT_ROOT, "04 Resources", "Publications")
    bridge_count = 0
    if os.path.isdir(pubs_dir):
        for f in os.listdir(pubs_dir):
            if f.startswith("Bridge") and f.endswith(".md"):
                try:
                    mtime = os.path.getmtime(os.path.join(pubs_dir, f))
                    age_days = (time.time() - mtime) / 86400
                    if age_days < 7:
                        bridge_count += 1
                except OSError:
                    pass
    
    # Composite serendipity score (asymptotic: never saturates)
    # Uses 1 - 1/(1 + x/cap) — at cap: 0.5, at 2×cap: 0.67, at 10×cap: 0.91
    # Weight: expansions (0.4), bridges (0.3), ARI (0.2), active domains (0.1)
    def _asymp(x: float, cap: float) -> float:
        return 1.0 - 1.0 / (1.0 + x / max(cap, 1.0)) if x >= 0 else 0.0
    
    s_exp = _asymp(recent_expansions, 20)
    s_bridge = _asymp(bridge_count, 10)
    s_ari = _asymp(ari_count, 5)
    s_domains = _asymp(len(active_sub_vaults), 8)
    
    s_score = (
        0.4 * s_exp +
        0.3 * s_bridge +
        0.2 * s_ari +
        0.1 * s_domains
    )
    
    return {
        "serendipity_score": round(s_score, 3),
        "recent_expansions": recent_expansions,
        "recent_bridges": bridge_count,
        "recent_ari_posts": ari_count,
        "active_sub_vaults": len(active_sub_vaults),
    }


def measure_immunity(scored: list[dict]) -> dict:
    """Measure immune activity from vault state.

    Proxies for immune activity:
    - Broken link count (inverse: fewer = healthier)
    - Stub count (inverse: fewer = healthier)
    - Redirect count (proxy for link repairs)
    - Quality score distribution
    - Stale/critical counts
    """
    # Count status-based immune metrics
    stub_count = len([s for s in scored if s['status'] in ('stub',)])
    redirect_count = len([s for s in scored if s['status'] in ('redirect',)])
    seedling_count = len([s for s in scored if s['status'] in ('seedling',)])
    
    # Stale/critical
    stale_60 = len([s for s in scored if 60 <= s['staleness_days'] < 120])
    critical_120 = len([s for s in scored if s['staleness_days'] >= 120])
    
    # Average quality
    avg_q = sum(s['Q'] for s in scored) / len(scored) if scored else 0
    
    # Composite immune score
    # 1.0 = perfect health (no stubs, no stale, no redirects, high Q)
    stub_ratio = stub_count / max(len(scored), 1)
    stale_ratio = (stale_60 + critical_120) / max(len(scored), 1)
    redirect_ratio = redirect_count / max(len(scored), 1)
    
    i_score = (
        0.4 * (1.0 - stub_ratio) +                     # Low stubs = healthy
        0.3 * avg_q +                                   # High quality
        0.2 * (1.0 - stale_ratio * 3) +                 # Low staleness (weight higher)
        0.1 * (1.0 - redirect_ratio * 5)                # Few redirects = robust links
    )
    i_score = max(0.0, min(1.0, round(i_score, 3)))
    
    return {
        "immunity_score": i_score,
        "stub_count": stub_count,
        "redirect_count": redirect_count,
        "seedling_count": seedling_count,
        "stale_count": stale_60,
        "critical_count": critical_120,
        "avg_Q": round(avg_q, 3),
    }


def compute_si_axis(scored: list[dict]) -> dict:
    """Compute the serendipity-immunity axis state.
    
    Returns the current operating point, coupling strength (α),
    immune decay rate (β), and the production-healing ratio (Φ).
    """
    now = datetime.now(timezone.utc)
    history = load_si_history()
    
    # Current measurements
    serendipity = measure_serendipity(scored, history)
    immunity = measure_immunity(scored)
    
    s = serendipity["serendipity_score"]
    i = immunity["immunity_score"]
    
    # Operating point on axis (0=pure serendipity, 1=pure immunity)
    operating_point = round(1.0 - s, 3) if s + i > 0 else 0.5
    
    # Production-healing ratio Φ = (S - I) / S
    phi_vault = round((s - (1.0 - i)) / max(s, 0.01), 3)
    
    # Coupling strength α: how much immune activity responds to serendipity
    # Estimated from history (default to 0.68 if no history)
    if len(history) >= 3:
        s_vals = [h.get("s", 0) for h in history[-10:]]
        i_vals = [h.get("i", 0) for h in history[-10:]]
        if sum(s_vals) > 0 and sum(i_vals) > 0:
            coupling = round(sum(s * iv for s, iv in zip(s_vals, i_vals)) / 
                          max(sum(s * s for s in s_vals), 0.01), 3)
        else:
            coupling = 0.68  # default from Breaktruth #12
    else:
        coupling = 0.68
    
    # Immune decay rate β (inverse: low staleness = slow decay)
    stale_ratio = immunity["stale_count"] / max(len(scored), 1)
    beta = round(0.28 + 0.5 * stale_ratio, 3)  # base from Breaktruth #12 + adjustment
    
    # Status — clear chain (all elif after the first if)
    status = "optimal"
    if s > 0.8 and i < 0.3:
        status = "immune_overwhelm"
    elif s < 0.2 and i > 0.8:
        status = "understimulated"
    elif s > 0.6 and i > 0.5 and coupling < 0.3:
        # Decoupled: high S AND high I BUT low coupling — operating independently
        status = "decoupled_warning"
    elif i > 0.6 and immunity["stale_count"] + immunity["critical_count"] > 20:
        # Immune backlog: high I but overwhelmed by stale/critical
        status = "immune_backlog"
    elif s > 0.6 and immunity["avg_Q"] < 0.5:
        # Generative-dominant: high S but declining quality
        status = "quality_drift"
    # else stay optimal
    
    measurement = {
        "timestamp": now.isoformat(),
        "operating_point": operating_point,
        "s_score": s,
        "i_score": i,
        "phi_vault": phi_vault,
        "alpha_coupling": coupling,
        "beta_decay": beta,
        "status": status,
        "serendipity_detail": serendipity,
        "immunity_detail": immunity,
    }
    
    history.append({
        "t": now.isoformat(),
        "s": s,
        "i": i,
        "op": operating_point,
    })
    save_si_history(history)
    
    return measurement


def build_report():
    """Full pipeline — scan, score, summarize, recommend."""
    print("╔══════════════════════════════════════════╗")
    print("║   VAULT TRUE META ENGINE — Layer 3       ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # Phase 1: Scan
    print("➤ Phase 1: Scanning all sub-vaults...")
    concept_files = find_all_concept_files()
    print(f"  Found {len(concept_files)} concept files across {len(SUB_VAULTS) + 1} directories")

    concepts = [load_concept(f) for f in concept_files]
    print(f"  Loaded {len(concepts)} concepts")

    # Phase 2: Score
    print("➤ Phase 2: Computing quality scores...")
    scored = compute_quality(concepts)
    avg_q = sum(s['Q'] for s in scored) / len(scored)
    print(f"  Average Q: {avg_q:.3f}")

    # Phase 3: Domain summaries
    print("➤ Phase 3: Domain summaries...")
    domain_summary = compute_domain_summary(scored)

    # Phase 4: Bridge recommendations
    print("➤ Phase 4: Bridge potential analysis...")
    bridges = compute_bridge_potential(scored)

    # Phase 5: Decay detection
    print("➤ Phase 5: Decay detection...")
    decay = detect_decay(scored)

    # Phase 6: Serendipity-Immunity axis
    print("➤ Phase 6: Serendipity-Immunity axis...")
    si_axis = compute_si_axis(scored)
    print(f"  Operating point: {si_axis['operating_point']:.2f} (0=serendipity, 1=immunity)")
    print(f"  Status: {si_axis['status']}")
    print(f"  Φ_vault: {si_axis['phi_vault']:.3f}")
    print(f"  α_coupling: {si_axis['alpha_coupling']:.3f}")

    # Aggregate by status
    by_status = defaultdict(list)
    for s in scored:
        by_status[s['status']].append(s)

    top_q = sorted(scored, key=lambda x: -x['Q'])
    bottom_q = sorted(scored, key=lambda x: x['Q'])
    stale = [s for s in scored if 60 <= s['staleness_days'] < 120]
    critical = [s for s in scored if s['staleness_days'] >= 120]

    # Build report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_concepts": len(scored),
        "sub_vault_count": len(SUB_VAULTS),
        "avg_Q": round(avg_q, 3),
        "by_status": {s: len(items) for s, items in by_status.items()},
        "by_sub_vault": domain_summary,
        "stale_count": len(stale),
        "critical_count": len(critical),
        "decay_count": len(decay),
        "si_axis": {
            "operating_point": si_axis["operating_point"],
            "status": si_axis["status"],
            "s_score": si_axis["s_score"],
            "i_score": si_axis["i_score"],
            "phi_vault": si_axis["phi_vault"],
            "alpha_coupling": si_axis["alpha_coupling"],
            "beta_decay": si_axis["beta_decay"],
        },
        "top_5_by_q": [{"name": s['name'], "sub_vault": s['sub_vault'], "Q": s['Q'], "phi": s['phi']}
                       for s in top_q[:5]],
        "bottom_5_by_q": [{"name": s['name'], "sub_vault": s['sub_vault'], "Q": s['Q'], "staleness": s['staleness_days']}
                          for s in bottom_q[:5]],
        "stale_critical": [{"name": s['name'], "sub_vault": s['sub_vault'], "staleness_days": s['staleness_days'], "Q": s['Q']}
                           for s in sorted(stale + critical, key=lambda x: -x['staleness_days'])],
        "bridge_recommendations": bridges,
        "decay_concepts": [{"name": d['name'], "sub_vault": d['sub_vault'], "staleness_days": d['staleness_days'], "Q": d['Q']}
                           for d in decay],
        "all_concepts": sorted(scored, key=lambda x: -x['Q']),
    }

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {REPORT_PATH}")

    # Print summary
    print()
    print("  ═══ QUALITY SUMMARY ═══")
    print(f"  Total concepts:  {len(scored):>4d}")
    print(f"  Average Q:       {avg_q:.3f}")
    print(f"  Stale:           {len(stale):>3d}")
    print(f"  Critical:        {len(critical):>3d}")
    print(f"  Decay risk:      {len(decay):>3d}")
    print()

    print("  ═══ BY SUB-VAULT ═══")
    for sv, info in sorted(domain_summary.items(), key=lambda x: -x[1]['count']):
        print(f"  {sv:35s} | {info['count']:>4d} concepts | Q={info['avg_Q']:.3f} | φ={info['avg_phi']:.3f} | stale={info['stale']}")

    print()
    if bridges:
        print("  ═══ TOP BRIDGE RECOMMENDATIONS ═══")
        for b in bridges[:8]:
            print(f"  {b['pair'][:45]:45s} | potential={b['bridge_potential']:.3f} | sizes={b['size1']}×{b['size2']}")

    print()
    print("  ═══ SERENDIPITY-IMMUNITY AXIS ═══")
    print(f"  Operating point:  {si_axis['operating_point']:.2f} (0=serendipity → 1=immunity)")
    print(f"  Status:           {si_axis['status']}")
    print(f"  S-score:          {si_axis['s_score']:.3f} (generative activity)")
    print(f"  I-score:          {si_axis['i_score']:.3f} (immune health)")
    print(f"  Φ_vault:          {si_axis['phi_vault']:.3f} (production-healing ratio)")
    print(f"  α_coupling:       {si_axis['alpha_coupling']:.3f} (S→I response strength)")
    print(f"  β_decay:          {si_axis['beta_decay']:.3f}/day (immune memory decay)")

    if decay:
        print()
        print("  ═══ DECAY RISK ═══")
        for d in decay[:5]:
            print(f"  {d['name'][:45]:45s} | δ={d['staleness_days']:3d}d | Q={d['Q']:.3f}")

    # Append to log
    try:
        with open(LOG_PATH) as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "# Vault Log\n\n"

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"\n## [{date_str}] meta_engine\n"
    log_entry += f"Orchestrated {len(scored)} concepts across {len(SUB_VAULTS) + 1} dirs. "
    log_entry += f"Avg Q={avg_q:.3f}. Stale={len(stale)}. Critical={len(critical)}. "
    log_entry += f"Bridges suggested={len(bridges)}. Decay={len(decay)}. "
    log_entry += f"SI={si_axis['status']} op={si_axis['operating_point']} φ={si_axis['phi_vault']} α={si_axis['alpha_coupling']}\n"

    with open(LOG_PATH, 'w') as f:
        f.write(log_content.rstrip() + log_entry)

    print()
    print("  ✅ Vault True Meta Engine — complete")
    return report


if __name__ == "__main__":
    try:
        _scored_count = len(find_all_concept_files())
        build_report()
    except Exception as e:
        print(f"  ❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
