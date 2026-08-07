"""Unit tests for shared.response_cache."""
import time

import pytest

from shared.response_cache import TTLResponseCache


@pytest.mark.unit
def test_cache_set_and_get():
    cache = TTLResponseCache(default_ttl_seconds=5, max_entries=10)
    cache.set("k1", {"a": 1})
    assert cache.get("k1") == {"a": 1}


@pytest.mark.unit
def test_cache_expires():
    cache = TTLResponseCache(default_ttl_seconds=1, max_entries=10)
    cache.set("k1", "v1", ttl_seconds=1)
    time.sleep(1.1)
    assert cache.get("k1") is None


@pytest.mark.unit
def test_cache_stats_hit_rate():
    cache = TTLResponseCache(default_ttl_seconds=10, max_entries=10)
    cache.set("k1", "v1")
    cache.get("k1")
    cache.get("missing")
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5


@pytest.mark.unit
def test_cache_build_key_is_stable():
    k1 = TTLResponseCache.build_key("GET", "/api/x", "a=1", "user1")
    k2 = TTLResponseCache.build_key("GET", "/api/x", "a=1", "user1")
    assert k1 == k2


@pytest.mark.unit
def test_cache_evicts_oldest_when_full():
    cache = TTLResponseCache(default_ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    time.sleep(0.01)
    cache.set("b", 2)
    time.sleep(0.01)
    cache.set("c", 3)  # should evict oldest
    assert cache.stats()["entries"] == 2
    assert cache.get("c") == 3


@pytest.mark.unit
def test_cache_invalidate_prefix_and_clear():
    cache = TTLResponseCache(default_ttl_seconds=60, max_entries=10)
    # SHA keys won't share prefix; use private store for prefix test via set then invalidate_prefix on known keys
    with cache._lock:
        cache._store["alerts:1"] = (time.time() + 60, {"x": 1})
        cache._store["alerts:2"] = (time.time() + 60, {"x": 2})
        cache._store["other:1"] = (time.time() + 60, {"x": 3})
    removed = cache.invalidate_prefix("alerts:")
    assert removed == 2
    assert cache.stats()["entries"] == 1
    cache.clear()
    assert cache.stats()["entries"] == 0
    assert cache.stats()["hits"] == 0


@pytest.mark.unit
def test_cacheable_json():
    from shared.response_cache import cacheable_json

    assert '"a": 1' in cacheable_json({"a": 1, "b": 2}) or '"a":1' in cacheable_json(
        {"a": 1, "b": 2}
    ).replace(" ", "")
