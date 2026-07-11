"""Backend contract tests (SQLite + TinyDB when available).

Run with: python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

from tau_hub.db.sqlite import SQLiteStore


class SQLiteStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SQLiteStore(":memory:")
        await self.store.init_db()

    async def asyncTearDown(self):
        await self.store.close()

    async def test_get_missing_returns_none(self):
        self.assertIsNone(await self.store.get("agents", "nope"))

    async def test_put_get_roundtrip(self):
        await self.store.put("agents", "a1", {"system": "hi", "extra": [1, 2]})
        doc = await self.store.get("agents", "a1")
        self.assertEqual(doc["name"], "a1")
        self.assertEqual(doc["system"], "hi")
        self.assertEqual(doc["extra"], [1, 2])

    async def test_put_replaces(self):
        await self.store.put("agents", "a1", {"system": "v1"})
        await self.store.put("agents", "a1", {"system": "v2"})
        doc = await self.store.get("agents", "a1")
        self.assertEqual(doc["system"], "v2")

    async def test_delete(self):
        await self.store.put("tools", "t", {"description": "d"})
        await self.store.delete("tools", "t")
        self.assertIsNone(await self.store.get("tools", "t"))

    async def test_batch_get(self):
        await self.store.put("skills", "s1", {"content": "one"})
        await self.store.put("skills", "s2", {"content": "two"})
        docs = await self.store.batch_get("skills")
        self.assertEqual({d["name"] for d in docs}, {"s1", "s2"})

    async def test_append_to_list_creates_and_appends(self):
        await self.store.append_to_list("sessions", "s", "entries", {"n": 1})
        await self.store.append_to_list("sessions", "s", "entries", {"n": 2})
        doc = await self.store.get("sessions", "s")
        self.assertEqual(doc["entries"], [{"n": 1}, {"n": 2}])

    async def test_url_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.sqlite3"
            store = SQLiteStore(f"sqlite:{path}")
            await store.put("agents", "a", {"system": "s"})
            await store.close()
            self.assertTrue(path.exists())


class TinyDBStoreTests(unittest.IsolatedAsyncioTestCase):
    """Same contract for TinyDB — skipped automatically if tinydb is absent."""

    async def asyncSetUp(self):
        try:
            from tau_hub.db.tinydb import TinyDBStore
        except ImportError:
            self.skipTest("tinydb is not installed")
        self._tmp = tempfile.TemporaryDirectory()
        self.store = TinyDBStore(path=str(Path(self._tmp.name) / "db.json"))
        await self.store.init_db()

    async def asyncTearDown(self):
        await self.store.close()
        self._tmp.cleanup()

    async def test_roundtrip_and_append(self):
        await self.store.put("agents", "a", {"system": "hello"})
        self.assertEqual((await self.store.get("agents", "a"))["system"], "hello")
        await self.store.append_to_list("sessions", "s", "entries", {"n": 1})
        doc = await self.store.get("sessions", "s")
        self.assertEqual(doc["entries"], [{"n": 1}])


if __name__ == "__main__":
    unittest.main()
