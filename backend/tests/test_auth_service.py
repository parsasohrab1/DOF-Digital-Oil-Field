"""
Tests for authentication service
"""

import importlib.util
import sys
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Loaded via importlib with a unique module name: several test files in this
# suite use a service's own directory + `from main import ...`, which all
# collide on the same `sys.modules['main']` entry when pytest collects them
# together (whichever service's test file collects first "wins" and every
# other file gets that service's main.py instead of its own).
MODULE_PATH = Path(__file__).resolve().parents[1] / "auth-service" / "main.py"
spec = importlib.util.spec_from_file_location("auth_service_main", MODULE_PATH)
auth_service_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(auth_service_main)

app = auth_service_main.app
rate_limit_dependency = auth_service_main.rate_limit_dependency

from shared.database import get_db
from shared.security import get_password_hash, verify_password
from shared.token_store import refresh_token_store


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
    app.dependency_overrides[rate_limit_dependency] = lambda: True
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_token_store():
    refresh_token_store.reset()


def test_password_hashing():
    """Test password hashing and verification"""
    password = "test_password_123"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_login_success(client, test_user):
    """Test successful login"""
    response = client.post(
        "/token", data={"username": "testuser", "password": "testpass123"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    """Test login with invalid credentials"""
    response = client.post(
        "/token", data={"username": "wronguser", "password": "wrongpass"}
    )

    assert response.status_code == 401


def test_get_current_user(client, auth_headers):
    """Test getting current user info"""
    response = client.get("/users/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["role"] == "field_operator"


def test_get_current_user_no_token(client):
    """Test getting current user without token"""
    response = client.get("/users/me")

    assert response.status_code == 401


def test_create_user_as_admin(client, test_db):
    """Test creating user as admin"""
    from shared.models import User

    # Create admin user
    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=get_password_hash("admin123"),
        role="system_admin",
        disabled=False,
    )
    test_db.add(admin)
    test_db.commit()

    # Get admin token
    from shared.security import create_access_token

    admin_token = create_access_token(data={"sub": "admin", "role": "system_admin"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create new user
    response = client.post(
        "/users",
        headers=admin_headers,
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newpass123",
            "role": "viewer",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
