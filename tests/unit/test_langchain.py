"""Тесты LangChain-интеграции: structured output, format="json", splitter.

Сценарии из `plans/PLAN_LANG_ECOSYSTEM.md`:
- 1A — `format: "json"` у скоринг-вызовов Ollama;
- 1B — `OllamaClient.generate_structured` (ChatOllama.with_structured_output)
  в scoring/classification/design с фолбэком на legacy-парсинг;
- 3 — `RecursiveCharacterTextSplitter` внутри `chunk_text` (контракт сохранён).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from src.core.structured import (
    ClassificationBatch,
    ClassificationRow,
    DesignScore,
    ScoreResult,
)
from src.features.chat.domain.interview_docx import InterviewQA
from src.features.chat.domain.vectorization import chunk_text
from src.features.chat.providers.ollama import OllamaClient
from src.features.design.domain.graph import Scenario, Step, score_step
from src.features.sobes.domain.classification import classify_batch
from src.features.sobes.domain.scoring import score_free_answer


def _settings():
    return SimpleNamespace(
        langsmith_tracing=False,
        langsmith_project="tech-interview-agent",
        ollama_model="test-model",
        ollama_embed_model="test-embed",
        embedding_batch_size=16,
        ollama_url="http://localhost:11434",
        ollama_timeout_sec=30,
    )


# --- Pydantic-схемы (структурный вывод) --------------------------------------


class TestScoreResult:
    def test_full_parse(self) -> None:
        obj = ScoreResult(
            score_percent="85",
            covered_points=["a", 1],
            missed_points=[],
            techlead_explanation="Хорошо",
        )
        assert obj.score_percent == 85
        assert obj.covered_points == ["a", "1"]
        assert obj.techlead_explanation == "Хорошо"

    def test_percent_clamped(self) -> None:
        assert ScoreResult(score_percent=150).score_percent == 100
        assert ScoreResult(score_percent=-5).score_percent == 0

    def test_points_capped_to_six(self) -> None:
        obj = ScoreResult(covered_points=[f"p{i}" for i in range(9)])
        assert len(obj.covered_points) == 6

    def test_defaults(self) -> None:
        obj = ScoreResult(score_percent=40)
        assert obj.covered_points == []
        assert obj.missed_points == []
        assert obj.techlead_explanation == ""


class TestDesignScore:
    def test_valid_rubric(self) -> None:
        obj = DesignScore(
            score_percent=80,
            rubric={"reqs": 90, "arch": 80, "data": 70, "scale": 60, "tradeoffs": 50},
            covered_points=["a"],
            missed_points=[],
            techlead_explanation="  Хорошо.  ",
        )
        assert obj.score_percent == 80
        assert obj.to_legacy_tuple(600)[0:2] == (80, {"reqs": 90, "arch": 80, "data": 70, "scale": 60, "tradeoffs": 50})
        assert obj.to_legacy_tuple(3)[4] == "Хор"

    def test_rubric_values_clamped(self) -> None:
        obj = DesignScore(rubric={"reqs": 200, "arch": -1, "data": 0, "scale": 0, "tradeoffs": 0})
        assert obj.rubric["reqs"] == 100
        assert obj.rubric["arch"] == 0

    def test_rubric_wrong_keys_raises(self) -> None:
        with pytest.raises(ValidationError):
            DesignScore(rubric={"reqs": 1, "arch": 1, "data": 1, "scale": 1})


class TestClassificationSchemas:
    def test_row_normalization(self) -> None:
        assert ClassificationRow(level="senior", difficulty_score=5).level == "senior"
        assert ClassificationRow(level="expert", difficulty_score=7).level == "middle"
        assert ClassificationRow(level="junior", difficulty_score=-3).difficulty_score == 0.0
        assert ClassificationRow(topic=12).topic == "12"

    def test_batch_type_adapter(self) -> None:
        rows = ClassificationBatch.validate_python(
            [{"topic": "python", "level": "middle", "difficulty_score": 0.7}]
        )
        assert isinstance(rows, list)
        assert rows[0].topic == "python"
        assert rows[0].level == "middle"


# --- 1A: format="json" у generate --------------------------------------------


class TestFormatJsonPayload:
    def _client(self, monkeypatch, resp_text: str = '{"message":{"content":"ok"}}'):
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        client = OllamaClient(_settings())
        resp = SimpleNamespace(status_code=200, json=lambda: json.loads(resp_text), raise_for_status=lambda: None)
        post = AsyncMock(return_value=resp)
        monkeypatch.setattr(client._http, "post", post)
        return client, post

    async def _run(self, client, **kwargs):
        return await client.generate([{"role": "user", "content": "hi"}], **kwargs)

    def test_format_json_added_to_payload(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(self._run(client, format="json", temperature=0.2))
        payload = post.await_args.kwargs["json"]
        assert payload["format"] == "json"

    def test_no_format_without_kwarg(self, monkeypatch) -> None:
        client, post = self._client(monkeypatch)
        asyncio.run(self._run(client))
        payload = post.await_args.kwargs["json"]
        assert "format" not in payload


# --- 1B: generate_structured на OllamaClient ---------------------------------


class _FakeChain:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages):
        return self._result


class TestGenerateStructured:
    def _client(self, monkeypatch):
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        return OllamaClient(_settings())

    def test_returns_parsed_model(self, monkeypatch) -> None:
        client = self._client(monkeypatch)
        expected = ScoreResult(score_percent=90, covered_points=["a"])
        monkeypatch.setattr(client, "_get_structured_chain", lambda schema: _FakeChain(expected))

        async def run():
            return await client.generate_structured(
                [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
                schema=ScoreResult,
                metadata={"feature": "sobes"},
                tags=["scoring"],
            )

        result = asyncio.run(run())
        assert result is expected
        assert result.score_percent == 90

    def test_returns_none_on_chain_failure(self, monkeypatch) -> None:
        client = self._client(monkeypatch)

        class BrokenChain:
            async def ainvoke(self, messages):
                raise RuntimeError("no model")

        monkeypatch.setattr(client, "_get_structured_chain", lambda schema: BrokenChain())

        async def run():
            return await client.generate_structured(
                [{"role": "user", "content": "u"}], schema=ScoreResult
            )

        assert asyncio.run(run()) is None


# --- 1B: ветки в точках вызова -----------------------------------------------


class _SpyLLM:
    """Фейк с обоими методами: записывает вызовы, отдаёт заскриптованные ответы."""

    def __init__(self, structured=None, text=None):
        self.structured = structured
        self.text = text
        self.generate_calls: list[dict] = []
        self.structured_calls: list[dict] = []

    async def generate(self, messages, **kwargs):
        self.generate_calls.append({"messages": messages, "kwargs": kwargs})
        return self.text

    async def generate_structured(self, messages, *, schema, **kwargs):
        self.structured_calls.append({"messages": messages, "schema": schema, "kwargs": kwargs})
        return self.structured


class TestScoreFreeAnswerStructured:
    def test_structured_path(self) -> None:
        llm = _SpyLLM(structured=ScoreResult(
            score_percent=60,
            covered_points=["x"],
            missed_points=["y"],
            techlead_explanation="Частично.",
        ))
        result = asyncio.run(score_free_answer(
            llm,
            question_text="Что такое GIL?",
            reference_answer="Ссылка",
            user_answer="Ответ",
            pass_threshold=50,
            max_expl_len=600,
            metadata={"feature": "sobes", "session_id": "sX"},
            use_structured=True,
        ))
        assert result[0] == 60
        assert result[1] is True
        assert llm.generate_calls == []  # generate не вызывался
        sc = llm.structured_calls[0]
        assert sc["schema"] is ScoreResult
        assert sc["kwargs"]["tags"] == ["scoring"]
        assert sc["kwargs"]["metadata"]["session_id"] == "sX"

    def test_fallback_when_structured_none(self) -> None:
        llm = _SpyLLM(structured=None, text=json.dumps({
            "score_percent": 40,
            "covered_points": ["x"],
            "missed_points": [],
            "techlead_explanation": "Слабо.",
        }))
        async def run():
            return await score_free_answer(
                llm,
                question_text="q",
                reference_answer="r",
                user_answer="a",
                pass_threshold=50,
                max_expl_len=600,
                use_structured=True,
            )
        result = asyncio.run(run())
        assert result[0] == 40
        assert result[1] is False
        assert len(llm.generate_calls) == 1
        assert llm.generate_calls[0]["kwargs"]["format"] == "json"

    def test_legacy_without_use_structured_still_has_format_json(self) -> None:
        llm = _SpyLLM(text=json.dumps({
            "score_percent": 70,
            "covered_points": [],
            "missed_points": [],
            "techlead_explanation": "Ок.",
        }))
        async def run():
            return await score_free_answer(
                llm,
                question_text="q",
                reference_answer="r",
                user_answer="a",
                pass_threshold=50,
                max_expl_len=600,
            )
        result = asyncio.run(run())
        assert result[0] == 70
        assert llm.generate_calls[0]["kwargs"]["format"] == "json"
        assert llm.structured_calls == []


class TestScoreStepStructured:
    @staticmethod
    def _scenario() -> Scenario:
        return Scenario(
            id="unit-sc",
            title="Unit",
            level="middle",
            summary="S",
            requirements=[],
            nfr=[],
            constraints=[],
            baseline_load={},
            topics=[],
            steps=[Step(id="s1", title="T", prompt="P", expected_points=[], rubric_weights={})],
            acceptance_criteria=[],
            failure_questions=[],
            advanced_questions=[],
        )

    def test_structured_path(self) -> None:
        llm = _SpyLLM(structured=DesignScore(
            score_percent=90,
            rubric={"reqs": 90, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0},
            covered_points=["a"],
            missed_points=[],
            techlead_explanation="Хорошо.",
        ))
        async def run():
            return await score_step(
                llm,
                scenario=self._scenario(),
                step=self._scenario().steps[0],
                user_answer="Ответ",
                history=[],
                hints_used=[],
                hint_penalty=10,
                max_tokens=800,
                max_expl_len=600,
                session_id="sess",
                use_structured=True,
            )
        res = asyncio.run(run())
        assert res.score_percent == 90
        assert llm.generate_calls == []
        assert llm.structured_calls[0]["schema"] is DesignScore
        assert llm.structured_calls[0]["kwargs"]["tags"] == ["scoring"]

    def test_fallback_on_invalid_structured(self) -> None:
        llm = _SpyLLM(structured=None, text=json.dumps({
            "score_percent": 80,
            "rubric": {"reqs": 80, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0},
            "covered_points": [],
            "missed_points": [],
            "techlead_explanation": "Норм.",
        }))
        async def run():
            return await score_step(
                llm,
                scenario=self._scenario(),
                step=self._scenario().steps[0],
                user_answer="Ответ",
                history=[],
                hints_used=[],
                hint_penalty=0,
                max_tokens=800,
                max_expl_len=600,
                use_structured=True,
            )
        res = asyncio.run(run())
        assert res.score_percent == 80
        assert len(llm.generate_calls) == 1
        assert llm.generate_calls[0]["kwargs"]["format"] == "json"


class TestClassifyBatchStructured:
    def _items(self) -> list[InterviewQA]:
        return [InterviewQA(number=1, question="Q1", answer="A1")]

    def test_structured_path(self) -> None:
        llm = _SpyLLM(structured=[
            ClassificationRow(topic="python", level="junior", difficulty_score=0.4),
        ])
        async def run():
            return await classify_batch(
                llm,
                self._items(),
                topics=["python", "db"],
                use_structured=True,
            )
        out = asyncio.run(run())
        assert len(out) == 1
        assert out[0].topic == "python"
        assert out[0].level == "junior"
        assert out[0].difficulty_score == 0.4
        assert llm.generate_calls == []
        assert llm.structured_calls[0]["schema"] is ClassificationBatch

    def test_unknown_topic_falls_to_other(self) -> None:
        llm = _SpyLLM(structured=[
            ClassificationRow(topic="quantum", level="middle", difficulty_score=0.5),
        ])
        async def run():
            return await classify_batch(llm, self._items(), topics=["python"], use_structured=True)
        out = asyncio.run(run())
        assert out[0].topic == "other"

    def test_legacy_path(self) -> None:
        llm = _SpyLLM(text=json.dumps([{"topic": "db", "level": "middle", "difficulty_score": 0.6}]))
        async def run():
            return await classify_batch(llm, self._items(), topics=["python", "db"])
        out = asyncio.run(run())
        assert out[0].topic == "db"
        assert llm.generate_calls[0]["kwargs"]["format"] == "json"


# --- Сценарий 3: chunk_text через RecursiveCharacterTextSplitter -------------


class TestChunkText:
    def test_empty(self) -> None:
        assert chunk_text("   \n\n  ", 100) == []

    def test_short_text_returned_as_is(self) -> None:
        assert chunk_text("Короткий ответ.", 100) == ["Короткий ответ."]

    def test_long_text_split_into_bounded_chunks(self) -> None:
        text = ("Очень длинный параграф про транзакции и уровни изоляции. " * 30).strip()
        chunks = chunk_text(text, max_chunk_chars=200, overlap=0)
        assert chunks
        assert all(len(c) <= 200 for c in chunks)

    def test_paragraphs_merged_up_to_limit(self) -> None:
        text = "\n\n".join([f"Параграф {i} с небольшим содержанием." for i in range(10)])
        chunks = chunk_text(text, max_chunk_chars=150, overlap=0)
        assert len(chunks) < 10
        assert all(len(c) <= 150 for c in chunks)

    def test_invalid_args_raise(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("t", 0)
        with pytest.raises(ValueError):
            chunk_text("t", 100, -1)
        with pytest.raises(ValueError):
            chunk_text("t", 100, 100)