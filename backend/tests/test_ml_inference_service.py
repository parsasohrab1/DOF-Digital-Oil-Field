"""
Tests for ML Model Management: version compare, A/B testing, drift detection.

These exercise the exact request/response shapes the MLModels frontend page
uses (frontend/web/src/pages/MLModels.tsx + api/services.ts's mlAPI), since a
previous mismatch there (frontend sent a single feature dict where the
backend requires a list of samples) meant the UI's drift-detection button
always failed with a 422 in practice despite both sides "existing".
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml-inference-service"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shared.auth as auth_module


def _fake_role_dependency():
    return {"sub": "test-user", "role": "system_admin"}


# require_roles({...}) is called inline at every route's `Depends(...)`, each
# producing a distinct closure -- patch it before the module is loaded so
# every route ends up depending on the same fake, overridable callable.
_original_require_roles = auth_module.require_roles
auth_module.require_roles = lambda *args, **kwargs: _fake_role_dependency

MODULE_PATH = Path(__file__).resolve().parents[1] / "ml-inference-service" / "main.py"
spec = importlib.util.spec_from_file_location("ml_inference_service_main", MODULE_PATH)
ml_inference_service_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ml_inference_service_main)

auth_module.require_roles = _original_require_roles

app = ml_inference_service_main.app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.skipif(
    not ml_inference_service_main.MLFLOW_AVAILABLE,
    reason="mlflow package not installed in this environment",
)
class TestDriftDetection:
    def test_baseline_normalizes_a_single_flat_dict(self, client):
        """A field_validator now normalizes a single {"feature": value} dict
        into a one-sample batch instead of 422ing on it (defense in depth
        alongside the frontend always sending an array)."""
        response = client.post(
            "/models/anomaly_detection/drift/baseline",
            json={"features": {"pressure": 318, "temperature": 84}},
        )
        assert response.status_code == 200
        assert response.json()["baseline"]["sample_size"] == 1

    def test_baseline_and_detect_full_cycle(self, client):
        baseline_response = client.post(
            "/models/anomaly_detection/drift/baseline",
            json={
                "features": [
                    {"pressure": 318, "temperature": 84},
                    {"pressure": 322, "temperature": 86},
                ]
            },
        )
        assert baseline_response.status_code == 200
        baseline_body = baseline_response.json()
        assert baseline_body["baseline"]["sample_size"] == 2
        assert baseline_body["baseline"]["means"]["pressure"] == 320.0

        no_drift_response = client.post(
            "/models/anomaly_detection/drift/detect",
            json={"features": [{"pressure": 320, "temperature": 85}], "threshold": 2.0},
        )
        assert no_drift_response.status_code == 200
        assert no_drift_response.json()["drift_detected"] is False

        drift_response = client.post(
            "/models/anomaly_detection/drift/detect",
            json={"features": [{"pressure": 500, "temperature": 84}], "threshold": 1.0},
        )
        assert drift_response.status_code == 200
        drift_body = drift_response.json()
        assert drift_body["drift_detected"] is True
        assert drift_body["feature_drift"]["pressure"]["drift"] is True

    def test_detect_without_baseline_returns_400(self, client):
        response = client.post(
            "/models/failure_prediction/drift/detect",
            json={"features": [{"pressure": 100}]},
        )
        assert response.status_code == 400


@pytest.mark.skipif(
    not ml_inference_service_main.MLFLOW_AVAILABLE,
    reason="mlflow package not installed in this environment",
)
class TestABTesting:
    def test_configure_and_read_back_ab_test(self, client):
        configure_response = client.post(
            "/models/anomaly_detection/ab-test",
            json={
                "baseline_version": 1,
                "candidate_version": 2,
                "candidate_weight": 0.3,
            },
        )
        assert configure_response.status_code == 200
        cfg = configure_response.json()["ab_test"]
        assert cfg["baseline_version"] == 1
        assert cfg["candidate_version"] == 2
        assert cfg["candidate_weight"] == 0.3

        get_response = client.get("/models/anomaly_detection/ab-test")
        assert get_response.status_code == 200
        assert get_response.json()["ab_test"]["candidate_version"] == 2

    def test_rejects_out_of_range_weight(self, client):
        response = client.post(
            "/models/anomaly_detection/ab-test",
            json={
                "baseline_version": 1,
                "candidate_version": 2,
                "candidate_weight": 1.5,
            },
        )
        assert response.status_code == 400

    def test_time_series_forecast_not_supported_for_ab_testing(self, client):
        response = client.post(
            "/models/time_series_forecast/ab-test",
            json={
                "baseline_version": 1,
                "candidate_version": 2,
                "candidate_weight": 0.5,
            },
        )
        assert response.status_code == 400


class TestFederatedLearning:
    """Regression coverage for the federated learning coordinator: previously
    this whole feature was a frontend-only mock (hardcoded nodes, Math.random()
    training history) with no backend at all."""

    @pytest.fixture(autouse=True)
    def reset_coordinator(self):
        # federated_coordinator is a module-level singleton shared by every
        # test in this class (the module is loaded once at collection time),
        # so each test needs a clean slate.
        coordinator = ml_inference_service_main.federated_coordinator
        coordinator.nodes.clear()
        coordinator.round_number = 0
        coordinator.global_weights = None
        coordinator.global_accuracy = None
        coordinator.round_history.clear()
        yield

    def _submit(self, client, node_id, well_name, weights, accuracy, data_size):
        return client.post(
            f"/federated/nodes/{node_id}/update",
            json={
                "well_name": well_name,
                "location": "Field Test",
                "local_weights": weights,
                "local_accuracy": accuracy,
                "data_size": data_size,
            },
        )

    def test_submit_rejects_wrong_weight_dimension(self, client):
        response = self._submit(client, "NODE-BAD", "WELL-X", [1.0, 2.0], 0.9, 100)
        assert response.status_code == 400

    def test_aggregate_requires_minimum_nodes(self, client):
        response = client.post(
            "/federated/nodes/NODE-SOLO/update",
            json={
                "well_name": "WELL-1",
                "location": "Field A",
                "local_weights": [0.1, 0.2, 0.3, 0.4, 0.5],
                "local_accuracy": 0.9,
                "data_size": 100,
            },
        )
        assert response.status_code == 200

        agg_response = client.post("/federated/aggregate", json={"min_nodes": 2})
        assert agg_response.status_code == 400

    def test_fedavg_is_correctly_weighted_by_data_size(self, client):
        # Two nodes with very different weights and very different dataset
        # sizes: the aggregate must land close to the larger node's weights,
        # not a plain unweighted average.
        self._submit(
            client, "NODE-SMALL", "WELL-1", [0.0, 0.0, 0.0, 0.0, 0.0], 0.80, 10
        )
        self._submit(
            client, "NODE-BIG", "WELL-2", [10.0, 10.0, 10.0, 10.0, 10.0], 0.90, 990
        )

        response = client.post("/federated/aggregate", json={"min_nodes": 2})
        assert response.status_code == 200
        body = response.json()
        assert body["round"] == 1
        # weighted average: 0*10/1000 + 10*990/1000 == 9.9, nowhere near the
        # unweighted average of 5.0
        assert all(w > 9.0 for w in body["global_weights"])
        assert 0.89 < body["global_accuracy"] < 0.90

        nodes_response = client.get("/federated/nodes")
        assert nodes_response.status_code == 200
        assert len(nodes_response.json()["nodes"]) == 2

        global_response = client.get("/federated/global-model")
        assert global_response.status_code == 200
        assert global_response.json()["global_model"]["round"] == 1
        assert len(global_response.json()["round_history"]) == 1

    def test_train_and_submit_fits_a_real_local_model(self, client):
        samples = [
            {
                "pressure": 300 + i,
                "temperature": 80 + i * 0.1,
                "flow_rate": 400,
                "vibration": 0.1,
            }
            for i in range(20)
        ] + [
            {
                "pressure": 600 + i,
                "temperature": 95 + i * 0.1,
                "flow_rate": 700,
                "vibration": 0.9,
            }
            for i in range(20)
        ]
        labels = [0.0] * 20 + [1.0] * 20

        response = client.post(
            "/federated/nodes/NODE-TRAIN/train-and-submit",
            json={
                "well_name": "WELL-3",
                "location": "Field C",
                "samples": samples,
                "labels": labels,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data_size"] == 40
        assert body["local_accuracy"] > 0.8  # this is a trivially separable dataset
