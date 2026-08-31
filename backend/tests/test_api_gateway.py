import importlib.util
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

MODULE_PATH = Path(__file__).resolve().parents[1] / "api-gateway" / "main.py"
spec = importlib.util.spec_from_file_location("api_gateway", MODULE_PATH)
api_gateway = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api_gateway)

client = TestClient(api_gateway.app)


@pytest.fixture(autouse=True)
def reset_state():
    # Ensure request state is clean between tests
    class DummyUpstreamClient:
        async def request(self, *args, **kwargs):
            return httpx.Response(status_code=200, json={"result": "ok"})

    api_gateway.upstream_client = DummyUpstreamClient()
    api_gateway.settings.RATE_LIMIT_ENABLED = False
    api_gateway.settings.ZERO_TRUST_ENFORCED = False
    api_gateway.settings.API_SECURITY_ENABLE_INPUT_HARDENING = True
    api_gateway.response_cache.clear()
    yield


def stub_async_client(monkeypatch, response=None, exception=None):
    class DummyUpstreamClient:
        async def request(self, *args, **kwargs):
            if exception:
                raise exception
            return response

    api_gateway.upstream_client = DummyUpstreamClient()


def stub_decode_token(monkeypatch, *, payload=None, error=None):
    def fake_decode(token: str):
        if error:
            raise error
        return payload or {"sub": "test-user", "role": "field_operator"}

    monkeypatch.setattr(api_gateway, "decode_token", fake_decode)


def auth_header(token: str = "valid-token"):
    return {"Authorization": f"Bearer {token}"}


def test_proxy_requires_authorization_header():
    response = client.get("/api/alert/alerts")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authorization token"


def test_proxy_rejects_invalid_token(monkeypatch):
    stub_decode_token(monkeypatch, error=ValueError("Token has expired"))

    response = client.get("/api/alert/alerts", headers=auth_header())
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


def test_proxy_success_json(monkeypatch):
    stub_decode_token(monkeypatch)

    response = client.get("/api/alert/alerts", headers=auth_header())
    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_proxy_downstream_error_propagates_status(monkeypatch):
    stub_decode_token(monkeypatch)
    downstream_response = httpx.Response(status_code=404, json={"detail": "Not found"})
    stub_async_client(monkeypatch, response=downstream_response)

    response = client.get("/api/alert/alerts", headers=auth_header())
    assert response.status_code == 404
    assert response.json()["detail"] == {"detail": "Not found"}


def test_proxy_non_json_response(monkeypatch):
    stub_decode_token(monkeypatch)
    downstream_response = httpx.Response(
        status_code=200, content=b"plain-text", headers={"content-type": "text/plain"}
    )
    stub_async_client(monkeypatch, response=downstream_response)

    response = client.get("/api/alert/alerts", headers=auth_header())
    assert response.status_code == 200
    assert response.text == "plain-text"


def test_proxy_timeout_returns_gateway_timeout(monkeypatch):
    stub_decode_token(monkeypatch)
    stub_async_client(monkeypatch, exception=httpx.TimeoutException("Timeout"))

    response = client.get("/api/alert/alerts", headers=auth_header())
    assert response.status_code == 504
    assert response.json()["detail"] == "Service alert timed out"


def test_proxy_forbidden_for_insufficient_role(monkeypatch):
    api_gateway.settings.ZERO_TRUST_ENFORCED = True
    api_gateway.settings.ZERO_TRUST_ALLOWED_NETWORKS = ""
    stub_decode_token(monkeypatch, payload={"sub": "viewer", "role": "viewer"})
    response = client.get("/api/command-control/commands", headers=auth_header())
    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


