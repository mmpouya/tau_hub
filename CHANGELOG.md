# Changelog

## 0.2.0 — 2026-07-11

### Added
- **Encrypted API keys at rest.** `TauHub(secret_key=...)` (or the
  `TAU_HUB_SECRET_KEY` environment variable) enables transparent Fernet
  encryption of provider API keys in `register_provider` and decryption in
  `get_provider` / `get_config`. New `tau_hub.crypto` module with `SecretBox`,
  `is_encrypted`, `SecretBox.generate_key()`, and dedicated error types
  (`MissingSecretKeyError`, `DecryptionError`). Legacy plaintext values stay
  readable.
- **DB-backed chat sessions.** New `tau_hub.sessions` module with
  `HubSessionStorage`, a drop-in implementation of `tau_agent`'s
  `SessionStorage` protocol (`append` / `read_all`) storing sessions in any
  hub backend instead of local JSONL files. New `TauHub` methods:
  `session_storage`, `list_sessions`, `delete_session`,
  `import_session_jsonl`, `export_session_jsonl`.
- **Skills management.** New skills CRUD (`register_skill`, `get_skill`,
  `list_skills`, `delete_skill`) and a typed `Skill` dataclass with
  `as_prompt_section()`. `register_config`/`get_config` accept `skill_names`
  and append skill content to the assembled system prompt.
- `BaseAgentStore.append_to_list` (atomic on MongoDB via `$push` and
  PostgreSQL via `jsonb` concatenation), `BaseAgentStore.close`, and a
  default no-op `init_db`.
- `TauHub(store=...)` to inject a pre-built/custom store instance.
- `TauHub.close()` and `TauHub.store` property.

### Fixed
- SQLite backend rewritten as a generic async `documents` table (previous
  version used per-entity fixed schemas that dropped fields, mixed sync/async,
  and broke on extra columns). Accepts `sqlite:` URLs and plain paths.
- `PostgresStore.init_db` crashed when called before `connect()`; it now
  connects on demand.
- `RedisStore` failed to instantiate because abstract `init_db` was missing.
- `get_tool` no longer crashes on tools registered without an executor.
- `list_agents` no longer performs one extra store round-trip per agent.

### Changed
- `cryptography` added as a core dependency; `requires-python` relaxed to
  `>=3.12` to match tau.
- Docstrings on every public class and method; expanded README.

## 0.1.3

- Initial public version: providers, agents, tools, configs on
  TinyDB/SQLite/MongoDB/Redis/PostgreSQL.
