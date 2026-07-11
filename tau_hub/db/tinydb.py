"""TinyDB backend — default, zero-configuration, single-writer."""

from __future__ import annotations

import asyncio
import logging
import os

try:
    from tinydb import Query, TinyDB
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "TinyDB is required for TinyDBStore.\nInstall it with: pip install tau-hub"
    ) from exc

from tau_hub.db.base import BaseAgentStore

logger = logging.getLogger(__name__)


class TinyDBStore(BaseAgentStore):
    """Async-friendly wrapper around TinyDB (pure-Python JSON file store).

    TinyDB itself is synchronous; every operation is dispatched to a thread
    pool so callers can ``await`` it without blocking the event loop.

    Best for single-process / single-writer deployments. For concurrent
    multi-process writes use :class:`~tau_hub.db.sqlite.SQLiteStore` or
    :class:`~tau_hub.db.postgres.PostgresStore`.

    Parameters
    ----------
    path:
        Path of the JSON database file. Parent directories are created
        automatically.
    """

    def __init__(self, path: str = "./.tau_hub/tau_hub.json") -> None:
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._db = TinyDB(path)
        except Exception:
            logger.exception("Failed to initialize TinyDBStore at path=%s", path)
            raise

    def _table(self, collection: str):
        """Return the TinyDB table backing *collection*."""
        return self._db.table(collection)

    async def _run(self, fn, *args):
        """Run a synchronous TinyDB call in the default thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn, *args)

    async def get(self, collection: str, name: str) -> dict | None:
        """Return the document stored under ``(collection, name)`` or ``None``."""

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
        """Insert or replace the document stored under ``(collection, name)``."""

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
        """Delete the document stored under ``(collection, name)``."""

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
        """Return every document in *collection*."""

        def _batch():
            return self._table(collection).all()

        try:
            return await self._run(_batch)
        except Exception:
            logger.exception("Failed to batch_get: collection=%s", collection)
            raise

    async def close(self) -> None:
        """Close the underlying TinyDB file handle."""
        await self._run(self._db.close)
