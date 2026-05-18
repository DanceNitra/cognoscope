"""
self_model.py — Self-Aware Agent Runtime (Level 8)

The RSI stack (L1-L7) can optimize parameters, detect exhaustion
in three spaces, coordinate multi-agent trust, and prove theorems.
But it has ZERO introspection about its own architecture.

The SelfModel fixes this. It maintains a generative model of the
entire RSI stack — what components exist, what they do, how they
connect, and how healthy each connection is.

ARCHITECTURAL PROBLEMS IT DETECTS:
  - Orphaned components (nothing depends on them)
  - Missing connections (two components that SHOULD talk but don't)
  - Over-coupled components (a single SPOF that everything routes through)
  - Under-utilized components (expensively maintained but never used)
  - Structural anti-patterns (e.g., FEPProver not connected to MetaKernel)

ARCHITECTURAL OPERATIONS IT CAN PROPOSE:
  - ADD: a new component at a specific level
  - REMOVE: an orphaned or under-utilized component
  - MERGE: two components with overlapping function
  - SPLIT: a component handling too many responsibilities
  - RECONNECT: reroute a connection through a different component
  - PROMOTE: move a component to a higher level

This is Level 8 because it operates on the architecture ITSELF,
not just on the parameters within it. It's the RSI of RSI —
the system that improves how it improves itself.

Bridge #64: The Self-Aware Agent Runtime — RSI of RSI
"""

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict


# ──────────────────────────────────────────────
# 1. ARCHITECTURE GRAPH
# ──────────────────────────────────────────────

@dataclass
class ComponentNode:
    """A single component in the RSI architecture."""
    name: str
    level: int  # L1 through L8
    description: str
    type: str  # 'executor', 'detector', 'optimizer', 'coordinator', 'prover', 'mirror'
    
    # How many lines of code (proxy for maintenance cost)
    loc: int = 0
    # How much it's been used (proxy for value)
    invocations: int = 0
    # Errors encountered
    errors: int = 0
    
    def value_ratio(self) -> float:
        """Value per line of code. Higher = more efficient."""
        if self.loc == 0:
            return 0.5
        return (self.invocations + 1) / (self.loc + 1) * 100


@dataclass
class ArchitectureEdge:
    """A connection between two components."""
    source: str
    target: str
    type: str  # 'data_flow', 'control', 'monitoring', 'exhaustion_detection'
    weight: float = 1.0  # How much data/control flows through
    healthy: bool = True


