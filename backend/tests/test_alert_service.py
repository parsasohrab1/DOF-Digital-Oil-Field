"""
Tests for alert service
"""

import pytest
import sys
import os
from datetime import datetime
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alert-service"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app, require_alert_read, require_alert_write, require_alert_admin
from shared.database import get_db
from shared.models import Alert, AlertRule


def override_get_db(test_db):
    """Override database dependency"""

    def _override():
        try:
            yield test_db
        finally:
            pass

    return _override


@pytest.fixture
def client(test_db):
    """Create test client"""
    app.dependency_overrides[get_db] = override_get_db(test_db)
    app.dependency_overrides[require_alert_read] = lambda: {
        "sub": "testuser",
        "role": "system_admin",
    }
    app.dependency_overrides[require_alert_write] = lambda: {
        "sub": "testuser",
        "role": "system_admin",
    }
    app.dependency_overrides[require_alert_admin] = lambda: {
        "sub": "testuser",
        "role": "system_admin",
    }
    return TestClient(app)


def test_create_alert(client):
    """Test creating an alert"""
    response = client.post(
        "/alerts",
        json={
            "alert_id": "TEST-ALERT-001",
            "timestamp": datetime.utcnow().isoformat(),
            "severity": "critical",
            "status": "open",
            "well_name": "WELL-A-001",
            "sensor_id": "WELL-A-001-pump-pressure",
            "message": "Pressure exceeded threshold",
            "rule_name": "pressure_high",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "alert_id" in data


def test_list_alerts(client):
    """Test listing alerts"""
    response = client.get("/alerts")

    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert "count" in data


def test_alert_correlation_groups(client):
    """Test correlation grouping endpoint"""
    now = datetime.utcnow().isoformat()
    client.post(
        "/alerts",
        json={
            "alert_id": "TEST-CORR-001",
            "timestamp": now,
            "severity": "warning",
            "status": "open",
            "well_name": "WELL-A-001",
            "sensor_id": "WELL-A-001-pump-pressure",
            "message": "Pressure high",
            "rule_name": "pressure_high",
        },
    )
    client.post(
        "/alerts",
        json={
            "alert_id": "TEST-CORR-002",
            "timestamp": now,
            "severity": "warning",
            "status": "open",
            "well_name": "WELL-A-001",
            "sensor_id": "WELL-A-001-pump-pressure",
            "message": "Pressure still high",
            "rule_name": "pressure_high",
        },
    )

    response = client.get("/alerts/correlations")
    assert response.status_code == 200
    data = response.json()
    assert "groups" in data
    assert data["count"] >= 1


def test_alert_rca_endpoint(client):
    """Test RCA generation endpoint"""
    alert_id = "TEST-RCA-001"
    response = client.post(
        "/alerts",
        json={
            "alert_id": alert_id,
            "timestamp": datetime.utcnow().isoformat(),
            "severity": "critical",
            "status": "open",
            "well_name": "WELL-B-001",
            "sensor_id": "WELL-B-001-valve-temp",
            "message": "Temperature exceeded threshold",
            "rule_name": "temperature_high",
        },
    )
    assert response.status_code == 201

    rca_response = client.post(f"/alerts/{alert_id}/rca", json={"lookback_minutes": 60})
    assert rca_response.status_code == 200
    rca_data = rca_response.json()
    assert rca_data["alert_id"] == alert_id
    assert "rca" in rca_data
    assert "suspected_root_cause" in rca_data["rca"]


def test_cross_well_correlation_flags_systemic_signal(client):
    """Three+ wells firing the same rule at once should get a shared
    facility_correlation_id, distinct from each well's own correlation_id."""
    now = datetime.utcnow().isoformat()
    wells = ["WELL-X-001", "WELL-X-002", "WELL-X-003"]
    for i, well in enumerate(wells):
        response = client.post(
            "/alerts",
            json={
                "alert_id": f"TEST-XWELL-{i:03d}",
                "timestamp": now,
                "severity": "critical",
                "status": "open",
                "well_name": well,
                "sensor_id": f"{well}-comm-link",
                "message": "Communication loss",
                "rule_name": "comm_loss",
            },
        )
        assert response.status_code == 201

    facility_response = client.get("/alerts/correlations/facility")
    assert facility_response.status_code == 200
    data = facility_response.json()
    assert data["count"] >= 1
    group = data["groups"][0]
    assert group["distinct_wells"] >= 3
    assert set(wells).issubset(set(group["wells"]))


def test_single_well_alert_has_no_facility_correlation(client):
    """A rule firing on only one well must not be flagged as systemic."""
    response = client.post(
        "/alerts",
        json={
            "alert_id": "TEST-SINGLEWELL-001",
            "timestamp": datetime.utcnow().isoformat(),
            "severity": "warning",
            "status": "open",
            "well_name": "WELL-Y-001",
            "sensor_id": "WELL-Y-001-flow",
            "message": "Flow anomaly",
            "rule_name": "flow_anomaly_unique_rule",
        },
    )
    assert response.status_code == 201

    facility_response = client.get("/alerts/correlations/facility")
    assert facility_response.status_code == 200
    facility_ids = {
        g["facility_correlation_id"] for g in facility_response.json()["groups"]
    }
    matching = [
        fid for fid in facility_ids if fid and "flow_anomaly_unique_rule" in fid
    ]
    assert matching == []


def test_rca_reports_systemic_root_cause_across_wells(client):
    """RCA on a cross-well incident should point to a systemic cause,
    not a well-local one."""
    now = datetime.utcnow().isoformat()
    wells = ["WELL-Z-001", "WELL-Z-002", "WELL-Z-003", "WELL-Z-004"]
    last_alert_id = None
    for i, well in enumerate(wells):
        alert_id = f"TEST-RCA-XWELL-{i:03d}"
        last_alert_id = alert_id
        response = client.post(
            "/alerts",
            json={
                "alert_id": alert_id,
                "timestamp": now,
                "severity": "critical",
                "status": "open",
                "well_name": well,
                "sensor_id": f"{well}-scada-link",
                "message": "SCADA link down",
                "rule_name": "scada_link_down",
            },
        )
        assert response.status_code == 201

    rca_response = client.post(
        f"/alerts/{last_alert_id}/rca", json={"lookback_minutes": 60}
    )
    assert rca_response.status_code == 200
    rca = rca_response.json()["rca"]
    assert rca["scope"] == "facility"
    assert rca["suspected_root_cause"] == "systemic:scada_link_down"
    assert rca["distinct_wells"] >= 4


def test_create_alert_rule(client):
    """Test creating an alert rule"""
    response = client.post(
        "/rules",
        json={
            "rule_id": "test-rule-001",
            "name": "Test Rule",
            "description": "Test alert rule",
            "condition": "threshold_high",
            "threshold": 450.0,
            "severity": "critical",
            "enabled": True,
        },
    )

    assert response.status_code == 200


def test_list_alert_rules(client):
    """Test listing alert rules"""
    response = client.get("/rules")

    assert response.status_code == 200
    data = response.json()
    assert "rules" in data
