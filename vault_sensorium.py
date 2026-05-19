#!/usr/bin/env python3
"""
vault_sensorium.py — Autonomous vault sensorium.

Polls external sources, detects novel signals, ingests them as seedling
concept notes, and auto-triggers bridge drafts when a signal bridges domains.

Architecture:
  ┌──────────────────────────────────────────────────────────────┐
  │                    VAULT SENSORIUM (L9)                       │
  │                                                              │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
  │  │ HN       │  │ arXiv    │  │ GitHub   │  │ (future) │    │
  │  │ Poller   │  │ Poller   │  │ Trending │  │ sources  │    │
  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
  │       │              │              │              │          │
  │       └──────────────┴──────────────┴──────────────┘          │
  │                          │                                   │
  │                    ┌─────▼──────┐                            │
  │                    │  Novelty   │  Compare against 706       │
  │                    │  Detector  │  existing concepts         │
  │                    └─────┬──────┘                            │
  │                          │ (novel, not redundant)            │
  │                    ┌─────▼──────┐                            │
  │                    │  Ingestion │  Write seedling note       │
  │                    │  Engine    │  Link into graph           │
  │                    └─────┬──────┘                            │
  │                          │ (if bridges 2+ domains)          │
  │                    ┌─────▼──────┐                            │
  │                    │  Bridge    │  Auto-draft bridge pub     │
  │                    │  Trigger   │  via ReasoningPath engine  │
  │                    └────────────┘                            │
  └──────────────────────────────────────────────────────────────┘

Usage:
    python3 vault_sensorium.py              # Full run (all sources)
    python3 vault_sensorium.py --source hn  # HN only
    python3 vault_sensorium.py --dry-run    # Show what would be created
"""

import os, sys, json, re, time, glob, math, random, hashlib
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, date
from typing import Any

VAULT_ROOT = os.path.expanduser("~/Obsidian Vault")
CONCEPTS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Concepts")
PUBLICATIONS_DIR = os.path.join(VAULT_ROOT, "04 Resources/Publications")
SENSORIUM_DIR = os.path.join(VAULT_ROOT, "04 Resources/raw/sensorium")
LOG_FILE = os.path.join(VAULT_ROOT, "log.md")
os.makedirs(SENSORIUM_DIR, exist_ok=True)

# Track which signals we've already ingested
SEEN_FILE = os.path.join(SENSORIUM_DIR, ".seen_signals.json")
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, 'r') as f:
        SEEN_SIGNALS: set[str] = set(json.load(f))
else:
    SEEN_SIGNALS: set[str] = set()


# ──────────────────────────────────────────────
# 1. VAULT GRAPH (fast load from cache if exists)
# ──────────────────────────────────────────────

CACHE_FILE = "/tmp/vault_sensorium_cache.json"


def load_vault_graph() -> dict:
    """Load the vault's concept graph. Returns dict with titles->info."""
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
        except:
            pass

    if cache.get('_meta') and cache['_meta'].get('node_count', 0) > 600:
        return cache

    # Build from scratch
    all_files = {}
    for f in glob.glob(os.path.join(CONCEPTS_DIR, "*.md")):
        t = os.path.splitext(os.path.basename(f))[0]
        try:
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                all_files[t] = fh.read()
        except:
            all_files[t] = ""

    nodes = {}
    for title, content in all_files.items():
        domain = "Unknown"
        m = re.search(r'domain:\s*(.+?)\n', content)
        if m and len(m.group(1).strip()) < 60:
            domain = m.group(1).strip()
        else:
            m2 = re.search(r'tags:\s*\[(.+?)\]', content)
            if m2:
                tags = m2.group(1)
                for k, v in {'neuroscience': 'Neuroscience', 'sleep': 'Sleep Science',
                             'finance': 'Finance', 'ai': 'AI', 'machine-learning': 'ML',
                             'software-engineering': 'Software Engineering',
                             'statistics': 'Statistics', 'causal-inference': 'Statistics',
                             'complexity': 'Complexity Science', 'physiology': 'Physiology',
                             'immunology': 'Immunology', 'philosophy': 'Philosophy',
                             'psychology': 'Psychology', 'endocrine': 'Physiology'}.items():
                    if k in tags.lower():
                        domain = v
                        break

        # Compute phi-like score
        all_links = re.findall(r'\[\[([^\]|]+)', content)
        links_count = len(all_links)
        backlinks_found = set()
        for t2, c2 in all_files.items():
            if t2 == title:
                continue
            for part in c2.split('[[')[1:]:
                target = part.split(']')[0].split('#')[0].strip()
                if target == title:
                    backlinks_found.add(t2)

        lines = len(content.split('\n'))
        phi = round(min(links_count, 30)/30*0.3 + min(len(backlinks_found), 50)/50*0.4 + min(lines, 200)/200*0.3, 4)
        body = content.split('---')[-1] if content.count('---') > 1 else content
        summary = ""
        for line in body.split('\n'):
            s = line.strip()
            if s and not s.startswith('#') and not s.startswith('>') and len(s) > 20 and not s.startswith('|') and not s.startswith('-') and not s.lower().startswith('related:'):
                summary = s[:200]
                break

        nodes[title] = {
            'title': title, 'domain': domain, 'phi': phi,
            'lines': lines, 'links_count': links_count,
            'backlinks_count': len(backlinks_found),
            'summary': summary,
        }

    meta = {
        'node_count': len(nodes),
        'edge_count': sum(n.get('links_count', 0) for n in nodes.values()),
        'domain_count': len(set(n['domain'] for n in nodes.values())),
        'all_titles_lower': {t.lower() for t in nodes},
        'all_keywords': set()
    }
    for n in nodes.values():
        for w in n['title'].lower().split():
            if len(w) > 3:
                meta['all_keywords'].add(w)
        for w in n['summary'].lower().split():
            if len(w) > 4:
                meta['all_keywords'].add(w)
        # Also add domain/keywords from content
    cache = {'nodes': nodes, '_meta': meta}
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except:
        pass
    return cache


