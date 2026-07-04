# tau_hub

A cross-service integration layer for [`tau_agent`](https://github.com/huggingface/tau) — the portable harness layer of the [tau](https://github.com/huggingface/tau) coding agent.

`tau_hub` adds persistence and a shared registry so multiple services can
create, load, and share agents, tools, and skills from a central database —
without duplicating configuration or bootstrapping logic.

---

## Why

`tau_agent` is intentionally stateless and portable — it has no file I/O,
no CLI, and no resource-loading. `tau_hub` fills that gap for
multi-service environments: it owns the database layer and exposes a clean
API for agent lifecycle management.

---

## Features

Overall, this package provides a CRUD for using agents, skills, and tools.

- `create_agent(...)` — define and persist a new agent with its tools and skills
- `get_agent(name)` — load a fully configured `tau_agent` harness from the database
- `register_tool(...)` — store a tool definition (name, description, schema)
- `get_skill(name)` — retrieve a skill prompt/config by name
- Backend-agnostic: designed for PostgreSQL (+ Redis cache), swappable

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌───────────────┐
│  Service A  │     │  Service B  │     │   Service C   │
└──────┬──────┘     └──────┬──────┘     └────────┬──────┘
       │                   │                     │
       └───────────────────┼─────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   tau_hub   │  ← this package
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐         ┌────────▼────────────┐
       │  Database   │         │  (cache layer)      │ 
       │ (agents,    │         │  not implemented yet│
       │  tools,     │         └─────────────────────┘
       │  skills)    │
       └─────────────┘
```

---

## Installation

```bash
pip install tau-hub
```

Or from source:

```bash
git clone https://github.com/mmpouya/tau_hub
cd tau_hub
pip install -e .
```

---

## Quick Start

```python
from tau_hub import TauRegistry
from tau_ai.anthropic import AnthropicProvider
from tau_ai.env import AnthropicConfig
from tau_agent.harness import AgentHarness, AgentHarnessConfig

registry = TauRegistry(db_url=os.getenv("TAUHUB_URL"))
# get provider or agent
provider = registry.get_provider("gemma-4")
harness_config = AgentHarnessConfig(
        provider=provider,
        model=provider.model,
        system=registry.get_agent("personal_query_agent"),
        tools=[registry.get_tool(name=get_weather)]
    )
# Initialize the Harness
harness = AgentHarness(harness_config)

# Prompt the agent and react to events
print("User: Hello, who are you?")
async for event in harness.prompt("Hello, who are you?"):
       ...

# Clean up provider resources
await provider.aclose()

```

---


## License

MIT