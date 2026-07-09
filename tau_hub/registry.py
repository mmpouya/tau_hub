"""Public API — TauRegistry wraps an AgentStore and exposes high-level
create/get/register/delete methods for agents, tools, and skills.
"""

from __future__ import annotations

import base64
import json
from typing import Callable, Literal

import dill
from tau_agent import (
    AgentHarnessConfig,
    AgentTool,
    AgentToolResult,
    JSONValue,  # let this import be there, sometimes they have usages in dumping executers
)
from tau_ai import ModelProvider

from tau_hub.db.base import BaseAgentStore

# these are collection names in the underlying AgentStore
_CONFIG = "config"
_PROVIDERS = "providers"
_AGENTS = "agents"
_TOOLS = "tools"
_SKILLS = "skills"
# for future: add a "memory" collection for storing memory objects,
# e.g. for agents that need to persist state between runs


class TauHub:
    """Cross-service agent registry.

    Parameters
    ----------
    store:
        Any AgentStore implementation.  Defaults to TinyDBStore.
        For different DB backends, check the extra packages in tau-hub, e.g. `pip install tau-hub[mongo]`.
    """

    def __init__(self, store_url: str | None = None) -> None:
        if store_url is None:
            from tau_hub.db.tinydb import TinyDBStore

            self._store = TinyDBStore()
        elif store_url.startswith("mongo"):
            from tau_hub.db.mongo import MongoStore

            self._store = MongoStore(store_url)
        elif store_url.startswith("redis"):
            from tau_hub.db.redis import RedisStore

            self._store = RedisStore(store_url)
        elif store_url.startswith("postgres"):
            from tau_hub.db.postgres import PostgresStore

            self._store = PostgresStore(store_url)
        elif store_url.startswith("sqlite"):
            from tau_hub.db.sqlite import SQLiteStore

            self._store = SQLiteStore(store_url)
        else:
            raise ValueError(f"Unsupported store_url: {store_url}")

    async def init_db(self) -> None:
        """Initialize the underlying database.

        For some backends, this may be a no-op.
        """
        await self._store.init_db()

    #####################################################################
    ##### Provider CRUD

    async def register_provider(
        self,
        name: str,
        provider_class: Literal["AnthropicProvider", "OpenAICompatibleProvider"],
        api_key: str,
        base_url: str | None,
        model_name: str | None,
        **extra,
    ) -> str:
        """Store a provider class and its config."""
        try:
            await self._store.put(
                _PROVIDERS,
                name,
                {
                    "provider_class": provider_class,
                    "api_key": api_key or "",
                    "base_url": base_url or "",
                    "model_name": model_name or "",
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to register provider {name}: {e}")
        return name

    async def get_provider(self, name: str) -> tuple[ModelProvider, str]:
        """Load a provider definition by name."""
        data = await self._store.get(_PROVIDERS, name)
        if data is None:
            raise ValueError(f"Provider {name} is not registered!")
        match data.get("provider_class"):
            case "AnthropicProvider":
                from tau_ai.anthropic import AnthropicProvider
                from tau_ai.env import AnthropicConfig

                provider_config = AnthropicConfig(api_key=data.get("api_key", ""))
                return (
                    AnthropicProvider(provider_config),
                    data.get("model_name", ""),
                )
            case "OpenAICompatibleProvider":
                # from tau_ai.openai import OpenAIProvider
                from tau_ai import OpenAICompatibleConfig, OpenAICompatibleProvider

                config = OpenAICompatibleConfig(
                    api_key=data.get("api_key", ""),
                    base_url=data.get("base_url", ""),
                )
                return (
                    OpenAICompatibleProvider(config=config),
                    data.get("model_name", ""),
                )
            case _:
                raise ValueError(f"Provider {name} has no provider_class defined.")

    async def list_providers(self) -> dict[str, tuple[ModelProvider, str]]:
        """List all registered providers."""
        providers = await self._store.batch_get(_PROVIDERS)
        result = {}
        for provider in providers:
            name = provider.get("name", "")
            if name:
                result[name] = await self.get_provider(name)
        return result

    async def delete_provider(self, name: str) -> None:
        """Delete a provider definition by name."""
        await self._store.delete(_PROVIDERS, name)

    #####################################################################
    ##### Agents CRUD

    async def register_agent(
        self,
        name: str,
        system: str,
        # tools: list[str] | None = None,
        # skills: list[str] | None = None,
        **extra,
    ) -> str:
        """Persist an agent definition.
        Note:
        the relation between agents and tools/skills is not enforced here;
        it's up to the user to ensure that the tools/skills exist
        and that the agent's config is consistent with them
        """
        try:
            await self._store.put(
                _AGENTS,
                name,
                {
                    "system": system,
                    # "tools": tools or [],
                    # "skills": skills or [],
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to create agent {name}: {e}")
        return name

    async def get_agent(self, name: str) -> str:
        """Load an agent definition by name."""
        data = await self._store.get(_AGENTS, name)
        if data:
            return data.get("system", "")
        else:
            raise ValueError(f"Agent {name} had not been registered yet.")

    async def delete_agent(self, name: str) -> None:
        await self._store.delete(_AGENTS, name)

    async def list_agents(self) -> dict[str, str]:
        agents = await self._store.batch_get(_AGENTS)
        result = {}
        for agent in agents:
            name = agent.get("name", "")
            if name:
                result[name] = await self.get_agent(name)
        return result

    #####################################################################
    #####  Tools CRUD

    # FUNCTION HELPER

    # @staticmethod
    # def _store_ref(func) -> str:
    #     return f"{func.__module__}.{func.__qualname__}"

    # @staticmethod
    # def load_ref(ref: str):
    #     module_name, func_name = ref.rsplit(".", 1)
    #     module = importlib.import_module(module_name)
    #     return getattr(module, func_name)

    async def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict | None,
        executor: Callable | None = None,
        **extra,
    ) -> str:
        """Store a tool definition."""

        try:
            executor_b64 = None
            if executor:
                executor_bytes = dill.dumps(executor)
                executor_b64 = base64.b64encode(executor_bytes).decode("ascii")

            await self._store.put(
                _TOOLS,
                name,
                {
                    "description": description,
                    "input_schema": json.dumps(input_schema),
                    "executor": executor_b64,
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to register tool {name}: {e}")
        return name

    async def get_tool(self, name: str) -> AgentTool:
        data = await self._store.get(_TOOLS, name)
        if data:
            return AgentTool(
                name=name,
                description=data.get("description", ""),
                input_schema=json.loads(data.get("input_schema")),  # ty:ignore[invalid-argument-type]
                executor=dill.loads(base64.b64decode(data["executor"])),
            )
        else:
            raise ValueError(f"Tool {name} had not get defined yet.")

    async def list_tools(self) -> dict[str, AgentTool]:
        tools = await self._store.batch_get(_TOOLS)
        result = {}
        for tool in tools:
            name = tool.get("name", "")
            if name:
                result[name] = await self.get_tool(name)
        return result

    async def delete_tool(self, name: str) -> None:
        await self._store.delete(_TOOLS, name)

    #####################################################################
    ##### Skills CRUD

    # async def register_skill(
    #     self,
    #     name: str,
    #     description: str,
    #     content: str,
    #     config: dict | None = None,
    #     **extra,
    # ) -> None:
    #     """Store a skill prompt/config."""
    #     await self._store.put(
    #         _SKILLS,
    #         name,
    #         {
    #             "name": name,
    #             "description": description,
    #             "content": content,
    #             "config": config or {},
    #             **extra,
    #         },
    #     )

    # async def get_skill(self, name: str):
    #     data = await self._store.get(_SKILLS, name)
    #     if not data:
    #         raise ValueError(f"Skill {name} had not get defined yet.")
    #     if data:
    #         return AgentTool(
    #             name=name,
    #             description=data.get("description", ""),
    #             input_schema=data.get(),
    #         )

    # async def list_skills(self) -> list[dict]:
    #     return await self._store.batch_get(_SKILLS)

    # async def delete_skill(self, name: str) -> None:
    #     await self._store.delete(_SKILLS, name)

    #####################################################################
    ##### Config CRUD

    async def register_config(
        self,
        name: str,
        agent_name: str,
        provider_name: str,
        tool_names: list[str] | None = None,
        # skill_names: list[str] | None = None,
        **extra,
    ) -> str:
        """Store a config."""
        try:
            await self._store.put(
                _CONFIG,
                name,
                {
                    "agent_name": agent_name,
                    "provider_name": provider_name,
                    "tool_names": tool_names or [],
                    # "skill_names": skill_names or [],
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to register config {name}: {e}")
        return name

    async def get_config(self, name: str) -> AgentHarnessConfig:
        """Load a config by name."""
        data = await self._store.get(_CONFIG, name)
        if not data:
            raise ValueError(f"Config {name} had not get defined yet.")
        provider, model_name = await self.get_provider(data.get("provider_name", ""))
        agent = await self.get_agent(data.get("agent_name", ""))
        tools = []
        for tool_name in data.get("tool_names", []):
            tool = await self.get_tool(tool_name)
            tools.append(tool)
        return AgentHarnessConfig(
            provider=provider,
            model=model_name,
            system=agent,
            tools=tools,
            # skills=data.get("skill_names", []),
        )

    async def list_configs(self) -> dict[str, AgentHarnessConfig]:
        """List all registered configs."""
        configs = await self._store.batch_get(_CONFIG)
        result = {}
        for config in configs:
            name = config.get("name", "")
            if name:
                result[name] = await self.get_config(name)
        return result

    async def delete_config(self, name: str) -> None:
        await self._store.delete(_CONFIG, name)