# ──────────────────────────────────────────────
# 2. SOURCE POLLERS
# ──────────────────────────────────────────────

@dataclass
class Signal:
    source: str       # 'hn', 'arxiv', 'github'
    title: str
    url: str
    summary: str
    domain_hints: list[str]  # guessed domains
    score: int        # relevance / points
    signal_id: str    # unique id for dedup

    def is_novel(self) -> bool:
        return self.signal_id not in SEEN_SIGNALS


def poll_hn(limit: int = 30) -> list[Signal]:
    """Poll Hacker News frontpage via Firebase API."""
    signals = []
    try:
        top = json.loads(urllib.request.urlopen(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10
        ).read())
        for sid in top[:limit]:
            try:
                s = json.loads(urllib.request.urlopen(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10
                ).read())
            except:
                continue
            title = s.get('title', '')[:200]
            url = s.get('url', f"https://news.ycombinator.com/item?id={sid}")[:500]
            score = s.get('score', 0)
            if score < 15 or not title:
                continue
            text = s.get('text', title)[:500]
            domain_hints = guess_domains(title + " " + text)
            sig_id = f"hn:{hashlib.md5(title.encode()).hexdigest()[:12]}"
            signals.append(Signal(
                source='HN', title=title, url=url,
                summary=text[:400], domain_hints=domain_hints,
                score=score, signal_id=sig_id,
            ))
    except Exception as e:
        print(f"  [HN ERROR] {e}", file=sys.stderr)
    return signals


def poll_arxiv(categories: list[str] | None = None, limit: int = 15) -> list[Signal]:
    """Poll arXiv for recent papers in relevant categories."""
    if categories is None:
        categories = ['cs.AI', 'cs.LG', 'cs.MA', 'cs.NE', 'cs.CL', 'cs.SE', 'q-bio.NC', 'q-fin.ST']
    signals = []
    for cat in categories:
        try:
            url = (f"http://export.arxiv.org/api/query?"
                   f"search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results={limit//len(categories)+1}")
            resp = urllib.request.urlopen(url, timeout=15)
            tree = ET.fromstring(resp.read())
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            for entry in tree.findall('a:entry', ns):
                title = entry.find('a:title', ns)
                title_text = title.text.strip().replace('\n', ' ')[:200] if title is not None and title.text else '?'
                summary = entry.find('a:summary', ns)
                summary_text = summary.text.strip().replace('\n', ' ')[:500] if summary is not None and summary.text else ''
                link = entry.find('a:link', ns)
                url_val = link.get('href', '')[:500] if link is not None else ''
                id_el = entry.find('a:id', ns)
                paper_id = id_el.text.split('/')[-1][:30] if id_el is not None and id_el.text else hashlib.md5(title_text.encode()).hexdigest()[:12]
                sig_id = f"arxiv:{paper_id}"
                dh = guess_domains(title_text + " " + summary_text)
                if not dh:
                    dh = guess_domains(cat.replace('.', ' '))
                signals.append(Signal(
                    source='arXiv', title=title_text, url=url_val,
                    summary=summary_text, domain_hints=dh,
                    score=50, signal_id=sig_id,
                ))
        except Exception as e:
            print(f"  [arXiv {cat} ERROR] {e}", file=sys.stderr)
    return signals


