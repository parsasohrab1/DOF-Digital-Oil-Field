"""
Rate limiting middleware
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import time
from typing import Dict
import redis
from .config import settings


class RateLimiter:
    """Rate limiter using Redis"""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        except Exception:
            # Fallback to in-memory if Redis unavailable
            self.redis_client = None
            self.memory_store: Dict[str, list] = {}

    async def check_rate_limit(
        self, key: str, max_requests: int = 100, window_seconds: int = 60
    ) -> bool:
        """Check if request is within rate limit"""
        current_time = int(time.time())

        if self.redis_client:
            # Redis-based rate limiting
            try:
                pipe = self.redis_client.pipeline()
                window_key = f"rate_limit:{key}:{current_time // window_seconds}"

                pipe.incr(window_key)
                pipe.expire(window_key, window_seconds)

                result = pipe.execute()
                request_count = result[0]

                return request_count <= max_requests
            except Exception:
                # Fallback to memory
                pass

        # Memory-based rate limiting (fallback)
        if key not in self.memory_store:
            self.memory_store[key] = []

        # Remove old timestamps
        self.memory_store[key] = [
            ts for ts in self.memory_store[key] if current_time - ts < window_seconds
        ]

        # Check limit
        if len(self.memory_store[key]) >= max_requests:
            return False

        # Add current timestamp
        self.memory_store[key].append(current_time)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter()


async def rate_limit_dependency(request: Request):
    """FastAPI dependency for rate limiting"""
    # Get client identifier
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    key = f"{client_ip}:{user_agent}"

    # Check rate limit
    if not await rate_limiter.check_rate_limit(
        key, max_requests=100, window_seconds=60
    ):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"}
        )

    return True
