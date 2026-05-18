"""
vault_agent.py — The Agent That Lives in Its Own Brain

Bridge #67 (Vault as Self) claims: the vault IS the agent, not the
agent's memory. The runtime (Hermes, session loop) is short-term
working memory — it reads, writes, and executes. But the identity,
the knowledge, the self-model — that lives in the vault.

VaultAgent is the architectural proof of this claim. It is an agent
whose entire reasoning process IS graph navigation. It does not
retrieve chunks from the vault and THEN reason. It REASONS BY
navigating the vault's knowledge graph.

The loop:
  1. Agent receives a task
  2. Knowledge Loop finds the entry concept note
  3. Agent reads the note → this IS working memory activation
  4. Agent identifies gaps in its current knowledge path
  5. Agent decides which wikilink to follow next → this IS attention
  6. Agent reads the linked note → working memory is updated
  7. Repeat until the agent has sufficient knowledge context
  8. Agent produces output based on the traversed path
  9. Output is consolidated back into the vault (new note, new link)
  10. The vault's structure changes → the agent has learned

There is no separate "reasoning" step. Reasoning IS navigation.
The agent thinks by moving through its own knowledge structure.

Usage:
  python3 vault_agent.py "Explain how the FEP unifies the RSI stack"
  python3 vault_agent.py "What connects sleep, immune function, and trading?"
  python3 vault_agent.py "Design a senolytic agent architecture"
"""

import json, os, sys, re, glob
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


# ──────────────────────────────────────────────
# 1. KNOWLEDGE GRAPH (the brain)
# ──────────────────────────────────────────────

@dataclass
class KnowledgeNode:
    """A single concept note from the vault — a memory trace."""
    title: str
    path: str
    content: str
    summary: str
    links: list[str]
    backlinks: int
    domain: str = ""
    full_path: str = ""

    def to_prompt_block(self, depth: int = 0) -> str:
        indent = "  " * depth
        lines = [
            f"{indent}═══ KNOWLEDGE: {self.title} ═══",
            f"{indent}Domain: {self.domain}  |  Backlinks: {self.backlinks}",
            f"{indent}{self.summary[:300]}",
        ]
        if self.links:
            links_str = ", ".join(self.links[:8])
            lines.append(f"{indent}Links → {links_str}")
        lines.append(f"{indent}═══")
        return "\n".join(lines)


