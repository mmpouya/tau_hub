from __future__ import annotations

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pymongo is required for MongoStore.\n"
        "Install it with: pip install tau-hub[mongo]"
    ) from exc

import asyncio
from typing import Any

from tau_hub.db.base import BaseAgentStore


class MongoStore(BaseAgentStore):
    """MongoDB backend using pymongo (synchronous driver, thread-pool offload).

    For async-native MongoDB, swap pymongo for motor and remove the
    ``run_in_executor`` wrapper.

    Parameters
    ----------
    uri:
        MongoDB connection string.
    db:
        Database name to use.
    """

    def __init__(
        self, uri: str = "mongodb://localhost:27017", db: str = "tau_hub"
    ) -> None:
        self._client = MongoClient(uri)
        self._db = self._client[db]

    def _col(self, collection: str) -> Collection:
        return self._db[collection]

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    async def get(self, collection: str, name: str) -> dict | None:
        def _get():
            return self._col(collection).find_one({"name": name}, {"_id": 0})

        return await self._run(_get)

    async def put(self, collection: str, name: str, data: dict, **extra) -> None:
        def _put():
            doc = {"name": name, **data, **extra}
            self._col(collection).replace_one({"name": name}, doc, upsert=True)

        await self._run(_put)

    async def delete(self, collection: str, name: str) -> None:
        def _delete():
            self._col(collection).delete_one({"name": name})

        await self._run(_delete)

    async def batch_get(self, collection: str) -> list[dict]:
        def _batch():
            return list(self._col(collection).find({}, {"_id": 0}))

        return await self._run(_batch)

    async def append_to_list(
        self, collection: str, name: str, field: str, item: Any
    ) -> None:
        """Atomically append *item* to ``doc[field]`` using MongoDB ``$push``.

        Safe for concurrent writers — no read-modify-write race.
        """

        def _append():
            self._col(collection).update_one(
                {"name": name},
                {"$push": {field: item}, "$setOnInsert": {"name": name}},
                upsert=True,
            )

        await self._run(_append)

    async def close(self) -> None:
        """Close the underlying MongoDB client."""
        await self._run(self._client.close)
