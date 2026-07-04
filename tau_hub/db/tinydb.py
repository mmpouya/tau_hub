"""TinyDB backend — default, zero-dependency, single-writer."""

from __future__ import annotations

import asyncio
import logging
import os

try:
    from tinydb import Query, TinyDB
except ImportError as exc:
    raise ImportError(
        "TinyDB is required for TinyDBStore.\nInstall it with: pip install tau-hub"
    ) from exc

from tau_hub.db.base import BaseAgentStore

logger = logging.getLogger(__name__)


class TinyDBStore(BaseAgentStore):
    """Async-friendly wrapper around TinyDB.

    TinyDB itself is synchronous;
    here, every operation is dispatched to a thread pool
    so callers can await it without blocking the event loop. ^-^
    this is not vibe coded BTW
    """

    def __init__(self, path: str = "./.tau_hub/tau_hub.json") -> None:
        try:
            if path.startswith("./.tau_hub/"):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            self._db = TinyDB(path)
        except Exception:
            logger.exception("Failed to initialize TinyDBStore at path=%s", path)
            raise

    async def init_db(self) -> None:
        try:
            pass
        except Exception:
            logger.exception("Failed to init_db")
            raise

    def _table(self, collection: str):
        return self._db.table(collection)

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    async def get(self, collection: str, name: str) -> dict | None:
        def _get():
            q = Query()
            return self._table(collection).get(q.name == name)

        try:
            return await self._run(_get)
        except Exception:
            logger.exception(
                "Failed to get document: collection=%s, name=%s", collection, name
            )
            raise

    async def put(self, collection: str, name: str, data: dict, **extra) -> None:
        def _put():
            q = Query()
            doc = {"name": name, **data, **extra}
            self._table(collection).upsert(doc, q.name == name)

        try:
            await self._run(_put)
        except Exception:
            logger.exception(
                "Failed to put document: collection=%s, name=%s", collection, name
            )
            raise

    async def delete(self, collection: str, name: str) -> None:
        def _delete():
            q = Query()
            self._table(collection).remove(q.name == name)

        try:
            await self._run(_delete)
        except Exception:
            logger.exception(
                "Failed to delete document: collection=%s, name=%s", collection, name
            )
            raise

    async def batch_get(self, collection: str) -> list[dict]:
        def _batch():
            return self._table(collection).all()

        try:
            return await self._run(_batch)
        except Exception:
            logger.exception("Failed to batch_get: collection=%s", collection)
            raise