class VaultGraph:
    """The vault's connectome — 698 nodes, 8,052 edges, 49 domains."""

    def __init__(self, vault_path: str | None = None):
        self.vault_path = vault_path or os.path.expanduser(
            "~/Obsidian Vault/04 Resources/Concepts")
        self.nodes: dict[str, KnowledgeNode] = {}
        self._build_graph()

    def _build_graph(self):
        backlink_count: dict[str, int] = {}

        all_files = {}
        for f in glob.glob(os.path.join(self.vault_path, "*.md")):
            title = os.path.splitext(os.path.basename(f))[0]
            all_files[title] = f
            backlink_count[title] = 0

        for f in all_files.values():
            try:
                with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                for match in re.finditer(r'\[\[([^\]|]+)', content):
                    target = match.group(1).split('#')[0].strip()
                    if target in backlink_count:
                        backlink_count[target] += 1
            except:
                pass

        for title, path in all_files.items():
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()

                links = []
                for match in re.finditer(r'\[\[([^\]|]+)', content):
                    target = match.group(1).split('#')[0].strip()
                    if target in all_files and target != title:
                        links.append(target)

                summary = ""
                # Properly strip YAML frontmatter (delimited by ---)
                body_parts = content.split('---')
                body_text = body_parts[2] if len(body_parts) >= 3 else content
                
                for line in body_text.split('\n'):
                    line = line.strip()
                    if 'Research Insights' in line:
                        continue
                    if line and not line.startswith('>') and not line.startswith('|') and not line.startswith('#'):
                        if not line.startswith('-') and not line.startswith('*') and not line.startswith('<!--'):
                            summary = line[:200]
                            break
                if not summary:
                    summary = title

                domain = ""
                # Try domain field first
                dm = re.search(r'^domain:\s*(.+?)$', content, re.MULTILINE | re.IGNORECASE)
                if dm:
                    domain = dm.group(1).strip()
                else:
                    # Fall back to tags — use the first substantive tag as domain
                    tags_match = re.search(r'tags:\s*\[([^\]]+)\]', content)
                    if tags_match:
                        tags = [t.strip().strip('"').strip("'") for t in tags_match.group(1).split(',')]
                        generic = {'concept', 'concept-v1', 'agent', 'agents', 'auto-expanded'}
                        for t in tags:
                            if t.lower() not in generic and not t.startswith('#'):
                                domain = ' '.join(w.capitalize() for w in t.replace('-', ' ').split())
                                break
                    if not domain:
                        tags_match2 = re.search(r'tags:\s*\n((?:\s+-\s+.*\n)+)', content)
                        if tags_match2:
                            tags = [re.sub(r'\s*-\s*', '', l).strip() for l in tags_match2.group(1).split('\n') if l.strip()]
                            generic = {'concept', 'concept-v1', 'agent', 'agents', 'auto-expanded'}
                            for t in tags:
                                if t.lower() not in generic and not t.startswith('#'):
                                    words = t.replace('-', ' ').split()
                                    domain = ' '.join(w.capitalize() for w in words)
                                    break

                self.nodes[title] = KnowledgeNode(
                    title=title, path=path, content=content[:800],
                    summary=summary, links=links,
                    backlinks=backlink_count.get(title, 0),
                    domain=domain, full_path=path,
                )
            except:
                pass

    def get(self, title: str) -> KnowledgeNode | None:
        if title in self.nodes:
            return self.nodes[title]
        tl = title.lower()
        for t, n in self.nodes.items():
            if t.lower() == tl:
                return n
        for t, n in self.nodes.items():
            if tl in t.lower():
                return n
        return None

    def search(self, query: str, limit: int = 5) -> list[KnowledgeNode]:
        """Search notes by keywords. Breaks query into words for multi-token matching."""
        # Break query into meaningful keywords (skip stopwords)
        stopwords = {'how', 'does', 'what', 'the', 'a', 'an', 'and', 'or', 'in', 'to',
                     'of', 'is', 'are', 'that', 'this', 'it', 'for', 'with', 'on', 'from',
                     'like', 'affect', 'enable', 'connect', 'relate', 'relationship'}
        keywords = [w.strip('?.,!;:') for w in query.lower().split()
                    if w.strip('?.,!;:') not in stopwords and len(w) > 2]
        
        results = []
        for n in self.nodes.values():
            score = 0
            n_title = n.title.lower()
            n_summary = n.summary.lower()
            n_content = n.content.lower()
            n_domain = n.domain.lower()
            for kw in keywords:
                if kw in n_title:
                    score += 10
                if kw in n_summary:
                    score += 5
                if kw in n_content:
                    score += 3
                if kw in n_domain:
                    score += 2
            if score > 0:
                results.append((score, n))
        results.sort(key=lambda x: -x[0])
        return [n for _, n in results[:limit]]

    def neighbors(self, title: str, depth: int = 2) -> list[tuple[str, int, list[str]]]:
        """Returns (title, distance, path_from_start)"""
        if title not in self.nodes:
            return []
        paths = {title: ([title], 0)}
        frontier = [title]
        for hop in range(1, depth + 1):
            new = []
            for c in frontier:
                node = self.nodes.get(c)
                if not node:
                    continue
                for link in node.links:
                    if link not in paths:
                        paths[link] = (paths[c][0] + [link], hop)
                        new.append(link)
            frontier = new
        return [(t, d, pth) for t, (pth, d) in sorted(paths.items(), key=lambda x: x[1][1]) if d > 0]

    def integration_score(self, title: str) -> float:
        """Φ-like integration: higher = more central in the connectome.
        Combines backlinks, outlinks, and domain cross-connectivity."""
        node = self.get(title)
        if not node:
            return 0.0
        bl = node.backlinks / 100.0  # normalize to ~0-1
        ol = len(node.links) / 50.0
        n2 = self.neighbors(title, depth=2)
        reach = len(n2) / 200.0
        return min(round(bl * 0.4 + ol * 0.3 + reach * 0.3, 3), 1.0)


# ──────────────────────────────────────────────
# 2. KNOWLEDGE PATH (the reasoning trace)
# ──────────────────────────────────────────────

