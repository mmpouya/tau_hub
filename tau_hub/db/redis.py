"""Redis backend (requires: pip install tau-hub[redis])."""
from __future__ import annotations

try:
    import redis.asyncio as aioredis
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "redis-py is required for RedisStore.\n"
        "Install it with: pip install tau-hub[redis]"
    ) from exc

import json
from tau_hub.db.base import AgentStore


class RedisStore(AgentStore):
    """Redis backend — documents stored as JSON strings under
    'prefix:collection:name' keys.

    Uses redis.asyncio so every method is truly async — no thread-pool
    overhead.
    """

    def __init__(self, url: str = "redis://localhost:6379", prefix: str = "tau") -> None:
        self._r = aioredis.from_url(url, decode_responses=True)
        self._prefix = prefix

    def _key(self, collection: str, name: str) -> str:
        return f"{self._prefix}:{collection}:{name}"

    def _index_key(self, collection: str) -> str:
        """A Redis Set that tracks all names in a collection."""
        return f"{self._prefix}:{collection}:__index__"

    async def get(self, collection: str, name: str) -> dict | None:
        raw = await self._r.get(self._key(collection, name))
        return json.loads(raw) if raw is not None else None

    async def put(self, collection: str, name: str, data: dict) -> None:
        doc = {"name": name, **data}
        async with self._r.pipeline() as pipe:
            pipe.set(self._key(collection, name), json.dumps(doc))
            pipe.sadd(self._index_key(collection), name)
            await pipe.execute()

    async def delete(self, collection: str, name: str) -> None:
        async with self._r.pipeline() as pipe:
            pipe.delete(self._key(collection, name))
            pipe.srem(self._index_key(collection), name)
            await pipe.execute()

    async def batch_get(self, collection: str) -> list[dict]:
        names = await self._r.smembers(self._index_key(collection))
        if not names:
            return []
        keys = [self._key(collection, n) for n in names]
        raws = await self._r.mget(keys)
        return [json.loads(r) for r in raws if r is not None]
