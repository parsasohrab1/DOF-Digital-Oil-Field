"""
Refresh token store with Redis fallback to in-memory cache.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional

import redis

from .config import settings


class RefreshTokenStore:
    """Manage issued refresh tokens and revocations."""

    def __init__(self, redis_url: Optional[str] = None, prefix: str = "refresh-token"):
        self.redis_url = redis_url or settings.REDIS_URL
        self.prefix = prefix
        self.memory_store: Dict[str, datetime] = {}
        self.memory_revoked: Dict[str, datetime] = {}

        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        except Exception:
            self.redis_client = None

    def _ttl(self, expires_at: datetime) -> int:
        return max(1, int((expires_at - datetime.utcnow()).total_seconds()))

    def _key(self, jti: str) -> str:
        return f"{self.prefix}:{jti}"

    def register_token(self, jti: str, expires_at: datetime) -> None:
        if not jti:
            return
        if self.redis_client:
            self.redis_client.setex(self._key(jti), self._ttl(expires_at), "active")
        else:
            self.memory_store[jti] = expires_at
            # remove from revoked list if present
            self.memory_revoked.pop(jti, None)

    def revoke_token(self, jti: str, expires_at: datetime) -> None:
        if not jti:
            return
        if self.redis_client:
            self.redis_client.setex(self._key(jti), self._ttl(expires_at), "revoked")
        else:
            self.memory_store.pop(jti, None)
            self.memory_revoked[jti] = expires_at

    def is_token_active(self, jti: Optional[str]) -> bool:
        if not jti:
            return False

        if self.redis_client:
            status = self.redis_client.get(self._key(jti))
            return status == "active"

        # Clean expired tokens
        now = datetime.utcnow()
        for store in (self.memory_store, self.memory_revoked):
            expired = [key for key, exp in store.items() if exp < now]
            for key in expired:
                store.pop(key, None)

        if jti in self.memory_revoked:
            return False

        expires_at = self.memory_store.get(jti)
        return expires_at is not None and expires_at > now

    def reset(self):
        """Testing helper to clear memory store."""
        if self.redis_client:
            return
        self.memory_store.clear()
        self.memory_revoked.clear()


refresh_token_store = RefreshTokenStore()