def guess_domains(text: str) -> list[str]:
    """Guess which vault domains a signal belongs to. Returns only
    domains with at least 2 keyword matches to avoid false positives."""
    tl = text.lower()
    scores = {}
    domain_keywords = {
        'Neuroscience': ['neuron', 'brain', 'neural', 'synapse', 'cortex', 'neuro', 'fmri',
                         'eeg', 'cognitive', 'memory', 'plasticity', 'sleep',
                         'consciousness', 'mind', 'visual cortex', 'hippocampus'],
        'AI': ['llm', 'agent', 'transformer', 'gpt', 'language model', 'reasoning', 'prompt',
               'alignment', 'safety', 'rlhf', 'rag', 'mcp', 'frontier model', 'gemini',
               'claude', 'openai', 'anthropic', 'codex', 'cursor', 'composer', 'ai agent',
               'tool use', 'function calling', 'multimodal', 'foundation model'],
        'ML': ['machine learning', 'deep learning', 'gradient', 'backprop', 'training',
               'dataset', 'overfitting', 'attention mechanism', 'reinforcement learning',
               'supervised', 'unsupervised', 'embedding', 'diffusion model'],
        'Finance': ['trading', 'market', 'portfolio', 'risk', 'stock', 'option', 'volatility',
                    'asset', 'sharpe', 'backtest', 'quant', 'alpaca', 'broker',
                    'financial', 'regime detection', 'geometric observables', 'yield', 'bond'],
        'Sleep Science': ['sleep', 'circadian', 'melatonin', 'insomnia', 'dream', 'rem',
                          'slow wave', 'chronotype'],
        'Psychology': ['psychology', 'behavior', 'bias', 'cognition', 'decision', 'attention',
                       'reasoning bias', 'heuristic'],
        'Physiology': ['hormone', 'cortisol', 'endocrine', 'immune', 'inflammation',
                       'metabolism', 'stress', 'hpa axis'],
        'Complexity Science': ['complexity', 'emergence', 'network', 'phase transition',
                               'scale-free', 'power law', 'tipping point', 'self-organi'],
        'Software Engineering': ['distributed', 'consensus', 'architecture', 'microservice',
                                 'api', 'testing', 'framework', 'library', 'rest', 'database',
                                 'compiler', 'open source', 'npm', 'rust', 'python', 'typescript',
                                 'os kernel', 'operating system', 'linux', 'bsd', 'unix',
                                 'container', 'kubernetes', 'docker', 'vulnerability', 'patch',
                                 'exploit', 'cve', 'malware', 'supply chain'],
    }
    for domain, keywords in domain_keywords.items():
        score = 0
        for kw in keywords:
            if kw in tl:
                score += 1
        if score >= 2:  # Require 2+ matches to avoid false positives
            scores[domain] = score

    sorted_domains = sorted(scores.items(), key=lambda x: -x[1])
    return [d for d, s in sorted_domains[:2]]


# ──────────────────────────────────────────────
# 3. NOVELTY DETECTOR
# ──────────────────────────────────────────────

