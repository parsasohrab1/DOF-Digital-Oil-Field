import pytest
from fastapi.testclient import TestClient

# Reuse the FastAPI apps already loaded by the per-service test modules rather
# than re-executing each service's main.py a second time: prometheus_client's
# default CollectorRegistry is a process-wide singleton, so loading the same
# main.py twice in one pytest run (e.g. once here, once in
# test_digital_twin_service.py) registers the same metric names twice and
# raises "Duplicated timeseries in CollectorRegistry".
from tests.test_auth_service import app as auth_app
from tests.test_api_gateway import api_gateway
from tests.test_alert_service import app as alert_app
from tests.test_reporting_service import app as reporting_app
from tests.test_digital_twin_service import app as twin_app
from shared.database import get_db

gateway_app = api_gateway.app


@pytest.fixture(autouse=True)
def _override_alert_health_db(test_db):
    # alert-service's /health queries the DB (open alert count), so it needs
    # the same sqlite test_db every other suite uses instead of the real
    # Postgres connection string from settings.
    def _get_db():
        try:
            yield test_db
        finally:
            pass

    alert_app.dependency_overrides[get_db] = _get_db
    yield
    alert_app.dependency_overrides.pop(get_db, None)


@pytest.mark.smoke
def test_auth_health():
    client = TestClient(auth_app)
    resp = client.get("/health")
    assert resp.status_code == 200


@pytest.mark.smoke
def test_gateway_root():
    client = TestClient(gateway_app)
    resp = client.get("/")
    assert resp.status_code == 200


@pytest.mark.smoke
def test_alert_health():
    client = TestClient(alert_app)
    resp = client.get("/health")
    assert resp.status_code == 200


@pytest.mark.smoke
def test_reporting_health():
    client = TestClient(reporting_app)
    resp = client.get("/health")
    assert resp.status_code == 200


@pytest.mark.smoke
def test_digital_twin_health():
    client = TestClient(twin_app)
    resp = client.get("/health")
    assert resp.status_code == 200
