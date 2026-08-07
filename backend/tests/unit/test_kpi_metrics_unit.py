"""Unit tests for shared.kpi_metrics."""
import pytest

from shared import kpi_metrics


@pytest.fixture(autouse=True)
def reset_kpi_state():
    kpi_metrics._kpi_state["latency_samples_ms"] = []
    kpi_metrics._kpi_state["uptime_checks"] = {"ok": 0, "fail": 0}
    kpi_metrics._kpi_state["feature_usage"] = {}
    kpi_metrics._kpi_state["false_positives"] = 0
    kpi_metrics._kpi_state["alerts_total"] = 0
    yield


@pytest.mark.unit
def test_record_latency_and_summary():
    kpi_metrics.record_latency("api-gateway", 0.05)
    kpi_metrics.record_latency("api-gateway", 0.08)
    summary = kpi_metrics.get_executive_summary()
    assert summary["latency"]["p50_ms"] is not None
    assert summary["latency"]["status"] in ("ok", "warning")


@pytest.mark.unit
def test_record_uptime_check():
    kpi_metrics.record_uptime_check(True)
    kpi_metrics.record_uptime_check(True)
    kpi_metrics.record_uptime_check(False)
    summary = kpi_metrics.get_executive_summary()
    assert summary["uptime"]["ratio"] == pytest.approx(0.6667, rel=1e-2)


@pytest.mark.unit
def test_record_feature_usage():
    kpi_metrics.record_feature_usage("dashboard")
    kpi_metrics.record_feature_usage("dashboard")
    kpi_metrics.record_feature_usage("alerts")
    summary = kpi_metrics.get_executive_summary()
    assert summary["adoption"]["total_events"] == 3
    assert summary["adoption"]["feature_hits"]["dashboard"] == 2


@pytest.mark.unit
def test_false_positive_rate():
    kpi_metrics.record_alert("warning", false_positive=False)
    kpi_metrics.record_alert("warning", false_positive=True)
    summary = kpi_metrics.get_executive_summary()
    assert summary["alert_quality"]["false_positive_rate"] == 0.5
    assert summary["alert_quality"]["alerts_total"] == 2


@pytest.mark.unit
def test_latency_sample_trimming():
    for i in range(510):
        kpi_metrics.record_latency("api-gateway", 0.001 + (i % 10) * 0.001)
    assert len(kpi_metrics._kpi_state["latency_samples_ms"]) <= 500
    summary = kpi_metrics.get_executive_summary()
    assert summary["latency"]["p95_ms"] is not None


@pytest.mark.unit
def test_empty_percentile_returns_none():
    assert kpi_metrics._percentile([], 0.95) is None
