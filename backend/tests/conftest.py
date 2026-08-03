"""
PyTest configuration and fixtures
"""
import pytest
import sys
import os

# Every service's main.py calls shared.tracing.setup_tracing() at import time,
# which otherwise starts a real OTLP exporter thread per test module that
# retries against an unreachable collector (see shared/tracing.py). Must be
# set before any service module is imported below.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Add backend root to path for shared package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.database import Base
from shared.models import User
from shared.security import get_password_hash


@pytest.fixture(scope="function")
def test_engine():
    """Create a fresh in-memory test database engine per test.

    Function-scoped (not session-scoped) so tests that share fixed usernames
    like "testuser"/"admin" (test_user, admin_user) never collide on unique
    constraints from data left behind by an earlier test in the same session.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine):
    """Create test database session"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def test_user(test_db):
    """Create test user"""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpass123"),
        role="field_operator",
        disabled=False
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_user(test_db):
    """Create system admin user"""
    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass123"),
        role="system_admin",
        disabled=False
    )
    test_db.add(admin)
    test_db.commit()
    test_db.refresh(admin)
    return admin


@pytest.fixture
def auth_headers(test_user):
    """Generate auth headers for testing"""
    from shared.security import create_access_token
    token = create_access_token(data={"sub": test_user.username, "role": test_user.role})
    return {"Authorization": f"Bearer {token}"}

