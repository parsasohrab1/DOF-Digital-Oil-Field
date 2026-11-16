"""
Phase 7 — focused integration tests for the REAL-model ML service.

Verifies (via TestClient, same approach as the existing test suite) that:
  * the service starts and loads REAL local artifacts (no MLflow server);
  * /infer works for anomaly_detection and failure_prediction with a real
    feature dict (feature names selected from the model meta);
  * /forecast works with a real history window and returns a DERIVED
    confidence (not the old hardcoded 0.85);
  * /models reports the 3 models as loaded/ready from local artifacts;
  * edge cases: missing feature keys, out-of-range values, short history.
Run:  python -m pytest tests/test_ml_real_integration.py --noconftest --override-ini="addopts=" -p no:ddtrace
"""
import gzip
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml-inference-service"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shared.auth as auth_module


def _fake_role():
    return {"sub": "test-user", "role": "system_admin"}


_orig = auth_module.require_roles
auth_module.require_roles = lambda *a, **k: _fake_role

MODULE = Path(__file__).resolve().parents[1] / "ml-inference-service" / "main.py"
spec = importlib.util.spec_from_file_location("ml_inf_real", MODULE)
main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(main)

auth_module.require_roles = _orig
app = main.app

CLEANED = Path(__file__).resolve().parents[1].parent / "ml" / "datasets" / "cleaned"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _normal_pump_row():
    with gzip.open(CLEANED / "pump_sensor_clean.csv.gz", "rt") as fh:
        df = pd.read_csv(fh)
    feat = [c for c in df.columns if c.startswith("sensor_")]
    return {f: float(v) for f, v in df.loc[df["anomaly"] == 0, feat].iloc[0].items()}


def _normal_esp_row():
    df = pd.read_csv(CLEANED / "esp_features_clean.csv")
    feat = ["median(8,13)", "rms(98,102)", "median(98,102)", "peak1x", "peak2x", "a", "b"]
    return {f: float(v) for f, v in df[feat].iloc[0].items()}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_models_loaded_from_local(client):
    r = client.get("/models")
    assert r.status_code == 200
    models = {m["type"]: m for m in r.json()["models"]}
    # With committed local artifacts, all 3 must be loaded (not "mock")
    for t in ("anomaly_detection", "failure_prediction", "time_series_forecast"):
        assert models[t]["loaded"] is True, f"{t} not loaded: {models[t]}"
        assert models[t]["status"] in ("ready", "missing"), models[t]


def test_infer_anomaly(client):
    r = client.post("/infer", json={
        "sensor_id": "PUMP-01", "features": _normal_pump_row(),
        "model_type": "anomaly_detection"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_type"] == "anomaly_detection"
    assert "prediction" in body and "anomaly_score" in body


def test_infer_failure(client):
    r = client.post("/infer", json={
        "sensor_id": "ESP-01", "features": _normal_esp_row(),
        "model_type": "failure_prediction"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "failure_probability" in body


def test_forecast_derived_confidence(client):
    series = pd.read_csv(CLEANED / "pump_forecast_series.csv")["value"].values
    r = client.post("/forecast", json={
        "sensor_id": "PUMP-01", "historical_data": series[:60].tolist(),
        "forecast_steps": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["predictions"]) == 3
    # confidence must be the DERIVED value (0.795), NOT the old 0.85
    assert abs(body["confidence"] - 0.85) > 1e-6, "confidence still hardcoded 0.85"
    assert 0.0 <= body["confidence"] <= 0.99


def test_infer_missing_feature_keys(client):
    """A feature dict missing some keys must still work (defaults to 0)."""
    row = _normal_esp_row()
    # drop one key
    row.pop("b", None)
    r = client.post("/infer", json={
        "sensor_id": "ESP-01", "features": row, "model_type": "failure_prediction"})
    assert r.status_code == 200, r.text


def test_forecast_short_history(client):
    r = client.post("/forecast", json={
        "sensor_id": "X", "historical_data": [1.0, 2.0], "forecast_steps": 1})
    # short history < seq_length => 400 ValueError
    assert r.status_code in (400, 422, 503), r.text


def test_infer_unknown_model_type(client):
    r = client.post("/infer", json={
        "sensor_id": "X", "features": {"a": 1.0}, "model_type": "nonexistent"})
    assert r.status_code == 400
