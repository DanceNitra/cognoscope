#!/usr/bin/env python3
"""
vault_reasoning_api.py — HTTP Reasoning API for the Vault Graph.

Any agent (Codex, Claude Code, Cursor, your future self) can ask
questions and get reasoning paths grounded in 706 concepts × 7,205 edges.

Endpoints:
  GET  /health              — Health check
  GET  /concept/<name>      — Get a concept node's details
  GET  /search?q=<query>    — Search concepts by keyword
  GET  /paths?limit=N       — Auto-discover N novel reasoning paths
  POST /reason              — Submit a question, get a reasoning chain
  POST /bridge              — Generate a bridge publication from a discovered path
  GET  /stats               — Vault graph statistics

Usage:
    python3 vault_reasoning_api.py [--port 8080] [--host 0.0.0.0]
"""

import os, sys, json, re, glob, math, random
from collections import deque, defaultdict
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Any
from io import BytesIO
import traceback


# ──────────────────────────────────────────────
# VAULT GRAPH (lightweight, self-contained)
# ──────────────────────────────────────────────

VAULT_PATH = os.path.expanduser("~/Obsidian Vault/04 Resources/Concepts")
PUBLICATIONS_PATH = os.path.expanduser("~/Obsidian Vault/04 Resources/Publications")
CACHE_FILE = "/tmp/vault_reasoning_cache.json"

@dataclass
class ConceptNode:
    title: str
    links: list[str]
    backlinks: int
    domain: str
    phi: float
    lines: int
    summary: str
    status: str

    def is_good(self) -> bool:
        return self.lines >= 20 and self.phi >= 0.1

    def to_dict(self) -> dict:
        return {
            'title': self.title,
            'links': self.links[:15],
            'link_count': len(self.links),
            'backlinks': self.backlinks,
            'domain': self.domain,
            'phi': self.phi,
            'lines': self.lines,
            'summary': self.summary[:300],
            'status': self.status,
        }


