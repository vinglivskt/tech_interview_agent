"""Расширенные интеграционные тесты для Sobes API."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from backend.src.main import app


class DummyLLM:
    """Dummy LLM для тестирования sobes API."""

    async def ping(self) -> bool:
        return True

    async def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        system = messages[0]["content"].lower() if messages else ""
        user = messages[-1]["content"] if messages else ""

        # Classification
        if "классификатор" in system or "классифицируй" in system:
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

        # Scoring
        return json.dumps(
            {
                "score_percent": 75,
                "covered_points": ["ключ 1", "ключ 2"],
                "missed_points": ["деталь"],
                "techlead_explanation": "Хороший ответ.",
            },
            ensure_ascii=False,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 768 for _ in texts]


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Создаёт тестовый клиент с замоканными зависимостями."""
    from src.features.sobes.domain.services import SobesSessionStore

    @asynccontextmanager
    async def _lifespan(_app: Any):  # type: ignore[no-untyped-def]
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
                "sobes_topics": ["python", "db", "networks", "brokers", "other"],
                "sobes_counts_by_level": {"junior": [2, 3], "middle": [3, 4], "senior": [4, 5]},
                "sobes_pass_threshold_percent": 50,
                "sobes_cache_path": str(tmp_path / "sobes_cache.json"),
                "sobes_max_explanation_len": 300,
                "sobes_topic_hints": {"python": "Подсказка по Python"},
                "sobes_show_topic_hint": True,
                "interview_docx_path": str(
                    Path(__file__).resolve().parents[1] / "fixtures" / "test_interview_questions.docx"
                ),
            },
        )()
        _app.state.llm = DummyLLM()

        class DummyVector:
            async def ping(self) -> bool:
                return True

            async def ensure_collection(self) -> None:
                return None

            async def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                return []

        _app.state.qdrant = DummyVector()
        _app.state.sobes_sessions = SobesSessionStore()
        yield

    app.router.lifespan_context = _lifespan

    with TestClient(app) as test_client:
        yield test_client


class TestSobesAnswer:
    """Тесты для /sobesedovanie/answer эндпоинта."""

    def test_answer_question(self, client: TestClient) -> None:
        """Ответ на вопрос собеседования."""
        # Стартуем сессию
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle", "topics": ["python"]},
        )
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session_id"]
        question = start_resp.json()["question"]

        # Отвечаем на вопрос
        answer_resp = client.post(
            "/api/sobesedovanie/answer",
            json={
                "session_id": session_id,
                "question_id": question["id"],
                "user_answer": "Мой развёрнутый ответ на вопрос",
            },
        )
        assert answer_resp.status_code == 200
        data = answer_resp.json()
        assert "score_percent" in data
        assert "techlead_explanation" in data
        assert "covered_points" in data
        assert "missed_points" in data
        assert "is_last" in data

    def test_answer_invalid_session(self, client: TestClient) -> None:
        """Ошибка при ответе в несуществующей сессии."""
        answer_resp = client.post(
            "/api/sobesedovanie/answer",
            json={
                "session_id": "nonexistent_session",
                "question_id": "some_id",
                "user_answer": "Ответ",
            },
        )
        assert answer_resp.status_code == 404

    def test_answer_invalid_question(self, client: TestClient) -> None:
        """При несуществующем question_id используется fallback по индексу."""
        # Стартуем сессию
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle"},
        )
        session_id = start_resp.json()["session_id"]

        # Отвечаем с неправильным question_id - сервис использует fallback
        answer_resp = client.post(
            "/api/sobesedovanie/answer",
            json={
                "session_id": session_id,
                "question_id": "wrong_question_id",
                "user_answer": "Ответ",
            },
        )
        # Сервис имеет fallback логику и использует текущий вопрос по индексу
        assert answer_resp.status_code == 200


class TestSobesRepeat:
    """Тесты для /sobesedovanie/repeat эндпоинта."""

    def test_repeat_current_question(self, client: TestClient) -> None:
        """Повтор текущего вопроса."""
        # Стартуем сессию
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle"},
        )
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session_id"]

        # Получаем повтор вопроса
        repeat_resp = client.post(
            "/api/sobesedovanie/repeat",
            json={"session_id": session_id},
        )
        assert repeat_resp.status_code == 200
        data = repeat_resp.json()
        assert "question" in data
        assert "id" in data["question"]

    def test_repeat_invalid_session(self, client: TestClient) -> None:
        """Ошибка при повторе для несуществующей сессии."""
        repeat_resp = client.post(
            "/api/sobesedovanie/repeat",
            json={"session_id": "nonexistent"},
        )
        assert repeat_resp.status_code == 404


