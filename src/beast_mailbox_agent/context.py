"""Conversation context storage primitives."""

from __future__ import annotations

import json
from typing import Dict, Optional, Protocol

from redis.asyncio import Redis as AsyncRedis, from_url as redis_from_url


class ContextStore(Protocol):
    """Interface for storing conversation context."""

    async def get(self, key: str) -> Optional[Dict]:
        """Retrieve stored context for the given key."""

    async def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> None:
        """Store context with optional time-to-live."""

    async def clear(self, key: str) -> None:
        """Remove stored context."""


class NullContextStore(ContextStore):
    """No-op context store used when persistence is disabled."""

    async def get(self, key: str) -> Optional[Dict]:
        return None

    async def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> None:
        return None

    async def clear(self, key: str) -> None:
        return None


class InMemoryContextStore(ContextStore):
    """Simple in-memory store primarily for testing or local runs."""

    def __init__(self) -> None:
        self._storage: Dict[str, Dict] = {}

    async def get(self, key: str) -> Optional[Dict]:
        return self._storage.get(key)

    async def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> None:
        self._storage[key] = value

    async def clear(self, key: str) -> None:
        self._storage.pop(key, None)


class RedisContextStore(ContextStore):
    """Redis-backed context store for persistent conversation history."""

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        prefix: str,
        redis_client: Optional[AsyncRedis] = None,
    ) -> None:
        if redis_client is None and url is None:
            raise ValueError("RedisContextStore requires either a redis_client or url")
        self._url = url
        self._client: Optional[AsyncRedis] = redis_client
        self._prefix = prefix.rstrip(":")

    async def _client_or_create(self) -> AsyncRedis:
        if self._client is None:
            assert self._url is not None
            self._client = redis_from_url(self._url, decode_responses=False)
        return self._client

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str) -> Optional[Dict]:
        client = await self._client_or_create()
        value = await client.get(self._key(key))
        if not value:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        return json.loads(value)

    async def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> None:
        client = await self._client_or_create()
        dump = json.dumps(value)
        if ttl and ttl > 0:
            await client.set(self._key(key), dump, ex=ttl)
        else:
            await client.set(self._key(key), dump)

    async def clear(self, key: str) -> None:
        client = await self._client_or_create()
        await client.delete(self._key(key))