class NoveltyDetector:
    """Compare a signal against existing vault knowledge."""

    def __init__(self, graph: dict):
        self.nodes = graph.get('nodes', {})
        self.meta = graph.get('_meta', {})

    def assess(self, signal: Signal) -> dict:
        """
        Returns:
          novel: bool — genuinely new information
          redundant_with: str | None — if signal is already covered
          suggested_domain: str | None — best domain to place it
          bridging_domains: list[str] — if it touches multiple domains
          confidence: float 0-1
        """
        sl = signal.title.lower() + " " + signal.summary.lower()[:200]

        # Check keyword overlap with existing concepts
        best_match = None
        best_score = 0
        for title, node in list(self.nodes.items())[:50]:  # top 50 by relevance
            score = 0
            tl = title.lower()
            # Direct keyword overlap
            for word in sl.split():
                if len(word) > 4 and word in tl:
                    score += 3
            if node.get('summary'):
                for word in sl.split():
                    if len(word) > 4 and word in node['summary'].lower():
                        score += 1
            # Title word in signal
            for w in title.lower().split():
                if len(w) > 4 and w in sl:
                    score += 5
            if score > best_score:
                best_score = score
                best_match = title

        # Also check all titles as bigrams
        for title in list(self.nodes.keys()):
            tw = title.lower()
            if len(tw) > 6 and tw in sl:
                best_score += 10
                best_match = title

        novel = best_score < 8  # threshold: less than 8 = novel
        redundant = best_match if best_score >= 8 else None

        # Domain assignment
        hints = signal.domain_hints[:]
        if not hints:
            hints = guess_domains(signal.title + " " + signal.summary)

        # If even re-checking yields no domains, this signal is too generic
        if not hints:
            return {
                'novel': False,
                'redundant_with': None,
                'redundant_score': 0,
                'suggested_domain': None,
                'bridging_domains': [],
                'confidence': 0.0,
            }

        bridging = hints if len(hints) >= 2 else []
        suggested = hints[0]

        confidence = 0.3 + len(hints) * 0.15 + min(signal.score / 200, 0.2)
        if novel and signal.score > 50:
            confidence = min(confidence + 0.15, 0.9)
        if not novel:
            confidence *= 0.3

        # Quality filters for HN noise
        if novel and signal.source == 'HN' and signal.score < 30:
            novel = False
        if novel and len(signal.title) < 10:
            novel = False
        if novel and confidence < 0.35:
            novel = False

        return {
            'novel': novel,
            'redundant_with': redundant,
            'redundant_score': best_score,
            'suggested_domain': suggested,
            'bridging_domains': bridging,
            'confidence': round(confidence, 3),
        }


# ──────────────────────────────────────────────
# 4. INGESTION ENGINE
# ──────────────────────────────────────────────

