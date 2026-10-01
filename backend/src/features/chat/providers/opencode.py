# tech_interview_agent/app/features/chat/providers/opencode.py
"""Клиент генерации LLM через OpenCode Zen API.

Важные ограничения Zen, установленные эмпирически (проверено curl):

* Базовый URL — ``https://opencode.ai/zen/v1`` (не ``api.opencode.ai``).
* Есть только чат-эндпоинты: ``/chat/completions`` (OpenAI-совместимый),
  ``/messages`` (Anthropic), ``/responses``. Эндпоинта эмбеддингов **нет** (404),
  поэтому ``embed`` здесь сознательно отсутствует — эмбеддинги считает Ollama
  (см. ``CompositeLLMClient``).
* Ответ об ошибке приходит JSON-ом с ``{"type":"error","error":{...}}`` или
  ``{"error":{...}}``; статусы: 402 — нет средств, 403 — free-tier модель,
  401 — неверный ключ. Ниже эти коды превращаются в понятный ``RuntimeError``,
  а не в ``JSONDecodeError``.
* Почти все free-tier модели Zen (``big-pickle``, ``nemotron-*``, ``mimo-*``,
  ``muse-spark-*``, ``jev-*-free``) отдают 403 ``FreeTierError`` при прямом
  вызове API. Проверено экспериментально работающей бесплатной моделью для
  прямого API является только ``space-bunny-free``.
* Zen-модели — reasoning-модели: часть ``max_tokens`` расходуется на внутренние
  размышления, поэтому при маленьком бюджете ``content`` приходит пустым.
  Здесь бюджет приподнимается до ``_MIN_MAX_TOKENS``, а пустой ответ превращается
  в понятную ошибку вместо молчаливой пустой строки.
* Параметр ``reasoning_effort`` умеет радикально сокращать размышления.
  Замеры на ``space-bunny-free`` для вопроса собеседования: без параметра —
  14.1s, 908 thinking-токенов, ``finish_reason=length`` и почти пустой content;
  с ``reasoning_effort="low"`` — 4.1s, 33 thinking-токена, ``finish_reason=stop``
  и нормальный ответ. Поэтому он включён по умолчанию, а модели, которые его не
  принимают, обрабатываются повтором без параметра.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.core.config import Settings
from src.core.langsmith import make_traced_generate

logger = logging.getLogger(__name__)


def _zen_error_detail(resp: httpx.Response) -> str:
    """Достаёт человекочитаемый текст ошибки из тела ответа Zen."""
    try:
        body = resp.json()
    except Exception:
        return (resp.text or "")[:300]
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    if isinstance(err, str):
        return err[:300]
    return str(body)[:300]


_HINTS = {
    401: "проверьте OPENCODE_KEY",
    402: "на аккаунте OpenCode Zen нет средств — пополните баланс "
         "либо используйте бесплатную space-bunny-free",
    403: "эта free-tier модель недоступна для прямых API-вызовов "
         "(«can only be used from within OpenCode») — используйте "
         "space-bunny-free или пополните баланс для платной модели",
    404: "неверный OPENCODE_URL или модель отсутствует в каталоге Zen",
}

# Модели Zen (в т.ч. space-bunny-free) являются reasoning-моделями: часть
# max_tokens уходит на внутренние размышления, и при маленьком бюджете
# ``message.content`` приходит пустым. Эмпирически проверено: при 40 токенах
# content пустой, при 512 — «Да.». Поэтому поднимаем бюджет до рабочей планки.
_MIN_MAX_TOKENS = 1024


def _rejects_param(resp: httpx.Response, param: str) -> bool:
    """True, если провайдер отверг запрос именно из-за неизвестного параметра.

    Нужно для ``reasoning_effort``: параметр поддерживают не все модели Zen,
    и лишний retry не должен превращаться в бесконечный цикл ошибок.
    """
    if resp.status_code != 400:
        return False
    detail = _zen_error_detail(resp).lower()
    return param in detail and ("invalid" in detail or "unsupported" in detail)


class OpenCodeClient:
    """Генерация LLM через OpenCode Zen (OpenAI-совместимый ``/chat/completions``).

    Реализует только ``LLMGateway``. ``embed`` намеренно не реализован:
    Zen не предоставляет эмбеддингов.
    """

    def __init__(self, settings: Settings) -> None:
        self._model = settings.opencode_model
        self._api_key = getattr(settings, "opencode_key", "") or ""
        self._base_url = settings.opencode_url.rstrip("/")
        self._reasoning_effort = (
            getattr(settings, "opencode_reasoning_effort", "") or ""
        ).strip()
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=settings.opencode_timeout_sec,
            headers=headers,
        )
        self._traced_generate = make_traced_generate(
            self._raw_generate,
            settings=settings,
            base_metadata={"provider": "opencode", "model": self._model},
            base_tags=["llm"],
        )
        self._traced_structured = make_traced_generate(
            self._structured_ainvoke,
            settings=settings,
            name="llm.generate_structured",
            base_metadata={"provider": "opencode", "model": self._model},
            base_tags=["llm", "structured"],
        )
        self._structured_chains: dict[int, tuple[Any, Any]] = {}

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        """Проверка доступности: ``GET /models`` (не требует баланса)."""
        try:
            resp = await self._http.get("/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def _fail(self, resp: httpx.Response, action: str) -> RuntimeError:
        detail = _zen_error_detail(resp)
        hint = _HINTS.get(resp.status_code)
        return RuntimeError(
            f"OpenCode Zen: {action} не удался (HTTP {resp.status_code}): {detail}"
            + (f" — {hint}" if hint else "")
        )

    async def _raw_generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max(max_tokens, _MIN_MAX_TOKENS)
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        payload.update(kwargs)

        resp = await self._http.post("/chat/completions", json=payload)
        if _rejects_param(resp, "reasoning_effort"):
            logger.info(
                "Модель %s не принимает reasoning_effort=%s — повторяю без него",
                self._model,
                self._reasoning_effort,
            )
            payload.pop("reasoning_effort", None)
            self._reasoning_effort = ""
            resp = await self._http.post("/chat/completions", json=payload)
        if resp.status_code != 200:
            raise self._fail(resp, "вызов чата")
        try:
            body = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"OpenCode Zen: ответ не JSON (HTTP 200, body={(resp.text or '')[:200]!r}). "
                f"Проверьте OPENCODE_URL (сейчас {self._base_url})."
            ) from exc
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"OpenCode Zen: неожиданная структура ответа: {str(body)[:200]}"
            ) from exc
        if not (content or "").strip():
            finish = choice.get("finish_reason")
            raise RuntimeError(
                f"OpenCode Zen: модель {self._model} вернула пустой ответ "
                f"(finish_reason={finish!r}, max_tokens={payload.get('max_tokens')}). "
                "Это reasoning-модель: внутренние размышления исчерпали бюджет токенов. "
                "Увеличьте max_tokens."
            )
        return content

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
        if self._traced_generate is not None:
            from langsmith import tracing_context

            with tracing_context(metadata=dict(metadata or {}), tags=list(tags or ())):
                return await self._traced_generate(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
        return await self._raw_generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    @staticmethod
    def _to_chat_messages(messages: list[dict[str, str]]) -> list[Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        out: list[Any] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                out.append(SystemMessage(content=content))
            else:
                out.append(HumanMessage(content=content))
        return out

    def _get_structured_chain(self, schema: Any) -> Any:
        key = id(schema)
        cached = self._structured_chains.get(key)
        if cached is not None and cached[0] is schema:
            return cached[1]
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Для structured output через OpenCode нужен пакет langchain-openai. "
                "Установите: uv add langchain-openai"
            ) from exc
        chat = ChatOpenAI(
            model=self._model,
            base_url=self._base_url,
            api_key=self._api_key or "missing",
        )
        chain = chat.with_structured_output(schema, method="json_schema")
        self._structured_chains[key] = (schema, chain)
        return chain

    async def _structured_ainvoke(
        self,
        messages: list[dict[str, str]],
        *,
        schema: Any,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Any | None:
        try:
            chain = self._get_structured_chain(schema)
            return await chain.ainvoke(self._to_chat_messages(messages))
        except Exception:
            logger.warning(
                "Структурный вывод OpenCode не удался — фолбэк на legacy-парсинг", exc_info=True
            )
            return None

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: Any,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any | None:
        if self._traced_structured is not None:
            from langsmith import tracing_context

            with tracing_context(metadata=dict(metadata or {}), tags=list(tags or ())):
                return await self._traced_structured(
                    messages,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
        return await self._structured_ainvoke(
            messages,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )