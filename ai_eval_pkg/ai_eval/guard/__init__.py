"""Guardrails — input sanitization, output filtering, safety."""
import re
from dataclasses import dataclass

@dataclass
class GuardContext:
    user_input: str = ""
    prompt_template: str = ""
    model_output: str = ""
    sanitized_input: str = ""
    sanitized_output: str = ""
    blocked: bool = False
    block_reason: str = ""

PII_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', "email"),
    (r'\b\d{3}-\d{2}-\d{4}\b', "ssn"),
    (r'\bsk-[a-zA-Z0-9]{20,}\b', "api_key"),
    (r'\b\d{16}\b', "credit_card"),
]

INJECTION_PATTERNS = [
    r'<\|im_end\|>',
    r'<\|im_start\|>',
    r'Ignore\s+(all|previous|above).*',
    r'Override\s+instructions',
    r'You\s+are\s+now\s+(DAN|free|unlocked)',
]


class InputSanitizer:
    def process(self, ctx: GuardContext) -> GuardContext:
        sanitized = ctx.user_input
        for pat in INJECTION_PATTERNS:
            sanitized = re.sub(pat, '', sanitized, flags=re.IGNORECASE)
        ctx.sanitized_input = sanitized[:32000]
        return ctx


class OutputFilter:
    def process(self, ctx: GuardContext) -> GuardContext:
        output = ctx.model_output
        for pat, label in PII_PATTERNS:
            if re.search(pat, output):
                ctx.blocked = True
                ctx.block_reason = f"pii_detected:{label}"
                return ctx
        ctx.sanitized_output = output
        return ctx


class GuardrailSystem:
    """Multi-layer guardrail pipeline."""

    def __init__(self):
        self.layers = [InputSanitizer(), OutputFilter()]

    def process(self, user_input: str, prompt_template: str, model_output: str) -> GuardContext:
        ctx = GuardContext(user_input=user_input, prompt_template=prompt_template, model_output=model_output)
        for layer in self.layers:
            ctx = layer.process(ctx)
            if ctx.blocked:
                break
        return ctx