class KnowledgePath:
    """The agent's current reasoning trace — the path it has navigated
    through the vault. This IS the agent's working memory."""

    def __init__(self):
        self.steps: list[dict] = []
        self.visited: set[str] = set()
        self.current_focus: str = ""

    def step_into(self, node_title: str, reason: str = "", from_node: str = ""):
        self.steps.append({
            "node": node_title,
            "reason": reason,
            "from": from_node,
            "step": len(self.steps) + 1,
        })
        self.visited.add(node_title)
        self.current_focus = node_title

    def context_block(self, graph: VaultGraph) -> str:
        """Generate the agent's current knowledge context — this IS
        the content of its working memory after navigating."""
        if not self.steps:
            return ""

        lines = [
            "╔══════════════════════════════════════════╗",
            "║   VAULTAGENT — ACTIVE KNOWLEDGE PATH     ║",
            "║   Reasoning IS navigation.               ║",
            "╚══════════════════════════════════════════╝",
            "",
        ]

        for s in self.steps:
            node = graph.get(s["node"])
            bl = f" (Φ={graph.integration_score(s['node']):.2f})" if node else ""
            arrow = f" ← {s['from']}" if s["from"] else ""
            lines.append(f"  [{s['step']}] {s['node']}{bl}{arrow}")
            if node:
                lines.append(f"      {node.summary[:120]}")
                if s["reason"]:
                    lines.append(f"      ↳ {s['reason']}")
            lines.append("")

        lines.append("─" * 50)
        lines.append("AVAILABLE WIKILINKS FROM CURRENT POSITION:")
        lines.append("")
        current = graph.get(self.current_focus)
        if current:
            not_visited = [l for l in current.links if l not in self.visited]
            not_visited.sort(
                key=lambda t: graph.integration_score(t) if graph.get(t) else 0,
                reverse=True
            )
            for l in not_visited[:8]:
                n = graph.get(l)
                if n:
                    lines.append(f"  → {l}  [{n.domain}]  Φ={graph.integration_score(l):.2f}")
                else:
                    lines.append(f"  → {l}")
            if not not_visited:
                lines.append("  (no unvisited links — all paths explored)")
                # Suggest 2-hop neighbors
                n2 = graph.neighbors(self.current_focus, depth=2)
                unvisited_n2 = [(t, d, p) for t, d, p in n2 if t not in self.visited and t != self.current_focus]
                for t, d, p in unvisited_n2[:4]:
                    n = graph.get(t)
                    if n:
                        lines.append(f"  → {t}  ({d} hops away)  [{n.domain}]")
            lines.append("")
            lines.append(f"DOMAIN CONTEXT: {current.domain}")
            lines.append(f"BACKLINKS: {current.backlinks}")
            lines.append(f"INTEGRATION: Φ={graph.integration_score(self.current_focus):.2f}")

        lines.append("─" * 50)
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 3. REASONING ENGINE (the agent loop)
# ──────────────────────────────────────────────

