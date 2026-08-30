"""Регресс-тест на баг B1.

До фикса эндпоинт /api/sobesedovanie/start пытался вернуть dataclass
SobesQuestion как поле Pydantic-модели SobesStartResponse.question, что
приводило к ValidationError (или к пустому text, в зависимости от версии
FastAPI/Pydantic). Тест проверяет, что в ответе присутствуют все поля DTO
и они непустые.
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app


class DummyLLM:
    async def ping(self):
        return True

    async def generate(self, messages, **kwargs):
        system = messages[0]["content"].lower() if messages else ""
        user = messages[-1]["content"] if messages else ""
        if "классификатор" in system:
            m = re.search(r"(\[.*\])", user, re.S)
            arr = []
            if m:
                try:
                    arr = json.loads(m.group(1))
                except Exception:
                    arr = []
            out = []
            for it in arr:
                out.append(
                    {
                        "number": it.get("number", 0),
                        "topic": "python",
                        "level": "middle",
                        "difficulty_score": 0.3,
                    }
                )
            return json.dumps(out, ensure_ascii=False)
        return json.dumps(
            {
                "score_percent": 80,
                "covered_points": ["ключ 1"],
                "missed_points": ["деталь"],
                "techlead_explanation": "Ответ в целом верный.",
            },
            ensure_ascii=False,
        )

    async def embed(self, texts):
        return [[0.0] * 768 for _ in texts]


@pytest.fixture
def client(tmp_path):
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
                "sobes_topics": ["python", "other"],
                "sobes_counts_by_level": {"junior": [1, 2], "middle": [1, 2], "senior": [1, 2]},
                "sobes_pass_threshold_percent": 50,
                "sobes_cache_path": str(tmp_path / "sobes_cache.json"),
                "sobes_max_explanation_len": 300,
                "sobes_show_topic_hint": True,
                "sobes_topic_hints": {"python": "уточни контекст"},
                "sobes_enrich_questions": False,
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


def test_sobes_start_returns_valid_dto(client):
    """Регресс на B1: /start возвращает DTO, а не dataclass.

    Проверяет, что в JSON есть все обязательные поля DTO и они непустые.
    До фикса Pydantic выкидывал ValidationError.
    """
    r = client.post("/api/sobesedovanie/start", json={"level": "middle", "topics": ["python"]})
    assert r.status_code == 200, r.text
    data = r.json()

    # Внешний контракт
    assert data["session_id"].startswith("sobes_")
    assert isinstance(data["total_planned"], int)
    assert data["total_planned"] >= 1

    # Контракт вопроса (SobesQuestionDTO)
    q = data["question"]
    assert isinstance(q["id"], str) and q["id"]
    assert isinstance(q["number"], int) and q["number"] >= 1
    assert isinstance(q["text"], str) and q["text"].strip(), "question.text не должен быть пустым"
    assert isinstance(q["topic"], str) and q["topic"]
    assert q["level"] in {"junior", "middle", "senior"}
    assert isinstance(q["difficulty_score"], (int, float))
    assert 0.0 <= q["difficulty_score"] <= 1.0
    # topic_hint может быть None — это допустимо
    assert "topic_hint" in q
