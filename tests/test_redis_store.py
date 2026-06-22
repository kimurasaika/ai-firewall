"""Tests for RedisStore — uses fakeredis to avoid real Redis dependency."""
import pytest
import pytest_asyncio
from unittest.mock import patch

fakeredis = pytest.importorskip("fakeredis", reason="fakeredis not installed — pip install fakeredis")
pytest.importorskip("redis", reason="redis not installed — pip install redis")


@pytest_asyncio.fixture
async def store():
    import fakeredis.aioredis as fake_aio
    from src.mapping_store.redis_store import RedisStore

    with patch("src.mapping_store.redis_store.get_secret", return_value="test-password"), \
         patch("src.mapping_store.redis_store._USE_TLS", False):
        s = RedisStore.__new__(RedisStore)
        s._client = fake_aio.FakeRedis(decode_responses=True)
        return s


@pytest.mark.asyncio
async def test_store_and_get(store):
    await store.store_mapping("sess1", "<<P001>>", "สมชาย")
    mapping = await store.get_mapping("sess1")
    assert mapping["<<P001>>"] == "สมชาย"


@pytest.mark.asyncio
async def test_store_bulk(store):
    data = {"<<P001>>": "Alice", "<<EM001>>": "alice@test.com"}
    await store.store_bulk("sess2", data)
    mapping = await store.get_mapping("sess2")
    assert mapping == data


@pytest.mark.asyncio
async def test_clear_session(store):
    await store.store_mapping("sess3", "<<PH001>>", "0812345678")
    await store.clear_session("sess3")
    mapping = await store.get_mapping("sess3")
    assert mapping == {}


@pytest.mark.asyncio
async def test_get_nonexistent_session(store):
    mapping = await store.get_mapping("nonexistent-session-xyz")
    assert mapping == {}


@pytest.mark.asyncio
async def test_empty_bulk_noop(store):
    await store.store_bulk("sess4", {})
    mapping = await store.get_mapping("sess4")
    assert mapping == {}