class VaultGraph:
    """Reads vault concepts into a navigable graph."""

    DOMAIN_ALIASES = {
        'neuroscience': 'Neuroscience', 'sleep': 'Sleep Science',
        'psychology': 'Psychology', 'finance': 'Finance',
        'causal-inference': 'Statistics', 'statistics': 'Statistics',
        'ai': 'AI', 'agents': 'AI / Agents', 'machine-learning': 'ML',
        'software-engineering': 'Software Engineering',
        'complexity': 'Complexity Science', 'systems-thinking': 'Complexity Science',
        'philosophy': 'Philosophy', 'physiology': 'Physiology',
        'endocrine': 'Physiology', 'immunology': 'Immunology',
    }

    def __init__(self):
        self.nodes: dict[str, ConceptNode] = {}
        self.domains: dict[str, set[str]] = defaultdict(set)
        self._build()
        self._cache()

    def _extract_domain(self, content: str) -> str:
        m = re.search(r'domain:\s*(.+?)\n', content)
        if m:
            d = m.group(1).strip()
            if d and len(d) < 60:
                return d
        tag_lines = []
        in_tags = False
        for line in content.split('\n'):
            s = line.strip()
            if s.startswith('tags:'):
                in_tags = True
                rest = s.split(':', 1)[1].strip()
                if not rest.startswith('['):
                    tag_lines.append(rest)
            elif in_tags and (s.startswith('- ') or s.startswith('  - ')):
                tag_lines.append(s.lstrip('- ').strip())
            elif in_tags and not s:
                in_tags = False
        m2 = re.search(r'tags:\s*\[(.+?)\]', content)
        if m2:
            tag_lines += [t.strip() for t in m2.group(1).split(',')]
        all_tags = ' '.join(t.lower() for t in tag_lines if t)
        for key, val in self.DOMAIN_ALIASES.items():
            if key in all_tags:
                return val
        return "Unknown"

    def _extract_summary(self, content: str) -> str:
        body = content.split('---')[-1] if content.count('---') > 1 else content
        for line in body.split('\n'):
            s = line.strip()
            if s and not s.startswith('#') and not s.startswith('>') \
               and not s.startswith('|') and not s.startswith('-') \
               and not s.lower().startswith('related:') and len(s) > 20:
                return s[:300]
        return ""

    def _compute_phi(self, links: int, backlinks: int, lines: int) -> float:
        ls = min(links, 30) / 30 * 0.3
        bs = min(backlinks, 50) / 50 * 0.4
        ss = min(lines, 200) / 200 * 0.3
        return round(ls + bs + ss, 4)

    def _build(self):
        all_files = {}
        backlinks = {}
        for f in glob.glob(os.path.join(VAULT_PATH, "*.md")):
            t = os.path.splitext(os.path.basename(f))[0]
            all_files[t] = f
            backlinks[t] = 0

        outgoing = {}
        statuses = {}
        line_counts = {}
        domains = {}
        summaries = {}

        for title, path in all_files.items():
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
            except:
                continue
            links = []
            for m in re.finditer(r'\[\[([^\]|]+)', content):
                target = m.group(1).split('#')[0].strip()
                if target in all_files and target != title:
                    links.append(target)
                    backlinks[target] = backlinks.get(target, 0) + 1
            outgoing[title] = links
            domains[title] = self._extract_domain(content)
            sm = re.search(r'status:\s*(evergreen|growing|seedling)', content)
            statuses[title] = sm.group(1) if sm else "Unknown"
            line_counts[title] = len(content.split('\n'))
            summaries[title] = self._extract_summary(content)

        for title in all_files:
            links = outgoing.get(title, [])
            bl = backlinks.get(title, 0)
            lines = line_counts.get(title, 0)
            dom = domains.get(title, "Unknown")
            phi = self._compute_phi(len(links), bl, lines)
            self.nodes[title] = ConceptNode(
                title=title, links=links, backlinks=bl,
                domain=dom, phi=phi, lines=lines,
                summary=summaries.get(title, title),
                status=statuses.get(title, "Unknown"))
            self.domains[dom].add(title)

    def _cache(self):
        try:
            data = {t: n.to_dict() for t, n in self.nodes.items()}
            data['_meta'] = {
                'node_count': len(self.nodes),
                'edge_count': sum(len(n.links) for n in self.nodes.values()),
                'domain_count': len(self.domains),
            }
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f)
        except:
            pass

    def get(self, title: str) -> ConceptNode | None:
        if title in self.nodes:
            return self.nodes[title]
        tl = title.lower()
        for t, n in self.nodes.items():
            if t.lower() == tl or tl in t.lower():
                return n
        return None

    def search(self, query: str, limit: int = 10) -> list[ConceptNode]:
        q = query.lower()
        scored = []
        for n in self.nodes.values():
            s = 0
            if q in n.title.lower():
                s += 10
            if q in n.domain.lower():
                s += 3
            if q in n.summary.lower():
                s += 2
            scored.append((s, n))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[:limit]]

    def stats(self) -> dict:
        domains_detail = {}
        for d, nodes in self.domains.items():
            phis = [self.nodes[t].phi for t in nodes if t in self.nodes]
            domains_detail[d] = {
                'count': len(nodes),
                'avg_phi': round(sum(phis)/len(phis), 3) if phis else 0,
            }
        return {
            'concepts': len(self.nodes),
            'edges': sum(len(n.links) for n in self.nodes.values()),
            'domains': len(self.domains),
            'evergreen': sum(1 for n in self.nodes.values() if n.status == 'evergreen'),
            'avg_phi': round(sum(n.phi for n in self.nodes.values()) / max(len(self.nodes), 1), 3),
            'domains_detail': dict(sorted(domains_detail.items(), key=lambda x: -x[1]['count'])[:20]),
        }


# ──────────────────────────────────────────────
# REASONING PATH FINDER
# ──────────────────────────────────────────────

