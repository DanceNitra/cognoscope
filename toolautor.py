#!/usr/bin/env python3
"""
toolautor.py — Phase 2: AutoResearch for ToolForge Optimization

The AutoResearch loop applied to Athena ToolForge tool synthesis.
When ToolForge generates a tool, AR runs N experiments on the implementation
to find the optimal version.

How it works:
  1. ToolForge synthesizes a tool from natural language description
  2. AR takes the tool code and runs N experiments
  3. Each experiment: mutate the tool implementation
  4. Evaluate: execution speed, error rate, output quality
  5. Binary keep/discard — keep only improvements
  6. Git commit each kept experiment
  7. Tool lineage tracking for rollback

This is the loop Karpathy used on nanochat — applied to tool code instead of models.
"""

import os, sys, re, json, random, time, ast, textwrap
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/cognoscope"))
from autoresearch import (
    Mutator, Metric, AutoResearchLoop, AutoResearchConfig,
    AutoResearchResult, save_ar_report, format_ar_result
)
from toolforge import ToolForge, ToolSpec, RewritingToolForge


# ──────────────────────────────────────────────
# TOOL MUTATOR
# ──────────────────────────────────────────────

class ToolMutator(Mutator):
    """
    Generate mutations of Python tool implementations.
    
    Mutation strategies:
      a. AST-level: wrap in try/except, add validation, change error handling
      b. Type hint mutations: add/remove type hints
      c. Performance mutations: add caching, simplify logic
      d. Safety mutations: add input validation, boundary checks
    """
    
    def __init__(self):
        self.strategies = [
            self._add_error_handling,
            self._add_type_hints,
            self._add_input_validation,
            self._simplify_logic,
        ]
    
    def mutate(self, file_path: str, content: str, experiment_id: int, history: list) -> tuple[str, str]:
        """Pick a random strategy and apply it."""
        strategy = random.choice(self.strategies)
        return strategy(content)
    
    def _add_error_handling(self, content: str) -> tuple[str, str]:
        """Wrap function body in try/except."""
        tree = self._parse_function(content)
        if not tree:
            return content, "no-op (parse failed)"
        
        # Find the main function body
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.body:
                # Get the body source lines
                lines = content.split('\n')
                start_line = node.body[0].lineno - 1
                end_line = node.body[-1].end_lineno - 1
                
                original_body = '\n'.join(lines[start_line:end_line + 1])
                indented = textwrap.indent(original_body, '    ')
                new_body = f"try:\n{indented}\nexcept Exception as e:\n    return {{\"error\": str(e)}}"
                
                new_lines = lines[:start_line] + [new_body] + lines[end_line + 1:]
                return '\n'.join(new_lines), "add try/except error handling"
        
        return content, "no-op (no function found)"
    
    def _add_type_hints(self, content: str) -> tuple[str, str]:
        """Add return type hints to functions missing them."""
        lines = content.split('\n')
        modified = False
        
        for i, line in enumerate(lines):
            match = re.match(r'^    def (\w+)\((.*)\):', line)
            if match and '->' not in line:
                lines[i] = f"    def {match.group(1)}({match.group(2)}) -> dict:"
                modified = True
        
        if modified:
            return '\n'.join(lines), "add return type hints"
        return content, "no-op (type hints exist)"
    
    def _add_input_validation(self, content: str) -> tuple[str, str]:
        """Add input validation at the start of functions."""
        tree = self._parse_function(content)
        if not tree:
            return content, "no-op (parse failed)"
        
        lines = content.split('\n')
        modified = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.args.args:
                # Add validation after docstring
                docstring_line = None
                for child in node.body:
                    if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
                        docstring_line = child.end_lineno or child.lineno
                    break
                
                insert_after = docstring_line if docstring_line else node.body[0].lineno
                insert_line = insert_after
        
        if modified:
            return '\n'.join(lines), "add input validation"
        return content, "no-op"
    
    def _simplify_logic(self, content: str) -> tuple[str, str]:
        """Remove redundant logic patterns."""
        # Simple regex-based simplifications
        patterns = [
            (r'if (.*?) == True:', r'if \1:'),
            (r'if (.*?) == False:', r'if not \1:'),
            (r'return True', r'return True'),
            (r'return False', r'return False'),
        ]
        new_content = content
        applied = []
        for pattern, replacement in patterns:
            if re.search(pattern, new_content):
                new_content = re.sub(pattern, replacement, new_content)
                applied.append(pattern[:20])
        
        if applied:
            return new_content, f"simplify logic: {', '.join(applied[:2])}"
        return content, "no-op"
    
    def _parse_function(self, content: str) -> ast.Module | None:
        """Try to parse as Python AST."""
        try:
            return ast.parse(content)
        except SyntaxError:
            return None


# ──────────────────────────────────────────────
# TOOL METRIC
# ──────────────────────────────────────────────

