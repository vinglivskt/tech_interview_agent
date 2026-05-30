# tech_interview_agent/app/features/chat/infrastructure/qdrant.py
"""
Инфраструктурная реализация VectorStoreGateway для Qdrant.
Обеспечивает хранение и поиск векторов для RAG через Qdrant.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Condition,
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import Settings
from app.core.interfaces.vectorstore import VectorStoreGateway

logger = logging.getLogger(__name__)

# Фиксированный UUID-неймспейс для uuid5 — стабильные id фрагментов между переиндексациями
_CHUNK_ID_NS = uuid.UUID("a1b2c3d4-e5f6-4789-a012-3456789abcde")


def point_id_for_chunk(*, source_file: str, question_number: int, chunk_index: int, chunk: str) -> str:
    """
    Стабильный id точки для фрагмента текста.

    Идентификатор строится из устойчивых бизнес-полей чанка, а не из позиции
    во временном списке индексации.
    """
    key = f"{source_file}:{question_number}:{chunk_index}:{chunk}"
    return str(uuid.uuid5(_CHUNK_ID_NS, key))


class QdrantService(VectorStoreGateway):
    """
    Обёртка над AsyncQdrantClient + эмбеддинги Ollama.
    Реализует протокол VectorStoreGateway.
    """

    def __init__(self, settings: Settings, llm: Any) -> None:
        self._settings = settings
        self._llm = llm
        self._client = AsyncQdrantClient(url=settings.qdrant_url)

    @property
    def collection(self) -> str:
        """Имя коллекции из настроек."""
        return self._settings.qdrant_collection

    async def ensure_collection(self) -> None:
        """
        Создаёт коллекцию, если её ещё нет.

        Параметры ``shard_number`` и ``replication_factor`` задаются только здесь;
        у существующей коллекции их не меняют — нужно удалить коллекцию и создать снова.
        """
        names = (await self._client.get_collections()).collections
        existing = {c.name for c in names}
        if self.collection in existing:
            return
        await self._client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self._settings.embedding_dim, distance=Distance.COSINE),
            shard_number=max(1, self._settings.qdrant_shard_number),
            replication_factor=max(1, self._settings.qdrant_replication_factor),
        )

    async def close(self) -> None:
        """Корректно закрывает клиент Qdrant."""
        await self._client.close()

    async def ping(self) -> bool:
        """Проверка доступности Qdrant (успешный list collections)."""
        try:
            await self._client.get_collections()
            return True
        except Exception:
            logger.exception("Не удалось выполнить ping Qdrant")
            return False

    # --- VectorStoreGateway protocol methods ---

    async def upsert(
        self,
        vectors: list[tuple[str, list[float]]],
        payloads: list[dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """
        Записывает векторы с соответствующими payloads.

        Ожидает список кортежей (id, вектор) и список payloads того же размера.
        """
        if not vectors:
            return
        points = []
        for (point_id, vector), payload in zip(vectors, payloads, strict=False):
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )
        await self._client.upsert(collection_name=self.collection, points=points, **kwargs)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Ищет ближайшие векторы и возвращает их payloads.
        """
        res = await self._client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            **kwargs,
        )
        out: list[dict[str, Any]] = []
        for hit in res.points:
            if hit.payload:
                out.append(dict(hit.payload))
        return out

    async def delete_by_payload_kind(self, kind: str, *, doc_hash: str | None = None) -> None:
        """Удаляет точки по `kind` и (опционально) `doc_hash`."""
        must: list[Condition] = [
            FieldCondition(key="kind", match=MatchValue(value=kind)),
        ]
        if doc_hash:
            must.append(FieldCondition(key="doc_hash", match=MatchValue(value=doc_hash)))

        await self._client.delete(
            collection_name=self.collection,
            points_selector=Filter(must=must),
        )

    # --- Feature-specific methods (convenience for chat feature) ---

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Векторизация списка строк через Ollama embeddings API.

        Порядок выходных векторов совпадает с порядком ``texts``.
        """
        return await self._llm.embed(texts)

    async def upsert_chunks_with_payloads(
        self,
        chunk_payload_pairs: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """
        Записывает фрагменты с индивидуальным payload для каждого чанка.

        Используется, когда у разных чанков отличаются метаданные
        (например ``question_number``).
        """
        if not chunk_payload_pairs:
            return
        chunks = [chunk for chunk, _ in chunk_payload_pairs]
        vectors = await self.embed_texts(chunks)
        # Prepare (id, vector) tuples and payloads list
        ids_and_vectors: list[tuple[str, list[float]]] = []
        payloads: list[dict[str, Any]] = []
        for i, (chunk, payload) in enumerate(chunk_payload_pairs):
            source_file = str(payload.get("source_file", ""))
            question_number = int(payload.get("question_number", 0))
            chunk_index = int(payload.get("chunk_index", i))
            point_id = point_id_for_chunk(
                source_file=source_file,
                question_number=question_number,
                chunk_index=chunk_index,
                chunk=chunk,
            )
            ids_and_vectors.append((point_id, vectors[i]))
            payloads.append(payload)
        await self.upsert(ids_and_vectors, payloads)

    async def search_payload(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        """Возвращает список payload найденных точек (для ссылок на номер ответа)."""
        vectors = await self.embed_texts([query])
        if not vectors:
            return []
        return await self.search(vectors[0], top_k=limit)
