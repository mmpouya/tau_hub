from abc import ABC, abstractmethod


class BaseAgentStore(ABC):
    def __init__(self) -> None:
        pass

    @abstractmethod
    async def get(self, collection: str, name: str) -> dict | None: ...
    @abstractmethod
    async def put(self, collection: str, name: str, data: dict, **extra) -> None: ...
    @abstractmethod
    async def delete(self, collection: str, name: str) -> None: ...
    @abstractmethod
    async def batch_get(self, collection: str) -> list[dict]: ...
    @abstractmethod
    async def init_db(self) -> None: ...
