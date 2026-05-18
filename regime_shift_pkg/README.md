# regime-shift

**Detect regime shifts in ANY metric stream before they cause incidents.**

The MetaKernel's CriticalSlowingDownDetector was built for the cognoscope RSI stack. But the signals it measures — rising variance, rising autocorrelation, slowing recovery — are **universal early warning indicators** for any complex system approaching a critical transition.

This package makes those signals available as a clean Python API and CLI.

## Quick Start

```bash
pip install regime-shift

# Run the demo
regime-shift demo

# Analyze a CSV of metrics
regime-shift analyze latency.csv --column p99 --name "api_latency"

# Start a lightweight HTTP server for metric ingestion
regime-shift serve --port 8080
```

## Python API

```python
from regime_shift import RegimeShiftDetector, MultiMetricMonitor, RegimeType

# Single metric
detector = RegimeShiftDetector(name="p99_latency_ms", window_size=30)
for latency in my_stream:
    detector.observe(latency)
    alert = detector.check()
    if alert.regime == RegimeType.CRITICAL:
        pagerduty.trigger(alert.to_dict())

# Multi-metric (microservice health)
monitor = MultiMetricMonitor({
    "p99_latency": {"variance_threshold": 3.0},
    "error_rate": {"autocorr_threshold": 0.5},
    "db_query_time": {},
})
monitor.observe_batch({"p99_latency": 150, "error_rate": 2.1})
if monitor.critical_metrics():
    print(monitor.summary())
```

## Signals

| Signal | Threshold | What It Detects |
|---|---|---|
| `variance_ratio` | > 5.0 | Metric fluctuating more than baseline — early warning |
| `autocorrelation` | > 0.6 | Each value predicts the next — approaching hard limits |
| `mean_shift` | > 5.0x | System moved to a new operating point |
| `high_fe` | > 3x baseline | Unsustainable metric level |

**Crisis requires 2+ signals simultaneously** — a single elevated statistic is just a bad day.

## Demo Result

```
Regime shift detected ~25 observations BEFORE the spike:
  At ~400ms: CSD probability hits 50%+
  At ~450ms: probability hits 75%+
  Traditional alerting fires at >1000ms
  RSI exhaustion detected the shift 25 generations EARLIER
```

## Applications

- API latency approaching degradation
- Error rate regime shift (precursor to sev-0)
- Deployment frequency stagnating (team exhaustion)
- Database query time increasing towards timeout
- User engagement plateau (product market fit exhaustion)
- Build times creeping up (CI/CD regime shift)

## Theory

This is extracted from the cognoscope RSI stack — an 8-level recursive self-improvement system. The Critical Slowing Down (CSD) framework was developed for the Meta-Kernel's parameter space exhaustion detection. It is mathematically identical to the early warning signals used in climate science, ecology, and neuroscience to detect tipping points before they occur.

## License

MIT