@dataclass
class ArchitectureGraph:
    """The complete graph of component connections."""
    nodes: dict[str, ComponentNode] = field(default_factory=dict)
    edges: list[ArchitectureEdge] = field(default_factory=list)
    
    def add_node(self, name: str, level: int, description: str, 
                 type: str, loc: int = 0):
        self.nodes[name] = ComponentNode(
            name=name, level=level, description=description,
            type=type, loc=loc
        )
    
    def add_edge(self, source: str, target: str, type: str, weight: float = 1.0):
        self.edges.append(ArchitectureEdge(
            source=source, target=target, type=type, weight=weight
        ))
    
    def incoming_edges(self, node: str) -> list[ArchitectureEdge]:
        return [e for e in self.edges if e.target == node]
    
    def outgoing_edges(self, node: str) -> list[ArchitectureEdge]:
        return [e for e in self.edges if e.source == node]
    
    def is_orphaned(self, node: str) -> bool:
        """Node has no incoming or outgoing edges."""
        return (len(self.incoming_edges(node)) == 0 
                and len(self.outgoing_edges(node)) == 0)
    
    def is_spof(self, node: str) -> bool:
        """Node is a single point of failure — high-degree hub with no redundancy."""
        if node not in self.nodes:
            return False
        
        node_obj = self.nodes[node]
        all_edges = self.incoming_edges(node) + self.outgoing_edges(node)
        degree = len(all_edges)
        
        # Only hubs can be SPOFs (degree > 2 means significant connectivity)
        # Also leaves and 1-connection nodes are never SPOFs
        if degree <= 2:
            return False
        
        # Check if this node has parallel/sibling alternatives
        # Same-level nodes of the same type might serve as backup
        siblings = [n for n_name, n in self.nodes.items() 
                   if n_name != node and n.level == node_obj.level 
                   and n.type == node_obj.type]
        if len(siblings) >= 1:
            # There's at least one sibling that could take over
            # Only SPOF if sibling can't reach/be reached by same nodes
            for sib in siblings:
                sib_ins = {e.source for e in self.incoming_edges(sib.name)}
                sib_outs = {e.target for e in self.outgoing_edges(sib.name)}
                node_ins = {e.source for e in all_edges if e.target == node}
                node_outs = {e.target for e in all_edges if e.source == node}
                # If sibling connects to similar nodes, it's not a SPOF
                overlap = len(sib_ins & node_ins) + len(sib_outs & node_outs)
                if overlap >= 2:
                    return False
        
        # Check graph connectivity loss
        remaining = [n for n in self.nodes if n != node]
        if len(remaining) < 2:
            return False
        disconnected = 0
        total_pairs = 0
        for i, n1 in enumerate(remaining):
            for n2 in remaining[i+1:]:
                total_pairs += 1
                has_path = self._has_path_without(n1, n2, node)
                if not has_path:
                    disconnected += 1
        return total_pairs > 0 and disconnected / total_pairs > 0.7
    
    def _has_path_without(self, start: str, end: str, 
                          banned: str, visited: set = None) -> bool:
        """Check if there's a path from start to end that avoids banned."""
        if visited is None:
            visited = set()
        if start == end:
            return True
        if start in visited or start == banned:
            return False
        visited.add(start)
        for edge in self.outgoing_edges(start):
            if self._has_path_without(edge.target, end, banned, visited):
                return True
        return False
    
    def connectivity_report(self) -> dict:
        """Report on graph health."""
        orphans = [n for n in self.nodes if self.is_orphaned(n)]
        spofs = [n for n in self.nodes if self.is_spof(n)]
        
        # Degree distribution
        degrees = [len(self.outgoing_edges(n)) + len(self.incoming_edges(n)) 
                  for n in self.nodes]
        avg_degree = statistics.mean(degrees) if degrees else 0
        
        return {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
            'orphans': orphans,
            'spofs': spofs,
            'avg_degree': round(avg_degree, 2),
            'max_degree': max(degrees) if degrees else 0,
        }
    
    def summarize(self) -> str:
        """Text summary of the architecture."""
        lines = ["Architecture Graph Summary:"]
        lines.append(f"  {len(self.nodes)} components, {len(self.edges)} connections")
        
        for level in sorted(set(n.level for n in self.nodes.values())):
            level_nodes = [n for n in self.nodes.values() if n.level == level]
            lines.append(f"\n  L{level}:")
            for n in level_nodes:
                ins = len(self.incoming_edges(n.name))
                outs = len(self.outgoing_edges(n.name))
                lines.append(f"    {n.name:25s} type={n.type:15s} "
                            f"conns={ins+outs} loc={n.loc}")
        
        report = self.connectivity_report()
        if report['orphans']:
            lines.append(f"\n  ⚠ Orphans: {', '.join(report['orphans'])}")
        if report['spofs']:
            lines.append(f"  ⚠ SPOFs: {', '.join(report['spofs'])}")
        
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# 2. ARCHITECTURAL PROBLEM DETECTOR
# ──────────────────────────────────────────────

@dataclass
class ArchitecturalProblem:
    type: str
    severity: float  # 0-1
    description: str
    components: list[str]
    suggestion: str


