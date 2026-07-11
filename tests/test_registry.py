"""Tests for tau_hub.registry.TauHub — run with: python -m unittest discover -s tests

These tests use the SQLite backend (stdlib) and avoid constructing live
tau_ai providers, so they run without tau/tau-ai installed.
"""

import unittest

from tau_hub import Skill, TauHub
from tau_hub.crypto import MissingSecretKeyError, is_encrypted
from tau_hub.db.sqlite import SQLiteStore


class ProviderEncryptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SQLiteStore(":memory:")
        self.hub = TauHub(store=self.store, secret_key="unit-test-secret")
        await self.hub.init_db()

    async def asyncTearDown(self):
        await self.hub.close()

    async def test_api_key_is_encrypted_at_rest(self):
        await self.hub.register_provider(
            "p1",
            "OpenAICompatibleProvider",
            api_key="sk-plaintext",
            base_url="https://api.example.com/v1",
            model_name="m",
        )
        raw = await self.store.get("providers", "p1")
        self.assertTrue(is_encrypted(raw["api_key"]))
        self.assertNotIn("sk-plaintext", raw["api_key"])
        # Other fields stay readable.
        self.assertEqual(raw["base_url"], "https://api.example.com/v1")
        self.assertEqual(raw["model_name"], "m")
        # And the hub can decrypt it back.
        self.assertEqual(self.hub._reveal(raw["api_key"]), "sk-plaintext")

    async def test_reading_encrypted_key_without_secret_raises(self):
        await self.hub.register_provider(
            "p1", "OpenAICompatibleProvider", "sk-x", None, None
        )
        raw = await self.store.get("providers", "p1")
        keyless_hub = TauHub(store=self.store)
        with self.assertRaises(MissingSecretKeyError):
            keyless_hub._reveal(raw["api_key"])

    async def test_plaintext_legacy_value_passthrough(self):
        # Simulate a row written by tau_hub < 0.2.0 (no encryption).
        await self.store.put(
            "providers",
            "legacy",
            {"provider_class": "OpenAICompatibleProvider", "api_key": "sk-legacy"},
        )
        raw = await self.store.get("providers", "legacy")
        self.assertEqual(self.hub._reveal(raw["api_key"]), "sk-legacy")

    async def test_no_secret_key_stores_plaintext_with_warning(self):
        keyless_hub = TauHub(store=self.store)
        with self.assertLogs("tau_hub.registry", level="WARNING"):
            await keyless_hub.register_provider(
                "p2", "OpenAICompatibleProvider", "sk-open", None, None
            )
        raw = await self.store.get("providers", "p2")
        self.assertEqual(raw["api_key"], "sk-open")


class AgentAndSkillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub = TauHub(store=SQLiteStore(":memory:"), secret_key="s")
        await self.hub.init_db()

    async def asyncTearDown(self):
        await self.hub.close()

    async def test_agent_crud(self):
        await self.hub.register_agent("a", system="You are helpful.")
        self.assertEqual(await self.hub.get_agent("a"), "You are helpful.")
        self.assertEqual(await self.hub.list_agents(), {"a": "You are helpful."})
        await self.hub.delete_agent("a")
        with self.assertRaises(ValueError):
            await self.hub.get_agent("a")

    async def test_skill_crud(self):
        await self.hub.register_skill(
            "metric",
            description="Metric units.",
            content="Always use metric units.",
            config={"strict": True},
        )
        skill = await self.hub.get_skill("metric")
        self.assertIsInstance(skill, Skill)
        self.assertEqual(skill.description, "Metric units.")
        self.assertEqual(skill.config, {"strict": True})
        section = skill.as_prompt_section()
        self.assertIn("## Skill: metric", section)
        self.assertIn("Always use metric units.", section)

        skills = await self.hub.list_skills()
        self.assertEqual(set(skills), {"metric"})

        await self.hub.delete_skill("metric")
        with self.assertRaises(ValueError):
            await self.hub.get_skill("metric")

    async def test_register_is_upsert(self):
        await self.hub.register_agent("a", system="v1")
        await self.hub.register_agent("a", system="v2")
        self.assertEqual(await self.hub.get_agent("a"), "v2")


class SessionApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub = TauHub(store=SQLiteStore(":memory:"), secret_key="s")
        await self.hub.init_db()

    async def asyncTearDown(self):
        await self.hub.close()

    async def test_session_storage_roundtrip_and_listing(self):
        storage = self.hub.session_storage("chat-1")
        await storage.append({"id": "e1", "parent_id": None, "timestamp": 1.0, "type": "label", "label": "x"})
        await storage.append({"id": "e2", "parent_id": "e1", "timestamp": 2.0, "type": "label", "label": "y"})
        self.assertEqual(len(await storage.read_all()), 2)
        self.assertEqual(await self.hub.list_sessions(), {"chat-1": 2})
        await self.hub.delete_session("chat-1")
        self.assertEqual(await self.hub.list_sessions(), {})


class StoreSelectionTests(unittest.TestCase):
    def test_unsupported_url_raises(self):
        with self.assertRaises(ValueError):
            TauHub("mysql://nope")

    def test_sqlite_url_selects_sqlite(self):
        hub = TauHub("sqlite::memory:")
        self.assertIsInstance(hub.store, SQLiteStore)


if __name__ == "__main__":
    unittest.main()
