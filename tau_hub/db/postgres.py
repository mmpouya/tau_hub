"""PostgreSQL backend (requires: pip install tau-hub[postgres])."""
from __future__ import annotations

try:
    import asyncpg
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "asyncpg is required for PostgresStore.\n"
        "Install it with: pip install tau-hub[postgres]"
    ) from exc

import json
from tau_hub.db.base import AgentStore

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    name       TEXT NOT NULL,
    data       JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (collection, name)
);
"""


class PostgresStore(AgentStore):
    """PostgreSQL backend using asyncpg.

    Uses a single 'documents' table with (collection, name, data jsonb).
    Safe for concurrent writes from multiple processes — no extra locking
    needed.

    Call await store.connect() before first use, or use as an async
    context manager.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(_INIT_SQL)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.close()

    @property
    def _p(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Call await store.connect() before using PostgresStore.")
        return self._pool

    async def get(self, collection: str, name: str) -> dict | None:
        row = await self._p.fetchrow(
            "SELECT data FROM documents WHERE collection=$1 AND name=$2",
            collection, name,
        )
        if row is None:
            return None
        return json.loads(row["data"])

    async def put(self, collection: str, name: str, data: dict) -> None:
        await self._p.execute(
            """
            INSERT INTO documents (collection, name, data)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (collection, name)
            DO UPDATE SET data = EXCLUDED.data
            """,
            collection, name, json.dumps(data),
        )

    async def delete(self, collection: str, name: str) -> None:
        await self._p.execute(
            "DELETE FROM documents WHERE collection=$1 AND name=$2",
            collection, name,
        )

    async def batch_get(self, collection: str) -> list[dict]:
        rows = await self._p.fetch(
            "SELECT data FROM documents WHERE collection=$1",
            collection,
        )
        return [json.loads(r["data"]) for r in rows]