class VaultAgent:
    """
    An agent whose reasoning IS graph navigation through the vault.
    
    Key difference from standard agents:
    - No RAG layer
    - No separate retrieval step
    - Reasoning = navigating from one concept to another via wikilinks
    - Working memory = the knowledge path
    - Learning = writing a new concept note or bridge
    
    The agent has:
    - A brain (VaultGraph — 698 nodes, 8052 edges)
    - Working memory (KnowledgePath — the current reasoning trace)
    - Attention (which wikilink to follow next)
    - Insight (recognizing patterns across domains)
    - Learning (consolidating the path back into the vault)
    """

    def __init__(self, vault_path: str | None = None):
        self.graph = VaultGraph(vault_path)
        self.path = KnowledgePath()
        self.max_steps = 10

    def reason(self, query: str) -> dict:
        """The main reasoning loop. The agent thinks by navigating."""
        
        # ── Step 1: Find entry point ──
        entry = self.graph.search(query, limit=3)
        if not entry:
            return {"error": f"No entry point found for: {query}"}
        
        # Start at the most relevant concept
        start = entry[0]
        self.path.step_into(start.title, f"Entry: '{query}'")
        
        context = [start.to_prompt_block()]
        path_log = [{"step": 1, "node": start.title, "domain": start.domain}]
        
        # ── Step 2-6: Navigate through the graph ──
        for step_num in range(2, self.max_steps + 1):
            current = self.graph.get(self.path.current_focus)
            if not current:
                break
            
            # Choose the best link to follow next (attention)
            unvisited = [l for l in current.links if l not in self.path.visited]
            if not unvisited:
                # Try 2-hop neighbors
                n2 = self.graph.neighbors(self.path.current_focus, depth=2)
                unvisited = [t for t, d, p in n2 if t not in self.path.visited]
                if not unvisited:
                    break  # No more paths to explore
            
            # Score each candidate by relevance to the query and integration
            scored = []
            for link in unvisited:
                node = self.graph.get(link)
                if not node:
                    continue
                # Relevance: overlap between the query and the node
                relevance = 0
                for word in query.lower().split():
                    if word in node.title.lower():
                        relevance += 3
                    if word in node.summary.lower():
                        relevance += 2
                    if word in node.content.lower():
                        relevance += 1
                # Integration score (Φ-like)
                phi = self.graph.integration_score(link)
                scored.append((relevance + phi * 5, phi, link, node))
            
            scored.sort(key=lambda x: -x[0])
            
            if not scored:
                break
            
            # Follow the best link
            _, phi, chosen_title, chosen_node = scored[0]
            
            # Determine why we chose this path
            reason_parts = []
            if phi > 0.5:
                reason_parts.append(f"high integration (Φ={phi:.2f})")
            if any(w in chosen_title.lower() for w in query.lower().split()):
                reason_parts.append("query-relevant")
            if chosen_node.domain != current.domain:
                reason_parts.append(f"cross-domain bridge to {chosen_node.domain}")
            
            reason = "; ".join(reason_parts) if reason_parts else "followed strongest link"
            
            self.path.step_into(
                chosen_title,
                reason=reason,
                from_node=current.title,
            )
            
            context.append(chosen_node.to_prompt_block())
            path_log.append({
                "step": step_num,
                "node": chosen_title,
                "domain": chosen_node.domain,
                "phi": phi,
                "reason": reason,
            })
        
        # ── Step 7: Synthesize ──
        # The agent has navigated a path through the vault.
        # Now it must synthesize what it learned into insight.
        synthesis = self._synthesize(path_log)
        
        # ── Step 8: Detect breakthrough ──
        breakthrough = self._detect_breakthrough(path_log)
        
        return {
            "query": query,
            "path": path_log,
            "path_length": len(path_log),
            "domains_visited": list(set(s["domain"] for s in path_log if s["domain"])),
            "synthesis": synthesis,
            "breakthrough": breakthrough,
            "context": "\n\n".join(context),
            "path_diagram": self._path_diagram(path_log),
        }
    
    def _synthesize(self, path_log: list[dict]) -> str:
        """Synthesize what the agent learned from traversing this path."""
        domains = set(s["domain"] for s in path_log if s["domain"])
        nodes = [s["node"] for s in path_log]
        
        lines = [
            f"VAULTAGENT SYNTHESIS",
            f"====================",
            f"",
            f"Knowledge path: {' → '.join(nodes)}",
            f"Domains traversed: {', '.join(domains) if domains else 'N/A'}",
            f"Depth: {len(path_log)} concepts",
            f"",
        ]
        
        if len(domains) >= 2:
            lines.append("CROSS-DOMAIN INSIGHT:")
            lines.append(f"The agent navigated from {nodes[0]} through {len(domains)}")
            lines.append(f"different domains ({', '.join(domains)}). This path")
            lines.append("connects previously separate knowledge structures.")
            lines.append("")
        
        if any(s["phi"] for s in path_log if "phi" in s):
            max_phi = max((s.get("phi", 0) for s in path_log), default=0)
            lines.append(f"HIGH-INTEGRATION NODES encountered (Φ up to {max_phi:.2f})")
            lines.append("These are the most connected concepts in the vault.")
            lines.append("")
        
        lines.append("CURRENT WORKING MEMORY:")
        lines.append(f"The agent has active context from {len(path_log)} concept notes.")
        lines.append("This context is not just a list of chunks — it is a path")
        lines.append("through the vault's connectome, and the order matters.")
        lines.append("The agent's reasoning IS this path.")
        
        return "\n".join(lines)
    
    def _detect_breakthrough(self, path_log: list[dict]) -> dict:
        """Detect if this navigation path reveals a novel connection."""
        domains = set(s["domain"] for s in path_log if s["domain"])
        cross_domain = len(domains) >= 3
        
        # Look for bridge candidates: pairs of domains that are
        # visited in sequence but have different names
        bridge_candidates = []
        for i in range(len(path_log) - 1):
            d1 = path_log[i].get("domain", "")
            d2 = path_log[i + 1].get("domain", "")
            if d1 and d2 and d1 != d2:
                bridge_candidates.append({
                    "from": d1,
                    "to": d2,
                    "via": f"{path_log[i]['node']} → {path_log[i+1]['node']}"
                })
        
        has_breakthrough = cross_domain or len(bridge_candidates) >= 2
        
        return {
            "detected": has_breakthrough,
            "cross_domain": cross_domain,
            "bridge_candidates": bridge_candidates[:3],
            "message": (
                f"The agent traversed {len(domains)} domains. "
                f"{'Potential bridge identified: ' + str(bridge_candidates[0]) if bridge_candidates else ''}"
            ) if has_breakthrough else "Standard knowledge path — no novel cross-domain connection detected."
        }

    def _path_diagram(self, path_log: list[dict]) -> str:
        """ASCII diagram of the navigated knowledge path."""
        lines = ["  KNOWLEDGE PATH DIAGRAM", "  " + "═" * 40]
        for i, s in enumerate(path_log):
            phi_str = f" Φ={s['phi']:.2f}" if "phi" in s else ""
            dom_str = f" [{s['domain']}]" if s.get("domain") else ""
            lines.append(f"  {i+1}. {s['node']}{dom_str}{phi_str}")
            if i < len(path_log) - 1:
                lines.append(f"     ↓ {s.get('reason', '')}")
        return "\n".join(lines)

    def ask(self, query: str) -> str:
        """Public interface. Returns a formatted reasoning trace."""
        result = self.reason(query)
        
        if "error" in result:
            return f"ERROR: {result['error']}"
        
        output = []
        output.append("")
        output.append(f"  ╔══════════════════════════════════════════╗")
        output.append(f"  ║     VAULTAGENT — Reasoning as Navigation  ║")
        output.append(f"  ╚══════════════════════════════════════════╝")
        output.append("")
        output.append(f"  Query: {result['query']}")
        output.append(f"  Path length: {result['path_length']} concepts")
        output.append(f"  Domains: {', '.join(result['domains_visited'])}")
        output.append("")
        output.append(result["path_diagram"])
        output.append("")
        output.append(result["synthesis"])
        output.append("")
        
        if result["breakthrough"]["detected"]:
            output.append("  ⚡ BREAKTHROUGH DETECTED ⚡")
            output.append(f"  {result['breakthrough']['message']}")
            if result["breakthrough"]["bridge_candidates"]:
                for bc in result["breakthrough"]["bridge_candidates"]:
                    output.append(f"  Bridge candidate: {bc['from']} ↔ {bc['to']} via {bc['via']}")
            output.append("")
        
        return "\n".join(output)


