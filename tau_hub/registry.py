"""Public API — TauRegistry wraps an AgentStore and exposes high-level
create/get/register/delete methods for agents, tools, and skills.
"""
from __future__ import annotations

from tau_hub.db.base import AgentStore
from tau_hub.db.tinydb import TinyDBStore

_AGENTS = "agents"
_TOOLS = "tools"
_SKILLS = "skills"


class TauRegistry:
    """Cross-service agent registry.

    Parameters
    ----------
    store:
        Any AgentStore implementation.  Defaults to TinyDBStore
        (pure-Python, zero dependencies).
    """

    def __init__(self, store: AgentStore | None = None) -> None:
        self._store = store or TinyDBStore()

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    async def create_agent(
        self,
        name: str,
        system: str,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        **extra,
    ) -> None:
        """Persist an agent definition."""
        await self._store.put(_AGENTS, name, {
            "system": system,
            "tools": tools or [],
            "skills": skills or [],
            **extra,
        })

    async def get_agent(self, name: str) -> dict | None:
        """Load an agent definition by name."""
        return await self._store.get(_AGENTS, name)

    async def delete_agent(self, name: str) -> None:
        await self._store.delete(_AGENTS, name)

    async def list_agents(self) -> list[dict]:
        return await self._store.batch_get(_AGENTS)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def register_tool(
        self,
        name: str,
        description: str,
        schema: dict | None = None,
        **extra,
    ) -> None:
        """Store a tool definition."""
        await self._store.put(_TOOLS, name, {
            "description": description,
            "schema": schema or {},
            **extra,
        })

    async def get_tool(self, name: str) -> dict | None:
        return await self._store.get(_TOOLS, name)

    async def list_tools(self) -> list[dict]:
        return await self._store.batch_get(_TOOLS)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    async def register_skill(
        self,
        name: str,
        prompt: str,
        config: dict | None = None,
        **extra,
    ) -> None:
        """Store a skill prompt/config."""
        await self._store.put(_SKILLS, name, {
            "prompt": prompt,
            "config": config or {},
            **extra,
        })

    async def get_skill(self, name: str) -> dict | None:
        return await self._store.get(_SKILLS, name)

    async def list_skills(self) -> list[dict]:
        return await self._store.batch_get(_SKILLS)
