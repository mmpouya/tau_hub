import sqlite3

from tau_hub.db.base import BaseAgentStore

# these are tables names in the underlying AgentStore
_CONFIG = "config"
_PROVIDERS = "providers"
_AGENTS = "agents"
_TOOLS = "tools"
_SKILLS = "skills"


class SQLiteStore(BaseAgentStore):
    def __init__(self, db_path: str):
        self.db_path = db_path
        # Initialize SQLite connection here

        self.conn = sqlite3.connect(self.db_path)

    def init_db(self):
        # Create the necessary tables in SQLite
        cursor = self.conn.cursor()
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_CONFIG} (name TEXT PRIMARY KEY, value TEXT)"
        )
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_PROVIDERS} (name TEXT PRIMARY KEY, provider_class TEXT, api_key TEXT, base_url TEXT, model_name TEXT)"
        )
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_AGENTS} (name TEXT PRIMARY KEY, system TEXT)"
        )
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_TOOLS} (name TEXT PRIMARY KEY, description TEXT)"
        )
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {_SKILLS} (name TEXT PRIMARY KEY, description TEXT)"
        )
        self.conn.commit()

    async def get(self, collection: str, name: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {collection} WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return dict(zip([column[0] for column in cursor.description], row))
        return None

    async def put(self, collection: str, name: str, data: dict, **extra) -> None:
        cursor = self.conn.cursor()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = list(data.values())
        cursor.execute(
            f"INSERT OR REPLACE INTO {collection} (name, {columns}) VALUES (?, {placeholders})",
            [name] + values,
        )
        self.conn.commit()

    async def delete(self, collection: str, name: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(f"DELETE FROM {collection} WHERE name = ?", (name,))
        self.conn.commit()

    async def batch_get(self, collection: str) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {collection}")
        rows = cursor.fetchall()
        return [
            dict(zip([column[0] for column in cursor.description], row)) for row in rows
        ]