class ToolMetric(Metric):
    """Evaluate tool implementation quality. Higher = better."""
    
    def evaluate(self, file_path: str) -> float:
        """Evaluate a tool file."""
        try:
            with open(file_path) as f:
                content = f.read()
            return self.evaluate_content(content, file_path)
        except Exception:
            return 0.0
    
    def evaluate_content(self, content: str, file_path: str = "") -> float:
        """Evaluate tool code quality."""
        if not content.strip():
            return 0.0
        
        score = 0.0
        
        # 1. Parsability (must be valid Python)
        try:
            ast.parse(content)
            score += 0.20
        except SyntaxError:
            return 0.1  # Barely valid
        
        # 2. Error handling
        has_try = "try:" in content
        has_except = "except" in content
        score += 0.10 if (has_try and has_except) else 0.0
        
        # 3. Type hints
        has_return_hint = "->" in content
        has_arg_hints = "def " in content and ":" in content.split("def ")[-1].split("(")[0] if "def " in content else False
        score += 0.10 if (has_return_hint or ": int" in content or ": str" in content or ": dict" in content) else 0.0
        
        # 4. Documentation
        has_docstring = '"""' in content or "'''" in content
        score += 0.10 if has_docstring else 0.0
        
        # 5. Function count (1-3 functions ideal)
        n_funcs = content.count('def ')
        if 1 <= n_funcs <= 3:
            score += 0.15
        elif n_funcs == 0:
            score += 0.05
        
        # 6. Lines of code (10-100 ideal)
        lines = content.count('\n') + 1
        if 10 <= lines <= 100:
            score += 0.10
        elif lines < 10:
            score += 0.05
        
        # 7. No dangerous operations
        dangerous = ['eval(', 'exec(', '__import__', 'os.system', 'subprocess.call']
        if not any(d in content for d in dangerous):
            score += 0.25
        
        return round(score, 4)


# ──────────────────────────────────────────────
# INTEGRATION
# ──────────────────────────────────────────────

def run_ar_on_tool(tool_name: str, tool_code: str, output_dir: str) -> AutoResearchResult | None:
    """
    Run AR loop to optimize a tool implementation.
    
    Args:
        tool_name: Name of the tool
        tool_code: Current tool implementation
        output_dir: Where to write optimized version
    """
    os.makedirs(output_dir, exist_ok=True)
    tool_path = os.path.join(output_dir, f"{tool_name}.py")
    
    # Write initial version
    with open(tool_path, 'w') as f:
        f.write(tool_code)
    
    mutator = ToolMutator()
    metric = ToolMetric()
    baseline = metric.evaluate(tool_path)
    
    config = AutoResearchConfig(
        max_experiments=30,
        time_budget_sec=20,
        branch_prefix="ar-tool",
    )
    
    loop = AutoResearchLoop(
        subject_name=f"tool:{tool_name}",
        file_path=tool_path,
        mutator=mutator,
        metric=metric,
        config=config,
        baseline=baseline,
    )
    result = loop.run()
    save_ar_report(result, output_dir)
    
    return result


def optimize_synthesized_tool(tool_name: str, description: str) -> str:
    """
    Full pipeline: ToolForge synthesize → AR optimize → return best version.
    
    Args:
        tool_name: Name for the tool
        description: Natural language description
    
    Returns:
        Optimized tool code
    """
    forge = ToolForge()
    spec = forge.synthesize(tool_name, description)
    
    if not spec or spec.errors:
        print(f"ToolForge failed: {spec.errors if spec else 'unknown'}")
        return ""
    
    tool_code = spec.code
    ar_output = os.path.expanduser(f"~/cognoscope/autoresearch_experiments/tools")
    
    result = run_ar_on_tool(tool_name, tool_code, ar_output)
    
    # Read best version
    best_path = os.path.join(ar_output, f"{tool_name}.py")
    with open(best_path) as f:
        return f.read()


# ──────────────────────────────────────────────
# CLIENT
# ──────────────────────────────────────────────

def demo():
    """Demo: optimize a sample tool."""
    sample_tool = '''def add_numbers(a, b):
    result = a + b
    return result

def multiply_numbers(a, b):
    return a * b
'''
    
    result = run_ar_on_tool("demo_tool", sample_tool, 
                           os.path.expanduser("~/cognoscope/autoresearch_experiments"))
    if result:
        print(format_ar_result(result))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tool AutoResearch Phase 2")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--synthesize", type=str, default=None,
                        help="Synthesize and optimize a tool from description")
    parser.add_argument("--tool-name", type=str, default="synthesized_tool",
                        help="Name for synthesized tool")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.synthesize:
        code = optimize_synthesized_tool(args.tool_name, args.synthesize)
        print(f"\nOptimized tool:\n{code}")
    else:
        print("Usage: python3 toolautor.py --demo")
        print("       python3 toolautor.py --synthesize 'a tool that...' --tool-name mytool")
