"""Cost governance — budget control, estimation, model selection."""
from dataclasses import dataclass

MODEL_COSTS = {
    "gpt-4o": {"input": 0.25, "output": 1.0},
    "gpt-4o-mini": {"input": 0.015, "output": 0.06},
    "gpt-4.1": {"input": 0.2, "output": 0.8},
    "claude-sonnet-4": {"input": 0.3, "output": 1.5},
    "claude-haiku-3.5": {"input": 0.08, "output": 0.4},
    "o3-mini": {"input": 0.11, "output": 0.44},
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in cents for a model request."""
    costs = MODEL_COSTS.get(model, {"input": 0.3, "output": 1.0})
    return round((input_tokens * costs["input"] + output_tokens * costs["output"]) / 1000, 4)


class TokenBudget:
    """Per-session token and cost budget enforcement."""

    def __init__(self, max_tokens: int = 50000, max_cost_cents: float = 50.0):
        self.max_tokens = max_tokens
        self.max_cost = max_cost_cents
        self.used_tokens = 0
        self.used_cents = 0.0

    @property
    def remaining_tokens(self) -> int:
        return self.max_tokens - self.used_tokens

    @property
    def remaining_cents(self) -> float:
        return max(0.0, self.max_cost - self.used_cents)

    @property
    def exhausted(self) -> bool:
        return self.remaining_tokens <= 0 or self.remaining_cents <= 0

    def check(self, estimated_tokens: int, estimated_cost_cents: float) -> bool:
        return self.remaining_tokens >= estimated_tokens and self.remaining_cents >= estimated_cost_cents

    def deduct(self, tokens: int, cost_cents: float):
        self.used_tokens += tokens
        self.used_cents += cost_cents


@dataclass
class RequestProfile:
    task_type: str
    complexity: float = 0.5
    context_tokens: int = 1000
    output_tokens: int = 500
    latency_sla_ms: int = 2000
    cost_sla_cents: float = 5.0


class ModelSelector:
    """Cost-optimized model selection."""

    def __init__(self):
        self.models = {
            "gpt-4o-mini": {"cost_per_k": 0.038, "quality": 0.6, "latency_ms": 400,
                            "tasks": ["classification", "extraction", "simple_reasoning"]},
            "gpt-4o": {"cost_per_k": 0.625, "quality": 0.9, "latency_ms": 800,
                       "tasks": ["reasoning", "code", "analysis", "classification"]},
            "claude-sonnet-4": {"cost_per_k": 0.75, "quality": 0.92, "latency_ms": 1000,
                                "tasks": ["reasoning", "code", "writing", "analysis"]},
            "o3-mini": {"cost_per_k": 0.275, "quality": 0.85, "latency_ms": 2000,
                        "tasks": ["complex_reasoning", "math", "science"]},
        }

    def select(self, profile: RequestProfile) -> list[tuple[str, float]]:
        """Return ranked list of (model_name, score)."""
        scored = []
        for name, spec in self.models.items():
            if profile.task_type not in spec["tasks"] and profile.complexity < 0.8:
                continue
            est_cost = estimate_cost(name, profile.context_tokens, profile.output_tokens)
            if est_cost > profile.cost_sla_cents:
                continue
            quality_fit = spec["quality"] / (1 + max(0, profile.complexity - 0.5) * 2)
            cost_score = 1 - (est_cost / max(profile.cost_sla_cents, 0.01)) * 0.5
            latency_ok = 1.0 if spec["latency_ms"] <= profile.latency_sla_ms else 0.3
            total = quality_fit * 0.5 + cost_score * 0.3 + latency_ok * 0.2
            scored.append((name, round(total, 3)))
        scored.sort(key=lambda x: -x[1])
        return scored[:3]