class ArchitectureAuditor:
    """
    Detects problems in the RSI architecture.
    
    Checks:
    1. Orphaned components (no connections)
    2. Missing expected connections (known anti-patterns)
    3. SPOFs (single-component bottlenecks)
    4. Value ratio anomalies (expensive but unused)
    5. Level violations (component at wrong level)
    """
    
    # Expected connections: (source_type, target_type, edge_type)
    EXPECTED_CONNECTIONS = [
        ('detector', 'optimizer', 'exhaustion_detection'),
        ('detector', 'coordinator', 'exhaustion_detection'),
        ('optimizer', 'executor', 'control'),
        ('coordinator', 'executor', 'data_flow'),
        ('prover', 'detector', 'exhaustion_detection'),
        ('mirror', 'coordinator', 'data_flow'),
    ]
    
    def audit(self, graph: ArchitectureGraph) -> list[ArchitecturalProblem]:
        problems = []
        
        # 1. Orphaned components
        for name in graph.nodes:
            if graph.is_orphaned(name):
                node = graph.nodes[name]
                problems.append(ArchitecturalProblem(
                    type='orphan',
                    severity=0.6,
                    description=f"'{name}' has no connections to any component",
                    components=[name],
                    suggestion=f"Connect '{name}' to another component or remove it "
                              f"(saves {node.loc} lines of maintenance)"
                ))
        
        # 2. SPOFs
        for name in graph.nodes:
            if graph.is_spof(name):
                problems.append(ArchitecturalProblem(
                    type='spof',
                    severity=0.8,
                    description=f"'{name}' is a single point of failure — "
                               f"the graph disconnects without it",
                    components=[name],
                    suggestion=f"Add redundancy for '{name}' or split its "
                              f"responsibilities across multiple components"
                ))
        
        # 3. Missing expected connections
        for src_type, tgt_type, edge_type in self.EXPECTED_CONNECTIONS:
            srcs = [n for n in graph.nodes.values() if n.type == src_type]
            tgts = [n for n in graph.nodes.values() if n.type == tgt_type]
            
            for src in srcs:
                for tgt in tgts:
                    # Check if this connection exists
                    exists = any(
                        e.source == src.name and e.target == tgt.name
                        for e in graph.edges
                    )
                    if not exists:
                        problems.append(ArchitecturalProblem(
                            type='missing_connection',
                            severity=0.5,
                            description=f"'{src.name}' ({src_type}) should connect "
                                       f"to '{tgt.name}' ({tgt_type}) but doesn't",
                            components=[src.name, tgt.name],
                            suggestion=f"Add a {edge_type} connection from "
                                      f"'{src.name}' to '{tgt.name}'"
                        ))
        
        # 4. Value ratio anomalies
        for name, node in graph.nodes.items():
            if node.loc > 200:  # Expensive component
                vr = node.value_ratio()
                if vr < 0.5:  # Low value per line
                    problems.append(ArchitecturalProblem(
                        type='low_value',
                        severity=0.4,
                        description=f"'{name}' costs {node.loc} LOC but has "
                                   f"low value ratio ({vr:.2f})",
                        components=[name],
                        suggestion=f"Consider simplifying '{name}' or removing "
                                  f"under-utilized functionality"
                    ))
        
        # 5. Level violations
        for name, node in graph.nodes.items():
            if node.type == 'executor' and node.level > 4:
                problems.append(ArchitecturalProblem(
                    type='level_violation',
                    severity=0.3,
                    description=f"'{name}' is type 'executor' at L{node.level} "
                               f"— executors typically belong at L1-L4",
                    components=[name],
                    suggestion=f"Move '{name}' to L1-L4 or reclassify its type"
                ))
        
        return problems


# ──────────────────────────────────────────────
# 3. ARCHITECTURE EVOLUTION ENGINE
# ──────────────────────────────────────────────

