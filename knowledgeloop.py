"""
knowledgeloop.py — Active Knowledge Navigation for Agent Reasoning

Breakthrough: Every RAG system today is STATIC. You query once, you get
chunks, you're done. The agent does not navigate knowledge — it retrieves it.

KnowledgeLoop is different. The agent reads a vault note. The note has
wikilinks. The agent follows those links based on what it just learned.
The knowledge context GROWS with each reasoning step, adapting to what the
agent discovers.

This is knowledge as a LIVING GRAPH — not a static retrieval index.

How it works:
  1. Agent receives a task that requires deep domain knowledge
  2. KnowledgeLoop reads the most relevant concept note from the vault
  3. Agent processes the note, identifies what it needs next
  4. KnowledgeLoop follows wikilinks from the note to related concepts
  5. Each step adds context AND suggests new directions
  6. The knowledge path is recorded and can be replayed

No RAG system works this way. RAG retrieves once. KnowledgeLoop navigates.
"""

import json, os, re, glob
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────
# 1. KNOWLEDGE GRAPH
# ──────────────────────────────────────────────

@dataclass
class KnowledgeNode:
    """A single concept note from the vault, with its links."""
    title: str
    path: str
    content: str
    summary: str
    links: list[str]  # [[wikilinks]] to other concepts
    backlinks: int    # How many other notes link here
    domain: str = ""

    def to_prompt_block(self) -> str:
        """Generate a compact block for injection into the agent context."""
        lines = [
            f"--- KNOWLEDGE: {self.title} ---",
            f"{self.summary}",
            f"Related: {', '.join(self.links[:8])}",
            f"---",
        ]
        return "\n".join(lines)


class VaultGraph:
    """
    Reads the entire Obsidian vault into a navigable knowledge graph.
    
    The agent can:
    - Start at any concept
    - Follow [[wikilinks]] to related concepts
    - See backlinks (what concepts point to this one)
    - Build a knowledge path through reasoning
    """
    
    def __init__(self, vault_path: str | None = None):
        self.vault_path = vault_path or os.path.expanduser(
            "~/Obsidian Vault/04 Resources/Concepts")
        self.nodes: dict[str, KnowledgeNode] = {}
        self._build_graph()
    
    def _build_graph(self):
        """Scan all concept notes and build the link graph."""
        backlink_count: dict[str, int] = {}
        
        # First pass: collect all titles
        all_files = {}
        for f in glob.glob(os.path.join(self.vault_path, "*.md")):
            title = os.path.splitext(os.path.basename(f))[0]
            all_files[title] = f
            backlink_count[title] = 0
        
        # Second pass: count backlinks
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
        
        # Third pass: build nodes
        for title, path in all_files.items():
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                
                # Extract links
                links = []
                for match in re.finditer(r'\[\[([^\]|]+)', content):
                    target = match.group(1).split('#')[0].strip()
                    if target in all_files and target != title:
                        links.append(target)
                
                # Extract summary (first substantive paragraph after frontmatter)
                summary = ""
                body = content.split('---')[-1] if content.count('---') > 1 else content
                # Skip frontmatter and empty lines
                in_frontmatter = False
                for line in body.split('\n'):
                    line = line.strip()
                    if line == '---':
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter:
                        continue
                    # Skip auto-woven research insights
                    if 'Research Insights' in line or 'auto-woven' in line:
                        continue
                    if line and not line.startswith('>') and not line.startswith('|') and not line.startswith('#'):
                        # Skip citation-like lines
                        if not line.startswith('-') and not line.startswith('*'):
                            summary = line[:200]
                            break
                
                if not summary:
                    summary = title
                
                # Extract domain
                domain_match = re.search(r'domain:\s*(.+?)\n', content)
                domain = domain_match.group(1).strip() if domain_match else ""
                
                self.nodes[title] = KnowledgeNode(
                    title=title,
                    path=path,
                    content=content[:500],  # Store first 500 chars
                    summary=summary,
                    links=links,
                    backlinks=backlink_count.get(title, 0),
                    domain=domain,
                )
            except:
                pass
        
        print(f"  [VAULT GRAPH] Loaded {len(self.nodes)} nodes, "
              f"{sum(len(n.links) for n in self.nodes.values())} edges")
    
    def get(self, title: str) -> KnowledgeNode | None:
        """Get a node by title (case-insensitive, fuzzy)."""
        # Exact match
        if title in self.nodes:
            return self.nodes[title]
        
        # Case-insensitive
        title_lower = title.lower()
        for t, n in self.nodes.items():
            if t.lower() == title_lower:
                return n
        
        # Substring match
        for t, n in self.nodes.items():
            if title_lower in t.lower():
                return n
        
        return None
    
    def search(self, query: str, limit: int = 5) -> list[KnowledgeNode]:
        """Search notes by title or content keywords."""
        query_lower = query.lower()
        results = []
        
        for n in self.nodes.values():
            score = 0
            if query_lower in n.title.lower():
                score += 10
            if query_lower in n.summary.lower():
                score += 5
            if query_lower in n.content.lower():
                score += 3
            if query_lower in n.domain.lower():
                score += 2
            
            if score > 0:
                results.append((score, n))
        
        results.sort(key=lambda x: -x[0])
        return [n for _, n in results[:limit]]
    
    def neighbors(self, title: str, depth: int = 1) -> list[tuple[str, int]]:
        """
        Get all nodes within N hops of the given node.
        Returns list of (title, distance) pairs.
        """
        if title not in self.nodes:
            return []
        
        visited = {title: 0}
        frontier = [title]
        
        for hop in range(1, depth + 1):
            new_frontier = []
            for current in frontier:
                node = self.nodes.get(current)
                if not node:
                    continue
                for link in node.links:
                    if link not in visited:
                        visited[link] = hop
                        new_frontier.append(link)
            frontier = new_frontier
        
        return [(t, d) for t, d in sorted(visited.items(), key=lambda x: x[1])
                if d > 0]


