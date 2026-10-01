"""Тесты OpenCode Zen провайдера и композитного маршрутизатора.

Проверенные эмпирически ограничения Zen (curl), которые зафиксированы здесь:
- базовый URL `https://opencode.ai/zen/v1`;
- эндпоинта эмбеддингов нет (`/embeddings` → 404), поэтому `embed` живёт
  в композитном клиенте и всегда идёт в Ollama;
- ошибки приходят JSON-ом и превращаются в понятный `RuntimeError`
  (402 — нет средств, 403 — free-tier, 401 — ключ).
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from src.features.chat.providers.composite import CompositeLLMClient
from src.features.chat.providers.opencode import OpenCodeClient


def _settings(**overrides):
    base = {
        "opencode_key": "oc_sk_test",
        "opencode_url": "https://opencode.ai/zen/v1",
        "opencode_model": "space-bunny-free",
        "opencode_timeout_sec": 30.0,
        "opencode_reasoning_effort": "low",
        "llm_structured_output": False,
        "langsmith_tracing": False,
        "langsmith_project": "tech-interview-agent",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _resp(status: int = 200, body=None, text: str | None = None, json_raises: bool = False):
    if body is None:
        body = {"choices": [{"message": {"content": "ok"}}]}

    def _json():
        if json_raises:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return body

    return SimpleNamespace(
        status_code=status,
        json=_json,
        text=text if text is not None else json.dumps(body),
        raise_for_status=lambda: None,
    )


# --- Конструкция --------------------------------------------------------------


class TestConstruction:
    def test_base_url_trailing_slash_stripped(self) -> None:
        client = OpenCodeClient(_settings(opencode_url="https://opencode.ai/zen/v1/"))
        assert client._base_url == "https://opencode.ai/zen/v1"

    def test_authorization_header_set(self) -> None:
        client = OpenCodeClient(_settings(opencode_key="oc_sk_abc"))
        assert client._http.headers["Authorization"] == "Bearer oc_sk_abc"

    def test_no_auth_header_when_key_empty(self) -> None:
        client = OpenCodeClient(_settings(opencode_key=""))
        assert "Authorization" not in client._http.headers

    def test_embed_is_not_implemented(self) -> None:
        """У Zen нет эндпоинта эмбеддингов — клиент не должен егоpretend'ить."""
        assert not hasattr(OpenCodeClient, "embed")


# --- ping ----------------------------------------------------------------------


class TestPing:
    def test_ping_true_on_200(self, monkeypatch) -> None:
        client = OpenCodeClient(_settings())
        monkeypatch.setattr(client._http, "get", AsyncMock(return_value=_resp(200, {"data": []})))
        assert asyncio.run(client.ping()) is True

    def test_ping_false_on_error(self, monkeypatch) -> None:
        client = OpenCodeClient(_settings())
        monkeypatch.setattr(client._http, "get", AsyncMock(side_effect=RuntimeError("boom")))
        assert asyncio.run(client.ping()) is False


# --- generate ------------------------------------------------------------------


