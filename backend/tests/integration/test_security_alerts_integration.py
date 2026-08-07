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


def _build_memory_alerts(threshold: int = 3) -> SecurityAlerts:
    alerts = SecurityAlerts(
        redis_url="redis://invalid-host:6379/0", threshold=threshold
    )
    alerts.redis_client = None
    alerts.memory_store = {}
    return alerts


def test_memory_mode_records_and_resets_failures():
    alerts = _build_memory_alerts(threshold=5)

    alerts.record_login_failure("user1")
    alerts.record_login_failure("user1")
    count, _ = alerts.memory_store["user1"]
    assert count == 2

    alerts.reset_user("user1")
    assert "user1" not in alerts.memory_store


def test_threshold_path_is_reached_without_crash():
    alerts = _build_memory_alerts(threshold=2)

    alerts.record_login_failure("user2")
    alerts.record_login_failure("user2")

    count, _ = alerts.memory_store["user2"]
    assert count >= 2


def test_multiple_users_are_tracked_independently():
    alerts = _build_memory_alerts(threshold=10)

    alerts.record_login_failure("alice")
    alerts.record_login_failure("bob")
    alerts.record_login_failure("alice")

    assert alerts.memory_store["alice"][0] == 2
    assert alerts.memory_store["bob"][0] == 1


def test_redis_mode_and_empty_username_path():
    alerts = _build_memory_alerts(threshold=2)
    alerts.redis_client = FakeRedis()

    # empty username should be ignored
    alerts.record_login_failure("")
    assert alerts.redis_client.store == {}

    alerts.record_login_failure("redis-user")
    alerts.record_login_failure("redis-user")

    assert alerts.redis_client.store["login-fail:redis-user"] == 2
    alerts.reset_user("redis-user")
    assert "login-fail:redis-user" not in alerts.redis_client.store