def test_proxy_blocks_suspicious_query(monkeypatch):
    stub_decode_token(monkeypatch)
    response = client.get(
        "/api/alert/alerts?search=<script>alert(1)</script>",
        headers=auth_header(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Request contains blocked input patterns"


def test_proxy_blocks_malformed_json(monkeypatch):
    stub_decode_token(monkeypatch)
    response = client.post(
        "/api/alert/alerts",
        headers={**auth_header(), "Content-Type": "application/json"},
        content="{not-json",
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Malformed JSON payload"


def test_proxy_blocks_sqli_in_json_body(monkeypatch):
    stub_decode_token(monkeypatch)
    response = client.post(
        "/api/alert/alerts",
        headers={**auth_header(), "Content-Type": "application/json"},
        json={"message": "1 OR 1=1", "well_name": "PROD-001"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Request contains blocked input patterns"


def test_kpi_summary_endpoint():
    response = client.get("/kpi/summary")
    assert response.status_code == 200
    body = response.json()
    assert "latency" in body
    assert "uptime" in body
    assert "adoption" in body
    assert "alert_quality" in body


def test_kpi_cache_stats_endpoint():
    response = client.get("/kpi/cache-stats")
    assert response.status_code == 200
    assert "hits" in response.json()


def test_kpi_feature_usage_endpoint():
    response = client.post("/kpi/feature-usage", json={"feature": "dashboard"})
    assert response.status_code == 200
    assert response.json()["recorded"] is True

    bad = client.post("/kpi/feature-usage", json={"feature": "<script>"})
    assert bad.status_code == 400

    empty = client.post("/kpi/feature-usage", json={"feature": ""})
    assert empty.status_code == 400


def test_kpi_cache_invalidate_endpoint():
    response = client.post("/kpi/cache/invalidate", json={})
    assert response.status_code == 200
    assert response.json()["invalidated"] is True


def test_proxy_blocks_oversized_body(monkeypatch):
    stub_decode_token(monkeypatch)
    api_gateway.settings.API_SECURITY_MAX_BODY_BYTES = 32
    response = client.post(
        "/api/alert/alerts",
        headers={**auth_header(), "Content-Type": "application/json"},
        content=b'{"message":"' + (b"x" * 100) + b'"}',
    )
    assert response.status_code == 413


def test_proxy_blocks_too_many_query_params(monkeypatch):
    stub_decode_token(monkeypatch)
    api_gateway.settings.API_SECURITY_MAX_QUERY_PARAMS = 3
    qs = "&".join([f"p{i}=v" for i in range(10)])
    response = client.get(f"/api/alert/alerts?{qs}", headers=auth_header())
    assert response.status_code == 400
    assert "Too many query parameters" in response.json()["detail"]


def test_security_siem_events_endpoint():
    response = client.get("/security/siem/events?limit=5")
    assert response.status_code == 200
    body = response.json()
    assert "events" in body
    assert "summary" in body


def test_security_threat_status_endpoint():
    response = client.get("/security/threat/status")
    assert response.status_code == 200
    body = response.json()
    assert "zero_trust_enforced" in body
    assert "api_security_hardening" in body
    assert "threat_block_threshold" in body


def test_internal_realtime_publish_rejects_wrong_token():
    response = client.post(
        "/internal/realtime/publish",
        headers={"X-Internal-Token": "not-the-real-token"},
        json={"type": "sensor_data", "data": {"sensor_records": []}},
    )
    assert response.status_code == 401


def test_realtime_websocket_delivers_pushed_event_immediately():
    """Regression test for data-ingestion -> Gateway WebSocket wiring.

    Previously the WebSocket loop only ever polled data-ingestion's REST
    endpoint once a second; a service pushing to /internal/realtime/publish
    must now reach a connected client without waiting for that poll cycle.
    """
    from shared.security import create_access_token

    token = create_access_token(data={"sub": "test-user", "role": "field_operator"})

    with client.websocket_connect(f"/stream/realtime/ws?token={token}") as websocket:
        publish_response = client.post(
            "/internal/realtime/publish",
            headers={"X-Internal-Token": api_gateway.settings.INTERNAL_SERVICE_TOKEN},
            json={
                "type": "sensor_data",
                "data": {
                    "sensor_records": [{"sensor_id": "WELL-1-pressure", "value": 123.4}]
                },
            },
        )
        assert publish_response.status_code == 200

        # The fallback heartbeat snapshot (sent when nothing has been
        # pushed recently) can legitimately interleave with the pushed
        # event depending on scheduling, so scan a bounded number of
        # messages rather than assuming the very first one is ours.
        message = None
        for _ in range(5):
            candidate = websocket.receive_json()
            if candidate.get("type") == "sensor_data":
                message = candidate
                break
        assert message is not None, "sensor_data event was never delivered"
        assert message["data"]["sensor_records"][0]["sensor_id"] == "WELL-1-pressure"
