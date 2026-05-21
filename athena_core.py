#!/usr/bin/env python3
"""
athena_core.py — Shared foundation for all Cognoscope components.

Provides:
  - VaultGraph: single connectome loader (cached, validated)
  - Logger: structured logging with severity
  - ResultBus: unified output channel
  - VaultPaths: canonical vault directory paths
  - readiness_check(): validate environment before running

Usage:
    from athena_core import VaultGraph, Logger, ResultBus, VaultPaths, readiness_check
    
    paths = VaultPaths()
    log = Logger("my_engine")
    graph = VaultGraph()
    bus = ResultBus()
    
    if readiness_check():  # check vault is accessible
        my_engine(graph, log, bus)
"""

import os, re, glob, json, hashlib, sys, math, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict, Counter
from typing import Any, Callable


# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────

@dataclass
class VaultPaths:
    """Canonical vault directory paths. Single source of truth for all components."""
    vault_root: str = field(default_factory=lambda: os.path.expanduser("~/Obsidian Vault"))
    concepts_dir: str = ""
    pubs_dir: str = ""
    ari_dir: str = ""
    research_dir: str = ""
    scripts_dir: str = ""
    meta_dir: str = ""
    daily_dir: str = ""
    
    def __post_init__(self):
        if not self.concepts_dir:
            self.concepts_dir = os.path.join(self.vault_root, "04 Resources/Concepts")
        if not self.pubs_dir:
            self.pubs_dir = os.path.join(self.vault_root, "04 Resources/Publications")
        if not self.ari_dir:
            self.ari_dir = os.path.join(self.vault_root, "04 Resources/ARI")
        if not self.research_dir:
            self.research_dir = os.path.join(self.vault_root, "04 Resources/Research")
        if not self.scripts_dir:
            self.scripts_dir = os.path.join(self.vault_root, "06 System/Scripts")
        if not self.meta_dir:
            self.meta_dir = os.path.join(self.vault_root, "90 Meta")
        if not self.daily_dir:
            self.daily_dir = os.path.join(self.vault_root, "01 Daily")

VAULT_PATHS = VaultPaths()


# ──────────────────────────────────────────────
# LOGGER
# ──────────────────────────────────────────────

class Logger:
    """Structured logger with severity levels. Writes to stderr by default.
    
    Usage:
        log = Logger("bridge_recommender")
        log.info("Loading vault...")
        log.warn("Graph has {n} orphans", n=42)
        log.error("Could not load connectome: {err}", err=str(e))
    """
    
    LEVELS = {"debug": 0, "info": 1, "warn": 2, "error": 3, "fatal": 4}
    
    def __init__(self, name: str = "cognoscope", min_level: str = "info"):
        self.name = name
        self.min_level = self.LEVELS.get(min_level, 1)
        self._entries: list[dict] = []
    
    def _log(self, level: str, msg: str, **kwargs):
        if self.LEVELS.get(level, 1) < self.min_level:
            return
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "name": self.name,
            "msg": msg.format(**kwargs) if kwargs else msg,
        }
        self._entries.append(entry)
        # Always print errors to stderr
        if level in ("error", "fatal"):
            print(f"[{level.upper()}] {self.name}: {entry['msg']}", file=sys.stderr)
        elif level == "warn":
            print(f"[WARN] {self.name}: {entry['msg']}", file=sys.stderr)
    
    def debug(self, msg: str, **kwargs): self._log("debug", msg, **kwargs)
    def info(self, msg: str, **kwargs): self._log("info", msg, **kwargs)
    def warn(self, msg: str, **kwargs): self._log("warn", msg, **kwargs)
    def error(self, msg: str, **kwargs): self._log("error", msg, **kwargs)
    def fatal(self, msg: str, **kwargs): self._log("fatal", msg, **kwargs)
    
    def get_entries(self, level: str | None = None) -> list[dict]:
        if level:
            return [e for e in self._entries if e["level"] == level]
        return self._entries
    
    def has_errors(self) -> bool:
        return any(e["level"] in ("error", "fatal") for e in self._entries)


# ──────────────────────────────────────────────
# VAULT GRAPH — The connectome
# ──────────────────────────────────────────────

@dataclass
class ConceptNode:
    """A single concept note from the vault with all metadata and link counts."""
    file: str
    title: str
    status: str = "unknown"
    domain: str = "General"
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    lines: int = 0
    wikilinks_out: list[str] = field(default_factory=list)
    wikilinks_in: int = 0
    has_sources: bool = False
    date: str = ""
    phi_estimate: float = 0.0


