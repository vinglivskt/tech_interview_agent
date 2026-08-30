"""Регресс-тест на контракт quiz options.

До рефакторинга фронт ожидал options как [{index, text}], а бэкенд отдавал
list[str]. Это ломало UI (пустые лейблы) и приводило к 422 на /quiz/answer,
когда selected_index был undefined.

Тест фиксирует контракт: options — массив из 4 непустых строк.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app


class DummyLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def ping(self) -> bool:
        return True

    async def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls += 1
        return "Правильный ответ"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 768 for _ in texts]


@pytest.fixture
def client(tmp_path):
    import src.features.quiz.api.router as quiz_router

    quiz_router._quiz_session_store = None

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.settings = type(
            "S",
            (),
            {
                "chat_max_message_length": 4000,
                "cors_allow_origins": ["*"],
                "session_store_max_sessions": 10,
                "session_history_limit": 20,
                "ingest_interval_hours": 9999,
                "interview_top_k": 5,
                "interview_docx_path": str(
                    Path(__file__).resolve().parents[1] / "fixtures" / "test_interview_questions.docx"
                ),
            },
        )()
        _app.state.llm = DummyLLM()

        class DummyVector:
            async def ping(self):
                return True

            async def ensure_collection(self):
                return None

            async def search(self, *_, **__):
                return []

        _app.state.qdrant = DummyVector()
        yield

    app.router.lifespan_context = _lifespan
    with TestClient(app) as c:
        yield c


def test_quiz_options_are_strings(client):
    """Контракт: /quiz/start возвращает options: list[str] из 4 непустых элементов."""
    r = client.post("/api/quiz/start", json={"level": "middle"})
    assert r.status_code == 200, r.text
    data = r.json()

    assert "options" in data
    opts = data["options"]
    assert isinstance(opts, list), "options должен быть массивом"
    assert len(opts) == 4, f"ожидалось 4 варианта, получено {len(opts)}"
    for i, opt in enumerate(opts):
        assert isinstance(opt, str), f"options[{i}] должен быть строкой, а не {type(opt).__name__}"
        assert opt.strip(), f"options[{i}] не должен быть пустым"

    # Контракт next_question (после ответа)
    sid = data["session_id"]
    qid = data["question_id"]
    r2 = client.post(
        "/api/quiz/answer",
        json={"session_id": sid, "question_id": qid, "selected_index": 0},
    )
    assert r2.status_code == 200, r2.text
    ans = r2.json()
    # На последнем вопросе next_question может быть None; в нашем случае квиз из 20,
    # так что next_question обязан быть.
    assert ans.get("next_question") is not None
    n_opts = ans["next_question"]["options"]
    assert isinstance(n_opts, list) and len(n_opts) == 4
    for i, opt in enumerate(n_opts):
        assert isinstance(opt, str) and opt.strip(), f"next_question.options[{i}] должен быть непустой строкой"
