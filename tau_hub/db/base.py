"""Abstract storage interface shared by all tau_hub backends.

Every backend stores flat, independent documents addressed by
``(collection, name)``. The public :class:`~tau_hub.TauHub` API only ever
talks to this interface, never to a concrete backend, so backends are fully
interchangeable.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

_FILTER_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class BaseAgentStore(ABC):
    """Abstract key/document store used by :class:`~tau_hub.TauHub`.

    Subclass this to add a new database backend. Only four methods are
    required (:meth:`get`, :meth:`put`, :meth:`delete`, :meth:`batch_get`);
    the rest have sensible default implementations.
    """

    @abstractmethod
    async def get(self, collection: str, name: str, **filters) -> dict | None:
        """Return the document stored under ``(collection, name)``.
        Returns ``None`` when no such document exists or when the document
        does not match all supplied ``**filters``. The returned dict includes
        the ``name`` key.
        """

    @abstractmethod
    async def put(self, collection: str, name: str, data: dict, **extra: Any) -> None:
        """Insert or fully replace the document under ``(collection, name)``.
        ``data`` (merged with ``extra``) becomes the new document body; the
        backend adds/keeps the ``name`` field automatically.
        """

    @abstractmethod
    async def delete(self, collection: str, name: str) -> None:
        """Delete the document under ``(collection, name)``. Missing documents are a no-op."""

    @abstractmethod
    async def batch_get(self, collection: str, **filters) -> list[dict]:
        """Return every document in *collection* that matches all supplied
        ``**filters``. When no filters are given, returns every document
        in the collection (order unspecified).
        """

    @staticmethod
    def _check_filters(doc: dict | None, **filters) -> dict | None:
        """Return *doc* when it matches all ``**filters``, or ``None``."""
        if doc is None:
            return None
        if filters and not all(doc.get(k) == v for k, v in filters.items()):
            return None
        return doc

    @staticmethod
    def _filter_docs(docs: list[dict], **filters) -> list[dict]:
        """Return only those documents in *docs* that match all ``**filters``."""
        if not filters:
            return docs
        return [d for d in docs if all(d.get(k) == v for k, v in filters.items())]

    @staticmethod
    def _validate_filter_keys(**filters) -> None:
        """Raise ``ValueError`` if any filter key contains unsafe characters."""
        for key in filters:
            if not _FILTER_KEY_RE.match(key):
                raise ValueError(
                    f"Filter key {key!r} contains unsafe characters. "
                    "Only alphanumeric and underscore are allowed."
                )

    async def init_db(self) -> None:
        """Create tables/collections/indexes if the backend needs them.
        Default is a no-op; schemaless backends don't need to override it.
        """

    async def close(self) -> None:
        """Release connections/pools held by the backend. Default is a no-op."""

    async def append_to_list(
        self, collection: str, name: str, field: str, item: Any
    ) -> None:
        """Append *item* to the list stored under ``doc[field]``, creating the
        document if it does not exist yet.

        The default implementation is a read-modify-write over :meth:`get` /
        :meth:`put`, which is correct for single-writer deployments. Backends
        with native atomic list operations (MongoDB ``$push``, PostgreSQL
        ``jsonb`` concatenation) override this for concurrency safety and
        performance.
        """
        doc = await self.get(collection, name) or {}
        doc.pop("name", None)
        items = list(doc.get(field) or [])
        items.append(item)
        doc[field] = items
        await self.put(collection, name, doc)