class VaultGraph:
    """Load all concept notes and build the wikilink graph.
    
    Singleton via VaultGraph.get_instance() — cached across imports.
    
    Usage:
        g = VaultGraph()
        print(f"Loaded {len(g.nodes)} concepts in {len(g.domains)} domains")
        for domain, titles in g.domains.items():
            print(f"  {domain}: {len(titles)} notes")
    """
    
    _instance: Any = None
    
    def __init__(self, paths: VaultPaths | None = None, force_reload: bool = False):
        if not force_reload and VaultGraph._instance is not None:
            self.__dict__ = VaultGraph._instance.__dict__
            return
        self.paths = paths or VAULT_PATHS
        self.nodes: dict[str, ConceptNode] = {}
        self.domains: dict[str, list[str]] = defaultdict(list)
        self.domain_pairs: dict[tuple[str, str], int] = Counter()
        self._load()
        self._compute_phi()
        VaultGraph._instance = self
    
    @staticmethod
    def get_instance(force_reload: bool = False) -> "VaultGraph":
        if VaultGraph._instance is None or force_reload:
            return VaultGraph(force_reload=force_reload)
        return VaultGraph._instance
    
    def _load(self):
        concepts_dir = self.paths.concepts_dir
        if not os.path.isdir(concepts_dir):
            print(f"[ERROR] VaultGraph: Concepts directory not found: {concepts_dir}", file=sys.stderr)
            return
        
        for f in sorted(glob.glob(os.path.join(concepts_dir, "*.md"))):
            fn = os.path.basename(f)
            try:
                with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                    raw = fh.read()
            except Exception as e:
                print(f"[WARN] VaultGraph: Cannot read {fn}: {e}", file=sys.stderr)
                continue
            
            # Parse frontmatter
            fm = re.search(r'^---\n(.*?)\n---', raw, re.DOTALL)
            metadata = {}
            if fm:
                for line in fm.group(1).strip().split('\n'):
                    if ': ' in line:
                        key, val = line.split(': ', 1)
                        metadata[key.strip()] = val.strip()
            
            title = fn.replace('.md', '')
            title_match = re.search(r'^# (.+)$', raw, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
            yt = metadata.get('title', '')
            if yt:
                title = yt
            
            status = metadata.get('status', 'unknown').strip('# ')
            domain = metadata.get('domain', 'General')
            
            # Tags
            tags_str = metadata.get('tags', '')
            tags = []
            if tags_str.startswith('['):
                tags = [t.strip().strip("'\"") for t in tags_str.strip('[]').split(',') if t.strip()]
            elif tags_str.startswith('#'):
                tags = [t.strip('# ') for t in tags_str.split() if t.startswith('#')]
            elif tags_str:
                tags = [tags_str]
            
            # Aliases
            aliases_str = metadata.get('aliases', '')
            aliases = []
            if aliases_str:
                if aliases_str.startswith('['):
                    aliases = [a.strip().strip("'\"") for a in aliases_str.strip('[]').split(',') if a.strip()]
                elif aliases_str.startswith('-'):
                    aliases = [a.strip('- ').strip("'\"") for a in aliases_str.split('\n') if a.strip().startswith('-')]
                else:
                    aliases = [aliases_str]
            
            has_sources = bool(metadata.get('sources', ''))
            date_val = metadata.get('updated', metadata.get('created', metadata.get('date', '')))
            lines = len(raw.splitlines())
            
            # Extract wikilinks from body (skip frontmatter)
            body = raw
            if fm:
                body = raw[fm.end():]
            wikilinks_out = list(set(re.findall(r'\[\[([^\]|]+)', body)))
            # Filter to only existing-ish looking links (no http, no #sections)
            wikilinks_out = [w.split('#')[0].strip() for w in wikilinks_out 
                           if not w.startswith('http') and not w.startswith('#') and w.strip()]
            
            node = ConceptNode(
                file=f,
                title=title,
                status=status,
                domain=domain,
                tags=tags,
                aliases=aliases,
                lines=lines,
                wikilinks_out=wikilinks_out,
                wikilinks_in=0,
                has_sources=has_sources,
                date=date_val,
                phi_estimate=0.0,
            )
            self.nodes[title] = node
            self.domains[domain].append(title)
        
        # Second pass: compute in-links
        for title, node in self.nodes.items():
            inbound = 0
            for other in self.nodes.values():
                if title in other.wikilinks_out:
                    inbound += 1
            node.wikilinks_in = inbound
        
        # Compute domain pairs (how many concepts bridge each pair)
        for title_a, node_a in self.nodes.items():
            for title_b, node_b in self.nodes.items():
                if title_a >= title_b:
                    continue
                if node_a.domain != node_b.domain:
                    shared = set(node_a.wikilinks_out) & set(node_b.wikilinks_out)
                    if shared:
                        pair = tuple(sorted([node_a.domain, node_b.domain]))
                        self.domain_pairs[pair] += 1
    
    def _compute_phi(self):
        """Estimate structural Φ — integration of each concept in the connectome."""
        if not self.nodes:
            return
        total = len(self.nodes)
        for node in self.nodes.values():
            inbound_norm = min(node.wikilinks_in / max(total * 0.05, 1), 1.0)
            outbound_norm = min(len(node.wikilinks_out) / 30, 1.0)
            node.phi_estimate = 0.6 * inbound_norm + 0.4 * outbound_norm
    
    def summary(self) -> dict:
        return {
            "nodes": len(self.nodes),
            "domain_count": len(self.domains),
            "domains_list": sorted(self.domains.keys()),
            "mean_phi": sum(n.phi_estimate for n in self.nodes.values()) / max(len(self.nodes), 1),
        }


# ──────────────────────────────────────────────
# RESULT BUS — Unified output channel
# ──────────────────────────────────────────────

class ResultBus:
    """Unified output channel. Collects results and flushes to the right place.
    
    Usage:
        bus = ResultBus()
        bus.note("concepts/AI Safety.md", "# AI Safety\n\nContent here...")
        bus.message("telegram", "Scan complete: 42 nodes")
        bus.stdout("Top candidate: Finance ↔ ML/AI")
    """
    
    def __init__(self):
        self.outputs: list[dict] = []
    
    def note(self, vault_rel_path: str, content: str, paths: VaultPaths | None = None):
        """Write a vault note at paths.vault_root / vault_rel_path."""
        p = paths or VAULT_PATHS
        full_path = os.path.join(p.vault_root, vault_rel_path.lstrip('/'))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        self.outputs.append({"type": "note", "path": full_path})
    
    def message(self, channel: str, text: str, **meta):
        """Queue a message for delivery (Telegram, stdout, etc)."""
        self.outputs.append({"type": "message", "channel": channel, "text": text, **meta})
        print(text)
    
    def stdout(self, text: str):
        """Print to stdout and log at info level."""
        self.outputs.append({"type": "stdout", "text": text})
        print(text)


# ──────────────────────────────────────────────
# READINESS CHECK
# ──────────────────────────────────────────────

def readiness_check(paths: VaultPaths | None = None, verbose: bool = False) -> bool:
    """Check environment is ready: vault accessible, imports work, paths exist.
    
    Returns True if everything looks good, False if critical components missing.
    """
    p = paths or VAULT_PATHS
    checks = []
    all_ok = True
    
    # Concepts directory
    ok = os.path.isdir(p.concepts_dir)
    checks.append(("concepts_dir", p.concepts_dir, ok))
    if not ok: all_ok = False
    
    # At least one .md file in concepts
    if ok:
        files = glob.glob(os.path.join(p.concepts_dir, "*.md"))
        ok = len(files) > 10  # at least 10 notes
        checks.append(("concept_notes", f"{len(files)} files", ok))
        if not ok: all_ok = False
    
    # Publications directory
    ok = os.path.isdir(p.pubs_dir)
    checks.append(("pubs_dir", p.pubs_dir, ok))
    if not ok: all_ok = False
    
    # Vault root
    ok = os.path.isdir(p.vault_root)
    checks.append(("vault_root", p.vault_root, ok))
    if not ok: all_ok = False
    
    if verbose:
        print("  ATHENA READINESS CHECK")
        print(f"  {'✓' if all_ok else '✗'} Overall: {'Ready' if all_ok else 'Issues found'}")
        for name, path, ok in checks:
            print(f"  {'✓' if ok else '✗'} {name}: {path}")
    
    return all_ok


# ──────────────────────────────────────────────
# UTILITY
# ──────────────────────────────────────────────

def extract_wikilinks(text: str) -> list[str]:
    """Extract unique [[wikilinks]] from text, no pipes, no sections."""
    return list(set(re.findall(r'\[\[([^\]|]+)', text)))


def extract_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from vault note text."""
    fm = re.search(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not fm:
        return {}
    result = {}
    for line in fm.group(1).strip().split('\n'):
        if ': ' in line:
            key, val = line.split(': ', 1)
            result[key.strip()] = val.strip()
    return result


# ──────────────────────────────────────────────
# MAIN / CLI
# ──────────────────────────────────────────────

def main():
    """Run readiness check on demand."""
    import argparse
    parser = argparse.ArgumentParser(description="Athena Core - Cognoscope foundation")
    parser.add_argument("--check", action="store_true", help="Run readiness check")
    parser.add_argument("--summary", action="store_true", help="Show vault summary")
    args = parser.parse_args()
    
    if args.check:
        ok = readiness_check(verbose=True)
        sys.exit(0 if ok else 1)
    
    if args.summary:
        g = VaultGraph()
        print(json.dumps(g.summary(), indent=2))
        return
    
    readiness_check(verbose=True)


if __name__ == "__main__":
    main()
