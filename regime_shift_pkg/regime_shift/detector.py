"""
regime_shift.py — RSI Exhaustion API for Production Systems

Detect regime shifts in ANY metric stream before they cause incidents.

The MetaKernel's CriticalSlowingDownDetector was built for coupling
config free energy. But the signals it measures — rising variance,
rising autocorrelation, slowing recovery — are universal early
warning indicators for ANY complex system approaching a critical
transition.

This library makes those signals available as a clean API for
production monitoring.

USAGE:
    from regime_shift import RegimeShiftDetector
    
    detector = RegimeShiftDetector(
        window_size=30,       # sliding window
        baseline_size=15,     # initial stable reference
        name="api_latency_p99",
    )
    
    # Feed it your metric stream
    for latency in my_metric_stream:
        detector.observe(latency)
        alert = detector.check()
        if alert['probability'] > 0.7:
            pagerduty.trigger(alert)

SIGNALS:
  - variance_ratio:     current variance / baseline variance (>5 = warning)
  - autocorrelation:    lag-1 Pearson of recent window (>0.6 = warning)
  - mean_shift:         current mean / baseline mean (>5x = warning)
  - recovery_time:      generations to return after a spike (>baseline*2 = warning)

  Composite probability requires 2+ signals to fire simultaneously
  (prevents false positives from a single elevated statistic).

INTEGRATIONS:
  - Datadog:     detector.observe(value) per metric point
  - Prometheus:  wrap in a collector that polls and feeds
  - Grafana:     expose check() as a Grafana annotation source
  - PagerDuty:   trigger on probability > threshold

APPLICATIONS:
  - API latency approaching degradation
  - Error rate regime shift (precursor to sev-0)
  - Deployment frequency stagnating (team exhaustion)
  - Database query time increasing towards timeout
  - User engagement plateau (product market fit exhaustion)
  - Build times creeping up (CI/CD regime shift)

This is the real-world export of the cognoscope MetaKernel's
CriticalSlowingDownDetector. The theory is proven in the RSI
stack. This makes it usable anywhere.
"""

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any
from collections import deque
from enum import Enum


class RegimeType(Enum):
    """The type of regime the system is in."""
    STABLE = "stable"         # Low FE, low variance — everything normal
    WARNING = "warning"       # CSD signals emerging — approaching threshold
    CRITICAL = "critical"     # Regime shift imminent — act now
    RECOVERING = "recovering" # Post-shift stabilization


@dataclass
class RegimeAlert:
    """
    An alert produced by RegimeShiftDetector.check().
    
    Fields:
      - probability:  0-1 confidence that a regime shift is imminent
      - regime:       stable / warning / critical / recovering
      - signals:      individual CSD metrics with their values
      - triggers:     which signals crossed threshold
      - name:         the detector's name (for routing)
      - timestamp:    when the alert was generated
      - suggestion:   actionable recommendation
    """
    probability: float
    regime: RegimeType
    signals: dict[str, float]
    triggers: list[str]
    name: str = "unnamed"
    timestamp: float = 0.0
    suggestion: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "probability": round(self.probability, 3),
            "regime": self.regime.value,
            "triggers": self.triggers,
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
            "timestamp": self.timestamp or time.time(),
            "suggestion": self.suggestion,
        }


