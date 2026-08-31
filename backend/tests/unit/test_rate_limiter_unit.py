"""
Tests for shared.rate_limiter (the simple Redis-or-memory limiter used by
rate_limit_dependency) and shared.advanced_rate_limiter (sliding window /
token bucket strategies used for per-endpoint, per-role limits).
"""

import asyncio

import pytest

from shared.rate_limiter import RateLimiter
from shared.advanced_rate_limiter import AdvancedRateLimiter, RateLimitConfig


class _BrokenRedis:
    """Constructs fine but every call raises -- simulates Redis going away
    *after* the client object was created, since redis.from_url() itself is
    lazy and doesn't touch the network."""

    def pipeline(self):
        raise ConnectionError("redis unreachable")


class TestRateLimiter:
    def test_memory_backend_allows_requests_within_limit(self):
        limiter = RateLimiter(redis_url="redis://invalid-host:6379/0")
        limiter.redis_client = None

        async def run():
            for _ in range(5):
                assert await limiter.check_rate_limit(
                    "client-a", max_requests=5, window_seconds=60
                )

        asyncio.run(run())

    def test_memory_backend_blocks_once_limit_exceeded(self):
        limiter = RateLimiter(redis_url="redis://invalid-host:6379/0")
        limiter.redis_client = None

        async def run():
            for _ in range(3):
                await limiter.check_rate_limit(
                    "client-b", max_requests=3, window_seconds=60
                )
            return await limiter.check_rate_limit(
                "client-b", max_requests=3, window_seconds=60
            )

        assert asyncio.run(run()) is False

    def test_different_keys_are_tracked_independently(self):
        limiter = RateLimiter(redis_url="redis://invalid-host:6379/0")
        limiter.redis_client = None

        async def run():
            for _ in range(3):
                await limiter.check_rate_limit(
                    "client-c", max_requests=3, window_seconds=60
                )
            # a different key must not be affected by client-c's usage
            return await limiter.check_rate_limit(
                "client-d", max_requests=3, window_seconds=60
            )

        assert asyncio.run(run()) is True

    def test_falls_back_to_memory_without_crashing_when_redis_client_errors_at_call_time(
        self,
    ):
        """Regression test: memory_store must exist even when redis.from_url()
        succeeded at construction time (the common case) and Redis only
        becomes unreachable later, once check_rate_limit() actually runs."""
        limiter = RateLimiter(redis_url="redis://invalid-host:6379/0")
        limiter.redis_client = _BrokenRedis()

        async def run():
            return await limiter.check_rate_limit(
                "client-e", max_requests=5, window_seconds=60
            )

        assert asyncio.run(run()) is True


class TestAdvancedRateLimiterSlidingWindow:
    def test_memory_sliding_window_allows_up_to_limit(self):
        limiter = AdvancedRateLimiter(redis_url=None)

        async def run():
            results = []
            for _ in range(3):
                allowed, _ = await limiter.check_sliding_window(
                    "k1", max_requests=3, window_seconds=60
                )
                results.append(allowed)
            return results

        assert asyncio.run(run()) == [True, True, True]

    def test_memory_sliding_window_blocks_after_limit(self):
        limiter = AdvancedRateLimiter(redis_url=None)

        async def run():
            for _ in range(3):
                await limiter.check_sliding_window(
                    "k2", max_requests=3, window_seconds=60
                )
            return await limiter.check_sliding_window(
                "k2", max_requests=3, window_seconds=60
            )

        allowed, info = asyncio.run(run())
        assert allowed is False
        assert info["remaining"] == 0

    def test_check_rate_limit_dispatches_to_sliding_window_by_default(self):
        limiter = AdvancedRateLimiter(redis_url=None)

        async def run():
            return await limiter.check_rate_limit(
                "user-1", endpoint="alerts", max_requests=2, window_seconds=60
            )

        allowed, info = asyncio.run(run())
        assert allowed is True
        assert info["limit"] == 2


class TestAdvancedRateLimiterTokenBucket:
    def test_token_bucket_allows_up_to_burst_then_blocks(self):
        limiter = AdvancedRateLimiter(redis_url=None)

        async def run():
            results = []
            for _ in range(5):
                allowed, _ = await limiter.check_token_bucket(
                    "bucket-1", max_tokens=5, refill_rate=0.0001, burst_size=5
                )
                results.append(allowed)
            sixth_allowed, _ = await limiter.check_token_bucket(
                "bucket-1", max_tokens=5, refill_rate=0.0001, burst_size=5
            )
            results.append(sixth_allowed)
            return results

        results = asyncio.run(run())
        assert results == [True, True, True, True, True, False]

    def test_check_rate_limit_dispatches_to_token_bucket_strategy(self):
        limiter = AdvancedRateLimiter(redis_url=None)

        async def run():
            return await limiter.check_rate_limit(
                "user-2", max_requests=1, window_seconds=60, strategy="token_bucket"
            )

        allowed, info = asyncio.run(run())
        assert allowed is True
        assert info["limit"] == 1


class TestRateLimitConfig:
    def test_unknown_service_falls_back_to_default_limit(self):
        limit = RateLimitConfig.get_limit("some-unlisted-service")
        assert limit == RateLimitConfig.DEFAULT_LIMITS["default"]

    def test_auth_service_has_a_stricter_limit_than_default(self):
        auth_limit = RateLimitConfig.get_limit("auth")
        default_limit = RateLimitConfig.DEFAULT_LIMITS["default"]
        assert auth_limit["max_requests"] < default_limit["max_requests"]

    def test_user_role_limit_takes_precedence_over_service_limit(self):
        limit = RateLimitConfig.get_limit("auth", user_role="system_admin")
        assert limit == RateLimitConfig.USER_LIMITS["system_admin"]

    def test_unknown_role_falls_back_to_service_limit(self):
        limit = RateLimitConfig.get_limit("ml-inference", user_role="not-a-real-role")
        assert limit == RateLimitConfig.DEFAULT_LIMITS["ml-inference"]
