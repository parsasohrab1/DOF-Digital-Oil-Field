"""
Security alert helpers for tracking suspicious activity.
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple

import redis

from .config import settings
from .logging_config import setup_logging

logger = setup_logging("security-alerts")


class SecurityAlerts:
    def __init__(self, redis_url: str = settings.REDIS_URL, threshold: int = 5):
        self.threshold = threshold
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
        except Exception:
            self.redis_client = None
            self.memory_store: Dict[str, Tuple[int, datetime]] = {}

    def _key(self, username: str) -> str:
        return f"login-fail:{username}"

    def record_login_failure(self, username: str) -> None:
        if not username:
            return
        if self.redis_client:
            count = self.redis_client.incr(self._key(username))
            self.redis_client.expire(self._key(username), 3600)
        else:
            count, expires = self.memory_store.get(
                username, (0, datetime.utcnow() + timedelta(hours=1))
            )
            if expires < datetime.utcnow():
                count = 0
                expires = datetime.utcnow() + timedelta(hours=1)
            count += 1
            self.memory_store[username] = (count, expires)
        self._maybe_alert(
            username, count if self.redis_client else self.memory_store[username][0]
        )

    def reset_user(self, username: str):
        if self.redis_client:
            self.redis_client.delete(self._key(username))
        else:
            self.memory_store.pop(username, None)

    def _maybe_alert(self, username: str, count: int):
        if count >= self.threshold:
            logger.warning(
                "Multiple failed logins for user=%s count=%s", username, count
            )


security_alerts = SecurityAlerts()
