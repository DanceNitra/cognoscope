"""Deployment — canary deployments, prompt registry, rollback."""
import json, hashlib, random, time
from dataclasses import dataclass, field


@dataclass
class PromptVersion:
    name: str
    version: int
    hash: str
    prompt: str
    author: str = ""
    date: str = ""
    parent: str = ""


class PromptRegistry:
    """Versioned prompt registry with rollback support."""

    def __init__(self, registry_path: str = None):
        self.versions: dict[str, list[PromptVersion]] = {}
        self.path = registry_path
        if registry_path:
            self._load()

    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
                for name, versions in data.items():
                    self.versions[name] = [PromptVersion(**v) for v in versions]
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        if not self.path:
            return
        data = {name: [asdict(v) for v in vers] for name, vers in self.versions.items()}
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    def register(self, name: str, prompt: str, author: str = "") -> PromptVersion:
        version = self.versions.get(name, [])
        v = PromptVersion(
            name=name,
            version=len(version) + 1,
            hash=hashlib.sha256(prompt.encode()).hexdigest()[:12],
            prompt=prompt,
            author=author,
            date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            parent=version[-1].hash if version else "",
        )
        self.versions.setdefault(name, []).append(v)
        self.save()
        return v

    def get_active(self, name: str) -> PromptVersion | None:
        versions = self.versions.get(name, [])
        return versions[-1] if versions else None

    def rollback(self, name: str, target_version: int) -> PromptVersion | None:
        versions = self.versions.get(name, [])
        if target_version < 1 or target_version > len(versions):
            return None
        target = versions[target_version - 1]
        return self.register(name, target.prompt, author="rollback")


@dataclass
class CanaryResult:
    production_samples: int = 0
    candidate_samples: int = 0
    production_quality: float = 0.0
    candidate_quality: float = 0.0
    production_cost: float = 0.0
    candidate_cost: float = 0.0
    passed: bool = False


class CanaryDeployer:
    """Canary deployment for prompt/model changes."""

    def __init__(self):
        self.results = {"production": [], "candidate": []}

    def simulate(self, prod_quality: float = 0.85, cand_quality: float = 0.88,
                 prod_cost: float = 0.5, cand_cost: float = 0.55,
                 percent: float = 5, samples: int = 100) -> CanaryResult:
        for _ in range(samples):
            if random.random() < percent / 100:
                self.results["candidate"].append({"quality": cand_quality, "cost": cand_cost})
            else:
                self.results["production"].append({"quality": prod_quality, "cost": prod_cost})

        def mean(lst, key):
            return sum(d[key] for d in lst) / len(lst) if lst else 0.0

        result = CanaryResult()
        result.production_samples = len(self.results["production"])
        result.candidate_samples = len(self.results["candidate"])
        result.production_quality = mean(self.results["production"], "quality")
        result.candidate_quality = mean(self.results["candidate"], "quality")
        result.production_cost = mean(self.results["production"], "cost")
        result.candidate_cost = mean(self.results["candidate"], "cost")
        result.passed = (result.candidate_quality >= result.production_quality * 0.95
                         and result.candidate_cost <= result.production_cost * 1.2)
        return result


# For PromptVersion serialization
def asdict(v: PromptVersion) -> dict:
    return {"name": v.name, "version": v.version, "hash": v.hash,
            "prompt": v.prompt, "author": v.author, "date": v.date, "parent": v.parent}
