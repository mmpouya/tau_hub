"""PostgreSQL backend (requires: ``pip install tau-hub[postgres]``)."""

from __future__ import annotations

try:
    import asyncpg
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "asyncpg is required for PostgresStore.\n"
        "Install it with: pip install tau-hub[postgres]"
    ) from exc

import json
from typing import Any

from tau_hub.db.base import BaseAgentStore

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    name       TEXT NOT NULL,
    data       JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (collection, name)
);
"""


class PostgresStore(BaseAgentStore):
    """PostgreSQL backend using asyncpg.

    Uses a single ``documents`` table with ``(collection, name, data jsonb)``.
    Safe for concurrent writes from multiple processes — no extra locking
    needed.

    Call ``await store.connect()`` (or ``await hub.init_db()``) before first
    use, or use the store as an async context manager.

    Parameters
    ----------
    dsn:
        PostgreSQL connection string, e.g. ``postgresql://user:pass@host/db``.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create the connection pool and ensure the schema exists."""
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(_INIT_SQL)

    async def init_db(self) -> None:
        """Connect (if needed) and create the ``documents`` table."""
        await self.connect()

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.close()

    @property
    def _p(self) -> asyncpg.Pool:
        """The active pool; raises if :meth:`connect` was never awaited."""
        if self._pool is None:
            raise RuntimeError(
                "Call 'await store.connect()' (or 'await hub.init_db()') "
                "before using PostgresStore."
            )
        return self._pool

    async def get(self, collection: str, name: str) -> dict | None:
        """Return the document stored under ``(collection, name)`` or ``None``."""
        row = await self._p.fetchrow(
            "SELECT data FROM documents WHERE collection=$1 AND name=$2",
            collection,
            name,
        )
        if row is None:
            return None
        doc = json.loads(row["data"])
        doc.setdefault("name", name)
        return doc

    async def put(self, collection: str, name: str, data: dict, **extra) -> None:
        """Insert or replace the document stored under ``(collection, name)``."""
        doc = {"name": name, **data, **extra}
        await self._p.execute(
            """
            INSERT INTO documents (collection, name, data)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (collection, name)
            DO UPDATE SET data = EXCLUDED.data
            """,
            collection,
            name,
            json.dumps(doc),
        )

    async def delete(self, collection: str, name: str) -> None:
        """Delete the document stored under ``(collection, name)``."""
        await self._p.execute(
            "DELETE FROM documents WHERE collection=$1 AND name=$2",
            collection,
            name,
        )

    async def batch_get(self, collection: str) -> list[dict]:
        """Return every document in *collection*."""
        rows = await self._p.fetch(
            "SELECT name, data FROM documents WHERE collection=$1",
            collection,
        )
        docs = []
        for row in rows:
            doc = json.loads(row["data"])
            doc.setdefault("name", row["name"])
            docs.append(doc)
        return docs

    async def append_to_list(
        self, collection: str, name: str, field: str, item: Any
    ) -> None:
        """Atomically append *item* to ``doc[field]`` with jsonb concatenation.

        Safe for concurrent writers — the append happens inside a single SQL
        statement, so there is no read-modify-write race.
        """
        item_json = json.dumps(item)
        await self._p.execute(
            """
            INSERT INTO documents (collection, name, data)
            VALUES ($1, $2, jsonb_build_object('name', $2::text, $3::text, jsonb_build_array($4::jsonb)))
            ON CONFLICT (collection, name)
            DO UPDATE SET data = jsonb_set(
                documents.data,
                ARRAY[$3::text],
                COALESCE(documents.data -> $3::text, '[]'::jsonb) || $4::jsonb
            )
            """,
            collection,
            name,
            field,
            item_json,
        )