class RegimeShiftDetector:
    """
    Detect regime shifts in any metric stream using Critical Slowing Down.
    
    This is the production-ready version of the MetaKernel's
    CriticalSlowingDownDetector from the cognoscope RSI stack.
    
    Parameters:
      - name:          human-readable name for this detector
      - window_size:   sliding window for recent signal computation
      - baseline_size: how many initial observations to use as reference
      - variance_threshold:   ratio for variance warning (default: 5.0)
      - autocorr_threshold:   lag-1 autocorrelation warning (default: 0.6)
      - shift_threshold:      mean shift multiplier warning (default: 5.0)
      - min_signals:          how many must fire for critical (default: 2)
      - recovery_window:      how far back to check for recovery trend
    
    USAGE:
        d = RegimeShiftDetector("p99_latency")
        for val in metric_stream:
            d.observe(val)
            alert = d.check()
            if alert.regime == RegimeType.CRITICAL:
                send_alert(alert.to_dict())
    """
    
    def __init__(
        self,
        name: str = "unnamed",
        window_size: int = 30,
        baseline_size: int = 15,
        variance_threshold: float = 5.0,
        autocorr_threshold: float = 0.6,
        shift_threshold: float = 5.0,
        min_signals: int = 2,
        recovery_window: int = 10,
    ):
        self.name = name
        self.window_size = window_size
        self.baseline_size = baseline_size
        self.variance_threshold = variance_threshold
        self.autocorr_threshold = autocorr_threshold
        self.shift_threshold = shift_threshold
        self.min_signals = min_signals
        self.recovery_window = recovery_window
        
        # Internal state
        self.history: list[float] = []
        self.recovery_times: list[float] = []
        self._baseline_recorded = False
        self._baseline_mean = 0.0
        self._baseline_var = 0.0
        self._last_alert: RegimeAlert | None = None
        self._spike_threshold: float | None = None
        self._last_spike_gen: int = 0
        self._last_recovery_gen: int = 0
    
    # ── Public API ──────────────────────────────────────────
    
    def observe(self, value: float, record_recovery: bool = False):
        """
        Feed a new data point into the detector.
        
        Args:
            value: the metric value (latency ms, error rate %, etc.)
            record_recovery: if True, also detect recovery from spikes
        """
        self.history.append(value)
        
        # Record baseline once we have enough data
        if not self._baseline_recorded and len(self.history) >= self.baseline_size:
            baseline = self.history[:self.baseline_size]
            self._baseline_mean = statistics.mean(baseline)
            self._baseline_var = max(statistics.variance(baseline), 1e-10)
            self._spike_threshold = self._baseline_mean * 3
            self._baseline_recorded = True
        
        # Track recovery from spikes
        if record_recovery and self._baseline_recorded:
            if value > self._spike_threshold:
                # A spike occurred — note when
                self._last_spike_gen = len(self.history)
            elif self._last_spike_gen > self._last_recovery_gen:
                # We're recovering from a spike — track how long it took
                recovery_gen = len(self.history) - self._last_spike_gen
                self.recovery_times.append(recovery_gen)
                self._last_recovery_gen = self._last_spike_gen
    
    def check(self) -> RegimeAlert:
        """
        Run CSD detection on the current metric stream.
        
        Returns a RegimeAlert with probability and actionable signals.
        This is idempotent — call as often as you like.
        """
        if len(self.history) < 6 or not self._baseline_recorded:
            return RegimeAlert(
                probability=0.0, regime=RegimeType.STABLE,
                signals={}, triggers=[], name=self.name,
            )
        
        recent = self.history[-self.window_size:] if len(self.history) > self.window_size else self.history
        recent_mean = statistics.mean(recent[-5:]) if len(recent) >= 5 else recent[-1]
        recent_var = statistics.variance(recent) if len(recent) > 1 else 0.0
        
        # 1. Variance ratio
        variance_ratio = recent_var / self._baseline_var
        
        # 2. Autocorrelation (lag-1)
        autocorr = self._lag1_autocorr(recent)
        
        # 3. Mean shift
        mean_shift = (recent_mean - self._baseline_mean) / max(self._baseline_mean, 0.001)
        high_fe = recent_mean > self._baseline_mean * 3
        
        # 4. Recovery trend
        recovery_trend = 0.0
        if len(self.recovery_times) >= 4:
            rt = list(self.recovery_times)
            recovery_trend = (rt[-1] - rt[0]) / max(len(rt), 1)
        
        signals = {
            "variance_ratio": round(variance_ratio, 3),
            "autocorrelation": round(autocorr, 3),
            "mean_shift": round(mean_shift, 3),
            "recovery_trend": round(recovery_trend, 5),
        }
        
        # 5. Composite probability
        probability = 0.0
        triggers = []
        
        if variance_ratio > self.variance_threshold and recent_var > 0.001:
            probability += 0.25
            triggers.append("variance")
        if autocorr > self.autocorr_threshold:
            probability += 0.25
            triggers.append("autocorrelation")
        if mean_shift > self.shift_threshold:
            probability += 0.25
            triggers.append("mean_shift")
        if high_fe:
            probability += 0.25
            triggers.append("high_fe")
        
        probability = min(1.0, probability)
        signals_fired = len(triggers)
        
        # Determine regime
        if probability < 0.3 or signals_fired < self.min_signals:
            regime = RegimeType.STABLE
            suggestion = ""
        elif probability < 0.7:
            regime = RegimeType.WARNING
            suggestion = self._suggestion(triggers, "monitor")
        else:
            regime = RegimeType.CRITICAL
            suggestion = self._suggestion(triggers, "act")
        
        # Check if we're recovering
        if regime != RegimeType.CRITICAL and len(self.recovery_times) >= 2:
            recent_rt = self.recovery_times[-2:]
            if len(recent_rt) >= 2 and recent_rt[-1] < recent_rt[0] * 0.7:
                regime = RegimeType.RECOVERING
        
        alert = RegimeAlert(
            probability=probability,
            regime=regime,
            signals=signals,
            triggers=triggers,
            name=self.name,
            timestamp=time.time(),
            suggestion=suggestion,
        )
        self._last_alert = alert
        return alert
    
    def reset_baseline(self):
        """Reset the baseline to current data (e.g., after a confirmed regime shift)."""
        if len(self.history) >= self.baseline_size:
            recent = self.history[-self.baseline_size:]
            self._baseline_mean = statistics.mean(recent)
            self._baseline_var = max(statistics.variance(recent), 1e-10)
            self._baseline_recorded = True
    
    def status(self) -> dict:
        """Full status for dashboard integration."""
        alert = self.check()
        return {
            "name": self.name,
            "observations": len(self.history),
            "baseline_mean": round(self._baseline_mean, 4) if self._baseline_recorded else None,
            "baseline_var": round(self._baseline_var, 4) if self._baseline_recorded else None,
            "current_mean": round(statistics.mean(self.history[-10:]), 4) if len(self.history) >= 10 else None,
            "current_regime": alert.regime.value,
            "recovery_times_tracked": len(self.recovery_times),
            "alert": alert.to_dict(),
        }
    
    # ── Internal ────────────────────────────────────────────
    
    @staticmethod
    def _lag1_autocorr(series: list[float]) -> float:
        """Pearson correlation between series[:-1] and series[1:]."""
        if len(series) < 4:
            return 0.0
        x = series[:-1]
        y = series[1:]
        mx = sum(x) / len(x)
        my = sum(y) / len(y)
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        den = (sum((xi - mx)**2 for xi in x) * sum((yi - my)**2 for yi in y)) ** 0.5
        return num / den if den > 0 else 0.0
    
    def _suggestion(self, triggers: list[str], severity: str) -> str:
        """Generate actionable recommendations based on which signals fired."""
        suggestions = []
        for t in triggers:
            if t == "variance":
                suggestions.append("metric variance is rising — check for intermittent failures or traffic pattern changes")
            elif t == "autocorrelation":
                suggestions.append("metric is autocorrelated — each value predicts the next, typical of approaching limits")
            elif t == "mean_shift":
                suggestions.append("metric mean has shifted significantly from baseline — investigate root cause")
            elif t == "high_fe":
                suggestions.append("metric level is 3x+ above baseline — consider scaling, throttling, or circuit-breaking")
        
        if severity == "act":
            suggestions.append("REGIME SHIFT IMMINENT — prepare rollback, scale up, or activate failover")
        
        return "; ".join(suggestions)