class ReasoningPathFinder:
    """Quick path finder using the loaded graph."""

    def __init__(self, graph: VaultGraph):
        self.graph = graph

    def find_path(self, start: str, end: str, max_hops: int = 6) -> dict | None:
        s = self.graph.get(start)
        e = self.graph.get(end)
        if not s or not e:
            return None

        # BFS
        from collections import deque
        q = deque()
        q.append((s.title, [s.title]))
        visited = {s.title}

        while q:
            current, path = q.popleft()
            if len(path) > max_hops + 1:
                continue
            node = self.graph.nodes.get(current)
            if not node:
                continue
            for link in node.links:
                if link == e.title:
                    full_path = path + [link]
                    return self._build_result(full_path)
                if link not in visited and link in self.graph.nodes:
                    link_n = self.graph.nodes[link]
                    if link_n.is_good():
                        visited.add(link)
                        q.append((link, path + [link]))
        return None

    def find_path_between(self, a_title: str, b_title: str, max_hops: int = 6) -> list[dict]:
        """Find multiple paths between two concepts. Returns up to 3 paths."""
        start = self.graph.get(a_title)
        end = self.graph.get(b_title)
        if not start or not end:
            return []

        paths = []
        q = deque()
        q.append((start.title, [start.title], set([start.title])))

        while q and len(paths) < 3:
            current, path, visited = q.popleft()
            if len(path) > max_hops + 1:
                continue
            node = self.graph.nodes.get(current)
            if not node:
                continue
            for link in node.links:
                if link in visited:
                    continue
                link_n = self.graph.nodes.get(link)
                if not link_n or not link_n.is_good():
                    continue
                new_path = path + [link]
                if link == end.title:
                    paths.append(self._build_result(new_path))
                    continue
                new_visited = visited | {link}
                q.append((link, new_path, new_visited))
        return paths

    def _build_result(self, titles: list[str]) -> dict:
        steps = []
        for i, t in enumerate(titles):
            n = self.graph.nodes.get(t)
            if n:
                steps.append(n.to_dict())
            else:
                steps.append({'title': t, 'domain': '?', 'phi': 0, 'links': []})
        domains = [s['domain'] for s in steps if s.get('domain')]
        unique_domains = len(set(d for d in domains if d != 'Unknown'))
        return {
            'path': titles,
            'steps': steps,
            'hop_count': len(titles) - 1,
            'unique_domains': unique_domains,
            'domain_chain': ' → '.join(domains),
            'avg_phi': round(sum(s.get('phi', 0) for s in steps) / max(len(steps), 1), 3),
        }

    def reason(self, question: str, limit: int = 5) -> dict:
        """
        Given a natural language question, find relevant concepts and
        build reasoning paths between them.
        """
        # Extract key terms from the question
        words = question.lower().split()
        # Find concepts matching key terms
        concepts = self.graph.search(question, limit=15)
        if len(concepts) < 2:
            return {
                'question': question,
                'found_concepts': [c.title for c in concepts],
                'paths': [],
                'answer': "Not enough matching concepts found in vault to build a reasoning path.",
            }

        # Try to find paths between the top concepts
        paths = []
        for i in range(min(len(concepts), 8)):
            for j in range(i + 1, min(len(concepts), 8)):
                a, b = concepts[i].title, concepts[j].title
                result = self.find_path(a, b, max_hops=4)
                if result:
                    paths.append(result)
                if len(paths) >= limit:
                    break
            if len(paths) >= limit:
                break

        paths.sort(key=lambda p: -p['avg_phi'])

        # Generate a text answer from the best path
        answer = ""
        if paths:
            best = paths[0]
            answer = (f"I found a {best['hop_count']}-hop reasoning path through "
                      f"{best['unique_domains']} domains: {best['domain_chain']}. "
                      f"The path connects {best['path'][0]} → "
                      f"{' → '.join(best['path'][1:-1])} → {best['path'][-1]}." 
                      if len(best['path']) > 2 else
                      f"The path connects {best['path'][0]} → {best['path'][1]} "
                      f"across {best['unique_domains']} domains.")
        else:
            answer = f"Found {len(concepts)} related concepts but couldn't connect them. Try a more specific question."
            if concepts:
                answer += f" Related concepts: {', '.join(c.title for c in concepts[:6])}."

        return {
            'question': question,
            'found_concepts': [c.title for c in concepts[:10]],
            'paths': paths[:limit],
            'path_count': len(paths),
            'answer': answer,
        }


# ──────────────────────────────────────────────
# HTTP HANDLER
# ──────────────────────────────────────────────

class VaultReasoningHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the vault reasoning API."""

    # Shared state (set at module level before server starts)
    graph: VaultGraph = None
    finder: ReasoningPathFinder = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        params = parse_qs(parsed.query)

        try:
            if path == '/health':
                self._json({'status': 'ok', 'concepts': len(self.graph.nodes)})

            elif path == '/stats':
                self._json(self.graph.stats())

            elif path.startswith('/concept/'):
                name = path[len('/concept/'):]
                node = self.graph.get(name)
                if node:
                    self._json(node.to_dict())
                else:
                    self._json({'error': f"Concept '{name}' not found"}, 404)

            elif path == '/search':
                q = params.get('q', [''])[0]
                if not q:
                    self._json({'error': 'Missing ?q= query parameter'}, 400)
                    return
                results = self.graph.search(q)
                self._json({
                    'query': q,
                    'results': [n.to_dict() for n in results],
                    'count': len(results),
                })

            elif path == '/paths':
                limit = int(params.get('limit', ['5'])[0])
                # Sample random concept pairs, find paths
                good_nodes = [n for n in self.graph.nodes.values() if n.is_good() and n.domain != 'Unknown']
                if len(good_nodes) < 10:
                    self._json({'paths': [], 'count': 0})
                    return
                random.shuffle(good_nodes)
                found = []
                for i in range(min(30, len(good_nodes))):
                    for j in range(i + 1, min(30, len(good_nodes))):
                        a, b = good_nodes[i].title, good_nodes[j].title
                        if a == b:
                            continue
                        result = self.finder.find_path(a, b, max_hops=4)
                        if result:
                            found.append(result)
                            if len(found) >= limit:
                                break
                    if len(found) >= limit:
                        break
                found.sort(key=lambda p: -p['avg_phi'])
                self._json({
                    'paths': found[:limit],
                    'count': min(len(found), limit),
                })

            elif path == '/answer':
                q = params.get('q', [''])[0]
                if not q:
                    self._json({'error': 'Missing ?q= query'}, 400)
                    return
                result = self.finder.reason(q)
                self._json(result)

            else:
                self._json({'error': f'Unknown endpoint: {path}', 'endpoints': [
                    '/health', '/stats', '/concept/<name>', '/search?q=',
                    '/paths?limit=5', '/answer?q=',
                ]}, 404)

        except Exception as e:
            self._json({'error': str(e), 'traceback': traceback.format_exc()}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            data = json.loads(body) if body else {}

            if path == '/reason':
                question = data.get('question', '')
                if not question:
                    self._json({'error': 'Missing "question" in request body'}, 400)
                    return
                max_paths = data.get('max_paths', 3)
                result = self.finder.reason(question, limit=max_paths)
                self._json(result)

            elif path == '/bridge':
                # Generate a bridge from a specific path
                start = data.get('start')
                end = data.get('end')
                if not start or not end:
                    self._json({'error': 'Missing "start" and/or "end" in request body'}, 400)
                    return
                result = self.finder.find_path(start, end, max_hops=5)
                if result:
                    self._json({
                        'success': True,
                        'path': result,
                        'message': f"Bridge draft ready: {start} → {end} "
                                  f"({result['hop_count']} hops, {result['unique_domains']} domains)",
                    })
                else:
                    self._json({'success': False, 'error': f'No path found between {start} and {end}'}, 404)

            elif path == '/bridge/from':
                # Accept a list of concept titles as a pre-defined path
                titles = data.get('path', [])
                if len(titles) < 2:
                    self._json({'error': 'Need at least 2 concepts in "path" array'}, 400)
                    return
                result = self.finder._build_result(titles)
                self._json({
                    'success': True,
                    'path': result,
                })

            else:
                self._json({'error': f'Unknown POST endpoint: {path}'}, 404)

        except json.JSONDecodeError:
            self._json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            self._json({'error': str(e), 'traceback': traceback.format_exc()}, 500)

    def _json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        sys.stderr.write(f"[VAULT API] {args[0]} {args[1]} {args[2]}\n")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault Reasoning API")
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--daemon', action='store_true', help='Print daemon info')
    args = parser.parse_args()

    print(f"  Loading vault graph from {VAULT_PATH}...", file=sys.stderr)
    graph = VaultGraph()
    finder = ReasoningPathFinder(graph)

    VaultReasoningHandler.graph = graph
    VaultReasoningHandler.finder = finder

    stats = graph.stats()
    print(f"  Loaded {stats['concepts']} concepts, {stats['edges']} edges, "
          f"{stats['domains']} domains", file=sys.stderr)
    print(f"  Cached to {CACHE_FILE}", file=sys.stderr)
    print(file=sys.stderr)

    if args.daemon:
        print(f"VAULT_API_HOST={args.host}")
        print(f"VAULT_API_PORT={args.port}")
        print(f"VAULT_API_URL=http://{args.host}:{args.port}")
        print(f"VAULT_CONCEPTS={stats['concepts']}")
        print(f"VAULT_EDGES={stats['edges']}")
        print(f"VAULT_DOMAINS={stats['domains']}")
        return

    server = HTTPServer((args.host, args.port), VaultReasoningHandler)
    print(f"  Vault Reasoning API running on http://{args.host}:{args.port}", file=sys.stderr)
    print(f"  Endpoints:", file=sys.stderr)
    print(f"    GET  /health              — Health check", file=sys.stderr)
    print(f"    GET  /stats               — Vault statistics", file=sys.stderr)
    print(f"    GET  /concept/<name>      — Concept details", file=sys.stderr)
    print(f"    GET  /search?q=<query>    — Search concepts", file=sys.stderr)
    print(f"    GET  /paths?limit=5       — Auto-discover paths", file=sys.stderr)
    print(f"    GET  /answer?q=<question> — Quick answer (GET)", file=sys.stderr)
    print(f"    POST /reason              — Submit question for reasoning", file=sys.stderr)
    print(f"    POST /bridge              — Generate bridge between 2 concepts", file=sys.stderr)
    print(f"    POST /bridge/from         — Generate bridge from explicit path", file=sys.stderr)
    print(file=sys.stderr)
    print(f"  Example: curl http://{args.host}:{args.port}/answer?q=how+does+sleep+affect+cognition", file=sys.stderr)
    print(f"  Example: curl -X POST http://{args.host}:{args.port}/reason \\", file=sys.stderr)
    print(f'           -d \'{{\\"question\\":\\"how does sleep affect cognition\\"}}\'', file=sys.stderr)
    print(file=sys.stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...", file=sys.stderr)
        server.server_close()


if __name__ == '__main__':
    main()
