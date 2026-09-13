import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.core.langsmith import make_traced_generate, tracing_ready
from src.features.chat.domain.services import run_chat
from src.features.chat.providers.ollama import OllamaClient
from src.features.design.domain.graph import Scenario, Step, score_step
from src.features.sobes.domain.scoring import score_free_answer


def _settings(tracing: bool = False, project: str = "tech-interview-agent"):
    return SimpleNamespace(
        langsmith_tracing=tracing,
        langsmith_project=project,
        ollama_model="test-model",
        ollama_embed_model="test-embed",
        embedding_batch_size=16,
        ollama_url="http://localhost:11434",
        ollama_timeout_sec=30,
    )


async def _raw_stub(messages, *, temperature=None, max_tokens=None, **kwargs):
    return "stub-ok"


# --- tracing_ready -----------------------------------------------------------


def test_tracing_ready_flag_off(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test")
    assert tracing_ready(_settings(tracing=False)) is False


def test_tracing_ready_flag_on_without_key(monkeypatch, caplog):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    with caplog.at_level(logging.WARNING, logger="src.core.langsmith"):
        assert tracing_ready(_settings(tracing=True)) is False
    assert "LANGSMITH_API_KEY" in caplog.text


def test_tracing_ready_flag_on_with_key(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test")
    assert tracing_ready(_settings(tracing=True)) is True


# --- make_traced_generate ----------------------------------------------------


def test_make_traced_generate_disabled(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert make_traced_generate(_raw_stub, settings=_settings(tracing=False)) is None


def test_make_traced_generate_enabled(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test")
    captured: dict = {}

    def fake_traceable(**trace_kwargs):
        captured.update(trace_kwargs)

        def decorator(func):
            return func

        return decorator

    monkeypatch.setattr("langsmith.traceable", fake_traceable)
    wrapper = make_traced_generate(
        _raw_stub,
        settings=_settings(tracing=True, project="project-x"),
        base_metadata={"provider": "ollama", "model": "m"},
        base_tags=["llm"],
    )
    assert wrapper is _raw_stub
    assert captured["name"] == "llm.generate"
    assert captured["run_type"] == "llm"
    assert captured["project_name"] == "project-x"
    assert captured["metadata"] == {"provider": "ollama", "model": "m"}
    assert captured["tags"] == ["llm"]


# --- OllamaClient.generate ---------------------------------------------------


def test_generate_untraced_calls_raw(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    client = OllamaClient(_settings(tracing=False))
    assert client._traced_generate is None

    raw = AsyncMock(return_value="ok")
    monkeypatch.setattr(client, "_raw_generate", raw)

    async def run():
        return await client.generate(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,
            metadata={"feature": "chat", "session_id": "s1"},
            tags=["answer"],
        )

    assert asyncio.run(run()) == "ok"
    assert raw.await_count == 1
    assert "metadata" not in raw.await_args.kwargs
    assert "tags" not in raw.await_args.kwargs
    assert raw.await_args.kwargs["temperature"] == 0.5


def test_generate_traced_sets_context(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test")
    client = OllamaClient(_settings(tracing=True))
    context_calls: list[dict] = []

    class FakeTC:
        def __init__(self, **kwargs):
            context_calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    traced = AsyncMock(return_value="traced-ok")
    monkeypatch.setattr(client, "_traced_generate", traced)
    monkeypatch.setattr("langsmith.tracing_context", FakeTC)

    async def run():
        return await client.generate(
            [{"role": "user", "content": "hi"}],
            metadata={"feature": "chat", "session_id": "s9"},
            tags=["answer", "extra"],
        )

    assert asyncio.run(run()) == "traced-ok"
    assert len(context_calls) == 1
    assert context_calls[0]["metadata"]["feature"] == "chat"
    assert context_calls[0]["metadata"]["session_id"] == "s9"
    assert context_calls[0]["tags"] == ["answer", "extra"]
    assert "metadata" not in traced.await_args.kwargs
    assert "tags" not in traced.await_args.kwargs


# --- run_chat прокидывает metadata/tags --------------------------------------


class _RecorderLLM:
    """Фейк-LLM: отдаёт ответы по очереди и записывает kwargs generate-вызовов."""

    def __init__(self, answers: list[str]):
        self._answers = list(answers)
        self.call_kwargs: list[dict] = []

    async def generate(self, messages, **kwargs):
        self.call_kwargs.append(kwargs)
        return self._answers.pop(0)


def _chat_settings(tmp_path: Path) -> SimpleNamespace:
    (tmp_path / "system.md").write_text("Ты помощник.", encoding="utf-8")
    (tmp_path / "question.md").write_text("Ты помощник для вопросов.", encoding="utf-8")
    return SimpleNamespace(
        system_prompt_path=str(tmp_path / "system.md"),
        interview_top_k=5,
        rag_score_threshold=0.5,
        rag_high_score_threshold=0.85,
        session_history_limit=20,
        sobes_pass_threshold_percent=50,
        interview_docx_path=str(tmp_path / "none.docx"),
    )


def _run_chat(settings, llm, user_message, question_type):
    async def run():
        return await run_chat(
            settings,
            llm,
            SimpleNamespace(),  # vectorstore: без search_payload -> нет RAG
            user_message,
            embedder=None,
            question_type=question_type,
            metadata={"feature": "chat", "session_id": "sX", "question_type": question_type},
        )

    return asyncio.run(run())


def test_run_chat_three_call_sites_get_metadata(tmp_path):
    settings = _chat_settings(tmp_path)
    llm = _RecorderLLM([
        "Ассистентский ответ на русском с рерайтом 好",  # 1-й вызов: есть CJK
        "Исправленный ответ без иероглифов",  # 2-й вызов: рерайт (без CJK)
        "Проверенный полный ответ." * 20,  # 3-й вызов: self-check (≥100 симв.)
    ])
    _run_chat(settings, llm, "Что такое GIL?", "direct_question")

    assert len(llm.call_kwargs) == 3
    assert llm.call_kwargs[0]["tags"] == ["answer"]
    assert llm.call_kwargs[1]["tags"] == ["rus-rewrite"]
    assert llm.call_kwargs[2]["tags"] == ["self-check"]
    for kwargs in llm.call_kwargs:
        assert kwargs["metadata"]["feature"] == "chat"
        assert kwargs["metadata"]["session_id"] == "sX"


def test_run_chat_without_metadata_is_plain(tmp_path):
    settings = _chat_settings(tmp_path)
    llm = _RecorderLLM(["Обычный ответ без иероглифов и без рерайта."])

    async def run():
        return await run_chat(
            settings,
            llm,
            SimpleNamespace(),
            "Что такое GIL?",
            embedder=None,
        )

    asyncio.run(run())
    assert len(llm.call_kwargs) == 1
    assert llm.call_kwargs[0].get("metadata") is None
    assert llm.call_kwargs[0].get("tags") == ["answer"]


# --- design score_step -------------------------------------------------------


def test_design_score_step_metadata(monkeypatch):
    scenario = Scenario(
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
    step = scenario.steps[0]
    llm = _RecorderLLM([json.dumps({
        "score_percent": 90,
        "rubric": {"reqs": 90, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0},
        "covered_points": ["a"],
        "missed_points": [],
        "techlead_explanation": "Хорошо.",
    })])

    async def run():
        return await score_step(
            llm,
            scenario=scenario,
            step=step,
            user_answer="Ответ",
            history=[],
            hints_used=[],
            hint_penalty=10,
            max_tokens=800,
            max_expl_len=600,
            session_id="sess-123",
        )

    res = asyncio.run(run())
    assert res.score_percent == 90
    kwargs = llm.call_kwargs[0]
    assert kwargs["tags"] == ["scoring"]
    assert kwargs["metadata"]["feature"] == "design"
    assert kwargs["metadata"]["scenario_id"] == "unit-sc"
    assert kwargs["metadata"]["step_id"] == "s1"
    assert kwargs["metadata"]["session_id"] == "sess-123"


# --- sobes score_free_answer -------------------------------------------------


def test_sobes_scoring_metadata():
    llm = _RecorderLLM([json.dumps({
        "score_percent": 60,
        "covered_points": ["x"],
        "missed_points": ["y"],
        "techlead_explanation": "Частично.",
    })])

    async def run():
        return await score_free_answer(
            llm,
            question_text="Что такое GIL?",
            reference_answer="Ссылка",
            user_answer="Глобальная блокировка интерпретатора",
            pass_threshold=50,
            max_expl_len=600,
            metadata={"feature": "sobes", "session_id": "sX", "topic": "python"},
        )

    percent, counted, *_ = asyncio.run(run())
    assert (percent, counted) == (60, True)
    kwargs = llm.call_kwargs[0]
    assert kwargs["tags"] == ["scoring"]
    assert kwargs["metadata"]["feature"] == "sobes"
    assert kwargs["metadata"]["session_id"] == "sX"
    assert kwargs["metadata"]["topic"] == "python"