"""End-to-end tau_hub example: registry + encrypted keys + skills + sessions.

Run with tau installed:  python examples/quickstart.py
"""

import asyncio

from tau_hub import TauHub


async def main() -> None:
    # SQLite keeps this example self-contained; any backend URL works.
    # The secret key encrypts provider API keys at rest — every service
    # sharing this database must use the same key.
    hub = TauHub("sqlite:./quickstart.sqlite3", secret_key="change-me")
    await hub.init_db()

    # --- Providers (API key is encrypted before it touches the DB) --------
    await hub.register_provider(
        name="local-llm",
        provider_class="OpenAICompatibleProvider",
        api_key="sk-demo-key",
        base_url="http://localhost:8000/v1",
        model_name="qwen-3",
    )

    # --- Agents, skills, configs ------------------------------------------
    await hub.register_agent(
        "weather_agent", system="You are a helpful weather assistant."
    )
    await hub.register_skill(
        "metric_units",
        description="Prefer the metric system.",
        content="Always report temperatures in Celsius and distances in km.",
    )
    await hub.register_config(
        "weather",
        agent_name="weather_agent",
        provider_name="local-llm",
        tool_names=[],
        skill_names=["metric_units"],
    )

    # --- Assemble a ready-to-run harness config ---------------------------
    config = await hub.get_config("weather")  # needs tau-ai installed
    print("System prompt:\n", config.system)

    # --- DB-backed session storage (instead of ~/.tau/sessions/*.jsonl) ---
    storage = hub.session_storage("demo-session")
    # Pass `storage` anywhere tau accepts a SessionStorage. For the demo we
    # just append a raw entry dict and read it back:
    await storage.append(
        {
            "id": "e1",
            "parent_id": None,
            "timestamp": 0.0,
            "type": "label",
            "label": "demo session",
        }
    )
    print("Sessions:", await hub.list_sessions())

    await hub.close()


if __name__ == "__main__":
    asyncio.run(main())