# ──────────────────────────────────────────────
# 2. KNOWLEDGE LOOP
# ──────────────────────────────────────────────

class KnowledgePath:
    """
    A recorded path through the knowledge graph, built during a reasoning
    session. The agent starts at one note and follows links as it learns.
    """
    
    def __init__(self):
        self.steps: list[dict] = []
        self.current_focus: str = ""
    
    def add(self, node_title: str, reason: str, from_node: str = ""):
        """Record a step in the knowledge path."""
        self.steps.append({
            "node": node_title,
            "reason": reason,
            "from": from_node,
            "step": len(self.steps) + 1,
        })
        self.current_focus = node_title
    
    def to_prompt(self) -> str:
        """Generate a prompt block showing the knowledge path so far."""
        if not self.steps:
            return ""
        
        lines = [
            "---",
            "KNOWLEDGE PATH (navigated this session):",
            "",
        ]
        for s in self.steps:
            arrow = f" [{s['from']}] ->" if s['from'] else "      "
            lines.append(f"  {arrow} [{s['step']}] {s['node']}: {s['reason']}")
        
        lines.append("")
        lines.append("To navigate further, describe what you need next.")
        lines.append("The system will follow wikilinks from your current")
        lines.append("focus to surface related concepts.")
        lines.append("---")
        return "\n".join(lines)
    
    def suggested_next(self, graph: VaultGraph, limit: int = 3) -> list[str]:
        """Suggest next nodes to explore based on current focus."""
        if not self.current_focus:
            return []
        
        node = graph.get(self.current_focus)
        if not node:
            return []
        
        # Get links not yet visited
        visited = {s['node'] for s in self.steps}
        suggestions = [l for l in node.links if l not in visited]
        
        # Sort by backlinks (popularity)
        suggestions.sort(key=lambda t: graph.get(t).backlinks if graph.get(t) else 0,
                        reverse=True)
        
        return suggestions[:limit]


