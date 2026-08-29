# tech_interview_agent/app/core/interfaces/embeddings.py
from typing import Protocol


class EmbeddingGateway(Protocol):
    """Абстракция для получения эмбеддингов (Ollama, OpenAI embeddings, локальная модель и т.д.)."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
