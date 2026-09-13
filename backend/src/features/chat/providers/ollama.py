# tech_interview_agent/app/features/chat/providers/ollama.py

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.core.config import Settings
from src.core.langsmith import make_traced_generate

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Клиент для взаимодействия с Ollama API (LLM и эмбеддинги).
    Реализует генерацию ответов и получение эмбеддингов.
    """

    def __init__(self, settings: Settings) -> None:
        self._model = settings.ollama_model
        self._embed_model = settings.ollama_embed_model
        self._batch_size = settings.embedding_batch_size
        self._base_url = settings.ollama_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=settings.ollama_timeout_sec,
        )
        # Кешируем рабочий endpoint после первого успешного вызова
        self._embed_endpoint: tuple[str, str, str] | None = None
        # LangSmith-обёртка фактического вызова (None = трассировка выключена)
        self._traced_generate = make_traced_generate(
            self._raw_generate,
            settings=settings,
            base_metadata={"provider": "ollama", "model": self._model},
            base_tags=["llm"],
        )
        # LangSmith-обёртка structured-вызова (None = трассировка выключена)
        self._traced_structured = make_traced_generate(
            self._structured_ainvoke,
            settings=settings,
            name="llm.generate_structured",
            base_metadata={"provider": "ollama", "model": self._model},
            base_tags=["llm", "structured"],
        )
        # Кеш скомпилированных structured-цепей по объекту схемы (id-ключ)
        self._structured_chains: dict[int, tuple[Any, Any]] = {}

    async def close(self) -> None:
        """
        Закрывает HTTP-клиент Ollama.
        """
        await self._http.aclose()

    async def ping(self) -> bool:
        """
        Проверяет доступность Ollama (по /api/tags).
        :return: True если Ollama доступен
        """
        try:
            resp = await self._http.get("/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def _raw_generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Фактический вызов Ollama API (сборка payload и HTTP)."""
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        resp = await self._http.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

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
        """
        Генерирует ответ LLM через Ollama API.

        Ожидает список сообщений в формате OpenAI:
            [{"role": "system", "content": "..."},
             {"role": "user", "content": "..."},
             ...]

        ``metadata``/``tags`` — контекст для трассировки LangSmith (фича, session_id
        и т.п.). При выключенной трассировке игнорируются, поведение прежнее.
        :return: сгенерированный текст
        """
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

    # --- Structured output (LangChain, уровень B) ---

    @staticmethod
    def _to_chat_messages(messages: list[dict[str, str]]) -> list[Any]:
        """Конвертирует списки сообщений OpenAI-формата в типизированные LangChain."""
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
        """Собирает и кеширует `ChatOllama.with_structured_output(schema)`."""
        key = id(schema)
        cached = self._structured_chains.get(key)
        if cached is not None and cached[0] is schema:
            return cached[1]
        from langchain_ollama import ChatOllama

        chat = ChatOllama(model=self._model, base_url=self._base_url)
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
        """Фактический structured-вызов через LangChain (`method="json_schema"`).

        Возвращает валидированный объект схемы или ``None`` при любой ошибке
        (сеть, модель, Pydantic) — вызывающий код фолбэчится на legacy-парсинг.
        """
        try:
            chain = self._get_structured_chain(schema)
            return await chain.ainvoke(self._to_chat_messages(messages))
        except Exception:
            logger.warning("Структурный вывод не удался — фолбэк на legacy-парсинг", exc_info=True)
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
        """
        Структурный вывод через LangChain ``ChatOllama.with_structured_output``.

        Вместо «текста + ручного json.loads» возвращает провалидированный объект
        схемы (Pydantic) или ``None`` при сбое. ``method="json_schema"`` использует
        structured output API Ollama. Так же, как ``generate``, прокидывает
        ``metadata``/``tags`` в трейс LangSmith (если включён).
        """
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

    # --- Embedding methods (implements EmbeddingGateway) ---
    async def _detect_embed_endpoint(self) -> tuple[str, str, str]:
        """
        Определяет рабочий endpoint для эмбеддингов и кеширует его.
        :return: url, ключ для тела, ключ для ответа
        """
        """Определяет рабочий embed endpoint один раз и кеширует результат."""
        if self._embed_endpoint is not None:
            return self._embed_endpoint

        # Поддерживаемые embed endpoints в порядке приоритета проверки.
        embed_endpoints = [
            ("/api/embeddings", "prompt", "embedding"),
            ("/api/embed", "input", "embeddings"),
            ("/v1/embeddings", "input", "data"),
        ]
        for url, body_key, response_key in embed_endpoints:
            resp = await self._http.post(
                url,
                json={"model": self._embed_model, body_key: " "},
            )
            if resp.status_code != 404:
                resp.raise_for_status()
                self._embed_endpoint = (url, body_key, response_key)
                return self._embed_endpoint

        raise RuntimeError(
            "Ollama не поддерживает embeddings endpoint. Обновите Ollama и установите embedding-модель."
        )

    @staticmethod
    def _extract_vector(payload: dict[str, Any], response_key: str) -> list[float]:
        """
        Извлекает вектор из ответа Ollama embed endpoint.
        :param payload: json-ответ
        :param response_key: ключ для поиска вектора
        :return: список float
        """
        """Извлекает вектор из ответа embed endpoint."""
        if response_key == "embedding" and "embedding" in payload:
            return payload["embedding"]
        if response_key == "embeddings" and payload.get("embeddings"):
            return payload["embeddings"][0]
        if response_key == "data" and payload.get("data"):
            return payload["data"][0]["embedding"]
        raise RuntimeError(f"Ollama embed вернул пустой ответ (ключ: {response_key})")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Векторизует список текстов батчами через Ollama.
        :param texts: список строк
        :return: список векторов
        """
        """Векторизует тексты батчами, используя кешированный endpoint."""
        if not texts:
            return []

        url, body_key, response_key = await self._detect_embed_endpoint()
        out: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            for text in batch:
                resp = await self._http.post(
                    url,
                    json={"model": self._embed_model, body_key: text},
                )
                resp.raise_for_status()
                out.append(self._extract_vector(resp.json(), response_key))

        return out
