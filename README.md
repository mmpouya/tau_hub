# tau_hub

A cross-service persistence and registry layer for [`tau_agent`](https://github.com/huggingface/tau) — the portable harness layer of the [tau](https://github.com/huggingface/tau) coding agent.

`tau_hub` adds a shared database layer so multiple services can create, load, and share **providers, agents, tools, skills, configs, and chat sessions** — without duplicating configuration or bootstrapping logic across processes. Provider API keys are **encrypted at rest**.

---

## Why

`tau_agent` is intentionally stateless and portable — it has no file I/O, no CLI, and no resource-loading. `tau_hub` fills that gap for multi-service environments: it owns the storage layer and exposes a clean API for agent lifecycle management.

---

## Features

- **Providers** — `register_provider(...)` / `get_provider(name)` with API keys **encrypted at rest** (Fernet, AES-128-CBC + HMAC-SHA256)
- **Agents** — `register_agent(...)` / `get_agent(name)` for shared system prompts
- **Tools** — `register_tool(...)` / `get_tool(name)`; executors round-trip through the DB via `dill`
- **Skills** — `register_skill(...)` / `get_skill(name)`; reusable prompt extensions attachable to configs
- **Configs** — `register_config(...)` / `get_config(name)` assembles a ready-to-run `AgentHarnessConfig` (provider + agent + tools + skills)
- **Sessions** — `hub.session_storage(session_id)` is a drop-in replacement for Tau's `JsonlSessionStorage`, storing durable chat history in **any hub backend** instead of local JSONL files, plus JSONL import/export for migration
- **Backend-agnostic** — pluggable `BaseAgentStore` interface; ships with TinyDB (default), SQLite, MongoDB, Redis, and PostgreSQL
- **Zero-configuration quick-start** — the TinyDB backend requires no external services

---

## Installation

```bash
# Default install — TinyDB backend (pure Python, no external services)
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

Core dependencies (installed automatically): `tinydb`, `tau-ai`, `dill`, `cryptography`.

---

## Quick Start

```python
import asyncio
from tau_hub import TauHub
from tau_agent.harness import AgentHarness

async def main():
    # TinyDB backend by default (./.tau_hub/tau_hub.json).
    # The secret key enables encryption of provider API keys at rest.
    hub = TauHub(secret_key="my-shared-secret")
    await hub.init_db()

    # Register once (e.g. from an admin service)...
    await hub.register_provider(
        name="claude",
        provider_class="AnthropicProvider",
        api_key="sk-ant-...",           # stored encrypted, never in plaintext
        base_url=None,
        model_name="claude-sonnet-4-5",
    )
    await hub.register_agent("assistant", system="You are a helpful assistant.")
    await hub.register_skill(
        "metric_units",
        description="Prefer the metric system.",
        content="Always answer using metric units.",
    )
    await hub.register_config(
        "assistant_config",
        agent_name="assistant",
        provider_name="claude",
        tool_names=[],
        skill_names=["metric_units"],
    )

    # ...and load a ready-to-run harness anywhere else.
    config = await hub.get_config("assistant_config")
    harness = AgentHarness(config)

    async for event in harness.prompt("Hello, who are you?"):
        print(event)

asyncio.run(main())
```

### Encrypted API keys

Pass a `secret_key` when constructing `TauHub` (or set the `TAU_HUB_SECRET_KEY` environment variable). Every service that shares the hub database must use the **same** secret key.

```python
from tau_hub import TauHub, SecretBox

# Generate a strong key once and keep it in your secrets manager:
print(SecretBox.generate_key())      # e.g. 'qERt3...44 chars...='

hub = TauHub("postgres://user:pass@localhost/tau", secret_key="<that key>")
```

- `register_provider(...)` encrypts `api_key` before it is written; the DB only ever sees `enc::v1::<token>`.
- `get_provider(name)` / `get_config(name)` decrypt transparently.
- Reading an encrypted key **without** a secret key raises `MissingSecretKeyError`; a **wrong** key raises `DecryptionError`.
- Plaintext keys written by older tau_hub versions remain readable, so you can migrate gradually (re-register providers to encrypt them).
- If no secret key is configured, keys are stored in plaintext and a warning is logged (legacy behaviour).

Keys are derived from the passphrase with PBKDF2-HMAC-SHA256 (600k iterations); a raw 44-char Fernet key is used directly.

### DB-backed chat sessions

Tau's `tau_coding` layer stores sessions as JSONL files under `~/.tau/sessions/`. With `tau_hub` you can keep them in the hub database instead — shared across services and backed up together with everything else:

```python
hub = TauHub("mongodb://localhost:27017")

# Drop-in replacement for tau_agent's JsonlSessionStorage —
# implements the same SessionStorage protocol (append / read_all):
storage = hub.session_storage("session-2026-07-11")

await storage.append(entry)          # SessionEntry models or dicts
entries = await storage.read_all()   # typed SessionEntry models

# Housekeeping
await hub.list_sessions()            # {session_id: entry_count}
await hub.delete_session("session-2026-07-11")

# Migrate existing JSONL sessions into the DB (and back out)
await hub.import_session_jsonl("old-session", "~/.tau/sessions/abc.jsonl")
await hub.export_session_jsonl("old-session", "/tmp/abc.jsonl")
```

Entries are stored with exactly the same JSON shape as Tau's JSONL lines, so import/export is lossless. On MongoDB and PostgreSQL, appends are atomic (`$push` / `jsonb` concatenation), making concurrent writers safe.

### Skills

Skills are reusable prompt extensions, mirroring Tau's user skills:

```python
await hub.register_skill(
    "code_review",
    description="Reviews code rigorously.",
    content="When reviewing code, check for correctness, security, and style.",
    config={"severity": "strict"},
)

skill = await hub.get_skill("code_review")     # -> Skill dataclass
print(skill.as_prompt_section())               # '## Skill: code_review\n...'

await hub.list_skills()                        # {name: Skill}
await hub.delete_skill("code_review")
```

Attach skills to a config via `skill_names=[...]`; `get_config` appends each skill to the agent's system prompt as a `## Skill: <name>` section.

### Using a different backend

Pick a backend with a URL...

```python
TauHub()                                            # TinyDB (default)
TauHub("sqlite:./tau_hub.sqlite3")                  # SQLite
TauHub("mongodb://localhost:27017")                 # MongoDB
TauHub("redis://localhost:6379")                    # Redis
TauHub("postgres://user:pass@localhost/tau")        # PostgreSQL
```

...or pass a pre-built store for full control:

```python
from tau_hub import TauHub
from tau_hub.db.mongo import MongoStore

hub = TauHub(store=MongoStore(uri="mongodb://localhost:27017", db="tau"))
```

Call `await hub.init_db()` once at startup (creates tables / connects pools where needed) and `await hub.close()` on shutdown.

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
         ┌──────────┬──────┴─────┬────────────┐
         │          │            │            │
   ┌─────▼───┐ ┌────▼────┐ ┌─────▼───┐ ┌──────▼────┐
   │ TinyDB  │ │ SQLite  │ │ MongoDB │ │ Postgres  │  ...
   │(default)│ │         │ │         │ │  / Redis  │
   └─────────┘ └─────────┘ └─────────┘ └───────────┘
```

`tau_hub` depends on an abstract `BaseAgentStore` interface. The public API (`register_provider`, `get_config`, `session_storage`, etc.) calls only this interface — never a concrete backend directly. You swap backends by passing a different `store_url`/`store=` at construction time.

### Collections

All entities are stored as **flat, independent documents** — no relational joins needed:

| Collection  | Key    | Value                                                          |
|-------------|--------|----------------------------------------------------------------|
| `providers` | `name` | `{provider_class, api_key (encrypted), base_url, model_name}`  |
| `agents`    | `name` | `{system}`                                                     |
| `tools`     | `name` | `{description, input_schema, executor (dill+base64)}`          |
| `skills`    | `name` | `{description, content, config}`                               |
| `config`    | `name` | `{agent_name, provider_name, tool_names, skill_names}`         |
| `sessions`  | `name` | `{entries: [<tau session entry>, ...]}`                        |

---

## Backends

### TinyDB *(default)*

Pure-Python JSON document store. No external service required. Best for single-process or single-writer deployments.

> ⚠️ TinyDB is **not ACID-compliant** and does not handle concurrent writes safely across multiple processes. If you run multiple workers writing to the same database simultaneously, use the SQLite or Postgres backend instead.

```python
from tau_hub.db.tinydb import TinyDBStore
store = TinyDBStore(path="tau_hub.json")
```

### SQLite

Standard-library backend using a single generic `documents` table with WAL journaling. ACID, no external service, good for local multi-writer setups.

```python
from tau_hub.db.sqlite import SQLiteStore
store = SQLiteStore("sqlite:./tau_hub.sqlite3")   # or a plain path / ":memory:"
```

### MongoDB *(requires `tau-hub[mongo]`)*

```python
from tau_hub.db.mongo import MongoStore
store = MongoStore(uri="mongodb://localhost:27017", db="tau")
```

Session appends use atomic `$push` — safe for concurrent writers.

### Redis *(requires `tau-hub[redis]`)*

Stores documents as JSON strings under `prefix:collection:name` keys. Suitable when Redis is already in your stack and you want sub-millisecond reads.

```python
from tau_hub.db.redis import RedisStore
store = RedisStore(url="redis://localhost:6379", prefix="tau")
```

### PostgreSQL *(requires `tau-hub[postgres]`)*

Uses a single `documents` table with `(collection, name, data jsonb)`. Good for multi-process concurrent writes; session appends are atomic `jsonb` concatenations.

```python
from tau_hub.db.postgres import PostgresStore
store = PostgresStore(dsn="postgresql://user:pass@localhost/tau")
```

---

## Implementing a Custom Backend

Subclass `BaseAgentStore` from `tau_hub.db.base`:

```python
from tau_hub.db.base import BaseAgentStore

class MyStore(BaseAgentStore):
    async def get(self, collection: str, name: str) -> dict | None: ...
    async def put(self, collection: str, name: str, data: dict, **extra) -> None: ...
    async def delete(self, collection: str, name: str) -> None: ...
    async def batch_get(self, collection: str) -> list[dict]: ...

    # Optional overrides (have working defaults):
    # async def init_db(self) -> None: ...
    # async def close(self) -> None: ...
    # async def append_to_list(self, collection, name, field, item) -> None: ...
```

Override `append_to_list` with your database's native atomic list-append if it has one — sessions use it on every appended entry.

---

## Security notes

- **API keys** are encrypted with authenticated symmetric encryption (Fernet). The secret key itself is never stored; keep it in a secrets manager or environment variable, not in code.
- **Tool executors** are serialized with `dill`; loading a tool executes arbitrary code on deserialization. Only share a hub database with services and people you trust.

---

## Running the tests

The test suite uses only the standard library plus `cryptography`, so it runs without any database services:

```bash
python -m unittest discover -s tests -v
```

---

## License

MIT
