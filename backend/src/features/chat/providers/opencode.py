"""OpenCode Zen adapter built on LangChain's OpenAI-compatible chat model."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.core.config import Settings
from src.core.langsmith import make_traced_generate

logger = logging.getLogger(__name__)
_MIN_MAX_TOKENS = 1024


class OpenCodeClient:
    """LangChain chat gateway for OpenCode Zen; embeddings remain Ollama-backed."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.opencode_model
        self._api_key = getattr(settings, "opencode_key", "") or ""
        self._base_url = settings.opencode_url.rstrip("/")
        self._timeout = settings.opencode_timeout_sec
        self._reasoning_effort = (getattr(settings, "opencode_reasoning_effort", "") or "").strip()
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
        )
        self._models: dict[tuple[float | None, int | None], Any] = {}
        self._structured_chains: dict[tuple[int, float | None, int | None], tuple[Any, Any]] = {}
        self._traced_generate = make_traced_generate(
            self._langchain_generate,
            settings=settings,
            base_metadata={"provider": "opencode", "model": self._model},
            base_tags=["llm"],
        )
        self._traced_structured = make_traced_generate(
            self._langchain_structured,
            settings=settings,
            name="llm.generate_structured",
            base_metadata={"provider": "opencode", "model": self._model},
            base_tags=["llm", "structured"],
        )

    async def close(self) -> None:
        for model in self._models.values():
            client = getattr(model, "async_client", None)
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                await close()
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            return (await self._http.get("/models", timeout=5.0)).status_code == 200
        except Exception:
            return False

    @staticmethod
    def _to_chat_messages(messages: list[dict[str, str]]) -> list[Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        converted: list[Any] = []
        for message in messages:
            cls = SystemMessage if message.get("role") == "system" else HumanMessage
            converted.append(cls(content=message.get("content", "")))
        return converted

    def _get_model(self, temperature: float | None, max_tokens: int | None) -> Any:
        key = (temperature, max_tokens)
        if key not in self._models:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {
                "model": self._model,
                "base_url": self._base_url,
                "api_key": self._api_key or "missing",
                "timeout": self._timeout,
                # Zen historically exposes the OpenAI-compatible `max_tokens` field.
                "model_kwargs": {
                    "max_tokens": max(max_tokens or _MIN_MAX_TOKENS, _MIN_MAX_TOKENS)
                },
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            if self._reasoning_effort:
                kwargs["reasoning_effort"] = self._reasoning_effort
            self._models[key] = ChatOpenAI(**kwargs)
        return self._models[key]

    @staticmethod
    def _content_text(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    async def _langchain_generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        result = await self._get_model(temperature, max_tokens).ainvoke(
            self._to_chat_messages(messages)
        )
        content = self._content_text(result)
        if not content.strip():
            raise RuntimeError(
                f"OpenCode Zen: модель {self._model} вернула пустой ответ. "
                "Попробуйте увеличить max_tokens или установить OPENCODE_REASONING_EFFORT=low."
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
    ) -> str:
        if self._traced_generate is not None:
            from langsmith import tracing_context

            with tracing_context(metadata=dict(metadata or {}), tags=list(tags or ())):
                return await self._traced_generate(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
        return await self._langchain_generate(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    async def _langchain_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: Any,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any | None:
        try:
            key = (id(schema), temperature, max_tokens)
            cached = self._structured_chains.get(key)
            if cached is not None and cached[0] is schema:
                chain = cached[1]
            else:
                chain = self._get_model(temperature, max_tokens).with_structured_output(
                    schema, method="json_schema"
                )
                self._structured_chains[key] = (schema, chain)
            return await chain.ainvoke(self._to_chat_messages(messages))
        except Exception:
            logger.warning("Структурный вывод OpenCode через LangChain не удался", exc_info=True)
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
    ) -> Any | None:
        if self._traced_structured is not None:
            from langsmith import tracing_context

            with tracing_context(metadata=dict(metadata or {}), tags=list(tags or ())):
                return await self._traced_structured(
                    messages,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
        return await self._langchain_structured(
            messages,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
