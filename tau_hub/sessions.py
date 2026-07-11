"""Database-backed chat-session storage for ``tau_agent``.

Tau keeps durable, append-only session history. By default the ``tau_coding``
layer persists it as JSONL files under ``~/.tau/sessions/`` via
``tau_agent.session.JsonlSessionStorage``. In multi-service deployments you
often want those sessions in a real database instead — shared, queryable, and
backed up together with the rest of your hub data.

:class:`HubSessionStorage` implements the same protocol as
``tau_agent.session.SessionStorage`` (``append`` / ``read_all``), so it is a
drop-in replacement anywhere Tau accepts a session storage::

    from tau_hub import TauHub

    hub = TauHub("postgres://user:pass@localhost/tau")
    storage = hub.session_storage("my-session-id")

    await storage.append(entry)      # instead of writing a JSONL line
    entries = await storage.read_all()

Each session is stored as one document in the ``sessions`` collection:
``{"name": <session_id>, "entries": [<entry dict>, ...]}``. Entry dicts use
exactly the same JSON shape as Tau's JSONL lines, which is what makes
:meth:`TauHub.import_session_jsonl` / :meth:`TauHub.export_session_jsonl`
lossless.

When ``tau_agent`` is installed, :meth:`HubSessionStorage.read_all` returns
fully validated ``SessionEntry`` models; without it, raw dicts are returned
(useful for inspection tools that only need the JSON).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tau_hub.db.base import BaseAgentStore

#: Name of the store collection that holds chat sessions.
SESSIONS_COLLECTION = "sessions"

_ENTRY_ADAPTER: Any | None = None
_ADAPTER_CHECKED = False


def _entry_adapter() -> Any | None:
    """Return a cached pydantic ``TypeAdapter`` for ``SessionEntry``.

    Returns ``None`` when ``tau_agent`` is not installed, in which case
    entries are handled as plain dicts.
    """
    global _ENTRY_ADAPTER, _ADAPTER_CHECKED
    if not _ADAPTER_CHECKED:
        _ADAPTER_CHECKED = True
        try:
            from pydantic import TypeAdapter
            from tau_agent.session.entries import SessionEntry

            _ENTRY_ADAPTER = TypeAdapter(SessionEntry)
        except ImportError:
            _ENTRY_ADAPTER = None
    return _ENTRY_ADAPTER


def entry_to_dict(entry: Any) -> dict:
    """Convert a session entry (pydantic model or dict) to a JSON-safe dict.

    The produced dict matches the JSON of one line in Tau's JSONL session
    files exactly.

    Raises
    ------
    TypeError
        If *entry* is neither a dict nor a pydantic model.
    """
    if isinstance(entry, dict):
        return entry
    if hasattr(entry, "model_dump"):
        return entry.model_dump(mode="json")
    raise TypeError(
        f"Unsupported session entry type: {type(entry)!r}. "
        "Expected a tau_agent SessionEntry model or a dict."
    )


def entry_from_dict(data: dict) -> Any:
    """Convert a stored dict back into a typed ``SessionEntry``.

    Falls back to returning the dict unchanged when ``tau_agent`` is not
    installed.
    """
    adapter = _entry_adapter()
    if adapter is None:
        return data
    return adapter.validate_python(data)


class HubSessionStorage:
    """Append-only session storage backed by a tau_hub store.

    Implements the ``tau_agent.session.SessionStorage`` protocol
    (``append`` / ``read_all``), so it can be used anywhere Tau expects a
    session storage — replacing the default ``JsonlSessionStorage``.

    Parameters
    ----------
    store:
        Any :class:`~tau_hub.db.base.BaseAgentStore` implementation.
    session_id:
        Unique identifier of the session (used as the document name).
    collection:
        Store collection to keep sessions in. Defaults to ``"sessions"``.
    """

    def __init__(
        self,
        store: BaseAgentStore,
        session_id: str,
        collection: str = SESSIONS_COLLECTION,
    ) -> None:
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._store = store
        self._session_id = session_id
        self._collection = collection

    @property
    def session_id(self) -> str:
        return self._session_id

    async def append(self, entry: Any) -> None:
        """Append one session entry to the session document.

        Accepts either a ``tau_agent`` ``SessionEntry`` model or an
        already-serialized entry dict.
        """
        await self._store.append_to_list(
            self._collection, self._session_id, "entries", entry_to_dict(entry)
        )

    async def read_all(self) -> list[Any]:
        """Read all entries of the session in append order.

        Missing sessions are treated as empty (mirroring the behaviour of
        ``JsonlSessionStorage`` for missing files).
        """
        doc = await self._store.get(self._collection, self._session_id)
        if not doc:
            return []
        return [entry_from_dict(e) for e in doc.get("entries") or []]


async def import_session_jsonl(
    store: BaseAgentStore,
    session_id: str,
    path: str | Path,
    collection: str = SESSIONS_COLLECTION,
) -> int:
    """Import a Tau JSONL session file into the store (full replace).

    Parameters
    ----------
    store:
        Target store.
    session_id:
        Name to store the session under.
    path:
        Path to a JSONL file as written by Tau (e.g. under ``~/.tau/sessions``).
    collection:
        Store collection to import into.

    Returns
    -------
    int
        The number of imported entries.
    """
    path = Path(path)
    entries: list[dict] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL on line {index} of {path}: {exc}") from exc
    await store.put(collection, session_id, {"entries": entries})
    return len(entries)


async def export_session_jsonl(
    store: BaseAgentStore,
    session_id: str,
    path: str | Path,
    collection: str = SESSIONS_COLLECTION,
) -> int:
    """Export a stored session back to a Tau-compatible JSONL file.

    Parameters
    ----------
    store:
        Source store.
    session_id:
        Name of the stored session.
    path:
        Destination file path. Parent directories are created as needed.
    collection:
        Store collection to read from.

    Returns
    -------
    int
        The number of exported entries.

    Raises
    ------
    ValueError
        If the session does not exist.
    """
    doc = await store.get(collection, session_id)
    if doc is None:
        raise ValueError(f"Session {session_id!r} does not exist.")
    entries = doc.get("entries") or []
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(entries)
