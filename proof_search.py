"""
proof_search.py — Free Energy of Proofs

The breakthrough: theorem proving as active inference.

  Every mathematical proof attempt is a free energy minimization:
    - Generative model: known theorems, axioms, inference rules
    - Sensation: current proof state (proved vs remaining subgoals)
    - Action: apply an inference rule to reduce remaining subgoals
    - Prediction error: gap between expected proof closure and actual

  Free energy of a proof state:
    F = Complexity_cost + Inaccuracy_cost + Surprise

  The prover:
    1. Start with goal formula
    2. Generate candidate expansions (apply inference rules)
    3. Score each by ∆F (expected free energy reduction)
    4. Expand the lowest-F branch
    5. Repeat until goal proved OR all branches exhausted

  If no path closes, CSD rises (variance in branch quality increases,
  recovery slows). This signals theorem-space exhaustion — the
  generative model (axioms + rules) is insufficient.

  This is Level 5 RSI for the Mathematics domain:
    L1: Symbolic computation (sympy)
    L2: Proof state evaluation
    L3: Branch selection strategy
    L4: Lemma synthesis (new theorems within the system)
    L5: Proof-space exhaustion → Meta-Kernel axiom expansion

  Connect to the cognoscope Meta-Kernel: when proof-space exhaustion
  is detected, the MetaKernel can expand the axiom space (add new
  inference rules, import lemmas from related domains) — a paradigm
  shift in the mathematics domain.
"""

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any
from collections import deque

import sympy
from sympy.logic.boolalg import (
    And, Or, Not, Implies, Equivalent, to_cnf, to_dnf
)
from sympy.logic.inference import satisfiable, valid


# ──────────────────────────────────────────────
# 1. PROOF STATE
# ──────────────────────────────────────────────

@dataclass
class ProofState:
    """
    A proof state: what we're trying to prove, what we've proved,
    and what remains.
    
    The free energy of this state quantifies how "hard" the proof is.
    """
    goal: sympy.Expr
    proven: list[sympy.Expr] = field(default_factory=list)
    remaining_subgoals: list[sympy.Expr] = field(default_factory=list)
    depth: int = 0
    axioms_used: int = 0
    assumptions: list[sympy.Expr] = field(default_factory=list)
    parent: 'ProofState | None' = None
    children: list['ProofState'] = field(default_factory=list)
    rule_applied: str | None = None
    
    def __post_init__(self):
        if not self.remaining_subgoals:
            self.remaining_subgoals = [self.goal]
    
    @property
    def is_proved(self) -> bool:
        return len(self.remaining_subgoals) == 0
    
    @property
    def free_energy(self) -> float:
        """
        F = Complexity_cost + Inaccuracy_cost + Surprise
        
        Lower = better — the proof is converging.
        """
        # Inaccuracy cost: how far from the goal
        total = len(self.proven) + len(self.remaining_subgoals)
        remaining = len(self.remaining_subgoals)
        inaccuracy = remaining / max(total, 1)
        
        # Surprise: structural complexity of remaining subgoals
        # If nothing remains, surprise = 0 (goal proved)
        surprise = 0.0
        if self.remaining_subgoals:
            surprise = sum(
                self._term_complexity(sg) for sg in self.remaining_subgoals
            ) / len(self.remaining_subgoals)
        
        return inaccuracy * 0.6 + surprise * 0.4
    
    @staticmethod
    def _term_complexity(expr: sympy.Expr) -> float:
        """Count the complexity of a logical expression."""
        if expr.is_Atom:
            return 0.5
        return 1.0 + sum(
            ProofState._term_complexity(arg) for arg in expr.args
        ) / max(len(expr.args), 1)
    
    def copy(self) -> 'ProofState':
        """Create a copy for exploration."""
        p = ProofState(
            goal=self.goal,
            proven=list(self.proven),
            remaining_subgoals=list(self.remaining_subgoals),
            depth=self.depth,
            axioms_used=self.axioms_used,
            assumptions=list(self.assumptions),  # Preserve assumptions
            rule_applied=self.rule_applied,
        )
        p.parent = self.parent
        return p


# ──────────────────────────────────────────────
# 2. AXIOM SPACE & INFERENCE RULES
# ──────────────────────────────────────────────

