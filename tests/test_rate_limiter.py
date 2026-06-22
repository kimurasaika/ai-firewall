"""Tests for RateLimiter sliding-window logic."""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch

pytest.importorskip("fastapi", reason="fastapi not installed — pip install fastapi")
pytest.importorskip("fakeredis", reason="fakeredis not installed — pip install fakeredis")

from fastapi import HTTPException
import fakeredis.aioredis as fake_aio
from src.orchestrator.rate_limiter import RateLimiter


@pytest_asyncio.fixture
async def limiter():
    redis = fake_aio.FakeRedis(decode_responses=True)
    return RateLimiter(redis)


@pytest.mark.asyncio
async def test_allows_under_limit(limiter):
    request = MagicMock()
    for _ in range(5):
        await limiter.check("user_A", request)


@pytest.mark.asyncio
async def test_blocks_over_minute_limit(limiter):
    request = MagicMock()
    with patch("src.orchestrator.rate_limiter._MAX_REQUESTS_PER_MINUTE", 3):
        for _ in range(3):
            await limiter.check("user_B", request)
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("user_B", request)
        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_different_users_independent(limiter):
    request = MagicMock()
    with patch("src.orchestrator.rate_limiter._MAX_REQUESTS_PER_MINUTE", 2):
        await limiter.check("user_C", request)
        await limiter.check("user_C", request)
        await limiter.check("user_D", request)   # user_D unaffected by user_C's count
