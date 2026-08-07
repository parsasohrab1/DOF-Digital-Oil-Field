"""Unit tests for shared.security_alerts (memory + fake Redis)."""
from datetime import datetime, timedelta

import pytest

from shared.security_alerts import SecurityAlerts


class FakeRedis:
    def __init__(self):
        self.store = {}

    def incr(self, key: str):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key: str, _: int):
        self.store[f"{key}:ttl"] = True

    def delete(self, key: str):
        self.store.pop(key, None)


def _memory_alerts(threshold: int = 3) -> SecurityAlerts:
    alerts = SecurityAlerts(redis_url="redis://invalid-host:6379/0", threshold=threshold)
    alerts.redis_client = None
    alerts.memory_store = {}
    return alerts


@pytest.mark.unit
def test_memory_records_and_resets():
    alerts = _memory_alerts(threshold=5)
    alerts.record_login_failure("user1")
    alerts.record_login_failure("user1")
    assert alerts.memory_store["user1"][0] == 2
    alerts.reset_user("user1")
    assert "user1" not in alerts.memory_store


@pytest.mark.unit
def test_threshold_alert_path():
    alerts = _memory_alerts(threshold=2)
    alerts.record_login_failure("user2")
    alerts.record_login_failure("user2")
    assert alerts.memory_store["user2"][0] >= 2


@pytest.mark.unit
def test_expired_memory_counter_resets():
    alerts = _memory_alerts(threshold=10)
    alerts.memory_store["stale"] = (5, datetime.utcnow() - timedelta(hours=2))
    alerts.record_login_failure("stale")
    assert alerts.memory_store["stale"][0] == 1


@pytest.mark.unit
def test_redis_mode_and_empty_username():
    alerts = _memory_alerts(threshold=2)
    alerts.redis_client = FakeRedis()
    alerts.record_login_failure("")
    assert alerts.redis_client.store == {}
    alerts.record_login_failure("redis-user")
    alerts.record_login_failure("redis-user")
    assert alerts.redis_client.store["login-fail:redis-user"] == 2
    alerts.reset_user("redis-user")
    assert "login-fail:redis-user" not in alerts.redis_client.store
