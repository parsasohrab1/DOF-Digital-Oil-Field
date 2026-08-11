"""
In-memory TTL response cache for high-read API paths.
"""

import hashlib
import json
import time
from threading import RLock
from typing import Any, Dict, Optional, Tuple


class TTLResponseCache:
    """Thread-safe TTL cache for serialized API responses."""

    def __init__(self, default_ttl_seconds: int = 10, max_entries: int = 2048):
        self.default_ttl_seconds = default_ttl_seconds
        self.max_entries = max_entries
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def build_key(method: str, path: str, query: str = "", user: str = "") -> str:
        raw = f"{method}:{path}:{query}:{user}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = time.time() + max(1, ttl)
        with self._lock:
            if len(self._store) >= self.max_entries:
                oldest_key = min(self._store.items(), key=lambda item: item[1][0])[0]
                del self._store[oldest_key]
            self._store[key] = (expires_at, value)

    def invalidate_prefix(self, prefix: str) -> int:
        removed = 0
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for key in keys:
                del self._store[key]
                removed += 1
        return removed

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total) if total else 0.0
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 4),
                "default_ttl_seconds": self.default_ttl_seconds,
                "max_entries": self.max_entries,
            }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0


def cacheable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)