class IngestionEngine:
    """Writes seedling notes + triggers bridge drafts."""

    def __init__(self, graph: dict):
        self.graph = graph

    def ingets(self, signal: Signal, assessment: dict) -> str | None:
        """Write a seedling concept note. Returns path or None."""
        title = self._clean_title(signal.title)
        existing = self.graph.get('nodes', {}).get(title)
        if existing:
            return f"  [SKIP] '{title}' already exists"
        if not assessment.get('novel'):
            return None

        domain = assessment.get('suggested_domain', 'AI')
        summary = signal.summary[:300]
        hints = assessment.get('bridging_domains', [])
        tags = ['sensorium', 'auto-ingested', domain.lower().replace(' ', '-')]
        tags += [d.lower().replace(' ', '-') for d in hints]

        frontmatter = [
            '---',
            f'status: seedling',
            f'domain: {domain}',
            f'tags:',
        ]
        for t in tags:
            frontmatter.append(f'  - {t}')
        frontmatter.extend([
            f'source: {signal.source}',
            f'source_url: {signal.url}',
            f'sensorium_date: {datetime.now().strftime("%Y-%m-%d")}',
            f'---',
        ])

        body = [
            f'# {title}',
            '',
            f'> **Signal from {signal.source}.** Ingested by vault sensorium on {datetime.now().strftime("%Y-%m-%d")}. Status: seedling — needs human expansion to evergreen.',
            '',
            summary,
            '',
            '## Key Points',
            f'- Signal source: {signal.source}',
            f'- Domain: {domain}',
            f'- Confidence: {assessment.get("confidence", 0)}',
            '',
            '## Raw Signal',
            f'- Title: {signal.title}',
            f'- URL: {signal.url}',
            f'- Score: {signal.score}',
            '',
            '## Related Vault Concepts',
        ]

        # Find up to 5 related vault concepts
        sl = signal.title.lower() + " " + signal.summary.lower()[:200]
        related = []
        for t, n in self.graph.get('nodes', {}).items():
            if any(w in t.lower() for w in sl.split() if len(w) > 4):
                related.append(t)
            if len(related) >= 5:
                break
        if not related:
            related = [d for d in hints if d in self.graph.get('nodes', {})]
        for r in related or []:
            body.append(f'- [[{r}]]')

        body.extend(['',
                     '## Status',
                     '#status/seedling — ingested by vault sensorium. Requires human expansion.',
                     '',
                     f'*Ingested {datetime.now().isoformat()}. Source: {signal.source}.*'])

        path = os.path.join(CONCEPTS_DIR, f"{title}.md")
        # Check if similar file already exists
        if os.path.exists(path) or os.path.exists(os.path.join(CONCEPTS_DIR, f"{title}.md")):
            return None
        for existing_file in os.listdir(CONCEPTS_DIR):
            ef = existing_file.replace('.md', '')
            if ef.lower() == title.lower():
                return f"  [SKIP] Similar file exists: {ef}"

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(frontmatter) + '\n\n' + '\n'.join(body))
            return path
        except Exception as e:
            return f"  [ERROR] Failed to write: {e}"

    def _clean_title(self, t: str) -> str:
        """Clean a signal title into a concept note title."""
        # Remove emoji
        t = re.sub(r'[^\x00-\x7F]+', '', t)
        # Remove long trailing URLs/info
        if ' — ' in t:
            t = t.split(' — ')[0]
        if ' – ' in t:
            t = t.split(' – ')[0]
        # Truncate
        t = t[:100]
        # Clean punctuation
        t = re.sub(r'[\[\]{}()<>"\'\\/]', '', t)
        t = t.strip(' .:;-')
        if not t:
            t = f"sensorium-signal-{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
        return t

    def draft_bridge_path(self, signal: Signal, assessment: dict) -> str | None:
        """If the signal bridges 2+ domains and is novel, draft a bridge publication."""
        bridges = assessment.get('bridging_domains', [])
        if len(bridges) < 2:
            return None

        title = self._clean_title(signal.title)
        pub_name = f"Bridge — Sensorium: {title} ({' × '.join(bridges[:3])})"
        safe_name = pub_name.replace('/', '-')[:100]

        content = f"""---
tags: [publication, bridge, sensorium, {'-'.join(b[:2] for b in bridges)}, cross-domain-synthesis, auto-drafted]
status: #status/seedling
domain: Cross-Domain Synthesis
source: {signal.source}
source_url: {signal.url}
sensorium_date: {datetime.now().strftime("%Y-%m-%d")}
---

# Bridge — Sensorium: {title}

> **Auto-discovered by the vault sensorium.** Signal from {signal.source} bridges {', '.join(bridges[:3])}. Drafted automatically — requires human editing before status promotion.

---

## The Signal

| | |
|---|---|
| **Source** | {signal.source} |
| **Title** | {signal.title} |
| **URL** | {signal.url} |
| **Score** | {signal.score} |
| **Domain hints** | {', '.join(signal.domain_hints)} |
| **Bridging** | {', '.join(bridges[:4])} |

## Summary

{signal.summary[:800]}

---

## What This Means

This signal was auto-detected as bridging {len(bridges)} domains. A human should:

1. Read the original source ({signal.url})
2. Expand this seedling into a full bridge publication
3. Cross-reference with the relevant concept notes
4. Check if the bridge is genuinely novel or already covered

---

*Auto-drafted by vault sensorium on {datetime.now().isoformat()}. Status: seedling — requires human review.*
"""
        path = os.path.join(PUBLICATIONS_DIR, f"{safe_name}.md")
        if os.path.exists(path):
            return None
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return path
        except:
            return None


# ──────────────────────────────────────────────
# 5. ORCHESTRATOR
# ──────────────────────────────────────────────

