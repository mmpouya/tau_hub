# tau_hub

A cross-service persistence and registry layer for [`tau_agent`](https://github.com/huggingface/tau) — the portable harness layer of the [tau](https://github.com/huggingface/tau) coding agent.

`tau_hub` adds a shared database layer so multiple services can create, load, and share agents, tools, and skills — without duplicating configuration or bootstrapping logic across processes.

---

## Why

`tau_agent` is intentionally stateless and portable — it has no file I/O, no CLI, and no resource-loading. `tau_hub` fills that gap for multi-service environments: it owns the storage layer and exposes a clean API for agent lifecycle management.

---

## Features

- `create_agent(...)` — define and persist a new agent with its tools and skills
- `get_agent(name)` — load a fully configured `tau_agent` harness from the database
- `register_tool(...)` — store a tool definition (name, description, schema)
- `get_skill(name)` — retrieve a skill prompt/config by name
- **Backend-agnostic** — pluggable `AgentStore` interface; ships with TinyDB by default
- **Zero-dependency quick-start** — TinyDB backend requires no external services

---

## Installation

```bash
# Default install — TinyDB backend (pure Python, zero external dependencies)
pip install tau-hub

# With MongoDB support
pip install tau-hub[mongo]

# With Redis support
pip install tau-hub[redis]

# With PostgreSQL support
pip install tau-hub[postgres]

# Everything
pip install tau-hub[all]
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
import asyncio
from tau_hub import TauRegistry

async def main():
    # Default: TinyDB backend, stores data in tau_hub.json
    registry = TauRegistry()

    # Persist an agent definition
    await registry.create_agent(
        name="weather_agent",
        system="You are a helpful weather assistant.",
        tools=["get_weather"],
        skills=["metric_units"],
    )

    # Load it back
    agent_data = await registry.get_agent("weather_agent")
    print(agent_data)

asyncio.run(main())
```

### Using a different backend

```python
from tau_hub import TauRegistry
from tau_hub.db.mongo import MongoStore

registry = TauRegistry(store=MongoStore(uri="mongodb://localhost:27017", db="tau"))
```

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
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──┐  ┌──────▼──┐  ┌─────▼─────┐
       │ TinyDB  │  │ MongoDB │  │ Postgres  │  ...
       │(default)│  │         │  │  / Redis  │
       └─────────┘  └─────────┘  └───────────┘
```

`tau_hub` depends on an abstract `AgentStore` interface. The public API (`create_agent`, `get_agent`, etc.) calls only this interface — never a concrete backend directly. You swap backends by passing a different `store=` at construction time.

### Collections

All entities are stored as **flat, independent documents** — no relational joins needed:

| Collection  | Key    | Value                                     |
|-------------|--------|-------------------------------------------|
| `agents`    | `name` | `{system, tools: [...], skills: [...]}`   |
| `tools`     | `name` | `{description, schema}`                   |
| `skills`    | `name` | `{prompt, config}`                        |

---

## Backends

### TinyDB *(default)*

Pure-Python JSON document store. No external service required. Best for single-process or single-writer deployments.

> ⚠️ TinyDB is **not ACID-compliant** and does not handle concurrent writes safely across multiple processes. If you run multiple workers writing to the same database simultaneously, use the SQLite or Postgres backend instead.

```python
from tau_hub.db.tinydb import TinyDBStore
store = TinyDBStore(path="tau_hub.json")
```

### MongoDB *(requires `tau-hub[mongo]`)*

```python
from tau_hub.db.mongo import MongoStore
store = MongoStore(uri="mongodb://localhost:27017", db="tau")
```

### Redis *(requires `tau-hub[redis]`)*

Stores documents as JSON-serialized hash fields. Suitable when Redis is already in your stack and you want sub-millisecond reads.

```python
from tau_hub.db.redis import RedisStore
store = RedisStore(url="redis://localhost:6379", prefix="tau")
```

### PostgreSQL *(requires `tau-hub[postgres]`)*

Uses a single `documents` table with `(collection, name, data jsonb)`. Good for multi-process concurrent writes.

```python
from tau_hub.db.postgres import PostgresStore
store = PostgresStore(dsn="postgresql://user:pass@localhost/tau")
```

---

## Implementing a Custom Backend

Subclass `AgentStore` from `tau_hub.db.base`:

```python
from tau_hub.db.base import AgentStore

class MyStore(AgentStore):
    async def get(self, collection: str, name: str) -> dict | None: ...
    async def put(self, collection: str, name: str, data: dict) -> None: ...
    async def delete(self, collection: str, name: str) -> None: ...
    async def batch_get(self, collection: str) -> list[dict]: ...
```

---

## License

MIT
