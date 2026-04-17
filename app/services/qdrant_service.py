"""Работа с Qdrant: создание коллекции, векторизация Ollama, upsert, поиск."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Condition, Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import Settings
from app.services.llm import OllamaClient

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


class QdrantService:
    """
    Обёртка над AsyncQdrantClient + эмбеддинги Ollama.
    """

    def __init__(self, settings: Settings, llm: OllamaClient) -> None:
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

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Векторизация списка строк через Ollama embeddings API.

        Порядок выходных векторов совпадает с порядком ``texts``.
        """
        return await self._llm.embed(texts)

    async def delete_by_payload_kind(self, kind: str, *, doc_hash: str | None = None) -> None:
        """
        Удаляет точки по ``kind`` и, если передан ``doc_hash``, только для этой версии документа.
        """
        must: list[Condition] = [
            FieldCondition(key="kind", match=MatchValue(value=kind)),
        ]
        if doc_hash:
            must.append(FieldCondition(key="doc_hash", match=MatchValue(value=doc_hash)))

        await self._client.delete(
            collection_name=self.collection,
            points_selector=Filter(must=must),
        )

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
        points = []
        for i, (chunk, payload) in enumerate(chunk_payload_pairs):
            source_file = str(payload.get("source_file", ""))
            question_number = int(payload.get("question_number", 0))
            chunk_index = int(payload.get("chunk_index", i))
            points.append(
                PointStruct(
                    id=point_id_for_chunk(
                        source_file=source_file,
                        question_number=question_number,
                        chunk_index=chunk_index,
                        chunk=chunk,
                    ),
                    vector=vectors[i],
                    payload={"text": chunk, **payload},
                )
            )
        await self._client.upsert(collection_name=self.collection, points=points)

    async def search_payload(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        """Возвращает список payload найденных точек (для ссылок на номер ответа)."""
        vectors = await self.embed_texts([query])
        res = await self._client.query_points(
            collection_name=self.collection,
            query=vectors[0],
            limit=limit,
            with_payload=True,
        )
        out: list[dict[str, Any]] = []
        for hit in res.points:
            if hit.payload:
                out.append(dict(hit.payload))
        return out
