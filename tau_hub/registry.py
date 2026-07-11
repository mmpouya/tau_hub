"""Public API — :class:`TauHub` wraps an agent store and exposes high-level
register / get / list / delete methods for providers, agents, tools, skills,
configs, and chat sessions.

All ``register_*`` methods are upserts: registering an existing name replaces
its stored definition, so they double as update endpoints.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

from tau_hub.crypto import MissingSecretKeyError, SecretBox, is_encrypted
from tau_hub.db.base import BaseAgentStore
from tau_hub.models import Skill
from tau_hub.sessions import (
    SESSIONS_COLLECTION,
    HubSessionStorage,
    export_session_jsonl,
    import_session_jsonl,
)

if TYPE_CHECKING:  # imported lazily at runtime so the module works without tau
    from tau_agent import AgentHarnessConfig, AgentTool
    from tau_ai import ModelProvider

logger = logging.getLogger(__name__)

# Collection names in the underlying agent store.
_CONFIG = "config"
_PROVIDERS = "providers"
_AGENTS = "agents"
_TOOLS = "tools"
_SKILLS = "skills"
# for future: add a "memory" collection for storing memory objects,
# e.g. for agents that need to persist state between runs

#: Environment variable checked when no ``secret_key`` argument is given.
SECRET_KEY_ENV_VAR = "TAU_HUB_SECRET_KEY"


class TauHub:
    """Cross-service agent registry and persistence layer for ``tau_agent``.

    A single hub instance manages six collections in one database:
    **providers** (model providers + encrypted API keys), **agents** (system
    prompts), **tools** (schemas + serialized executors), **skills** (reusable
    prompt extensions), **configs** (named provider/agent/tools/skills
    bundles), and **sessions** (durable chat history usable in place of Tau's
    JSONL files).

    Parameters
    ----------
    store_url:
        Connection URL selecting a backend by scheme:

        - ``None`` → TinyDB at ``./.tau_hub/tau_hub.json`` (default)
        - ``sqlite:...`` → :class:`~tau_hub.db.sqlite.SQLiteStore`
        - ``mongo...`` → :class:`~tau_hub.db.mongo.MongoStore`
        - ``redis...`` → :class:`~tau_hub.db.redis.RedisStore`
        - ``postgres...`` → :class:`~tau_hub.db.postgres.PostgresStore`
    secret_key:
        Passphrase used to encrypt provider API keys at rest and decrypt them
        on read. Falls back to the ``TAU_HUB_SECRET_KEY`` environment
        variable. When omitted entirely, API keys are stored in plaintext (a
        warning is logged) and reading encrypted keys raises
        :class:`~tau_hub.crypto.MissingSecretKeyError`.
    store:
        A pre-built :class:`~tau_hub.db.base.BaseAgentStore` instance. Takes
        precedence over ``store_url``; use it for custom backends or custom
        backend options.

    read quickstart for seeing the examples
    """

    def __init__(
        self,
        store_url: str | None = None,
        *,
        secret_key: str | None = None,
    ) -> None:
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

        secret_key = secret_key or os.environ.get(SECRET_KEY_ENV_VAR)
        self._box: SecretBox | None = SecretBox(secret_key) if secret_key else None

    @property
    def store(self) -> BaseAgentStore:
        """The underlying document store (useful for custom collections)."""
        return self._store

    async def init_db(self) -> None:
        """Initialize the underlying database (create tables, connect pools).

        For schemaless backends this is a no-op; for SQL backends it creates
        the schema. Postgres also opens its connection pool here.
        """
        await self._store.init_db()

    async def close(self) -> None:
        """Release database connections held by the backend."""
        await self._store.close()

    def _protect(self, value: str) -> str:
        """Encrypt *value* for storage when a secret key is configured.

        Without a secret key the value is stored as-is and a warning is
        logged, preserving the old (insecure) behaviour for local use.
        """
        if not value:
            return value
        if self._box is None:
            logger.warning(
                "Storing an API key in PLAINTEXT because TauHub was created "
                "without a secret_key. Pass secret_key=... or set the %s "
                "environment variable to encrypt keys at rest.",
                SECRET_KEY_ENV_VAR,
            )
            return value
        return self._box.encrypt(value)

    def _reveal(self, value: str) -> str:
        """Decrypt *value* if it is encrypted; return plaintext untouched.

        Raises
        ------
        MissingSecretKeyError
            If the stored value is encrypted but this hub instance has no
            secret key.
        """
        if not is_encrypted(value):
            return value
        if self._box is None:
            raise MissingSecretKeyError(
                "This value was stored encrypted. Initialise TauHub with the "
                f"same secret_key used when it was stored (or set {SECRET_KEY_ENV_VAR})."
            )
        return self._box.decrypt(value)

    #####################################################################
    ##### Provider CRUD

    async def register_provider(
        self,
        name: str,
        provider_class: Literal["AnthropicProvider", "OpenAICompatibleProvider"],
        api_key: str,
        base_url: str | None,
        model_name: str | None,
        **extra: Any,
    ) -> str:
        """Store (or replace) a provider definition.

        The ``api_key`` is encrypted at rest when the hub has a secret key
        (see :class:`TauHub`); other fields are stored as-is.

        Parameters
        ----------
        name:
            Unique provider name (the lookup key).
        provider_class:
            Which tau_ai provider implementation to build on
            :meth:`get_provider`.
        api_key:
            The provider API key. Encrypted before storage when possible.
        base_url:
            Base URL for OpenAI-compatible endpoints (may be ``None``).
        model_name:
            Default model to use with this provider (may be ``None``).
        **extra:
            Additional fields stored verbatim on the document.

        Returns
        -------
        str
            The registered provider name.
        """
        try:
            await self._store.put(
                _PROVIDERS,
                name,
                {
                    "provider_class": provider_class,
                    "api_key": self._protect(api_key or ""),
                    "base_url": base_url or "",
                    "model_name": model_name or "",
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to register provider {name}: {e}") from e
        return name

    def _provider_from_doc(self, name: str, data: dict) -> tuple[ModelProvider, str]:
        """Build a live tau_ai provider from a stored provider document."""
        api_key = self._reveal(data.get("api_key", ""))
        match data.get("provider_class"):
            case "AnthropicProvider":
                from tau_ai.anthropic import AnthropicProvider
                from tau_ai.env import AnthropicConfig

                provider_config = AnthropicConfig(api_key=api_key)
                return (
                    AnthropicProvider(provider_config),
                    data.get("model_name", ""),
                )
            case "OpenAICompatibleProvider":
                from tau_ai import OpenAICompatibleConfig, OpenAICompatibleProvider

                config = OpenAICompatibleConfig(
                    api_key=api_key,
                    base_url=data.get("base_url", ""),
                )
                return (
                    OpenAICompatibleProvider(config=config),
                    data.get("model_name", ""),
                )
            case _:
                raise ValueError(f"Provider {name} has no provider_class defined.")

    async def get_provider(self, name: str) -> tuple[ModelProvider, str]:
        """Load a provider by name and return ``(provider, model_name)``.

        The stored API key is decrypted transparently.

        Raises
        ------
        ValueError
            If no provider with that name is registered.
        MissingSecretKeyError
            If the key is encrypted and the hub has no secret key.
        """
        data = await self._store.get(_PROVIDERS, name)
        if data is None:
            raise ValueError(f"Provider {name} is not registered!")
        return self._provider_from_doc(name, data)

    async def list_providers(self) -> dict[str, tuple[ModelProvider, str]]:
        """Return all registered providers as ``{name: (provider, model_name)}``."""
        providers = await self._store.batch_get(_PROVIDERS)
        result = {}
        for data in providers:
            name = data.get("name", "")
            if name:
                result[name] = self._provider_from_doc(name, data)
        return result

    async def delete_provider(self, name: str) -> None:
        """Delete a provider definition by name (no-op when missing)."""
        await self._store.delete(_PROVIDERS, name)

    #####################################################################
    ##### Agents CRUD

    async def register_agent(
        self,
        name: str,
        system: str,
        **extra: Any,
    ) -> str:
        """Persist (or replace) an agent definition.

        Note
        ----
        The relation between agents and tools/skills is not enforced here;
        configs (see :meth:`register_config`) reference agents, providers,
        tools, and skills by name, and it's up to the user to keep those
        names consistent.

        Parameters
        ----------
        name:
            Unique agent name (the lookup key).
        system:
            The agent's system prompt.
        **extra:
            Additional fields stored verbatim on the document.

        Returns
        -------
        str
            The registered agent name.
        """
        try:
            await self._store.put(
                _AGENTS,
                name,
                {
                    "system": system,
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to create agent {name}: {e}") from e
        return name

    async def get_agent(self, name: str) -> str:
        """Return the system prompt of the agent registered under *name*.

        Raises
        ------
        ValueError
            If no agent with that name is registered.
        """
        data = await self._store.get(_AGENTS, name)
        if data:
            return data.get("system", "")
        raise ValueError(f"Agent {name} had not been registered yet.")

    async def delete_agent(self, name: str) -> None:
        """Delete an agent definition by name (no-op when missing)."""
        await self._store.delete(_AGENTS, name)

    async def list_agents(self) -> dict[str, str]:
        """Return all registered agents as ``{name: system_prompt}``."""
        agents = await self._store.batch_get(_AGENTS)
        result = {}
        for agent in agents:
            name = agent.get("name", "")
            if name:
                result[name] = agent.get("system", "")
        return result

    #####################################################################
    #####  Tools CRUD

    async def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict | None,
        executor: Callable | None = None,
        **extra: Any,
    ) -> str:
        """Store (or replace) a tool definition.

        The executor callable is serialized with ``dill`` and base64-encoded
        so it can round-trip through any backend.

        Warning
        -------
        Deserializing an executor runs arbitrary code. Only share a hub
        database with services and people you trust.

        Parameters
        ----------
        name:
            Unique tool name (the lookup key).
        description:
            Human/model-readable description of what the tool does.
        input_schema:
            JSON schema of the tool's arguments.
        executor:
            The async callable that executes the tool.
        **extra:
            Additional fields stored verbatim on the document.

        Returns
        -------
        str
            The registered tool name.
        """
        import dill

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
            raise ValueError(f"Failed to register tool {name}: {e}") from e
        return name

    async def get_tool(self, name: str) -> AgentTool:
        """Load a tool by name and return a ready-to-use ``AgentTool``.

        Raises
        ------
        ValueError
            If no tool with that name is registered.
        """
        import dill
        from tau_agent import AgentTool

        data = await self._store.get(_TOOLS, name)
        if data:
            executor_b64 = data.get("executor")
            return AgentTool(
                name=name,
                description=data.get("description", ""),
                input_schema=json.loads(data.get("input_schema") or "null"),
                executor=(
                    dill.loads(base64.b64decode(executor_b64)) if executor_b64 else None
                ),  # ty:ignore[invalid-argument-type]
            )
        raise ValueError(f"Tool {name} had not been defined yet.")

    async def list_tools(self) -> dict[str, AgentTool]:
        """Return all registered tools as ``{name: AgentTool}``."""
        tools = await self._store.batch_get(_TOOLS)
        result = {}
        for tool in tools:
            name = tool.get("name", "")
            if name:
                result[name] = await self.get_tool(name)
        return result

    async def delete_tool(self, name: str) -> None:
        """Delete a tool definition by name (no-op when missing)."""
        await self._store.delete(_TOOLS, name)

    #####################################################################
    ##### Skills CRUD

    async def register_skill(
        self,
        name: str,
        description: str,
        content: str,
        config: dict | None = None,
        **extra: Any,
    ) -> str:
        """Store (or replace) a skill definition.

        Skills are reusable prompt extensions (mirroring Tau's user skills).
        Attach them to a config via ``skill_names`` and :meth:`get_config`
        appends each skill to the agent's system prompt.

        Parameters
        ----------
        name:
            Unique skill name (the lookup key).
        description:
            Short summary of what the skill does.
        content:
            The skill body — the instructions injected into the prompt.
        config:
            Optional structured configuration for the consuming application.
        **extra:
            Additional fields stored verbatim on the document.

        Returns
        -------
        str
            The registered skill name.
        """
        try:
            await self._store.put(
                _SKILLS,
                name,
                {
                    "description": description,
                    "content": content,
                    "config": config or {},
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to register skill {name}: {e}") from e
        return name

    async def get_skill(self, name: str) -> Skill:
        """Load a skill by name.

        Raises
        ------
        ValueError
            If no skill with that name is registered.
        """
        data = await self._store.get(_SKILLS, name)
        if not data:
            raise ValueError(f"Skill {name} had not been defined yet.")
        return Skill(
            name=name,
            description=data.get("description", ""),
            content=data.get("content", ""),
            config=data.get("config") or {},
        )

    async def list_skills(self) -> dict[str, Skill]:
        """Return all registered skills as ``{name: Skill}``."""
        skills = await self._store.batch_get(_SKILLS)
        result = {}
        for data in skills:
            name = data.get("name", "")
            if name:
                result[name] = Skill(
                    name=name,
                    description=data.get("description", ""),
                    content=data.get("content", ""),
                    config=data.get("config") or {},
                )
        return result

    async def delete_skill(self, name: str) -> None:
        """Delete a skill definition by name (no-op when missing)."""
        await self._store.delete(_SKILLS, name)

    #####################################################################
    ##### Config CRUD

    async def register_config(
        self,
        name: str,
        agent_name: str,
        provider_name: str,
        tool_names: list[str] | None = None,
        skill_names: list[str] | None = None,
        **extra: Any,
    ) -> str:
        """Store (or replace) a named harness configuration.

        A config bundles an agent, a provider, tools, and skills by name so
        that :meth:`get_config` can assemble a ready-to-run
        ``AgentHarnessConfig`` in one call.

        Parameters
        ----------
        name:
            Unique config name (the lookup key).
        agent_name:
            Name of a registered agent (supplies the system prompt).
        provider_name:
            Name of a registered provider.
        tool_names:
            Names of registered tools to attach.
        skill_names:
            Names of registered skills; their content is appended to the
            system prompt when the config is loaded.
        **extra:
            Additional fields stored verbatim on the document.

        Returns
        -------
        str
            The registered config name.
        """
        try:
            await self._store.put(
                _CONFIG,
                name,
                {
                    "agent_name": agent_name,
                    "provider_name": provider_name,
                    "tool_names": tool_names or [],
                    "skill_names": skill_names or [],
                    **extra,
                },
            )
        except Exception as e:
            raise ValueError(f"Failed to register config {name}: {e}") from e
        return name

    async def get_config(self, name: str) -> AgentHarnessConfig:
        """Assemble a ready-to-run ``AgentHarnessConfig`` from a stored config.

        Loads the referenced provider (decrypting its API key), agent, tools,
        and skills. Skill content is appended to the agent's system prompt as
        ``## Skill: <name>`` sections.

        Raises
        ------
        ValueError
            If the config — or anything it references — is missing.
        """
        from tau_agent import AgentHarnessConfig

        data = await self._store.get(_CONFIG, name)
        if not data:
            raise ValueError(f"Config {name} had not been defined yet.")
        provider, model_name = await self.get_provider(data.get("provider_name", ""))
        system = await self.get_agent(data.get("agent_name", ""))
        tools = []
        for tool_name in data.get("tool_names", []):
            tools.append(await self.get_tool(tool_name))
        skill_sections = []
        for skill_name in data.get("skill_names", []):
            skill = await self.get_skill(skill_name)
            skill_sections.append(skill.as_prompt_section())
        if skill_sections:
            system = "\n\n".join([system, *skill_sections])
        return AgentHarnessConfig(
            provider=provider,
            model=model_name,
            system=system,
            tools=tools,
        )

    async def list_configs(self) -> dict[str, AgentHarnessConfig]:
        """Return all registered configs as ``{name: AgentHarnessConfig}``."""
        configs = await self._store.batch_get(_CONFIG)
        result = {}
        for config in configs:
            name = config.get("name", "")
            if name:
                result[name] = await self.get_config(name)
        return result

    async def delete_config(self, name: str) -> None:
        """Delete a config by name (no-op when missing)."""
        await self._store.delete(_CONFIG, name)

    #####################################################################
    ##### Sessions

    def session_storage(self, session_id: str) -> HubSessionStorage:
        """Return a DB-backed session storage for *session_id*.

        The returned object implements the ``tau_agent.session.SessionStorage``
        protocol (``append`` / ``read_all``), so it can be used anywhere Tau
        accepts a session storage — as a drop-in replacement for the default
        ``JsonlSessionStorage``.

        Parameters
        ----------
        session_id:
            Unique identifier of the session; created lazily on first append.
        """
        return HubSessionStorage(self._store, session_id)

    async def list_sessions(self) -> dict[str, int]:
        """Return all stored sessions as ``{session_id: entry_count}``."""
        docs = await self._store.batch_get(SESSIONS_COLLECTION)
        result = {}
        for doc in docs:
            name = doc.get("name", "")
            if name:
                result[name] = len(doc.get("entries") or [])
        return result

    async def delete_session(self, session_id: str) -> None:
        """Delete a stored session by id (no-op when missing)."""
        await self._store.delete(SESSIONS_COLLECTION, session_id)

    async def import_session_jsonl(self, session_id: str, path: str | Path) -> int:
        """Import a Tau JSONL session file (e.g. from ``~/.tau/sessions/``).

        Replaces any existing session stored under *session_id*.

        Returns
        -------
        int
            The number of imported entries.
        """
        return await import_session_jsonl(self._store, session_id, path)

    async def export_session_jsonl(self, session_id: str, path: str | Path) -> int:
        """Export a stored session to a Tau-compatible JSONL file.

        Returns
        -------
        int
            The number of exported entries.
        """
        return await export_session_jsonl(self._store, session_id, path)