class VaultSensorium:
    """Full sensorium orchestrator: poll → assess → ingest → bridge."""

    def __init__(self, dry_run: bool = False, sources: list[str] | None = None):
        self.dry_run = dry_run
        self.sources = sources or ['hn', 'arxiv']
        self.graph = load_vault_graph()
        self.detector = NoveltyDetector(self.graph)
        self.ingestor = IngestionEngine(self.graph)

        stats = self.graph.get('_meta', {})
        print(f"  Vault: {stats.get('node_count', '?')} concepts, "
              f"{stats.get('domain_count', '?')} domains", file=sys.stderr)
        print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}", file=sys.stderr)
        print(f"  Sources: {', '.join(self.sources)}", file=sys.stderr)

    def run(self) -> dict:
        results = {
            'signals_found': 0,
            'novel_signals': 0,
            'ingested_notes': [],
            'ingested_bridges': [],
            'redundant': 0,
            'errors': [],
            'summary': '',
        }

        # Poll all sources
        all_signals: list[Signal] = []
        if 'hn' in self.sources:
            print("\n  Polling HN...", file=sys.stderr)
            hn = poll_hn(limit=30)
            print(f"    Found {len(hn)} signals", file=sys.stderr)
            all_signals.extend(hn)
        if 'arxiv' in self.sources:
            print("  Polling arXiv...", file=sys.stderr)
            ax = poll_arxiv(limit=20)
            print(f"    Found {len(ax)} signals", file=sys.stderr)
            all_signals.extend(ax)

        results['signals_found'] = len(all_signals)

        # Filter by source if limited
        if self.sources:
            all_signals = [s for s in all_signals if s.source.lower()[:5] in [ss for ss in self.sources]]

        print(f"\n  Total signals: {len(all_signals)}", file=sys.stderr)

        # Assess each signal
        novel_entries = []
        for sig in all_signals:
            assessment = self.detector.assess(sig)
            if assessment.get('novel'):
                novel_entries.append((sig, assessment))
                results['novel_signals'] += 1
            else:
                results['redundant'] += 1

        # Dedup by similar title
        seen_titles = set()
        unique_novel = []
        for sig, assessment in novel_entries:
            t = self.ingestor._clean_title(sig.title).lower()[:30]
            if t in seen_titles:
                continue
            seen_titles.add(t)
            unique_novel.append((sig, assessment))

        print(f"  Novel (unique): {len(unique_novel)}", file=sys.stderr)
        print(f"  Redundant: {results['redundant']}", file=sys.stderr)

        # Ingest unique novel signals
        for sig, assessment in unique_novel:
            print(f"\n  [{sig.source}] {sig.title[:80]}...", file=sys.stderr)
            print(f"    Domains: {assessment.get('suggested_domain', '?')} "
                  f"| Confidence: {assessment.get('confidence', 0):.2f}", file=sys.stderr)
            print(f"    Bridging: {assessment.get('bridging_domains', [])}", file=sys.stderr)

            if self.dry_run:
                results['ingested_notes'].append(f"[DRY] {sig.title[:80]}")
                continue

            # Ingest as concept note
            note = self.ingestor.ingets(sig, assessment)
            if note:
                results['ingested_notes'].append(note)
                print(f"    ✓ Ingested: {os.path.basename(note)}", file=sys.stderr)

            # Draft bridge if bridging
            if assessment.get('bridging_domains') and len(assessment['bridging_domains']) >= 2:
                bridge = self.ingestor.draft_bridge_path(sig, assessment)
                if bridge:
                    results['ingested_bridges'].append(bridge)
                    print(f"    ✓ Bridge drafted: {os.path.basename(bridge)}", file=sys.stderr)

        # Save seen signals
        all_ids = {s.signal_id for s in all_signals if not self.dry_run}
        if not self.dry_run:
            global SEEN_SIGNALS
            SEEN_SIGNALS.update(all_ids)
            with open(SEEN_FILE, 'w') as f:
                f.write(json.dumps(list(SEEN_SIGNALS)))

        total_c = len(results['ingested_notes'])
        total_b = len(results['ingested_bridges'])
        results['summary'] = (f"Sensorium run: {len(all_signals)} signals, "
                              f"{results['novel_signals']} novel, "
                              f"{total_c} notes ingested, "
                              f"{total_b} bridges drafted" if not self.dry_run else
                              f"DRY RUN: {len(all_signals)} signals, "
                              f"{results['novel_signals']} would be novel, "
                              f"{len(unique_novel)} would be ingested")

        return results


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault Sensorium")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created')
    parser.add_argument('--source', choices=['hn', 'arxiv'], action='append',
                        help='Limit to specific sources (can repeat)')
    parser.add_argument('--cron', action='store_true', help='Cron mode — quiet output')
    args = parser.parse_args()

    t0 = time.time()
    sensorium = VaultSensorium(dry_run=args.dry_run, sources=args.source)
    results = sensorium.run()
    elapsed = time.time() - t0

    if args.cron:
        print(results['summary'])
    else:
        print(f"\n  {'='*50}", file=sys.stderr if not args.dry_run else sys.stderr)
        print(f"  SENSORIUM COMPLETE — {elapsed:.0f}s", file=sys.stderr)
        print(f"  {results['summary']}", file=sys.stderr)
        print(f"  {'='*50}", file=sys.stderr)

    print(json.dumps({'summary': results['summary'],
                      'signals': results['signals_found'],
                      'novel': results['novel_signals'],
                      'ingested': len(results['ingested_notes']),
                      'bridges': len(results['ingested_bridges']),
                      'elapsed_s': round(elapsed, 1)}))


if __name__ == '__main__':
    main()