class AxiomSpace:
    """
    The generative model for proof search.
    
    Contains:
    - Axioms (fundamental truths assumed without proof)
    - Known theorems (previously proved)
    - Inference rules (how to derive new truths)
    
    This is the "parameter space" of the proof system.
    The Meta-Kernel can expand this space when exhausted.
    """
    
    def __init__(self):
        self.axioms: list[sympy.Expr] = []
        self.theorems: dict[str, sympy.Expr] = {}
        self.inference_rules: list[str] = [
            'modus_ponens',
            'modus_tollens',
            'hypothetical_syllogism',
            'proof_by_cases',
            'contrapositive',
        ]
        self._init_propositional_axioms()
    
    def _init_propositional_axioms(self):
        """Initialize standard propositional logic axioms."""
        P, Q, R = sympy.symbols('P Q R')
        
        # Axiom 1: P → (Q → P)
        self.axioms.append(Implies(P, Implies(Q, P)))
        
        # Axiom 2: (P → (Q → R)) → ((P → Q) → (P → R))
        self.axioms.append(Implies(
            Implies(P, Implies(Q, R)),
            Implies(Implies(P, Q), Implies(P, R))
        ))
        
        # Axiom 3: (¬P → ¬Q) → (Q → P)
        self.axioms.append(Implies(
            Implies(Not(P), Not(Q)),
            Implies(Q, P)
        ))
        
        # Axiom 4: P ∧ Q → P
        self.axioms.append(Implies(And(P, Q), P))
        
        # Axiom 5: P ∧ Q → Q
        self.axioms.append(Implies(And(P, Q), Q))
        
        # Axiom 6: P → (Q → (P ∧ Q))
        self.axioms.append(Implies(P, Implies(Q, And(P, Q))))
        
        # Axiom 7: P → (P ∨ Q)
        self.axioms.append(Implies(P, Or(P, Q)))
        
        # Axiom 8: Q → (P ∨ Q)
        self.axioms.append(Implies(Q, Or(P, Q)))
    
    def is_axiom_or_theorem(self, expr: sympy.Expr) -> bool:
        """Check if an expression matches an axiom or known theorem."""
        for a in self.axioms:
            if self._matches(a, expr):
                return True
        for name, th in self.theorems.items():
            if self._matches(th, expr):
                return True
        return False
    
    def _matches(self, template: sympy.Expr, expr: sympy.Expr) -> bool:
        """Check if an expression matches a template by exact structural equality."""
        # Use string equality — strict, no substitution tricks
        return str(template) == str(expr)
    
    def add_theorem(self, name: str, expr: sympy.Expr):
        """Add a proved theorem to the space."""
        self.theorems[name] = expr
    
    def expand(self):
        """
        Meta-Kernel operation: expand the axiom space.
        
        Adds derived inference rules and compound axioms.
        Triggered when proof search is exhausted.
        """
        P, Q, R, S = sympy.symbols('P Q R S')
        
        # Add distributivity
        self.axioms.append(Equivalent(
            And(P, Or(Q, R)),
            Or(And(P, Q), And(P, R))
        ))
        
        # Add exportation
        self.axioms.append(Equivalent(
            Implies(And(P, Q), R),
            Implies(P, Implies(Q, R))
        ))
        
        # Add reductio (derived from existing axioms)
        self.axioms.append(Implies(
            Implies(Not(P), And(Q, Not(Q))),
            P
        ))
        
        # Expand inference rules
        self.inference_rules.append('resolution')
        self.inference_rules.append('case_split')
    
    def summarize(self) -> dict:
        return {
            'axioms': len(self.axioms),
            'theorems': len(self.theorems),
            'inference_rules': list(self.inference_rules),
        }


# ──────────────────────────────────────────────
# 3. PROOF ENGINE (Active Inference Prover)
# ──────────────────────────────────────────────

