import json
from pathlib import Path

from shared.threat_detection import (
    SIEMEventLogger,
    ThreatDetector,
    is_private_or_loopback,
)


def test_threat_detector_scores_spiky_traffic_and_auth_failures():
    detector = ThreatDetector()

    risk = 0
    reasons = []
    for _ in range(130):
        risk, reasons = detector.evaluate(
            ip="10.10.10.10",
            user="operator",
            path="/api/alert/alerts",
            method="GET",
            status_code=200,
            user_agent="ogim-test-client",
        )

    assert risk > 0
    assert "high_request_rate_ip" in reasons

    risk2, reasons2 = detector.evaluate(
        ip="10.10.10.10",
        user="operator",
        path="/api/admin",
        method="GET",
        status_code=403,
        user_agent="sqlmap",
    )
    assert risk2 >= risk
    assert "authz_failure" in reasons2
    assert "known_attack_pattern" in reasons2


def test_siem_logger_writes_jsonl_file(tmp_path: Path):
    out_file = tmp_path / "siem-events.jsonl"
    logger = SIEMEventLogger(output_file=str(out_file))

    logger.emit(
        "threat_detected_warning",
        "medium",
        {"ip": "192.168.1.20", "risk_score": 55, "reasons": ["authz_failure"]},
    )

    assert out_file.exists()
    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "threat_detected_warning"
    assert payload["severity"] == "medium"
    assert payload["payload"]["risk_score"] == 55


def test_siem_logger_write_failure_and_ip_helpers(monkeypatch):
    logger = SIEMEventLogger(output_file="Z:/non-existent/siem.jsonl")
    logger.emit("test_event", "low", {"ok": True})

    assert is_private_or_loopback("127.0.0.1") is True
    assert is_private_or_loopback("192.168.1.1") is True
    assert is_private_or_loopback("8.8.8.8") is False
    assert is_private_or_loopback("not-an-ip") is False

    detector = ThreatDetector()
    risk, reasons = detector.evaluate(
        ip="8.8.8.8",
        user=None,
        path="/health",
        method="DELETE",
        status_code=200,
        user_agent="clean-client",
    )
    assert risk >= 30
    assert "suspicious_method_for_health" in reasons
