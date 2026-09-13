# tech_interview_agent/app/core/interfaces/llm.py
from typing import Any, Protocol


class LLMGateway(Protocol):
    """Абстракция над LLM‑провайдером (Ollama, OpenAI, Anthropic …)."""

    async def ping(self) -> bool:
        """Проверка доступности сервиса."""
        ...

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Генерация ответа LLM.

        * ``messages`` – список сообщений в формате OpenAI.
        * Параметры ``temperature``/``max_tokens`` и любые ``kwargs`` передаются
          конкретному провайдеру.
        * ``metadata``/``tags`` – контекст для трассировки LangSmith (фича,
          session_id и т.п.); при выключенной трассировке игнорируются.
        """
        ...
