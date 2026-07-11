"""Database backends for tau_hub.

All backends implement :class:`tau_hub.db.base.BaseAgentStore`. Import the
concrete backend you need directly, e.g.::

    from tau_hub.db.sqlite import SQLiteStore
    from tau_hub.db.mongo import MongoStore

Only :mod:`tau_hub.db.base` is imported eagerly so that optional backend
dependencies (pymongo, redis, asyncpg) stay optional.
"""

from tau_hub.db.base import BaseAgentStore

__all__ = ["BaseAgentStore"]
