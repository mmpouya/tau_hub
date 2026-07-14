"""SQLite backend — file-based, ACID, safe for multiple local writers.

Uses a single generic ``documents`` table (``collection``, ``name``,
``data`` JSON) so it can store any collection — providers, agents, tools,
skills, configs, and chat sessions — without schema migrations.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

from tau_hub.db.base import BaseAgentStore

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    name       TEXT NOT NULL,
    data       TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (collection, name)
);
"""


class SQLiteStore(BaseAgentStore):
    """SQLite backend using the standard library ``sqlite3`` module.

    Synchronous ``sqlite3`` calls are dispatched to a thread pool so callers
    can ``await`` them. WAL journaling is enabled so concurrent local readers
    don't block the writer.

    Parameters
    ----------
    url_or_path:
        Either a filesystem path (``"./tau_hub.sqlite3"``), an in-memory
        database (``":memory:"``), or a URL of the form
        ``sqlite:///path/to/db.sqlite3``.
    """

    def __init__(self, url_or_path: str = "./.tau_hub/tau_hub.sqlite3") -> None:
        self.db_path = self._path_from_url(url_or_path)
        # check_same_thread=False: access is serialized through the internal
        # lock below, but calls may run on any thread-pool thread.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_INIT_SQL)
        self._conn.commit()
        self._lock = asyncio.Lock()

    @staticmethod
    def _path_from_url(url_or_path: str) -> str:
        """Strip an optional ``sqlite:`` URL scheme, returning a plain path."""
        for prefix in ("sqlite:///", "sqlite://", "sqlite:"):
            if url_or_path.startswith(prefix):
                remainder = url_or_path[len(prefix) :]
                return remainder or "./.tau_hub/tau_hub.sqlite3"
        return url_or_path

    async def _run(self, fn, *args):
        """Run a synchronous sqlite3 call in the thread pool, serialized."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, fn, *args)

    async def init_db(self) -> None:
        """Create the ``documents`` table if needed (also done in ``__init__``)."""

        def _init():
            self._conn.execute(_INIT_SQL)
            self._conn.commit()

        await self._run(_init)

    async def get(self, collection: str, name: str, **filters) -> dict | None:
        """Return the document stored under ``(collection, name)`` or ``None``."""

        def _get():
            self._validate_filter_keys(**filters)
            conditions = ["collection = ?", "name = ?"]
            params = [collection, name]
            for key, value in filters.items():
                conditions.append(f"json_extract(data, '$.{key}') = ?")
                params.append(value)
            where = " AND ".join(conditions)
            row = self._conn.execute(
                f"SELECT data FROM documents WHERE {where}",
                params,
            ).fetchone()
            if row is None:
                return None
            doc = json.loads(row[0])
            doc.setdefault("name", name)
            return doc

        return await self._run(_get)

    async def put(self, collection: str, name: str, data: dict, **extra) -> None:
        """Insert or replace the document stored under ``(collection, name)``."""

        def _put():
            doc = {"name": name, **data, **extra}
            self._conn.execute(
                "INSERT OR REPLACE INTO documents (collection, name, data) "
                "VALUES (?, ?, ?)",
                (collection, name, json.dumps(doc, ensure_ascii=False)),
            )
            self._conn.commit()

        await self._run(_put)

    async def delete(self, collection: str, name: str) -> None:
        """Delete the document stored under ``(collection, name)``."""

        def _delete():
            self._conn.execute(
                "DELETE FROM documents WHERE collection = ? AND name = ?",
                (collection, name),
            )
            self._conn.commit()

        await self._run(_delete)

    async def batch_get(self, collection: str, **filters) -> list[dict]:
        """Return every document in *collection* matching all ``**filters``."""

        def _batch():
            self._validate_filter_keys(**filters)
            conditions = ["collection = ?"]
            params = [collection]
            for key, value in filters.items():
                conditions.append(f"json_extract(data, '$.{key}') = ?")
                params.append(value)
            where = " AND ".join(conditions)
            rows = self._conn.execute(
                f"SELECT name, data FROM documents WHERE {where}",
                params,
            ).fetchall()
            docs = []
            for name, data in rows:
                doc = json.loads(data)
                doc.setdefault("name", name)
                docs.append(doc)
            return docs

        return await self._run(_batch)

    async def close(self) -> None:
        """Close the underlying SQLite connection."""

        await self._run(self._conn.close)
