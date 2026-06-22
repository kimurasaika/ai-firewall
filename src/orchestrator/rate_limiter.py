"""Per-user/session sliding-window rate limiter backed by Redis."""
from __future__ import annotations

import logging
import time

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_MINUTE = 60
_MAX_REQUESTS_PER_HOUR = 500


class RateLimiter:
    """Sliding-window rate limiter using Redis sorted sets."""

    def __init__(self, redis_client: object) -> None:
        self._redis = redis_client  # redis.asyncio.Redis instance

    async def check(self, user_id: str, request: Request) -> None:
        """Raise HTTP 429 if the user exceeds rate limits."""
        now = time.time()
        minute_key = f"ratelimit:minute:{user_id}"
        hour_key = f"ratelimit:hour:{user_id}"

        pipe = self._redis.pipeline()
        # Minute window
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zadd(minute_key, {str(now): now})
        pipe.zcard(minute_key)
        pipe.expire(minute_key, 120)
        # Hour window
        pipe.zremrangebyscore(hour_key, 0, now - 3600)
        pipe.zadd(hour_key, {str(now): now})
        pipe.zcard(hour_key)
        pipe.expire(hour_key, 7200)
        results = await pipe.execute()

        per_minute: int = results[2]
        per_hour: int = results[6]

        if per_minute > _MAX_REQUESTS_PER_MINUTE:
            logger.warning("Rate limit exceeded (minute): user=%s count=%d", user_id, per_minute)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again in 60 seconds.",
                headers={"Retry-After": "60"},
            )

        if per_hour > _MAX_REQUESTS_PER_HOUR:
            logger.warning("Rate limit exceeded (hour): user=%s count=%d", user_id, per_hour)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Hourly rate limit exceeded.",
                headers={"Retry-After": "3600"},
            )
