"""Tests for context store implementations."""

import pytest

import fakeredis.aioredis

from beast_mailbox_agent.context import (
    InMemoryContextStore,
    NullContextStore,
    RedisContextStore,
)


@pytest.mark.asyncio
async def test_null_context_store_is_noop():
    store = NullContextStore()
    assert await store.get("missing") is None
    await store.set("missing", {"value": 1})
    assert await store.get("missing") is None
    await store.clear("missing")  # Should not raise


@pytest.mark.asyncio
async def test_inmemory_context_store_roundtrip():
    store = InMemoryContextStore()
    await store.set("thread", {"messages": [{"role": "user", "content": "hi"}]})
    value = await store.get("thread")
    assert value == {"messages": [{"role": "user", "content": "hi"}]}
    await store.clear("thread")
    assert await store.get("thread") is None


@pytest.mark.asyncio
async def test_redis_context_store_roundtrip():
    fake_client = fakeredis.aioredis.FakeRedis()
    store = RedisContextStore(prefix="ctx", redis_client=fake_client)

    await store.set("thread", {"state": 1}, ttl=60)
    value = await store.get("thread")
    assert value == {"state": 1}
    await store.clear("thread")
    assert await store.get("thread") is None
