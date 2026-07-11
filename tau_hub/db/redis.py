"""Redis backend (requires: ``pip install tau-hub[redis]``)."""

from __future__ import annotations

try:
    import redis.asyncio as aioredis
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "redis-py is required for RedisStore.\n"
        "Install it with: pip install tau-hub[redis]"
    ) from exc

import json

from tau_hub.db.base import BaseAgentStore


class RedisStore(BaseAgentStore):
    """Redis backend — documents stored as JSON strings under
    ``prefix:collection:name`` keys.

    Uses ``redis.asyncio``, so every method is truly async — no thread-pool
    overhead. A Redis Set per collection (``prefix:collection:__index__``)
    tracks document names to make :meth:`batch_get` efficient.

    Parameters
    ----------
    url:
        Redis connection URL.
    prefix:
        Key prefix that namespaces all tau_hub data.
    """

    def __init__(
        self, url: str = "redis://localhost:6379", prefix: str = "tau"
    ) -> None:
        self._r = aioredis.from_url(url, decode_responses=True)
        self._prefix = prefix

    def _key(self, collection: str, name: str) -> str:
        """Return the Redis key that stores one document."""
        return f"{self._prefix}:{collection}:{name}"

    def _index_key(self, collection: str) -> str:
        """Return the key of the Redis Set that tracks all names in a collection."""
        return f"{self._prefix}:{collection}:__index__"

    async def get(self, collection: str, name: str) -> dict | None:
        """Return the document stored under ``(collection, name)`` or ``None``."""
        raw = await self._r.get(self._key(collection, name))
        return json.loads(raw) if raw is not None else None

    async def put(self, collection: str, name: str, data: dict, **extra) -> None:
        """Insert or replace the document stored under ``(collection, name)``."""
        doc = {"name": name, **data, **extra}
        async with self._r.pipeline() as pipe:
            pipe.set(self._key(collection, name), json.dumps(doc))
            pipe.sadd(self._index_key(collection), name)
            await pipe.execute()

    async def delete(self, collection: str, name: str) -> None:
        """Delete the document stored under ``(collection, name)``."""
        async with self._r.pipeline() as pipe:
            pipe.delete(self._key(collection, name))
            pipe.srem(self._index_key(collection), name)
            await pipe.execute()

    async def batch_get(self, collection: str) -> list[dict]:
        """Return every document in *collection*."""
        names = await self._r.smembers(self._index_key(collection))
        if not names:
            return []
        keys = [self._key(collection, n) for n in names]
        raws = await self._r.mget(keys)
        return [json.loads(r) for r in raws if r is not None]

    async def close(self) -> None:
        """Close the underlying Redis connection pool."""
        await self._r.aclose()
