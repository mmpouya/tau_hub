"""Tests for tau_hub.sessions — run with: python -m unittest discover -s tests"""

import json
import tempfile
import unittest
from pathlib import Path

from tau_hub.db.sqlite import SQLiteStore
from tau_hub.sessions import (
    HubSessionStorage,
    export_session_jsonl,
    import_session_jsonl,
)

_ENTRY_1 = {
    "id": "e1",
    "parent_id": None,
    "timestamp": 1.0,
    "type": "session_info",
    "created_at": 1.0,
    "cwd": "/tmp",
    "title": "demo",
}
_ENTRY_2 = {
    "id": "e2",
    "parent_id": "e1",
    "timestamp": 2.0,
    "type": "label",
    "label": "hello",
}


class HubSessionStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SQLiteStore(":memory:")
        self.storage = HubSessionStorage(self.store, "session-1")

    async def asyncTearDown(self):
        await self.store.close()

    async def test_missing_session_reads_empty(self):
        self.assertEqual(await self.storage.read_all(), [])

    async def test_append_and_read_all_in_order(self):
        await self.storage.append(_ENTRY_1)
        await self.storage.append(_ENTRY_2)
        entries = await self.storage.read_all()
        self.assertEqual(len(entries), 2)
        first, second = (self._as_dict(e) for e in entries)
        self.assertEqual(first["id"], "e1")
        self.assertEqual(second["id"], "e2")

    async def test_sessions_are_isolated(self):
        other = HubSessionStorage(self.store, "session-2")
        await self.storage.append(_ENTRY_1)
        self.assertEqual(await other.read_all(), [])

    async def test_empty_session_id_rejected(self):
        with self.assertRaises(ValueError):
            HubSessionStorage(self.store, "")

    @staticmethod
    def _as_dict(entry):
        return entry if isinstance(entry, dict) else entry.model_dump(mode="json")


class JsonlImportExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SQLiteStore(":memory:")

    async def asyncTearDown(self):
        await self.store.close()

    async def test_import_then_export_is_lossless(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "session.jsonl"
            src.write_text(
                json.dumps(_ENTRY_1) + "\n\n" + json.dumps(_ENTRY_2) + "\n",
                encoding="utf-8",
            )
            count = await import_session_jsonl(self.store, "imported", src)
            self.assertEqual(count, 2)

            dst = Path(tmp) / "out" / "session.jsonl"
            exported = await export_session_jsonl(self.store, "imported", dst)
            self.assertEqual(exported, 2)
            lines = [
                json.loads(line)
                for line in dst.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(lines, [_ENTRY_1, _ENTRY_2])

    async def test_export_missing_session_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                await export_session_jsonl(self.store, "nope", Path(tmp) / "x.jsonl")

    async def test_import_invalid_jsonl_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.jsonl"
            src.write_text("{not json}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                await import_session_jsonl(self.store, "bad", src)


if __name__ == "__main__":
    unittest.main()
