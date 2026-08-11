"""
Tests for tag catalog service
"""

import importlib.util
import pytest
import sys
import os
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MODULE_PATH = Path(__file__).resolve().parents[1] / "tag-catalog-service" / "main.py"
spec = importlib.util.spec_from_file_location("tag_catalog_service_main", MODULE_PATH)
tag_catalog_service_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tag_catalog_service_main)

app = tag_catalog_service_main.app
require_tag_read = tag_catalog_service_main.require_tag_read
require_tag_write = tag_catalog_service_main.require_tag_write
require_tag_admin = tag_catalog_service_main.require_tag_admin

from shared.database import get_db
from shared.models import Tag
from shared.auth import require_authentication, require_roles


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
    app.dependency_overrides[require_tag_read] = lambda: {
        "sub": "testuser",
        "role": "system_admin",
    }
    app.dependency_overrides[require_tag_write] = lambda: {
        "sub": "testuser",
        "role": "system_admin",
    }
    app.dependency_overrides[require_tag_admin] = lambda: {
        "sub": "testuser",
        "role": "system_admin",
    }
    return TestClient(app)


@pytest.fixture
def test_tag(test_db):
    """Create test tag"""
    tag = Tag(
        tag_id="TEST-WELL-001-pressure",
        well_name="TEST-WELL-001",
        equipment_type="pump",
        sensor_type="pressure",
        unit="psi",
        valid_range_min=0.0,
        valid_range_max=500.0,
        critical_threshold_min=10.0,
        critical_threshold_max=450.0,
        status="active",
    )
    test_db.add(tag)
    test_db.commit()
    test_db.refresh(tag)
    return tag


def test_create_tag(client):
    """Test creating a tag"""
    response = client.post(
        "/tags",
        json={
            "tag_id": "WELL-A-001-temperature",
            "well_name": "WELL-A-001",
            "equipment_type": "heater",
            "sensor_type": "temperature",
            "unit": "C",
            "valid_range_min": -40.0,
            "valid_range_max": 150.0,
            "status": "active",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "tag_id" in data


def test_get_tag(client, test_tag):
    """Test getting a tag"""
    response = client.get(f"/tags/{test_tag.tag_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["tag_id"] == test_tag.tag_id
    assert data["well_name"] == test_tag.well_name


def test_list_tags(client, test_tag):
    """Test listing tags"""
    response = client.get("/tags")

    assert response.status_code == 200
    data = response.json()
    assert "tags" in data
    assert "count" in data
    assert data["count"] > 0


def test_list_tags_filter_by_well(client, test_tag):
    """Test filtering tags by well name"""
    response = client.get(f"/tags?well_name={test_tag.well_name}")

    assert response.status_code == 200
    data = response.json()
    assert all(tag["well_name"] == test_tag.well_name for tag in data["tags"])


def test_update_tag(client, test_tag):
    """Test updating a tag"""
    response = client.put(
        f"/tags/{test_tag.tag_id}",
        json={
            "tag_id": test_tag.tag_id,
            "well_name": test_tag.well_name,
            "equipment_type": test_tag.equipment_type,
            "sensor_type": test_tag.sensor_type,
            "unit": test_tag.unit,
            "valid_range_min": 0.0,
            "valid_range_max": 600.0,  # Updated
            "status": "active",
        },
    )

    assert response.status_code == 200


def test_delete_tag(client, test_tag):
    """Test deleting a tag (soft delete)"""
    response = client.delete(f"/tags/{test_tag.tag_id}")

    assert response.status_code == 200

    # Verify tag is soft deleted
    response = client.get(f"/tags/{test_tag.tag_id}")
    data = response.json()
    assert data["status"] == "deleted"
