import importlib.util
import os
import sys
from pathlib import Path

import pytest
import pyotp
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "remote-operations-service" / "main.py"
)
spec = importlib.util.spec_from_file_location(
    "remote_operations_service_main", MODULE_PATH
)
remote_operations_service_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(remote_operations_service_main)

app = remote_operations_service_main.app
require_operator = remote_operations_service_main.require_operator
require_command_admin = remote_operations_service_main.require_command_admin

from shared.database import get_db
from shared.security import create_access_token
from shared.secure_command_workflow import secure_command_workflow


class _FakeResponse:
    """Stands in for the Digital Twin service's /simulate response."""

    status_code = 200

    def json(self):
        return {
            "results": {"predicted_pressure": 100}
        }  # below the 500 psi safety threshold


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResponse()


class _FakeProducer:
    """Stands in for the Kafka producer so tests don't need a real broker."""

    def send(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass


def override_get_db(test_db):
    def _override():
        try:
            yield test_db
        finally:
            pass

    return _override


@pytest.fixture(autouse=True)
def _fake_external_dependencies(monkeypatch):
    """
    Prevent real network calls: verify_two_factor() calls out to
    digital-twin-service over httpx, and execute paths publish to Kafka.
    Both are faked at the lowest level so the *real* workflow state-machine
    logic in secure_command_workflow.py still runs end to end.
    """
    monkeypatch.setattr(
        "shared.secure_command_workflow.httpx.AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(),
    )
    monkeypatch.setattr(secure_command_workflow, "_command_producer", _FakeProducer())
    monkeypatch.setattr(
        secure_command_workflow, "_critical_command_producer", _FakeProducer()
    )


@pytest.fixture
def client(test_db, test_user, admin_user):
    app.dependency_overrides[get_db] = override_get_db(test_db)
    app.dependency_overrides[require_operator] = lambda: {
        "sub": test_user.username,
        "role": test_user.role,
    }
    app.dependency_overrides[require_command_admin] = lambda: {
        "sub": admin_user.username,
        "role": admin_user.role,
    }
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _enable_2fa(db, user):
    """Enroll a user in 2FA and return their TOTP secret."""
    secret = pyotp.random_base32()
    user.two_factor_enabled = True
    user.two_factor_secret = secret
    db.add(user)
    db.commit()
    db.refresh(user)
    return secret


def test_full_happy_path_setpoint_adjustment(client, test_db, test_user):
    """initiate -> real 2FA check -> digital twin simulation -> two-person approval -> execute."""
    secret = _enable_2fa(test_db, test_user)

    initiate_resp = client.post(
        "/setpoint/adjust",
        json={
            "well_name": "WELL-1",
            "equipment_id": "PUMP-1",
            "parameter_name": "pressure",
            "target_value": 1500.0,
        },
    )
    assert initiate_resp.status_code == 200
    body = initiate_resp.json()
    assert body["status"] == "pending"
    command_id = body["command_id"]

    code = pyotp.TOTP(secret).now()
    verify_resp = client.post(
        f"/operations/{command_id}/verify-2fa", json={"two_fa_code": code}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["stage"] == "digital_twin_simulation"

    approve_resp = client.post(
        f"/operations/{command_id}/approve", json={"approval_notes": "looks safe"}
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["stage"] == "simulation_approved"

    execute_resp = client.post(f"/operations/{command_id}/execute")
    assert execute_resp.status_code == 200
    assert execute_resp.json()["stage"] == "executed"


def test_verify_2fa_rejects_wrong_code(client, test_db, test_user):
    """A wrong TOTP code must not advance the workflow past the 2FA gate."""
    _enable_2fa(test_db, test_user)

    initiate_resp = client.post(
        "/equipment/control",
        json={
            "well_name": "WELL-1",
            "equipment_id": "PUMP-1",
            "equipment_type": "pump",
            "operation": "stop",
        },
    )
    command_id = initiate_resp.json()["command_id"]

    resp = client.post(
        f"/operations/{command_id}/verify-2fa", json={"two_fa_code": "000000"}
    )
    assert resp.status_code == 400


def test_verify_2fa_requires_2fa_enrollment(client):
    """A requester who never enrolled in 2FA can never verify a command (no secret to check against)."""
    initiate_resp = client.post(
        "/valve/control",
        json={
            "well_name": "WELL-1",
            "valve_id": "VALVE-1",
            "operation": "open",
        },
    )
    command_id = initiate_resp.json()["command_id"]

    resp = client.post(
        f"/operations/{command_id}/verify-2fa", json={"two_fa_code": "123456"}
    )
    assert resp.status_code == 400


def test_two_person_rule_rejects_self_approval(client, test_db, test_user):
    """The requester must not be able to approve their own command."""
    secret = _enable_2fa(test_db, test_user)

    initiate_resp = client.post(
        "/equipment/control",
        json={
            "well_name": "WELL-1",
            "equipment_id": "PUMP-2",
            "equipment_type": "pump",
            "operation": "start",
        },
    )
    command_id = initiate_resp.json()["command_id"]

    code = pyotp.TOTP(secret).now()
    verify_resp = client.post(
        f"/operations/{command_id}/verify-2fa", json={"two_fa_code": code}
    )
    assert verify_resp.status_code == 200

    # Simulate the requester themself holding an admin role and trying to self-approve.
    app.dependency_overrides[require_command_admin] = lambda: {
        "sub": test_user.username,
        "role": "system_admin",
    }
    resp = client.post(f"/operations/{command_id}/approve", json={})
    assert resp.status_code == 400
    assert (
        "two-person" in resp.json()["detail"].lower()
        or "own command" in resp.json()["detail"].lower()
    )


def test_emergency_shutdown_executes_without_crashing(test_db, admin_user):
    """
    Regression test: this endpoint used to pass `critical=True` to a Command
    model with no such column (TypeError on every call) and never actually
    published anywhere even when it didn't crash. Both are now fixed.
    """
    app.dependency_overrides[get_db] = override_get_db(test_db)
    token = create_access_token(
        data={"sub": admin_user.username, "role": admin_user.role}
    )
    test_client = TestClient(app)

    resp = test_client.post(
        "/emergency/shutdown",
        json={"well_name": "WELL-1", "reason": "gas leak detected"},
        headers={"Authorization": f"Bearer {token}"},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "executed"
