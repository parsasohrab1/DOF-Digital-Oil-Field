"""
Regression test for the API Gateway login chicken-and-egg bug.

Before the fix, `/api/auth/token` (and `/api/auth/refresh`, `/api/auth/health`)
required a valid Bearer token to reach the proxy, which made it impossible for
any user to ever obtain their first token through the gateway. These tests
exercise the real (unmocked) `authenticate_request` / `enforce_zero_trust`
gateway logic to make sure that regression can't come back silently.
"""

import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

MODULE_PATH = Path(__file__).resolve().parents[2] / "api-gateway" / "main.py"
spec = importlib.util.spec_from_file_location("api_gateway_login_flow", MODULE_PATH)
api_gateway = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api_gateway)

client = TestClient(api_gateway.app)


class DummyAuthUpstream:
    """Stands in for auth-service, simulating its real token response."""

    async def request(self, method, url, **kwargs):
        if url.endswith("/token"):
            return httpx.Response(
                status_code=200,
                json={
                    "access_token": "fake-access-token",
                    "refresh_token": "fake-refresh-token",
                    "token_type": "bearer",
                },
            )
        if url.endswith("/health"):
            return httpx.Response(status_code=200, json={"status": "healthy"})
        return httpx.Response(status_code=200, json={"result": "ok"})


@pytest.fixture(autouse=True)
def reset_state():
    api_gateway.upstream_client = DummyAuthUpstream()
    api_gateway.settings.RATE_LIMIT_ENABLED = False
    api_gateway.settings.ZERO_TRUST_ENFORCED = False
    api_gateway.response_cache.clear()
    yield


def test_login_without_a_token_reaches_auth_service():
    """The core regression: logging in must not itself require being logged in."""
    response = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "irrelevant-for-this-test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_without_a_token_reaches_auth_service_under_zero_trust():
    """The bypass must hold even when zero-trust enforcement is enabled."""
    api_gateway.settings.ZERO_TRUST_ENFORCED = True
    api_gateway.settings.ZERO_TRUST_ALLOWED_NETWORKS = ""

    response = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "irrelevant-for-this-test"},
    )
    assert response.status_code == 200


def test_refresh_endpoint_is_reachable_without_a_token():
    response = client.post("/api/auth/refresh", params={"refresh_token": "whatever"})
    assert response.status_code == 200


def test_auth_health_endpoint_is_reachable_without_a_token():
    response = client.get("/api/auth/health")
    assert response.status_code == 200


def test_protected_auth_path_still_requires_a_token():
    """Guard against widening the public bypass to all of /api/auth/*."""
    response = client.get("/api/auth/users/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authorization token"


def test_other_services_still_require_a_token():
    response = client.get("/api/alert/alerts")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authorization token"
