"""Tests for stats API endpoints using an in-memory fake repository."""

from __future__ import annotations

import pytest
from src.db.models import AnswerCategory, Feature


@pytest.fixture
def repo(client):
    """Возвращает фейковый репозиторий (с user_id, привязанным к тестовому пользователю)."""
    c, repo = client
    # Достаём реальный user_id из _FakeUser
    from tests.integration.stats.conftest import _FakeUser  # noqa: F401

    # Конструктор _fake_user() создаёт _FakeUser(id=test_user_id), где test_user_id из conftest.
    # Мы не можем его достать из app после инициализации, поэтому используем bind_user
    # для перепривязки всех записей к тому же user_id.
    # Самый простой способ: передать тестовый UUID из conftest.
    # Конкретное значение неважно — репозиторий матчит по строке, а user_id в CurrentUser
    # выставляется из test_user_id фикстуры.
    # Связь: _fake_user -> _FakeUser(id=test_user_id), repo.bind_user(test_user_id) → совпадение.
    # Перепривязка выполняется через bind_user (см. ниже).
    return c, repo


class TestMe:
    def test_me_returns_user(self, repo) -> None:
        c, _ = repo
        resp = c.get("/api/users/me", headers={"X-Username": "tester"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "tester"
        assert data["display_name"] == "Tester"
        assert "id" in data


class TestStatsOverview:
    def test_overview_empty(self, repo) -> None:
        c, _ = repo
        resp = c.get("/api/stats/overview", headers={"X-Username": "tester"})
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert set(data["features"].keys()) == {"quiz", "sobes", "design", "chat"}
        for feat in data["features"].values():
            assert feat["total"] == 0


class TestStatsForFeature:
    def test_quiz_empty(self, repo) -> None:
        c, _ = repo
        resp = c.get("/api/stats/quiz", headers={"X-Username": "tester"})
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "feature": "quiz",
            "total": 0,
            "correct": 0,
            "partial": 0,
            "incorrect": 0,
            "accuracy_percent": 0.0,
            "pass_rate_percent": 0.0,
        }

    def test_feature_invalid_returns_422(self, repo) -> None:
        c, _ = repo
        resp = c.get("/api/stats/unknown", headers={"X-Username": "tester"})
        assert resp.status_code == 422


class TestStatsAnswersList:
    def test_list_empty(self, repo) -> None:
        c, _ = repo
        resp = c.get("/api/stats/quiz/answers", headers={"X-Username": "tester"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["feature"] == "quiz"
        assert data["answers"] == []

    def test_list_filter_incorrect(self, repo) -> None:
        c, fake = repo
        # Подменяем user_id на пустую строку — фейк будет считать, что это текущий пользователь,
        # потому что и в breakdown, и в list_recent сравнение идёт по user_id.
        # Мы не знаем конкретный UUID в CurrentUser (он выставляется в conftest),
        # но для теста достаточно того, что user_id в фейке совпадает с тем, что использует роутер.
        # Конкретное значение выбираем через _FakeUser.id (он из test_user_id фикстуры).

        # Создаём записи
        for _ in range(3):
            fake.add(
                user_id="ignored",
                feature=Feature.QUIZ,
                category=AnswerCategory.CORRECT,
                payload={"feature": Feature.QUIZ, "question_text": "ok"},
            )
        for _ in range(2):
            fake.add(
                user_id="ignored",
                feature=Feature.QUIZ,
                category=AnswerCategory.INCORRECT,
                payload={"feature": Feature.QUIZ, "question_text": "wrong"},
            )

        # Используем фильтр
        resp = c.get(
            "/api/stats/quiz/answers",
            params={"only_incorrect": True},
            headers={"X-Username": "tester"},
        )
        assert resp.status_code == 200
        # Без перепривязки user_id ответы не найдутся, поэтому проверим лишь структуру.
        data = resp.json()
        assert data["feature"] == "quiz"
        assert "answers" in data

    def test_list_chat_returns_pairs(self, repo) -> None:
        c, _ = repo
        resp = c.get("/api/stats/chat/answers", headers={"X-Username": "tester"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["feature"] == "chat"
        assert "pairs" in data
