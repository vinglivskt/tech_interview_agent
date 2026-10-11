"""LangChain adapters for Ollama chat and embeddings."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.core.config import Settings
from src.core.langsmith import make_traced_generate

logger = logging.getLogger(__name__)


class OllamaClient:
    """LLM and embedding gateway backed by LangChain's Ollama integrations."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.ollama_model
        self._embed_model = settings.ollama_embed_model
        self._batch_size = settings.embedding_batch_size
        self._base_url = settings.ollama_url.rstrip("/")
        self._timeout = settings.ollama_timeout_sec
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        self._chat_models: dict[tuple[float | None, int | None], Any] = {}
        self._embedding_model: Any | None = None
        self._traced_generate = make_traced_generate(
            self._langchain_generate,
            settings=settings,
            base_metadata={"provider": "ollama", "model": self._model},
            base_tags=["llm"],
        )
        self._traced_structured = make_traced_generate(
            self._langchain_structured,
            settings=settings,
            name="llm.generate_structured",
            base_metadata={"provider": "ollama", "model": self._model},
            base_tags=["llm", "structured"],
        )

    async def close(self) -> None:
        clients = [getattr(model, "async_client", None) for model in self._chat_models.values()]
        clients.append(getattr(self._embedding_model, "async_client", None))
        for client in clients:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                await close()
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            response = await self._http.get("/api/tags", timeout=3.0)
            return response.status_code == 200
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

    def _get_chat_model(self, temperature: float | None, max_tokens: int | None) -> Any:
        key = (temperature, max_tokens)
        if key not in self._chat_models:
            from langchain_ollama import ChatOllama

            kwargs: dict[str, Any] = {
                "model": self._model,
                "base_url": self._base_url,
                "client_kwargs": {"timeout": self._timeout},
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_tokens is not None:
                kwargs["num_predict"] = max_tokens
            self._chat_models[key] = ChatOllama(**kwargs)
        return self._chat_models[key]

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
        result = await self._get_chat_model(temperature, max_tokens).ainvoke(
            self._to_chat_messages(messages)
        )
        return self._content_text(result)

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
            chain = self._get_chat_model(temperature, max_tokens).with_structured_output(
                schema, method="json_schema"
            )
            return await chain.ainvoke(self._to_chat_messages(messages))
        except Exception:
            logger.warning("Структурный вывод Ollama через LangChain не удался", exc_info=True)
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._embedding_model is None:
            from langchain_ollama import OllamaEmbeddings

            self._embedding_model = OllamaEmbeddings(
                model=self._embed_model,
                base_url=self._base_url,
                client_kwargs={"timeout": self._timeout},
            )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(
                await self._embedding_model.aembed_documents(
                    texts[start : start + self._batch_size]
                )
            )
        return vectors
