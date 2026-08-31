import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MODULE_PATH = Path(__file__).resolve().parents[1] / "digital-twin-service" / "main.py"
spec = importlib.util.spec_from_file_location("digital_twin_service_main", MODULE_PATH)
digital_twin_service_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(digital_twin_service_main)

app = digital_twin_service_main.app
simulations_db = digital_twin_service_main.simulations_db


@pytest.fixture(autouse=True)
def clear_sim_db():
    simulations_db.clear()
    yield
    simulations_db.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_run_simulation(client):
    payload = {
        "well_name": "WELL-100",
        "simulation_type": "production_optimization",
        "parameters": {"pressure": 320.0, "flow_rate": 450.0},
    }

    response = client.post("/simulate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["well_name"] == "WELL-100"
    assert data["simulation_id"].startswith("SIM-")


def test_list_simulations(client):
    client.post(
        "/simulate",
        json={
            "well_name": "WELL-111",
            "simulation_type": "pressure_analysis",
            "parameters": {"pressure": 300.0},
        },
    )

    response = client.get("/simulations")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["simulations"][0]["well_name"] == "WELL-111"
