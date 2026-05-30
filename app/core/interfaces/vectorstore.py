# tech_interview_agent/app/core/interfaces/vectorstore.py
from typing import Any, Protocol


class VectorStoreGateway(Protocol):
    """Абстракция над векторным хранилищем (Qdrant, Pinecone, Chroma …)."""

    async def ensure_collection(self) -> None: ...

    async def upsert(
        self,
        vectors: list[tuple[str, list[float]]],
        payloads: list[dict],
        **kwargs: Any,
    ) -> None: ...

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict]: ...

    async def ping(self) -> bool: ...
