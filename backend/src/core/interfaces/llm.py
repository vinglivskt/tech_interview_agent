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
    ) -> str:
        """Генерация ответа LLM.

        * ``messages`` – список сообщений в формате OpenAI.
        * ``temperature`` и ``max_tokens`` конфигурируют вызов модели.
        * ``metadata``/``tags`` – контекст для трассировки LangSmith (фича,
          session_id и т.п.); при выключенной трассировке игнорируются.
        """
        ...

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
        """Структурный вывод через LangChain ``with_structured_output``.

        Возвращает валидированную Pydantic-модель либо ``None`` при сбое;
        вызывающая фича применяет собственную безопасную деградацию.
        """
        ...