class TestGenerate:
    def _client(self, monkeypatch, resp=None, settings=None):
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        client = OpenCodeClient(settings or _settings())
        post = AsyncMock(return_value=resp or _resp())
        monkeypatch.setattr(client._http, "post", post)
        return client, post

    def test_returns_content(self, monkeypatch) -> None:
        client, _ = self._client(monkeypatch)
        out = asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert out == "ok"

    def test_payload_shape(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(client.generate(
            [{"role": "user", "content": "hi"}], temperature=0.7, max_tokens=256,
        ))
        payload = post.await_args.kwargs["json"]
        assert payload["model"] == "space-bunny-free"
        assert payload["stream"] is False
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 1024

    def test_posts_to_chat_completions(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert post.await_args.args[0] == "/chat/completions"

    def test_no_optional_keys_without_kwargs(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        payload = post.await_args.kwargs["json"]
        assert "temperature" not in payload
        assert "max_tokens" not in payload

    def test_extra_kwargs_passthrough(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(client.generate([{"role": "user", "content": "hi"}], format="json"))
        assert post.await_args.kwargs["json"]["format"] == "json"

    def test_insufficient_funds_error_is_actionable(self, monkeypatch) -> None:
        """402 от Zen должен превращаться в понятный RuntimeError, не в JSONDecodeError."""
        client, _ = self._client(monkeypatch, resp=_resp(
            402, {"error": {"type": "server_error", "message": "Insufficient account funds"}},
        ))
        with pytest.raises(RuntimeError, match="402") as exc:
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert "Insufficient account funds" in str(exc.value)
        assert "средств" in str(exc.value)

    def test_free_tier_403_hint(self, monkeypatch) -> None:
        client, _ = self._client(monkeypatch, resp=_resp(
            403, {"error": {"message": "OpenCode's free tier can only be used from within OpenCode"}},
        ))
        with pytest.raises(RuntimeError, match="403") as exc:
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert "free-tier" in str(exc.value)

    def test_bad_key_401_hint(self, monkeypatch) -> None:
        client, _ = self._client(monkeypatch, resp=_resp(401, {"error": {"message": "invalid key"}}))
        with pytest.raises(RuntimeError, match="OPENCODE_KEY"):
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))

    def test_non_json_200_points_to_url(self, monkeypatch) -> None:
        """Раньше здесь был JSONDecodeError; теперь подсказка про OPENCODE_URL."""
        client, _ = self._client(
            monkeypatch, resp=_resp(200, None, text="Not Found", json_raises=True),
        )
        with pytest.raises(RuntimeError, match="OPENCODE_URL"):
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))

    def test_unexpected_structure_is_wrapped(self, monkeypatch) -> None:
        client, _ = self._client(monkeypatch, resp=_resp(200, {"unexpected": True}))
        with pytest.raises(RuntimeError, match="неожиданная структура"):
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))

    def test_empty_content_is_actionable_not_silent(self, monkeypatch) -> None:
        client, _ = self._client(monkeypatch, resp=_resp(200, {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
        }))
        with pytest.raises(RuntimeError, match="пустой ответ"):
            asyncio.run(client.generate([{"role": "user", "content": "hi"}], max_tokens=256))

    def test_whitespace_content_is_actionable(self, monkeypatch) -> None:
        client, _ = self._client(monkeypatch, resp=_resp(200, {
            "choices": [{"message": {"content": "   "}, "finish_reason": "stop"}],
        }))
        with pytest.raises(RuntimeError, match="пустой ответ"):
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))

    def test_reasoning_effort_sent_in_payload(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert post.await_args.kwargs["json"]["reasoning_effort"] == "low"

    def test_reasoning_effort_omitted_when_blank(self, monkeypatch) -> None:
        client, post = self._client(
            monkeypatch, settings=_settings(opencode_reasoning_effort="")
        )
        asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert "reasoning_effort" not in post.await_args.kwargs["json"]

    def test_reasoning_effort_400_retries_without_param(self, monkeypatch) -> None:
        rejected = _resp(400, {"error": {
            "message": "invalid_request_error: invalid reasoning_effort value",
        }})
        post = AsyncMock(side_effect=[rejected, _resp()])
        client = OpenCodeClient(_settings())
        monkeypatch.setattr(client._http, "post", post)
        assert asyncio.run(client.generate([{"role": "user", "content": "hi"}])) == "ok"
        assert post.await_count == 2
        assert "reasoning_effort" not in post.await_args.kwargs["json"]

    def test_other_400_is_not_retried(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch, resp=_resp(400, {
            "error": {"message": "context length exceeded"},
        }))
        with pytest.raises(RuntimeError, match="HTTP 400"):
            asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
        assert post.await_count == 1

    def test_large_max_tokens_not_clamped_down(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(client.generate(
            [{"role": "user", "content": "hi"}], max_tokens=4096,
        ))
        assert post.await_args.kwargs["json"]["max_tokens"] == 4096

    def test_tracing_context_used(self, monkeypatch) -> None:
        monkeypatch.setenv("LANGSMITH_API_KEY", "sk-test")
        client = OpenCodeClient(_settings(langsmith_tracing=True))
        monkeypatch.setattr(client._http, "post", AsyncMock(return_value=_resp()))
        with patch("langsmith.tracing_context") as mock_trace:
            mock_trace.return_value.__enter__ = lambda s: s
            mock_trace.return_value.__exit__ = lambda s, *exc: None
            asyncio.run(client.generate(
                [{"role": "user", "content": "hi"}],
                metadata={"feature": "chat"}, tags=["answer"],
            ))
            assert mock_trace.called


# --- generate_structured -------------------------------------------------------


class _FakeChain:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages):
        return self._result


class TestGenerateStructured:
    def _fake_module(self, monkeypatch):
        fake_chat = AsyncMock()
        mod = types.ModuleType("langchain_openai")
        mod.ChatOpenAI = lambda *a, **k: fake_chat
        monkeypatch.setitem(sys.modules, "langchain_openai", mod)
        return fake_chat

    def test_chain_cached_by_schema(self, monkeypatch) -> None:
        client = OpenCodeClient(_settings())
        fake_chat = self._fake_module(monkeypatch)
        fake_chat.with_structured_output.return_value = _FakeChain(None)
        schema = object()
        c1 = client._get_structured_chain(schema)
        c2 = client._get_structured_chain(schema)
        assert c1 is c2
        assert fake_chat.with_structured_output.call_count == 1

    def test_returns_model_on_success(self, monkeypatch) -> None:
        client = OpenCodeClient(_settings())
        expected = SimpleNamespace(score_percent=90)
        monkeypatch.setattr(client, "_get_structured_chain", lambda s: _FakeChain(expected))
        out = asyncio.run(client.generate_structured(
            [{"role": "user", "content": "u"}], schema=object(), tags=["scoring"],
        ))
        assert out is expected

    def test_returns_none_on_failure(self, monkeypatch) -> None:
        client = OpenCodeClient(_settings())

        class Broken:
            async def ainvoke(self, messages):
                raise RuntimeError("no model")

        monkeypatch.setattr(client, "_get_structured_chain", lambda s: Broken())
        assert asyncio.run(client.generate_structured(
            [{"role": "user", "content": "u"}], schema=object(),
        )) is None


# --- CompositeLLMClient --------------------------------------------------------


class _FakeLLM:
    def __init__(self):
        self.generate_calls = []
        self.structured_calls = []
        self.embed_calls = []
        self.closed = False
        self.ping_result = True

    async def ping(self):
        return self.ping_result

    async def generate(self, messages, **kwargs):
        self.generate_calls.append({"messages": messages, "kwargs": kwargs})
        return "gen"

    async def generate_structured(self, messages, *, schema, **kwargs):
        self.structured_calls.append({"schema": schema, "kwargs": kwargs})
        return "structured"

    async def embed(self, texts):
        self.embed_calls.append(list(texts))
        return [[0.1]]

    async def close(self):
        self.closed = True


class TestComposite:
    def test_routes_generate_to_llm(self) -> None:
        llm, emb = _FakeLLM(), _FakeLLM()
        c = CompositeLLMClient(llm, emb)
        assert asyncio.run(c.generate([{"role": "user", "content": "hi"}], tags=["answer"])) == "gen"
        assert len(llm.generate_calls) == 1
        assert llm.generate_calls[0]["kwargs"]["tags"] == ["answer"]
        assert emb.generate_calls == []

    def test_routes_structured_to_llm(self) -> None:
        llm, emb = _FakeLLM(), _FakeLLM()
        c = CompositeLLMClient(llm, emb)
        assert asyncio.run(c.generate_structured([], schema=object())) == "structured"
        assert len(llm.structured_calls) == 1

    def test_routes_embed_to_embedder_not_llm(self) -> None:
        """Ключевая проверка: эмбеддинги уходят в Ollama, а не в Zen."""
        llm, emb = _FakeLLM(), _FakeLLM()
        c = CompositeLLMClient(llm, emb)
        assert asyncio.run(c.embed(["текст"])) == [[0.1]]
        assert emb.embed_calls == [["текст"]]
        assert llm.embed_calls == []

    def test_ping_uses_llm(self) -> None:
        llm, emb = _FakeLLM(), _FakeLLM()
        llm.ping_result = False
        assert asyncio.run(CompositeLLMClient(llm, emb).ping()) is False

    def test_close_closes_both_when_distinct(self) -> None:
        llm, emb = _FakeLLM(), _FakeLLM()
        asyncio.run(CompositeLLMClient(llm, emb).close())
        assert llm.closed and emb.closed

    def test_close_does_not_double_close_same_instance(self) -> None:
        shared = _FakeLLM()
        asyncio.run(CompositeLLMClient(shared, shared).close())
        assert shared.closed


# --- close ---------------------------------------------------------------------


class TestClose:
    def test_close_calls_aclose(self) -> None:
        client = OpenCodeClient(_settings())
        with patch.object(client._http, "aclose", new_callable=AsyncMock) as mock_close:
            asyncio.run(client.close())
            mock_close.assert_awaited_once()