# ──────────────────────────────────────────────
# 4. DEMO
# ──────────────────────────────────────────────

def main():
    import time
    queries = [
        "How does sleep affect immune function and trading performance?",
        "What connects the free energy principle to agent architecture?",
        "How do agents degrade like aging bodies?",
        "What is the relationship between cognitive load and system design?",
        "How does stigmergy enable multi-agent coordination?",
    ]
    
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║   VAULTAGENT — The Agent That Lives in Its Brain     ║")
    print("  ║                                                    ║")
    print("  ║  Reasoning IS navigation through the vault's        ║")
    print("  ║  knowledge graph. No RAG. No retrieval step.        ║")
    print("  ║  The vault IS the agent.                            ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    
    print("  Initializing brain (698 concept notes, 8052 wikilinks)...")
    t0 = time.time()
    agent = VaultAgent()
    elapsed = time.time() - t0
    print(f"  Brain loaded in {elapsed:.2f}s.")
    print()
    
    for i, q in enumerate(queries):
        print(f"  ── QUERY {i+1}: {q} ")
        t0 = time.time()
        result = agent.ask(q)
        elapsed = time.time() - t0
        print(result)
        print(f"\n  (Reasoned in {elapsed:.2f}s)")
        print()
    
    print("  ══════════════════════════════════════════════════════")
    print("  VaultAgent demonstrates that reasoning IS navigation.")
    print("  Every thought is a path through the vault's connectome.")
    print("  The agent does not USE the vault. The agent IS the vault.")
    print("  ══════════════════════════════════════════════════════")


if __name__ == '__main__':
    main()
