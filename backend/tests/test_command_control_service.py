import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "command-control-service" / "main.py"
)
spec = importlib.util.spec_from_file_location(
    "command_control_service_main", MODULE_PATH
)
command_control_service_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(command_control_service_main)

app = command_control_service_main.app
require_command_read = command_control_service_main.require_command_read
require_command_admin = command_control_service_main.require_command_admin

from shared.database import get_db


def override_get_db(test_db):
    def _override():
        try:
            yield test_db
        finally:
            pass

    return _override


class _FakeCommandProducer:
    """Stands in for the real Kafka producer in tests.

    execute_command() intentionally raises (-> 500) when no producer is
    available at all, since a command that isn't actually relayed to SCADA
    must not be reported as successfully executed. That's correct production
    behavior, not something to bypass here -- so tests exercising the success
    path need a producer that accepts sends, not None.
    """

    def send(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass


@pytest.fixture
def client(test_db, test_user, admin_user, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(test_db)
    app.dependency_overrides[require_command_read] = lambda: {
        "sub": test_user.username,
        "role": test_user.role,
    }
    app.dependency_overrides[require_command_admin] = lambda: {
        "sub": admin_user.username,
        "role": admin_user.role,
    }
    monkeypatch.setattr(
        command_control_service_main, "command_producer", _FakeCommandProducer()
    )
    monkeypatch.setattr(
        command_control_service_main,
        "critical_command_producer",
        _FakeCommandProducer(),
    )
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_create_command(client, test_user):
    payload = {
        "well_name": "WELL-1",
        "equipment_id": "PUMP-1",
        "command_type": "start_pump",
        "parameters": {"speed": 1200},
        "requested_by": test_user.username,
        "requires_two_factor": False,
    }

    response = client.post("/commands", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert "command_id" in data


def test_approve_and_execute_command(client, test_user):
    payload = {
        "well_name": "WELL-2",
        "equipment_id": "VALVE-1",
        "command_type": "open_valve",
        "parameters": {"percent": 50},
        "requested_by": test_user.username,
    }

    create_resp = client.post("/commands", json=payload)
    command_id = create_resp.json()["command_id"]

    approve_resp = client.post(f"/commands/{command_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    execute_resp = client.post(f"/commands/{command_id}/execute")
    assert execute_resp.status_code == 200
    assert execute_resp.json()["status"] == "executed"
