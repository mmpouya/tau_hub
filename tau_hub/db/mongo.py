"""MongoDB backend (requires: pip install tau-hub[mongo])."""

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

from tau_hub.db.base import BaseAgentStore


class MongoStore(BaseAgentStore):
    """MongoDB backend using pymongo (synchronous driver, thread-pool offload).

    For async-native MongoDB, swap pymongo for motor and remove the
    run_in_executor wrapper.
    """

    def __init__(
        self, uri: str = "mongodb://localhost:27017", db: str = "tau_hub"
    ) -> None:
        self._client = MongoClient(uri)
        self._db = self._client[db]

    def _col(self, collection: str) -> Collection:
        return self._db[collection]

    async def init_db(self) -> None:
        """Initialize the database.
        Create all the collections if they don't exist.
        MongoDB creates collections on the fly, so this is a no-op.
        """

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    async def get(self, collection: str, name: str) -> dict | None:
        def _get():
            doc = self._col(collection).find_one({"name": name}, {"_id": 0})
            return doc

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