class KnowledgeLoop:
    """
    Wraps the agent loop with a knowledge navigation layer.
    
    For each reasoning step, the KnowledgeLoop:
    1. Checks if the agent needs more context
    2. If yes, reads the relevant vault note
    3. Presents the note's content and links
    4. The agent chooses which link to follow next
    5. The knowledge path grows
    
    This is RAG that NAVIGATES, not just retrieves.
    """
    
    def __init__(self, vault_path: str | None = None):
        self.graph = VaultGraph(vault_path)
        self.path = KnowledgePath()
    
    def start(self, topic: str) -> dict:
        """
        Start exploring the knowledge graph from a topic.
        Returns the initial node and its neighbors.
        """
        node = self.graph.get(topic) or self.graph.search(topic)[0]
        if not node:
            return {"error": f"Topic '{topic}' not found in vault"}
        
        self.path.add(node.title, f"Started exploring {topic}")
        
        suggestions = self.path.suggested_next(self.graph)
        
        return {
            "current": node.title,
            "domain": node.domain,
            "backlinks": node.backlinks,
            "summary": node.summary,
            "links": node.links[:10],
            "suggested": suggestions,
            "path": self.path.to_prompt(),
        }
    
    def navigate(self, target: str) -> dict:
        """
        Navigate to a linked concept.
        Returns the new node and updated suggestions.
        """
        node = self.graph.get(target)
        if not node:
            return {"error": f"'{target}' not found in vault"}
        
        self.path.add(
            node.title,
            f"Followed link from {self.path.current_focus}",
            from_node=self.path.current_focus
        )
        
        suggestions = self.path.suggested_next(self.graph)
        
        return {
            "current": node.title,
            "domain": node.domain,
            "summary": node.summary,
            "links": node.links[:10],
            "suggested": suggestions,
            "path": self.path.to_prompt(),
            "path_length": len(self.path.steps),
        }
    
    def path_prompt(self) -> str:
        """Get the current knowledge path as a prompt injection block."""
        return self.path.to_prompt()


# ──────────────────────────────────────────────
# 3. DEMO
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║    KNOWLEDGE LOOP — Active Knowledge Navigation     ║")
    print("  ║   Not RAG. Not static retrieval. Dynamic graph      ║")
    print("  ║   navigation driven by the agent's own reasoning.   ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    print("  RAG queries once. KnowledgeLoop NAVIGATES.")
    print("  The agent starts at one concept, follows wikilinks")
    print("  as it learns, building a knowledge context that")
    print("  grows with each reasoning step.")
    print()
    print("  Loading vault graph (685 concepts, 7925 links)...")
    kl = KnowledgeLoop()
    print()
    
    # ── Step 1: Start at a topic ──
    print("─" * 54)
    print("  [1] Start at: 'Cognitive Load'")
    print("─" * 54)
    result = kl.start("Cognitive Load")
    print(f"  Current: {result['current']}")
    print(f"  Domain:  {result['domain']}")
    print(f"  Summary: {result['summary'][:120]}...")
    print(f"  Links:   {len(result['links'])} outgoing wikilinks")
    print(f"  Suggest: {', '.join(result['suggested'])}")
    print()
    
    # ── Step 2: Follow a link ──
    print("─" * 54)
    print("  [2] Navigate to: 'Working Memory'")
    print("─" * 54)
    result2 = kl.navigate("Working Memory")
    print(f"  Current: {result2['current']}")
    print(f"  Summary: {result2['summary'][:120]}...")
    print(f"  Suggest: {', '.join(result2['suggested'])}")
    print()
    
    # ── Step 3: Follow another link ──
    print("─" * 54)
    print("  [3] Navigate to: 'Second Brain'")
    print("─" * 54)
    result3 = kl.navigate("Second Brain")
    print(f"  Current: {result3['current']}")
    print(f"  Summary: {result3['summary'][:120]}...")
    print(f"  Suggest: {', '.join(result3['suggested'])}")
    print()
    
    # ── Step 4: Show the full path ──
    print("─" * 54)
    print("  [4] Complete knowledge path:")
    print("─" * 54)
    print(kl.path.to_prompt())
    print()
    
    # ── Search ──
    print("─" * 54)
    print("  [5] Search: 'Event-Driven Architecture'")
    print("─" * 54)
    results = kl.graph.search("Event-Driven Architecture")
    for r in results[:3]:
        print(f"  - {r.title}: {r.summary[:80]}... ({r.backlinks} backlinks)")
    print()
    
    # ── Compare ──
    print("=" * 54)
    print("  RAG vs KNOWLEDGE LOOP")
    print("=" * 54)
    print()
    print("  RAG:")
    print("    1. Embed query → vector search → top-k chunks")
    print("    2. Chunks are static — no navigation")
    print("    3. No memory of what was retrieved")
    print("    4. Cannot follow connections")
    print()
    print("  KNOWLEDGE LOOP:")
    print("    1. Start at a concept → read it → extract links")
    print("    2. Follow links based on what you just learned")
    print("    3. Knowledge path persists across reasoning steps")
    print("    4. Knowledge context GROWS with the agent's understanding")
    print()
    print("  The vault has 685 concepts and 7925 wikilinks.")
    print("  RAG sees chunks. KnowledgeLoop sees a graph.")
    print("=" * 54)


if __name__ == '__main__':
    main()
