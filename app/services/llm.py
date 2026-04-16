"""HTTP-клиент к Ollama API (POST /api/chat)."""

from __future__ import annotations

import httpx

from app.config import Settings


class OllamaClient:

    def __init__(self, settings: Settings) -> None:
        self._model = settings.ollama_model
        self._embed_model = settings.ollama_embed_model
        self._http = httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/"),
            timeout=settings.ollama_timeout_sec,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            resp = await self._http.get("/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        resp = await self._http.post(
            "/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            # Варианты API у разных версий Ollama/прокси:
            # 1) /api/embeddings (старый)
            # 2) /api/embed (новый)
            # 3) /v1/embeddings (OpenAI-compatible)
            resp = await self._http.post("/api/embeddings", json={"model": self._embed_model, "prompt": text})
            if resp.status_code == 404:
                resp = await self._http.post("/api/embed", json={"model": self._embed_model, "input": text})
            if resp.status_code == 404:
                resp = await self._http.post("/v1/embeddings", json={"model": self._embed_model, "input": text})
            if resp.status_code == 404:
                raise RuntimeError(
                    "Ollama не поддерживает embeddings endpoint. "
                    "Обновите Ollama и установите embedding-модель."
                )

            resp.raise_for_status()
            payload = resp.json()

            if "embedding" in payload:
                out.append(payload["embedding"])
                continue
            if "embeddings" in payload and payload["embeddings"]:
                out.append(payload["embeddings"][0])
                continue
            if "data" in payload and payload["data"]:
                out.append(payload["data"][0]["embedding"])
                continue

            raise RuntimeError("Ollama embed вернул пустой ответ")
        return out
