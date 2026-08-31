"""
PyTest configuration and fixtures
"""

import os
import pytest
import sys

# Every service's main.py calls shared.tracing.setup_tracing() at import time,
# which otherwise starts a real OTLP exporter thread per test module that
# retries against an unreachable collector (see shared/tracing.py). Must be
# set before any service module is imported below.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
# Belt-and-suspenders in case anything still builds a real exporter: fall
# back to console output instead of a network collector.
os.environ.setdefault("OTEL_TRACING_CONSOLE", "true")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Add backend root to path for shared package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import Base
from shared.models import User
from shared.security import get_password_hash

TEST_DATABASE_URL = "sqlite:///./test.db"


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine):
    """
    Create a test database session that is fully rolled back after each test.

    Application/test code may call session.commit() freely (it needs to, to
    match production behavior) - those commits only release a SAVEPOINT here,
    because the session is bound to a connection-level transaction that is
    itself rolled back at teardown. Without this, data inserted by one test
    (e.g. the fixed-username `test_user`/`admin_user` fixtures) collides with
    the next test via a UNIQUE constraint violation, since `test_engine` is
    session-scoped and the sqlite file persists across tests.
    """
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=connection
    )
    db = TestingSessionLocal()

    nested = connection.begin_nested()

    @event.listens_for(db, "after_transaction_end")
    def _restart_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield db
    finally:
        db.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture(scope="function")
def test_user(test_db):
    """Create test user"""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpass123"),
        role="field_operator",
        disabled=False,
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
        disabled=False,
    )
    test_db.add(admin)
    test_db.commit()
    test_db.refresh(admin)
    return admin


@pytest.fixture
def auth_headers(test_user):
    """Generate auth headers for testing"""
    from shared.security import create_access_token

    token = create_access_token(
        data={"sub": test_user.username, "role": test_user.role}
    )
    return {"Authorization": f"Bearer {token}"}
