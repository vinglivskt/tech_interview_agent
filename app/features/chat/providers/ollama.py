# tech_interview_agent/app/features/chat/providers/ollama.py

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._model = settings.ollama_model
        self._embed_model = settings.ollama_embed_model
        self._batch_size = settings.embedding_batch_size
        self._http = httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/"),
            timeout=settings.ollama_timeout_sec,
        )
        # Кешируем рабочий endpoint после первого успешного вызова
        self._embed_endpoint: tuple[str, str, str] | None = None

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            resp = await self._http.get("/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Генерация ответа LLM через Ollama API.

        Ожидает список сообщений в формате OpenAI:
            [{"role": "system", "content": "..."},
             {"role": "user", "content": "..."},
             ...]
        """
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

    # --- Embedding methods (implements EmbeddingGateway) ---
    async def _detect_embed_endpoint(self) -> tuple[str, str, str]:
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

        raise RuntimeError("Ollama не поддерживает embeddings endpoint. Обновите Ollama и установите embedding-модель.")

    @staticmethod
    def _extract_vector(payload: dict[str, Any], response_key: str) -> list[float]:
        """Извлекает вектор из ответа embed endpoint."""
        if response_key == "embedding" and "embedding" in payload:
            return payload["embedding"]
        if response_key == "embeddings" and payload.get("embeddings"):
            return payload["embeddings"][0]
        if response_key == "data" and payload.get("data"):
            return payload["data"][0]["embedding"]
        raise RuntimeError(f"Ollama embed вернул пустой ответ (ключ: {response_key})")

    async def embed(self, texts: list[str]) -> list[list[float]]:
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
