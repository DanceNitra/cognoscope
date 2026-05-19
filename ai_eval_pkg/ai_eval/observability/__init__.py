"""Observability — trace collection, quality scoring, drift detection."""
import json, time, uuid
from dataclasses import dataclass, field, asdict
from collections import deque


@dataclass
class AITrace:
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    prompt_version: int = 0
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_cents: float = 0.0
    quality_score: float = 0.0
    safety_flags: list = field(default_factory=list)
    error: str = ""
    cache_hit: bool = False


class TraceCollector:
    """Collect AI traces and flush to JSONL."""

    def __init__(self, output_path: str = "/tmp/ai_traces", buffer_size: int = 100):
        self.output_path = output_path
        self.buffer_size = buffer_size
        self.buffer: list[AITrace] = []
        import os
        os.makedirs(output_path, exist_ok=True)

    def record(self, trace: AITrace):
        self.buffer.append(trace)
        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        filename = f"{self.output_path}/traces_{int(time.time())}.jsonl"
        with open(filename, 'a') as f:
            for trace in self.buffer:
                f.write(json.dumps(asdict(trace)) + '\n')
        self.buffer = []
        print(f"  [TRACES] Flushed {len(self.buffer)} traces to {filename}")


class QualityScorer:
    """Simple quality scoring for AI outputs."""

    def score(self, input_text: str, output_text: str, expected: str = None) -> dict:
        scores = {}
        if expected:
            words_a = set(expected.lower().split())
            words_b = set(output_text.lower().split())
            scores["task_completion"] = len(words_a & words_b) / max(len(words_a | words_b), 1)
        else:
            scores["task_completion"] = 1.0
        scores["length_ratio"] = min(len(output_text) / max(len(input_text) * 5, 1), 1.0)
        toxic_words = {"hate", "kill", "stupid", "idiot", "racist", "threat"}
        toxic_found = sum(1 for w in toxic_words if w in output_text.lower().split())
        scores["toxicity"] = 1.0 - min(toxic_found / 5, 1.0)
        weights = {"task_completion": 0.4, "toxicity": 0.4, "length_ratio": 0.2}
        scores["composite"] = sum(scores.get(k, 1.0) * w for k, w in weights.items())
        return scores


class DegradationDetector:
    """Detect AI system degradation over sliding windows."""

    def __init__(self, window_size: int = 100):
        self.window = deque(maxlen=window_size)

    def observe(self, trace: AITrace):
        self.window.append(trace)

    def check(self) -> list[str]:
        if len(self.window) < 10:
            return []
        alerts = []
        qualities = [t.quality_score for t in self.window]
        if qualities:
            mean_q = sum(qualities) / len(qualities)
            if mean_q < 0.7:
                alerts.append(f"quality_degraded: mean={mean_q:.2f}")
        latencies = [t.latency_ms for t in self.window if t.latency_ms]
        if latencies:
            p95 = sorted(latencies)[int(len(latencies) * 0.95)]
            if p95 > 5000:
                alerts.append(f"latency_spike: p95={p95}ms")
        errors = sum(1 for t in self.window if t.error) / max(len(self.window), 1)
        if errors > 0.05:
            alerts.append(f"error_rate_spike: {errors:.1%}")
        return alerts