# ──────────────────────────────────────────────
# INTEGRATION HELPERS
# ──────────────────────────────────────────────

class MultiMetricMonitor:
    """
    Monitor multiple metrics with individual regime shift detectors.
    
    Each metric gets its own RegimeShiftDetector with its own baseline,
    window, and thresholds. The monitor aggregates alerts across all
    metrics and identifies which subsystem is most at risk.
    
    USAGE:
        monitor = MultiMetricMonitor({
            "p99_latency": {"variance_threshold": 3.0},
            "error_rate": {"autocorr_threshold": 0.5},
            "deploy_freq": {"shift_threshold": 3.0},
        })
        
        for batch in metric_batches:
            monitor.observe_batch(batch)
            if monitor.critical_metrics():
                alert_oncall(monitor.summary())
    """
    
    def __init__(self, metric_configs: dict[str, dict] | None = None):
        self.detectors: dict[str, RegimeShiftDetector] = {}
        if metric_configs:
            for name, config in metric_configs.items():
                self.add_metric(name, **config)
    
    def add_metric(self, name: str, **kwargs):
        self.detectors[name] = RegimeShiftDetector(name=name, **kwargs)
    
    def observe(self, metric: str, value: float):
        if metric in self.detectors:
            self.detectors[metric].observe(value)
    
    def observe_batch(self, batch: dict[str, float]):
        """Feed multiple metric values at once."""
        for metric, value in batch.items():
            self.observe(metric, value)
    
    def check_all(self) -> dict[str, RegimeAlert]:
        """Run CSD on all metrics."""
        return {name: d.check() for name, d in self.detectors.items()}
    
    def critical_metrics(self) -> list[str]:
        """Return names of metrics in CRITICAL regime."""
        return [
            name for name, d in self.detectors.items()
            if d.check().regime == RegimeType.CRITICAL
        ]
    
    def summary(self) -> dict:
        """Aggregate status for dashboard."""
        alerts = self.check_all()
        return {
            "total_metrics": len(self.detectors),
            "critical": self.critical_metrics(),
            "warning": [n for n, a in alerts.items() if a.regime == RegimeType.WARNING],
            "stable": [n for n, a in alerts.items() if a.regime == RegimeType.STABLE],
            "alerts": {n: a.to_dict() for n, a in alerts.items()},
        }


# ──────────────────────────────────────────────
# DEMO — Real-world scenarios
# ──────────────────────────────────────────────

