# tech_interview_agent/app/features/chat/providers/composite.py

"""Композитный клиент: генерация LLM и эмбеддинги от разных провайдеров.

Зачем это нужно. OpenCode Zen — шлюз только для чата: эндпоинта эмбеддингов у него
нет (проверено: ``GET/POST https://opencode.ai/zen/v1/embeddings`` → 404). А RAG
требует эмбеддингов для индексации docx и поиска по Qdrant. Поэтому один объект,
который отдаётся в ``QdrantService`` и в сервисы фич, должен уметь:

* ``generate`` / ``generate_structured`` / ``ping`` — от ``llm`` (Ollama или Zen);
* ``embed`` — всегда от ``embedder`` (Ollama).

Оба провайдера удовлетворяют ``LLMGateway``; ``EmbeddingGateway`` реализует
только Ollama. Класс не добавляет сетевых вызовов и не меняет сигнатуры.
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces.embeddings import EmbeddingGateway
from src.core.interfaces.llm import LLMGateway


class CompositeLLMClient:
    """Маршрутизирует LLM-вызовы к ``llm``, а эмбеддинги — к ``embedder``."""

    def __init__(self, llm: LLMGateway, embedder: EmbeddingGateway) -> None:
        self._llm = llm
        self._embedder = embedder

    @property
    def llm(self) -> LLMGateway:
        """Провайдер генерации (для логов и метаданных)."""
        return self._llm

    async def ping(self) -> bool:
        return await self._llm.ping()

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        return await self._llm.generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
            tags=tags,
        )

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: Any,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Any | None:
        return await self._llm.generate_structured(
            messages,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
            tags=tags,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embedder.embed(texts)

    async def close(self) -> None:
        await self._llm.close()
        # Не закрываем Ollama дважды, если он же выбран генератором.
        if self._embedder is not self._llm:
            await self._embedder.close()  # type: ignore[attr-defined]