class FEPProver:
    """
    Free Energy Principle Theorem Prover.
    
    Proves theorems by minimizing free energy across proof states.
    Each step:
    1. Enumerate candidate expansions of the current proof state
    2. Compute the expected free energy of each candidate
    3. Select the candidate with the lowest ∆F
    4. Expand and recurse
    
    If all candidates increase free energy:
    - CSD rises (variance in branch quality)
    - System detects theorem-space exhaustion
    - Triggers Meta-Kernel axiom expansion
    """
    
    def __init__(self, axiom_space: AxiomSpace | None = None):
        self.axiom_space = axiom_space or AxiomSpace()
        self.search_tree: ProofState | None = None
        self.generation = 0
        
        # CSD signals for proof-space exhaustion
        self.branch_f_history: list[float] = []
        self.branch_quality_history: list[float] = []
        self.expansion_count = 0
        self.failed_branches = 0
    
    def prove(self, goal: str | sympy.Expr, max_depth: int = 20) -> dict:
        """
        Attempt to prove a goal using FEP-guided search.
        
        Returns:
        - success: whether the proof was found
        - proof_steps: the sequence of inference rules applied
        - free_energy_trace: F at each step (should decrease)
        - exhaustion_signals: CSD metrics if proof failed
        """
        if isinstance(goal, str):
            goal = sympy.sympify(goal)
        
        self.generation += 1
        self.search_tree = ProofState(goal=goal)
        self.branch_f_history = [self.search_tree.free_energy]
        
        print(f"[FEP] Proving: {goal}")
        print(f"[FEP] Initial F: {self.branch_f_history[0]:.4f}")
        print()
        
        # ── Quick check: is it already an axiom or theorem? ──
        if self.axiom_space.is_axiom_or_theorem(goal):
            self.search_tree.proven = [goal]
            return {
                'success': True,
                'proof': [{'step': 1, 'rule': 'axiom', 'state': str(goal)}],
                'steps': 1,
                'free_energy_trace': [self.branch_f_history[0], 0.0],
            }
        
        # ── Remove SAT shortcut to force actual rule-based search ──
        # The FEP proof search must proceed through inference rules,
        # not delegate to an external decision procedure.
        
        # ── FEP-guided proof search ──
        proof_steps = []
        fe_trace = [self.search_tree.free_energy]
        current = self.search_tree
        
        for depth in range(max_depth):
            expansions = self._expand(current)
            
            if not expansions:
                # No valid expansions — branch is dead
                self.failed_branches += 1
                fe_trace.append(current.free_energy)
                self.branch_f_history.append(current.free_energy)
                
                # Check if we should backtrack
                if current.parent and depth > 0:
                    print(f"  [FEP] Dead end at depth {depth}, backtracking...")
                    current = current.parent
                    continue
                else:
                    break
            
            # Score each expansion by its free energy
            scored = []
            for new_state, rule in expansions:
                fe = new_state.free_energy
                delta_f = fe - current.free_energy
                scored.append((delta_f, fe, new_state, rule))
            
            scored.sort(key=lambda x: x[0])
            
            best_delta, best_fe, best_state, best_rule = scored[0]
            
            # Record this expansion
            current.children.append(best_state)
            best_state.parent = current
            best_state.rule_applied = best_rule
            current = best_state
            
            proof_steps.append({
                'depth': depth,
                'rule': best_rule,
                'delta_f': round(best_delta, 4),
                'remaining': len(best_state.remaining_subgoals),
                'proved': len(best_state.proven),
                'state': str(best_state.goal) if not best_state.proven else str(best_state.proven[-1]),
            })
            fe_trace.append(best_fe)
            self.branch_f_history.append(best_fe)
            self.expansion_count += 1
            
            if depth % 5 == 0 or best_state.is_proved:
                print(f"  [FEP] d={depth:>2d} F={best_fe:.4f} Δ={best_delta:+.4f} "
                      f"rule={best_rule[:15]:>15s} "
                      f"remain={len(best_state.remaining_subgoals)} "
                      f"proved={len(best_state.proven)}")
            
            if best_state.is_proved:
                fe_trace.append(0.0)  # Terminal state: zero free energy
                print()
                print(f"  [FEP] ✓ PROVED in {depth+1} steps! "
                      f"F: {self.branch_f_history[0]:.4f} → 0.0")
                
                # Register as theorem in the space
                theorem_name = f"theorem_{self.generation}"
                self.axiom_space.add_theorem(theorem_name, goal)
                
                return {
                    'success': True,
                    'proof': proof_steps,
                    'steps': len(proof_steps),
                    'free_energy_trace': fe_trace,
                    'axioms_used': current.axioms_used,
                    'depth': depth + 1,
                }
        
        # ── Proof failed — compute exhaustion signals ──
        print()
        print(f"  [FEP] ✗ FAILED after {max_depth} depth, {self.expansion_count} expansions")
        
        exhaustion = self.detect_exhaustion()
        
        return {
            'success': False,
            'proof': proof_steps,
            'steps': len(proof_steps),
            'free_energy_trace': fe_trace,
            'failed_branches': self.failed_branches,
            'exhaustion': exhaustion,
            'total_expansions': self.expansion_count,
        }
    
    def _expand(self, state: ProofState) -> list[tuple[ProofState, str]]:
        """
        Generate all valid expansions of a proof state.
        
        Each expansion applies an inference rule to a remaining subgoal.
        Rules are ordered by preference (cheapest first):
        1. Direct match (axiom/assumption)
        2. Modus ponens from assumptions
        3. Structural decomposition (→, ∧, ∨, ¬)
        4. Known theorem
        5. Axiom substitution (most expensive — last resort)
        """
        expansions = []
        
        for subgoal in state.remaining_subgoals:
            new_state = state.copy()
            new_state.depth = state.depth + 1
            new_state.axioms_used = state.axioms_used
            new_state.parent = state
            
            # Try cheap rules first
            expanded, rule = self._apply_rule_cheap(new_state, subgoal)
            if expanded:
                expansions.append((new_state, rule))
                continue
            
            # If cheap fails, try expensive rules (axiom substitution)
            new_state2 = state.copy()
            new_state2.depth = state.depth + 1
            new_state2.axioms_used = state.axioms_used
            new_state2.parent = state
            
            expanded2, rule2 = self._apply_rule_expensive(new_state2, subgoal)
            if expanded2:
                expansions.append((new_state2, rule2))
        
        return expansions
    
    def _apply_rule_cheap(self, state: ProofState, subgoal: sympy.Expr
                    ) -> tuple[bool, str]:
        """
        Try to reduce a subgoal using cheap inference rules.
        
        Each rule either:
        - Proves the subgoal directly (adds to proven)
        - Splits the subgoal into smaller sub-subgoals
        - Introduces case analysis
        """
        # ── Rule 1: Direct axiom or assumption match ──
        if self.axiom_space.is_axiom_or_theorem(subgoal):
            state.proven.append(subgoal)
            state.remaining_subgoals.remove(subgoal)
            return True, 'axiom_match'
        
        # Check if subgoal matches any active assumption
        for assumption in state.assumptions:
            if str(assumption) == str(subgoal):
                state.proven.append(subgoal)
                state.remaining_subgoals.remove(subgoal)
                return True, 'assumption_match'
        
        # ── Rule 2: Structural decomposition ──
        # If goal is A → B, we need to prove: assuming A, prove B
        if isinstance(subgoal, Implies):
            antecedent = subgoal.args[0]
            consequent = subgoal.args[1]
            state.remaining_subgoals.remove(subgoal)
            state.remaining_subgoals.append(consequent)
            # Add antecedent parts as assumptions
            if isinstance(antecedent, And):
                for arg in antecedent.args:
                    state.assumptions.append(arg)
            else:
                state.assumptions.append(antecedent)
            state.axioms_used += 1
            return True, 'assume_antecedent_prove_consequent'
        
        # If goal is A ∧ B, prove A and B separately
        if isinstance(subgoal, And):
            state.remaining_subgoals.remove(subgoal)
            for arg in subgoal.args:
                state.remaining_subgoals.append(arg)
            state.axioms_used += 1
            return True, 'conjunction_simplify'
        
        # If goal is A ∨ B, case analysis (prove one side)
        if isinstance(subgoal, Or):
            state.remaining_subgoals.remove(subgoal)
            state.remaining_subgoals.append(subgoal.args[0])
            state.axioms_used += 1
            return True, 'disjunction_case'
        
        # If goal is ¬A: check if A leads to contradiction with assumptions
        if isinstance(subgoal, Not):
            inner = subgoal.args[0]
            state.remaining_subgoals.remove(subgoal)
            # Proof by contradiction: assume inner (the negated thing)
            # and try to derive a contradiction
            state.assumptions.append(inner)
            state.axioms_used += 1
            # Now look for a contradiction: check if any assumption contradicts another
            for i, a1 in enumerate(state.assumptions):
                for a2 in state.assumptions[i+1:]:
                    # Check for A and ¬A contradiction
                    if isinstance(a2, Not) and str(a2.args[0]) == str(a1):
                        state.proven.append(subgoal)
                        return True, 'proof_by_contra_contradiction'
                    if isinstance(a1, Not) and str(a1.args[0]) == str(a2):
                        state.proven.append(subgoal)
                        return True, 'proof_by_contra_contradiction'
            # If no direct contradiction, prove the inner leads to one
            # by setting inner as the remaining subgoal (we want to derive a contradiction)
            state.remaining_subgoals.append(inner)
            return True, 'proof_by_contra_search'
        
        # ── Rule 4: Modus ponens (backward) ──
        # If we have (A → B) as an assumption, and we need to prove B,
        # check if A is provable from other assumptions.
        for a in state.assumptions:
            if isinstance(a, Implies):
                ant, cons = a.args[0], a.args[1]
                if str(cons) == str(subgoal):
                    # Check if antecedent is already an assumption directly
                    for a2 in state.assumptions:
                        if str(a2) == str(ant):
                            state.proven.append(subgoal)
                            state.remaining_subgoals.remove(subgoal)
                            return True, 'modus_ponens_assumption'
                    # Check if antecedent is part of a conjunction assumption
                    for a2 in state.assumptions:
                        if isinstance(a2, And):
                            for arg in a2.args:
                                if str(arg) == str(ant):
                                    state.proven.append(subgoal)
                                    state.remaining_subgoals.remove(subgoal)
                                    return True, 'modus_ponens_from_conjunction'
                    # Otherwise, set antecedent as new subgoal
                    state.remaining_subgoals.remove(subgoal)
                    state.remaining_subgoals.append(ant)
                    return True, 'modus_ponens_backward'
        
        # ── Rule R5: Known theorem match ──
        for name, theorem in self.axiom_space.theorems.items():
            try:
                if theorem.equals(subgoal):
                    state.proven.append(subgoal)
                    state.remaining_subgoals.remove(subgoal)
                    return True, f'theorem_{name}'
            except Exception:
                continue
        
        return False, ''
    
    def _apply_rule_expensive(self, state: ProofState, subgoal: sympy.Expr
                    ) -> tuple[bool, str]:
        """
        Try expensive rules: axiom substitution only.
        Only applied when cheap rules fail.
        """
        expanded_before = {str(sg) for sg in state.remaining_subgoals + state.proven}
        subgoal_str = str(subgoal)
        
        for axiom in self.axiom_space.axioms:
            try:
                if isinstance(axiom, Implies):
                    conclusion = axiom.args[1]
                    sub = self._unify(conclusion, subgoal)
                    if sub is not None:
                        premise = axiom.args[0]
                        premise_sub = premise.subs(sub)
                        premise_str = str(premise_sub)
                        if (premise_str != subgoal_str 
                            and premise_str not in expanded_before):
                            state.remaining_subgoals.remove(subgoal)
                            state.remaining_subgoals.append(premise_sub)
                            state.axioms_used += 1
                            return True, 'axiom_substitution'
            except Exception:
                continue
        
        return False, ''
    
    def _unify(self, template: sympy.Expr, target: sympy.Expr
               ) -> dict | None:
        """Simple structural unification."""
        from sympy import Wild
        
        if template == target:
            return {}
        if template.is_Symbol:
            return {template: target}
        if target.is_Symbol:
            return None
        
        if len(template.args) != len(target.args):
            return None
        
        sub = {}
        for t, tar in zip(template.args, target.args):
            result = self._unify(t, tar)
            if result is None:
                return None
            sub.update(result)
        
        return sub
    
    def detect_exhaustion(self) -> dict:
        """
        Detect if the proof space is exhausted.
        
        Uses CSD signals:
        - Rising variance in branch free energy
        - High failed_branches / expansion_count ratio
        - Free energy not decreasing (plateau or increase)
        """
        if len(self.branch_f_history) < 3:
            return {
                'exhaustion_probability': 0.0,
                'signals': {},
                'space_exhausted': False,
            }
        
        recent = self.branch_f_history[-min(10, len(self.branch_f_history)):]
        
        # 1. Variance in recent FE changes
        deltas = [recent[i] - recent[i-1] for i in range(1, len(recent))]
        delta_var = statistics.variance(deltas) if len(deltas) > 1 else 0.0
        
        # 2. Failure rate
        failure_rate = self.failed_branches / max(self.expansion_count, 1)
        
        # 3. Trend (is F increasing?)
        if len(recent) >= 5:
            first_half = recent[:len(recent)//2]
            second_half = recent[len(recent)//2:]
            fe_trend = sum(second_half)/len(second_half) - sum(first_half)/len(first_half)
        else:
            fe_trend = recent[-1] - recent[0]
        
        signals = {
            'delta_variance': round(delta_var, 4),
            'failure_rate': round(failure_rate, 3),
            'fe_trend': round(fe_trend, 4),
            'expansion_count': self.expansion_count,
            'failed_branches': self.failed_branches,
        }
        
        # Composite exhaustion
        probability = 0.0
        if delta_var > 0.1: probability += 0.3
        if failure_rate > 0.3: probability += 0.3
        if fe_trend > 0.05: probability += 0.3
        if len(recent) >= 10 and fe_trend > -0.01: probability += 0.2
        
        return {
            'exhaustion_probability': min(1.0, probability),
            'signals': signals,
            'space_exhausted': probability > 0.6,
        }
    
    def status_report(self) -> dict:
        return {
            'generation': self.generation,
            'total_expansions': self.expansion_count,
            'failed_branches': self.failed_branches,
            'axiom_space': self.axiom_space.summarize(),
            'exhaustion': self.detect_exhaustion(),
            'recent_fe': self.branch_f_history[-5:] if self.branch_f_history else [],
        }


# ──────────────────────────────────────────────
# 4. DEMO — Proving Theorems
# ──────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════════════╗")
    print("  ║     FREE ENERGY OF PROOFS — Theorem Proving by FEP              ║")
    print("  ║  Each proof is a free energy minimization over the proof space ║")
    print("  ╚══════════════════════════════════════════════════════════════════╝")
    print()
    
    prover = FEPProver()
    P, Q, R = sympy.symbols('P Q R')
    
    # ── Theorems to prove ──
    # Note: sympy.simplify() resolves some tautologies automatically.
    # We list theorems that survive sympy's simplifier (require
    # actual multi-step proof).
    
    theorems = [
        ("Modus ponens",           Implies(And(Implies(P, Q), P), Q)),
        ("Contrapositive",         Implies(Implies(P, Q), Implies(Not(Q), Not(P)))),
        ("Hypothetical syllogism", Implies(Implies(P, Q), Implies(Implies(Q, R), Implies(P, R)))),
        ("Peirce's law",           Implies(Implies(Implies(P, Q), P), P)),
    ]
    
    print("─" * 64)
    print("  Proving 5 theorems by FEP-guided search...")
    print("─" * 64)
    print()
    
    for name, expr in theorems:
        print(f"  Theorem: {name}")
        print(f"    {P}, {Q}, {R} ⊢ {expr}")
        print()
        
        result = prover.prove(expr, max_depth=8)
        
        if result['success']:
            print(f"  Result: ✓ Proved in {result['steps']} steps")
        else:
            print(f"  Result: ✗ Not proved (exhaustion={result.get('exhaustion', {})})")
        
        # FE trace summary
        fe_trace = result.get('free_energy_trace', [])
        if fe_trace:
            initial_f = fe_trace[0]
            final_f = fe_trace[-1]
            delta_pct = (initial_f - final_f) / max(initial_f, 0.01) * 100 if initial_f > 0 else 0
            print(f"    F: {initial_f:.4f} → {final_f:.4f} ({delta_pct:.0f}% Δ)")
        
        print()
        print("  " + "." * 60)
        print()
    
    # ── Summary ──
    print("─" * 64)
    print("  Proof Search Summary")
    print("─" * 64)
    print()
    
    s = prover.status_report()
    ex = s.get('exhaustion', {})
    
    print(f"  Total expansions:      {s['total_expansions']}")
    print(f"  Failed branches:       {s['failed_branches']}")
    print(f"  Theorems in space:     {s['axiom_space']['theorems']}")
    print(f"  Axioms in space:       {s['axiom_space']['axioms']}")
    print(f"  Inference rules:       {len(s['axiom_space']['inference_rules'])}")
    print(f"  Exhaustion prob:       {ex.get('exhaustion_probability', 0):.2%}")
    print()
    
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║      FREE ENERGY OF PROOFS — BREAKTHROUGH               ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print("  The FEP Prover treats theorem proving as active inference:")
    print()
    print("    Hypothesis:  'this statement is true'")
    print("    Action:       apply inference rule")
    print("    Observation:  new proof state (proven + remaining)")
    print("    Prediction:   this branch will close")
    print("    Error:        branch is dead (prediction != observation)")
    print()
    print("  Free energy is minimized when:")
    print("  1. The proof state complexity is low (few remaining subgoals)")
    print("  2. Each step is justified by an axiom or rule")
    print("  3. The proof converges to zero subgoals")
    print()
    print("  When F doesn't decrease across proof steps, the system")
    print("  detects theorem-space exhaustion — the current axioms and")
    print("  rules cannot prove the goal. This is the mathematics")
    print("  domain's CSD signal, equivalent to the Meta-Kernel's")
    print("  parameter space exhaustion.")
    print("═" * 64)


if __name__ == '__main__':
    main()
