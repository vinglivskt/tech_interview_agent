"""Шлюз трассировки LLM-вызовов через LangSmith.

Все LLM-вызовы в проекте идут только через `OllamaClient.generate`. Этот модуль
решает:
- когда трассировка активна (`tracing_ready`): флаг `langsmith_tracing` в настройках
  **и** заданный API-ключ в окружении (`LANGSMITH_API_KEY` / `LANGCHAIN_API_KEY`);
- как собрать `traceable`-обёртку над фактическим вызовом (`make_traced_generate`).

Выключенная трассировка не приносит ни сети, ни задержек: гейт проверяется до
ленивого импорта `langsmith`, а вернувшаяся `None` означает «работаем как раньше».
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

_GENERATE_NAME = "llm.generate"
_GENERATE_RUN_TYPE = "llm"
_DEFAULT_PROJECT = "tech-interview-agent"

TracedGenerate = Callable[..., Awaitable[str]]


def tracing_ready(settings: Any) -> bool:
    """Активна ли трассировка: флаг `langsmith_tracing` + заданный API-ключ.

    Если флаг включён, а ключа нет — предупреждаем и отключаем трассировку,
    чтобы никогда не пытаться ходить в сеть «вслепую».
    """
    if not getattr(settings, "langsmith_tracing", False):
        return False
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        logger.warning(
            "langsmith_tracing=true, но LANGSMITH_API_KEY/LANGCHAIN_API_KEY не задан(ы) "
            "в окружении — трассировка LLM-вызовов отключена."
        )
        return False
    return True


def _tracer_env(settings: Any) -> None:
    """Гарантируем SDK-переменные окружения (проект и master-переключатель)."""
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault(
        "LANGSMITH_PROJECT", getattr(settings, "langsmith_project", _DEFAULT_PROJECT)
    )


def make_traced_generate(
    raw: TracedGenerate,
    *,
    settings: Any,
    name: str = _GENERATE_NAME,
    run_type: str = _GENERATE_RUN_TYPE,
    base_metadata: dict[str, Any] | None = None,
    base_tags: list[str] | None = None,
) -> TracedGenerate | None:
    """Собрать `traceable`-обёртку над async-`raw` (метод `generate`).

    Возвращает `None`, если трассировка выключена: вызывающая сторона использует
    прежний прямой вызов без накладных расходов. Per-call `metadata`/`tags`
    задаются вызывающей стороной через `langsmith.tracing_context`.
    """
    if not tracing_ready(settings):
        return None
    from langsmith import traceable  # ленивый импорт: SDK не нужен на offline-путях

    _tracer_env(settings)
    project = getattr(settings, "langsmith_project", _DEFAULT_PROJECT)
    return traceable(
        name=name,
        run_type=run_type,
        project_name=project,
        metadata=base_metadata or None,
        tags=base_tags or None,
    )(raw)