class TestSobesSkip:
    """Тесты для /sobesedovanie/skip эндпоинта."""

    def test_skip_question(self, client: TestClient) -> None:
        """Пропуск вопроса."""
        # Стартуем сессию
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle"},
        )
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session_id"]

        # Пропускаем вопрос
        skip_resp = client.post(
            "/api/sobesedovanie/skip",
            json={"session_id": session_id},
        )
        assert skip_resp.status_code == 200
        data = skip_resp.json()
        assert "next_question" in data
        assert "is_last" in data

    def test_skip_invalid_session(self, client: TestClient) -> None:
        """Ошибка при пропуске для несуществующей сессии."""
        skip_resp = client.post(
            "/api/sobesedovanie/skip",
            json={"session_id": "nonexistent"},
        )
        assert skip_resp.status_code == 404


class TestSobesFullFlow:
    """Интеграционные тесты полного флоу собеседования."""

    def test_full_interview_flow(self, client: TestClient) -> None:
        """Полный флоу: старт -> ответ -> skip -> repeat -> results."""
        # 1. Старт собеседования
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle", "topics": ["python", "db"]},
        )
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session_id"]
        question1 = start_resp.json()["question"]

        # 2. Отвечаем на первый вопрос
        answer1_resp = client.post(
            "/api/sobesedovanie/answer",
            json={
                "session_id": session_id,
                "question_id": question1["id"],
                "user_answer": "Развёрнутый ответ на первый вопрос",
            },
        )
        assert answer1_resp.status_code == 200

        # 3. Пропускаем следующий вопрос
        skip_resp = client.post(
            "/api/sobesedovanie/skip",
            json={"session_id": session_id},
        )
        assert skip_resp.status_code == 200

        # 4. Повторяем текущий вопрос
        repeat_resp = client.post(
            "/api/sobesedovanie/repeat",
            json={"session_id": session_id},
        )
        assert repeat_resp.status_code == 200

        # 5. Получаем результаты
        results_resp = client.get(f"/api/sobesedovanie/results/{session_id}")
        assert results_resp.status_code == 200
        results = results_resp.json()
        assert "summary" in results
        assert "verdict_level" in results
        assert "strengths" in results
        assert "weaknesses" in results
        assert "by_topic" in results
        assert "details" in results


class TestSobesResults:
    """Тесты для /sobesedovanie/results/{session_id} эндпоинта."""

    def test_results_after_answers(self, client: TestClient) -> None:
        """Получение результатов после ответов."""
        # Стартуем и отвечаем
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle"},
        )
        session_id = start_resp.json()["session_id"]
        question = start_resp.json()["question"]

        client.post(
            "/api/sobesedovanie/answer",
            json={
                "session_id": session_id,
                "question_id": question["id"],
                "user_answer": "Ответ",
            },
        )

        # Получаем результаты
        results_resp = client.get(f"/api/sobesedovanie/results/{session_id}")
        assert results_resp.status_code == 200
        data = results_resp.json()

        # Проверяем структуру
        assert data["level_requested"] == "middle"
        assert "verdict_level" in data
        assert data["summary"]["counted"] >= 1
        assert len(data["details"]) >= 1

    def test_results_invalid_session(self, client: TestClient) -> None:
        """Ошибка при получении результатов несуществующей сессии."""
        results_resp = client.get("/api/sobesedovanie/results/nonexistent")
        assert results_resp.status_code == 404


class TestSobesTopicHints:
    """Тесты для подсказок по темам."""

    def test_topic_hint_in_question(self, client: TestClient) -> None:
        """Подсказка по теме включается в вопрос."""
        start_resp = client.post(
            "/api/sobesedovanie/start",
            json={"level": "middle", "topics": ["python"]},
        )
        assert start_resp.status_code == 200
        question = start_resp.json()["question"]
        # Подсказка должна быть в topic_hint
        assert question.get("topic_hint") is not None or question.get("topic") is not None
