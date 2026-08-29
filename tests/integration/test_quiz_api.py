"""Интеграционные тесты для Quiz API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


class DummyLLM:
    """Dummy LLM для тестирования quiz API."""

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
def client(monkeypatch, tmp_path):
    """Создаёт тестовый клиент с замоканными зависимостями."""
    # Сбрасываем глобальное состояние между тестами
    import app.features.quiz.api.router as quiz_router
    from app.features.quiz.domain.services import QuizSessionStore

    quiz_router._quiz_session_store = None

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
                "interview_docx_path": str(
                    Path(__file__).resolve().parents[1] / "fixtures" / "test_interview_questions.docx"
                ),
                "quiz_questions_count": 20,
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
        _app.state.quiz_sessions = QuizSessionStore()
        yield

    app.router.lifespan_context = _lifespan

    with TestClient(app) as test_client:
        yield test_client

    # Очищаем глобальное состояние после теста
    quiz_router._quiz_session_store = None


class TestQuizStart:
    """Тесты для /quiz/start эндпоинта."""

    def test_start_quiz_junior_level(self, client: TestClient) -> None:
        """Старт квиза с junior уровнем."""
        response = client.post("/api/quiz/start", json={"level": "junior"})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "question_id" in data
        assert "question_text" in data
        assert len(data["options"]) == 4
        assert data["question_number"] == 1
        assert data["total_questions"] == 20

    def test_start_quiz_middle_level(self, client: TestClient) -> None:
        """Старт квиза с middle уровнем (по умолчанию)."""
        response = client.post("/api/quiz/start", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["question_number"] == 1

    def test_start_quiz_senior_level(self, client: TestClient) -> None:
        """Старт квиза с senior уровнем."""
        response = client.post("/api/quiz/start", json={"level": "senior"})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data


class TestQuizAnswer:
    """Тесты для /quiz/answer эндпоинта."""

    def test_submit_answer_correct(self, client: TestClient) -> None:
        """Отправка правильного ответа."""
        # Сначала стартуем квиз
        start_resp = client.post("/api/quiz/start", json={"level": "junior"})
        assert start_resp.status_code == 200
        session_data = start_resp.json()
        session_id = session_data["session_id"]
        question_id = session_data["question_id"]

        # Отправляем ответ
        answer_resp = client.post(
            "/api/quiz/answer",
            json={
                "session_id": session_id,
                "question_id": question_id,
                "selected_index": 0,
            },
        )
        assert answer_resp.status_code == 200
        data = answer_resp.json()
        assert "is_correct" in data
        assert "correct_index" in data
        assert "explanation" in data
        assert "is_last" in data

    def test_submit_answer_wrong_session(self, client: TestClient) -> None:
        """Ошибка при несуществующей сессии."""
        answer_resp = client.post(
            "/api/quiz/answer",
            json={
                "session_id": "nonexistent_session",
                "question_id": "some_question",
                "selected_index": 0,
            },
        )
        assert answer_resp.status_code == 404

    def test_submit_answer_wrong_question(self, client: TestClient) -> None:
        """Ошибка при несуществующем вопросе."""
        # Стартуем квиз
        start_resp = client.post("/api/quiz/start", json={"level": "junior"})
        session_id = start_resp.json()["session_id"]

        # Отправляем ответ с неправильным question_id
        answer_resp = client.post(
            "/api/quiz/answer",
            json={
                "session_id": session_id,
                "question_id": "wrong_question_id",
                "selected_index": 0,
            },
        )
        # Должен вернуть 404 или обработать ошибку
        assert answer_resp.status_code in (404, 400)


class TestQuizResults:
    """Тесты для /quiz/results/{session_id} эндпоинта."""

    def test_get_results_after_answers(self, client: TestClient) -> None:
        """Получение результатов после ответов."""
        # Стартуем квиз
        start_resp = client.post("/api/quiz/start", json={"level": "junior"})
        session_id = start_resp.json()["session_id"]
        question_id = start_resp.json()["question_id"]

        # Отправляем ответ
        client.post(
            "/api/quiz/answer",
            json={
                "session_id": session_id,
                "question_id": question_id,
                "selected_index": 0,
            },
        )

        # Получаем результаты
        results_resp = client.get(f"/api/quiz/results/{session_id}")
        assert results_resp.status_code == 200
        data = results_resp.json()
        assert "total_score" in data
        assert "total_questions" in data
        assert "level" in data
        assert "results" in data

    def test_get_results_nonexistent_session(self, client: TestClient) -> None:
        """Ошибка при несуществующей сессии."""
        results_resp = client.get("/api/quiz/results/nonexistent_session")
        assert results_resp.status_code == 404


class TestQuizFlow:
    """Интеграционные тесты полного флоу квиза."""

    def test_full_quiz_flow(self, client: TestClient) -> None:
        """Полный флоу: старт -> ответы -> результаты."""
        # 1. Старт квиза
        start_resp = client.post("/api/quiz/start", json={"level": "middle"})
        assert start_resp.status_code == 200
        session_data = start_resp.json()
        session_id = session_data["session_id"]

        # 2. Отвечаем на несколько вопросов
        for i in range(3):
            # Получаем текущий вопрос
            current_question_id = session_data["question_id"]

            # Отправляем ответ
            answer_resp = client.post(
                "/api/quiz/answer",
                json={
                    "session_id": session_id,
                    "question_id": current_question_id,
                    "selected_index": i % 4,
                },
            )
            assert answer_resp.status_code == 200
            answer_data = answer_resp.json()

            # Проверяем структуру ответа
            assert "is_correct" in answer_data
            assert "is_last" in answer_data

            # Если есть следующий вопрос - получаем его
            if answer_data.get("next_question"):
                session_data = answer_data["next_question"]

        # 3. Получаем финальные результаты
        results_resp = client.get(f"/api/quiz/results/{session_id}")
        assert results_resp.status_code == 200
        results = results_resp.json()
        assert results["total_questions"] > 0
        assert len(results["results"]) > 0

    def test_quiz_session_isolation(self, client: TestClient) -> None:
        """Проверка изоляции сессий - разные пользователи получают разные сессии."""
        # Создаём две сессии
        resp1 = client.post("/api/quiz/start", json={"level": "junior"})
        resp2 = client.post("/api/quiz/start", json={"level": "senior"})

        session_id_1 = resp1.json()["session_id"]
        session_id_2 = resp2.json()["session_id"]

        assert session_id_1 != session_id_2

        # Результаты одной сессии не должны влиять на другую
        results1 = client.get(f"/api/quiz/results/{session_id_1}")
        results2 = client.get(f"/api/quiz/results/{session_id_2}")

        assert results1.status_code == 200
        assert results2.status_code == 200