class ArchitectureEvolution:
    """
    Proposes and applies architectural changes.
    
    Operations:
    - ADD_COMPONENT: create a new component
    - REMOVE_COMPONENT: delete a component
    - MERGE_COMPONENTS: combine two into one
    - SPLIT_COMPONENT: divide one into two
    - RECONNECT: change a connection
    - PROMOTE: move to higher level
    """
    
    def __init__(self):
        self.operations_applied: list[dict] = []
    
    def propose(self, problem: ArchitecturalProblem) -> dict:
        """Propose an architectural change to fix a problem."""
        if problem.type == 'orphan':
            return {
                'operation': 'RECONNECT',
                'components': problem.components,
                'description': f"Connect '{problem.components[0]}' to the most "
                              f"relevant upstream component",
                'rationale': problem.suggestion,
                'risk': 'low',
            }
        elif problem.type == 'spof':
            return {
                'operation': 'SPLIT',
                'components': problem.components,
                'description': f"Split '{problem.components[0]}' into two "
                              f"independent instances for redundancy",
                'rationale': problem.suggestion,
                'risk': 'medium',
            }
        elif problem.type == 'missing_connection':
            return {
                'operation': 'RECONNECT',
                'components': problem.components,
                'description': f"Add edge from '{problem.components[0]}' "
                              f"to '{problem.components[1]}'",
                'rationale': problem.suggestion,
                'risk': 'low',
            }
        elif problem.type == 'low_value':
            return {
                'operation': 'REMOVE',
                'components': problem.components,
                'description': f"Remove '{problem.components[0]}' or "
                              f"extract core functionality to a smaller component",
                'rationale': problem.suggestion,
                'risk': 'medium',
            }
        else:
            return {
                'operation': 'RECONNECT',
                'components': problem.components,
                'description': f"Review and adjust '{problem.components[0]}'",
                'rationale': problem.suggestion,
                'risk': 'low',
            }
    
    def apply(self, graph: ArchitectureGraph, proposal: dict) -> str:
        """Apply the proposal and return a summary."""
        op = proposal['operation']
        comps = proposal['components']
        
        if op == 'RECONNECT' and len(comps) >= 2:
            # Reconnect: remove old edges from first component,
            # add new edge to second
            src = comps[0]
            tgt = comps[1]
            # Remove all outgoing edges from src
            graph.edges = [e for e in graph.edges if e.source != src]
            # Add new connection
            graph.add_edge(src, tgt, 'data_flow')
            result = f"Reconnected '{src}' → '{tgt}'"
        
        elif op == 'SPLIT' and comps:
            name = comps[0]
            node = graph.nodes.get(name)
            if node:
                # Create two instances
                graph.add_node(f"{name}_1", node.level, 
                              f"{node.description} (instance 1)", node.type, node.loc // 2)
                graph.add_node(f"{name}_2", node.level,
                              f"{node.description} (instance 2)", node.type, node.loc // 2)
                # Copy edges to both
                for edge in graph.edges:
                    if edge.source == name:
                        graph.add_edge(f"{name}_1", edge.target, edge.type, edge.weight * 0.5)
                        graph.add_edge(f"{name}_2", edge.target, edge.type, edge.weight * 0.5)
                    if edge.target == name:
                        graph.add_edge(edge.source, f"{name}_1", edge.type, edge.weight * 0.5)
                        graph.add_edge(edge.source, f"{name}_2", edge.type, edge.weight * 0.5)
                # Remove original
                del graph.nodes[name]
                graph.edges = [e for e in graph.edges 
                              if e.source != name and e.target != name]
                result = f"Split '{name}' into '{name}_1' and '{name}_2'"
            else:
                result = f"Cannot split '{name}': not found"
        
        elif op == 'REMOVE' and comps:
            name = comps[0]
            if name in graph.nodes:
                del graph.nodes[name]
                graph.edges = [e for e in graph.edges 
                              if e.source != name and e.target != name]
                result = f"Removed '{name}' from architecture"
            else:
                result = f"Cannot remove '{name}': not found"
        
        else:
            result = f"No action taken for proposal: {proposal}"
        
        self.operations_applied.append({
            'operation': op,
            'result': result,
            'components': comps,
        })
        return result


# ──────────────────────────────────────────────
# 4. SELF MODEL — The Full L8 System
# ──────────────────────────────────────────────

class SelfModel:
    """
    The Self-Aware Agent Runtime (Level 8).
    
    Maintains:
    - An ArchitectureGraph of all components
    - An ArchitectureAuditor that detects structural problems
    - An ArchitectureEvolution that proposes and applies fixes
    
    The SelfModel runs periodically (every N generations) to:
    1. Update the architecture graph with current component state
    2. Audit for problems
    3. Propose architectural changes
    4. Apply the highest-priority fix
    
    This is the RSI of RSI — the system that improves how it improves itself.
    """
    
    def __init__(self):
        self.graph = ArchitectureGraph()
        self.auditor = ArchitectureAuditor()
        self.evolution = ArchitectureEvolution()
        self.generation = 0
        self.audit_history: list[list[ArchitecturalProblem]] = []
        self.proposals_applied: list[str] = []
    
    def register_cognoscope(self):
        """Register all cognoscope components in the architecture graph."""
        g = self.graph
        
        # Level 1: Execution
        g.add_node('react_loop', 1, 'Perceive → think → act cycle', 'executor', 300)
        g.add_node('tool_calls', 1, 'Hermes tool execution', 'executor', 150)
        
        # Level 2: Meta-inference
        g.add_node('metaloloop', 2, 'Reconfigures reasoning parameters', 'optimizer', 200)
        g.add_node('recovery', 2, 'Detects degradation and recovers', 'detector', 180)
        
        # Level 3: Guardrail
        g.add_node('msr', 3, 'Guardrail homeostasis (Goldilocks zone)', 'detector', 250)
        
        # Level 4: Tool creation
        g.add_node('toolforge', 4, 'Synthesizes new tools from descriptions', 'executor', 380)
        g.add_node('rewriting_toolforge', 5, 'Rewrites existing tool code via AST', 'executor', 460)
        g.add_node('code_cmp', 6, 'Computes CMP for code lineages', 'detector', 200)
        
        # Level 5: RSI Kernel
        g.add_node('rsi_kernel', 5, 'Coupling optimization (L5 actions)', 'optimizer', 400)
        g.add_node('clade_tracker', 5, 'Tracks agent lineages, computes CMP', 'detector', 200)
        
        # Level 6: Meta-Kernel
        g.add_node('csd_detector', 6, 'Critical Slowing Down on free energy', 'detector', 180)
        g.add_node('parameter_genotype', 6, 'Genotype grammar for parameter spaces', 'optimizer', 120)
        g.add_node('meta_kernel', 6, 'Paradigm shift engine (L6 orchestrator)', 'optimizer', 200)
        
        # Level 7: Multi-agent
        g.add_node('social_mirror', 7, 'Recursive belief modeling (ToM)', 'mirror', 250)
        g.add_node('talent_market', 7, 'E²R loop for agent pool', 'coordinator', 500)
        
        # Level 7.5: Mathematics
        g.add_node('axiom_space', 5, 'Axiom + theorem space for proofs', 'executor', 150)
        g.add_node('fep_prover', 5, 'FEP-guided theorem prover', 'prover', 500)
        
        # Level 8 (this model)
        g.add_node('self_model', 8, 'Self-aware architecture model', 'detector', 30)
        
        # ── Edges ──
        g.add_edge('react_loop', 'tool_calls', 'control', 1.0)
        g.add_edge('tool_calls', 'metaloloop', 'monitoring', 0.5)
        g.add_edge('metaloloop', 'recovery', 'exhaustion_detection', 0.7)
        g.add_edge('recovery', 'msr', 'exhaustion_detection', 0.6)
        g.add_edge('msr', 'rsi_kernel', 'exhaustion_detection', 0.5)
        g.add_edge('toolforge', 'rewriting_toolforge', 'data_flow', 0.8)
        g.add_edge('rewriting_toolforge', 'code_cmp', 'exhaustion_detection', 0.6)
        g.add_edge('code_cmp', 'meta_kernel', 'exhaustion_detection', 0.5)
        g.add_edge('rsi_kernel', 'clade_tracker', 'monitoring', 0.3)
        g.add_edge('csd_detector', 'meta_kernel', 'exhaustion_detection', 0.8)
        g.add_edge('parameter_genotype', 'meta_kernel', 'data_flow', 0.6)
        g.add_edge('meta_kernel', 'rsi_kernel', 'control', 0.9)
        g.add_edge('social_mirror', 'talent_market', 'data_flow', 0.7)
        g.add_edge('talent_market', 'rsi_kernel', 'monitoring', 0.4)
        g.add_edge('axiom_space', 'fep_prover', 'data_flow', 0.9)
        g.add_edge('fep_prover', 'meta_kernel', 'exhaustion_detection', 0.3)
        g.add_edge('self_model', 'meta_kernel', 'exhaustion_detection', 0.2)
    
    def run_audit(self) -> list[ArchitecturalProblem]:
        """Run a full architectural audit."""
        self.generation += 1
        problems = self.auditor.audit(self.graph)
        self.audit_history.append(problems)
        return problems
    
    def run_evolution(self, problems: list[ArchitecturalProblem]) -> list[str]:
        """Propose and apply fixes for the top problems."""
        results = []
        
        # Sort by severity
        sorted_problems = sorted(problems, key=lambda p: p.severity, reverse=True)
        
        for problem in sorted_problems[:3]:  # Top 3
            proposal = self.evolution.propose(problem)
            result = self.evolution.apply(self.graph, proposal)
            results.append(f"[{problem.severity:.0%}] {result}")
            self.proposals_applied.append(result)
        
        return results
    
    def status_report(self) -> dict:
        """Full L8 status."""
        report = self.graph.connectivity_report()
        problems = self.run_audit()
        
        return {
            'generation': self.generation,
            'audits_run': len(self.audit_history),
            'problems_found': len(problems),
            'top_problems': [
                {'type': p.type, 'severity': p.severity, 
                 'desc': p.description[:60]}
                for p in sorted(problems, key=lambda p: p.severity, reverse=True)[:5]
            ],
            'proposals_applied': len(self.proposals_applied),
            'connectivity': report,
            'graph_summary': self.graph.summarize(),
        }


# ──────────────────────────────────────────────
# 5. DEMO — Self-Aware Agent Runtime
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════════════╗")
    print("  ║      SELF-AWARE AGENT RUNTIME — Level 8                         ║")
    print("  ║    The system that knows its own architecture and evolves it    ║")
    print("  ╚══════════════════════════════════════════════════════════════════╝")
    print()
    
    model = SelfModel()
    model.register_cognoscope()
    
    # Phase 1: Architecture Discovery
    print("─" * 64)
    print("  Phase 1: Architecture Discovery")
    print("─" * 64)
    print()
    print(model.graph.summarize())
    print()
    
    # Phase 2: Audit
    print("─" * 64)
    print("  Phase 2: Architectural Audit")
    print("─" * 64)
    print()
    
    problems = model.run_audit()
    
    if problems:
        print(f"  Found {len(problems)} architectural issues:")
        print()
        for p in sorted(problems, key=lambda x: x.severity, reverse=True):
            bar = "█" * int(p.severity * 10) + "░" * (10 - int(p.severity * 10))
            print(f"  [{bar}] {p.type:22s} {p.description[:70]}")
            if p.severity >= 0.5:
                print(f"        → {p.suggestion[:70]}")
            print()
    else:
        print("  No issues found. Architecture is healthy.")
        print()
    
    # Phase 3: Evolution
    print("─" * 64)
    print("  Phase 3: Architecture Evolution")
    print("─" * 64)
    print()
    
    if problems:
        changes = model.run_evolution(problems)
        print("  Applied changes:")
        for c in changes:
            print(f"    {c}")
        print()
    
    # Phase 4: Summary
    print("─" * 64)
    print("  Self-Aware Runtime Summary")
    print("─" * 64)
    print()
    
    s = model.status_report()
    print(f"  Audits run:          {s['audits_run']}")
    print(f"  Problems found:      {s['problems_found']}")
    print(f"  Proposals applied:   {s['proposals_applied']}")
    print()
    
    top = s.get('top_problems', [])
    if top:
        print("  Top problems:")
        for p in top:
            print(f"    [{p['severity']:.0%}] {p['type']}: {p['desc']}")
        print()
    
    conn = s.get('connectivity', {})
    print(f"  Graph: {conn.get('total_nodes', 0)} nodes, "
          f"{conn.get('total_edges', 0)} edges")
    print(f"  Orphans: {len(conn.get('orphans', []))}")
    print(f"  SPOFs: {len(conn.get('spofs', []))}")
    print(f"  Avg degree: {conn.get('avg_degree', 0)}")
    print()
    
    print("═" * 64)
    print("  Level 8 is the RSI of RSI:")
    print("  L1-L7 optimize within the architecture.")
    print("  L8 optimizes the architecture itself.")
    print()
    print("  Every component, every connection, every level")
    print("  is visible to the SelfModel. It detects structural")
    print("  flaws, proposes fixes, and evolves the stack.")
    print()
    print("  This is how the system redesigns itself.")
    print("═" * 64)


if __name__ == '__main__':
    main()
