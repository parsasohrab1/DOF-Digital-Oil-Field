"""
Executive KPI metrics for OGIM (Prometheus + summary helpers).
"""
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from prometheus_client import Counter, Gauge, Histogram

    PROM_ENABLED = True
except ImportError:  # pragma: no cover
    PROM_ENABLED = False
    Counter = Gauge = Histogram = None  # type: ignore

# Performance
API_LATENCY = (
    Histogram(
        "ogim_kpi_api_latency_seconds",
        "API latency for executive KPI tracking",
        ["service"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    )
    if PROM_ENABLED
    else None
)

SYSTEM_UPTIME_RATIO = (
    Gauge(
        "ogim_kpi_system_uptime_ratio",
        "Rolling system uptime ratio (0-1)",
    )
    if PROM_ENABLED
    else None
)

# Adoption
FEATURE_USAGE = (
    Counter(
        "ogim_kpi_feature_usage_total",
        "Feature adoption counter by page/feature",
        ["feature"],
    )
    if PROM_ENABLED
    else None
)

ACTIVE_USERS = (
    Gauge(
        "ogim_kpi_active_users",
        "Approximate active users in current window",
    )
    if PROM_ENABLED
    else None
)

# Alert quality
ALERT_FALSE_POSITIVE = (
    Counter(
        "ogim_kpi_alert_false_positive_total",
        "Alerts marked as false positive",
        ["severity"],
    )
    if PROM_ENABLED
    else None
)

ALERT_TOTAL = (
    Counter(
        "ogim_kpi_alert_total",
        "Total alerts generated",
        ["severity"],
    )
    if PROM_ENABLED
    else None
)

# In-memory rolling stats (for /kpi/summary when Prometheus unavailable)
_kpi_state: Dict[str, Any] = {
    "latency_samples_ms": [],
    "uptime_checks": {"ok": 0, "fail": 0},
    "feature_usage": {},
    "false_positives": 0,
    "alerts_total": 0,
}


def record_latency(service: str, latency_seconds: float) -> None:
    if API_LATENCY:
        API_LATENCY.labels(service=service).observe(latency_seconds)
    samples = _kpi_state["latency_samples_ms"]
    samples.append(latency_seconds * 1000)
    if len(samples) > 500:
        del samples[: len(samples) - 500]


def record_uptime_check(ok: bool) -> None:
    key = "ok" if ok else "fail"
    _kpi_state["uptime_checks"][key] += 1
    checks = _kpi_state["uptime_checks"]
    total = checks["ok"] + checks["fail"]
    ratio = checks["ok"] / total if total else 1.0
    if SYSTEM_UPTIME_RATIO:
        SYSTEM_UPTIME_RATIO.set(ratio)


def record_feature_usage(feature: str) -> None:
    if FEATURE_USAGE:
        FEATURE_USAGE.labels(feature=feature).inc()
    usage = _kpi_state["feature_usage"]
    usage[feature] = usage.get(feature, 0) + 1


def record_alert(severity: str, false_positive: bool = False) -> None:
    if ALERT_TOTAL:
        ALERT_TOTAL.labels(severity=severity).inc()
    _kpi_state["alerts_total"] += 1
    if false_positive:
        if ALERT_FALSE_POSITIVE:
            ALERT_FALSE_POSITIVE.labels(severity=severity).inc()
        _kpi_state["false_positives"] += 1


def _percentile(values: list, pct: float) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * pct)
    idx = min(idx, len(sorted_vals) - 1)
    return round(sorted_vals[idx], 2)


def get_executive_summary() -> Dict[str, Any]:
    samples = _kpi_state["latency_samples_ms"]
    checks = _kpi_state["uptime_checks"]
    total_checks = checks["ok"] + checks["fail"]
    uptime_ratio = checks["ok"] / total_checks if total_checks else 1.0
    alerts_total = _kpi_state["alerts_total"]
    false_positives = _kpi_state["false_positives"]
    fp_rate = false_positives / alerts_total if alerts_total else 0.0
    adoption_total = sum(_kpi_state["feature_usage"].values())

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "latency": {
            "p50_ms": _percentile(samples, 0.50),
            "p95_ms": _percentile(samples, 0.95),
            "target_p95_ms": 100,
            "status": "ok" if (_percentile(samples, 0.95) or 0) < 100 else "warning",
        },
        "uptime": {
            "ratio": round(uptime_ratio, 4),
            "target_ratio": 0.999,
            "status": "ok" if uptime_ratio >= 0.999 else "warning",
        },
        "adoption": {
            "feature_hits": dict(_kpi_state["feature_usage"]),
            "total_events": adoption_total,
            "target_monthly_active_features": 5,
            "status": "ok" if len(_kpi_state["feature_usage"]) >= 3 else "warning",
        },
        "alert_quality": {
            "false_positive_rate": round(fp_rate, 4),
            "target_max_false_positive_rate": 0.30,
            "alerts_total": alerts_total,
            "false_positives": false_positives,
            "status": "ok" if fp_rate <= 0.30 else "warning",
        },
    }
