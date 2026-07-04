"""TinyDB backend — default, zero-dependency, single-writer."""
from __future__ import annotations

try:
    from tinydb import TinyDB, Query
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "TinyDB is required for TinyDBStore.\n"
        "Install it with: pip install tau-hub"
    ) from exc

import asyncio
from tau_hub.db.base import AgentStore


class TinyDBStore(AgentStore):
    """Async-friendly wrapper around TinyDB.

    TinyDB itself is synchronous; every operation is dispatched to a thread
    pool so callers can await it without blocking the event loop.
    """

    def __init__(self, path: str = "tau_hub.json") -> None:
        self._db = TinyDB(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _table(self, collection: str):
        return self._db.table(collection)

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ------------------------------------------------------------------
    # AgentStore interface
    # ------------------------------------------------------------------

    async def get(self, collection: str, name: str) -> dict | None:
        def _get():
            q = Query()
            return self._table(collection).get(q.name == name)
        return await self._run(_get)

    async def put(self, collection: str, name: str, data: dict) -> None:
        def _put():
            q = Query()
            doc = {"name": name, **data}
            self._table(collection).upsert(doc, q.name == name)
        await self._run(_put)

    async def delete(self, collection: str, name: str) -> None:
        def _delete():
            q = Query()
            self._table(collection).remove(q.name == name)
        await self._run(_delete)

    async def batch_get(self, collection: str) -> list[dict]:
        def _batch():
            return self._table(collection).all()
        return await self._run(_batch)
