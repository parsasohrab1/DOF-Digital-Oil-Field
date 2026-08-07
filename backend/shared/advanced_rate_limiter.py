"""
Advanced Rate Limiting with Multiple Strategies
Rate limiting سخت‌گیرانه‌تر با استراتژی‌های مختلف
"""
import time
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class AdvancedRateLimiter:
    """
    Advanced rate limiter with multiple strategies:
    - Per-IP limiting
    - Per-user limiting
    - Per-endpoint limiting
    - Sliding window
    - Token bucket
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self.redis_client = None

        if REDIS_AVAILABLE and redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                logger.info("Rate limiter using Redis")
            except Exception as e:
                logger.warning(f"Redis unavailable, using in-memory: {e}")
                self.redis_client = None

        # In-memory fallback
        self.memory_store: Dict[str, list] = defaultdict(list)
        self.token_buckets: Dict[
            str, Tuple[float, float]
        ] = {}  # key -> (tokens, last_update)
        self.lock = asyncio.Lock()

    def _get_key(self, identifier: str, endpoint: Optional[str] = None) -> str:
        """Generate rate limit key"""
        if endpoint:
            return f"rate_limit:{identifier}:{endpoint}"
        return f"rate_limit:{identifier}"

    async def check_sliding_window(
        self, key: str, max_requests: int, window_seconds: int
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Sliding window rate limiting
        """
        current_time = time.time()
        window_start = current_time - window_seconds

        if self.redis_client:
            try:
                # Use Redis sorted set for sliding window
                pipe = self.redis_client.pipeline()
                window_key = f"sliding:{key}"

                # Remove old entries
                pipe.zremrangebyscore(window_key, 0, window_start)

                # Count current requests
                pipe.zcard(window_key)

                # Add current request
                pipe.zadd(window_key, {str(current_time): current_time})

                # Set expiry
                pipe.expire(window_key, window_seconds)

                results = pipe.execute()
                count = results[1]

                allowed = count < max_requests

                return allowed, {
                    "limit": max_requests,
                    "remaining": max(0, max_requests - count - 1),
                    "reset": int(current_time + window_seconds),
                    "window_seconds": window_seconds,
                }
            except Exception as e:
                logger.warning(f"Redis error in sliding window: {e}")

        # Memory-based sliding window
        async with self.lock:
            if key not in self.memory_store:
                self.memory_store[key] = []

            # Remove old timestamps
            self.memory_store[key] = [
                ts for ts in self.memory_store[key] if ts > window_start
            ]

            count = len(self.memory_store[key])
            allowed = count < max_requests

            if allowed:
                self.memory_store[key].append(current_time)

            return allowed, {
                "limit": max_requests,
                "remaining": max(0, max_requests - count - 1),
                "reset": int(current_time + window_seconds),
                "window_seconds": window_seconds,
            }

    async def check_token_bucket(
        self,
        key: str,
        max_tokens: int,
        refill_rate: float,  # tokens per second
        burst_size: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Token bucket rate limiting
        """
        current_time = time.time()
        burst = burst_size or max_tokens

        if self.redis_client:
            try:
                # Use Redis for token bucket
                bucket_key = f"bucket:{key}"

                pipe = self.redis_client.pipeline()
                pipe.hgetall(bucket_key)
                results = pipe.execute()

                bucket_data = results[0]

                if bucket_data:
                    tokens = float(bucket_data.get("tokens", max_tokens))
                    last_update = float(bucket_data.get("last_update", current_time))
                else:
                    tokens = max_tokens
                    last_update = current_time

                # Refill tokens
                elapsed = current_time - last_update
                tokens = min(burst, tokens + elapsed * refill_rate)

                allowed = tokens >= 1.0

                if allowed:
                    tokens -= 1.0

                # Update bucket
                pipe = self.redis_client.pipeline()
                pipe.hset(
                    bucket_key,
                    mapping={"tokens": str(tokens), "last_update": str(current_time)},
                )
                pipe.expire(bucket_key, int(2 * max_tokens / refill_rate))
                pipe.execute()

                return allowed, {
                    "limit": max_tokens,
                    "remaining": int(tokens),
                    "refill_rate": refill_rate,
                    "burst": burst,
                }
            except Exception as e:
                logger.warning(f"Redis error in token bucket: {e}")

        # Memory-based token bucket
        async with self.lock:
            if key not in self.token_buckets:
                self.token_buckets[key] = (max_tokens, current_time)

            tokens, last_update = self.token_buckets[key]

            # Refill tokens
            elapsed = current_time - last_update
            tokens = min(burst, tokens + elapsed * refill_rate)

            allowed = tokens >= 1.0

            if allowed:
                tokens -= 1.0

            self.token_buckets[key] = (tokens, current_time)

            return allowed, {
                "limit": max_tokens,
                "remaining": int(tokens),
                "refill_rate": refill_rate,
                "burst": burst,
            }

    async def check_rate_limit(
        self,
        identifier: str,
        endpoint: Optional[str] = None,
        max_requests: int = 100,
        window_seconds: int = 60,
        strategy: str = "sliding_window",
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check rate limit with specified strategy

        Args:
            identifier: Client identifier (IP, user ID, etc.)
            endpoint: Optional endpoint path
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
            strategy: "sliding_window" or "token_bucket"

        Returns:
            (allowed, info_dict)
        """
        key = self._get_key(identifier, endpoint)

        if strategy == "token_bucket":
            # Token bucket: refill_rate = max_requests / window_seconds
            refill_rate = max_requests / window_seconds
            return await self.check_token_bucket(key, max_requests, refill_rate)
        else:
            # Default: sliding window
            return await self.check_sliding_window(key, max_requests, window_seconds)


class RateLimitConfig:
    """Rate limit configuration per endpoint"""

    # Default limits
    DEFAULT_LIMITS = {
        "default": {"max_requests": 100, "window_seconds": 60},
        "auth": {"max_requests": 10, "window_seconds": 60},  # Stricter for auth
        "command-control": {"max_requests": 50, "window_seconds": 60},
        "ml-inference": {"max_requests": 200, "window_seconds": 60},
        "data-ingestion": {
            "max_requests": 1000,
            "window_seconds": 60,
        },  # Higher for ingestion
    }

    # Per-user limits (higher for admins)
    USER_LIMITS = {
        "system_admin": {"max_requests": 500, "window_seconds": 60},
        "data_engineer": {"max_requests": 300, "window_seconds": 60},
        "field_operator": {"max_requests": 200, "window_seconds": 60},
        "viewer": {"max_requests": 100, "window_seconds": 60},
    }

    @classmethod
    def get_limit(
        cls, service_name: str, user_role: Optional[str] = None
    ) -> Dict[str, int]:
        """Get rate limit for service and user role"""
        # Check per-user limits first
        if user_role and user_role in cls.USER_LIMITS:
            base_limit = cls.USER_LIMITS[user_role]
        else:
            base_limit = cls.DEFAULT_LIMITS.get(
                service_name, cls.DEFAULT_LIMITS["default"]
            )

        return base_limit


# Global rate limiter instance
_global_rate_limiter: Optional[AdvancedRateLimiter] = None


def get_rate_limiter(redis_url: Optional[str] = None) -> AdvancedRateLimiter:
    """Get or create global rate limiter"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = AdvancedRateLimiter(redis_url=redis_url)
    return _global_rate_limiter
