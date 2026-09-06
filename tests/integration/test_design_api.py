import json
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from src.db.repository import DesignScenariosRepository

from backend.src.main import app


class FakeSessionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSessionMaker:
    """Имитирует async_sessionmaker: config()/start() работают без PostgreSQL."""

    def __call__(self) -> FakeSessionContext:
        return FakeSessionContext()


class DummyLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return "not json"
        return json.dumps(
            {
                "score_percent": 80,
                "rubric": {"reqs": 80, "arch": 80, "data": 80, "scale": 80, "tradeoffs": 80},
                "covered_points": ["ключевой пункт"],
                "missed_points": ["одна деталь"],
                "techlead_explanation": "Корректное решение.",
            }
        )


async def _list_brief(_self, **kwargs):
    return [
        {
            "id": "movie-seat-booking",
            "title": "Movie Seat Booking",
            "level": "middle",
            "category": "ecommerce",
            "primary_pattern": "event-driven + state machine",
            "summary": "Резервирование мест в кинотеатре с конкурентным доступом.",
            "is_detailed": False,
        }
    ]


async def _list_categories(_self, **kwargs):
    return [{"id": "ecommerce", "count": 1}]


async def _get(_self, scenario_id, **kwargs):
    return None


async def _get_random(_self, **kwargs):
    return None


async def _count(_self, **kwargs):
    return 1


@pytest.fixture
def client(monkeypatch):
    @asynccontextmanager
    async def _lifespan(application):
        application.state.settings = type(
            "Settings",
            (),
            {
                "design_levels": ["junior", "middle", "senior"],
                "design_hint_penalty_percent": 10,
                "design_pass_threshold_percent": 50,
                "design_max_explanation_len": 600,
                "design_max_tokens": 800,
                "design_scenarios_path": "backend/prompts/design/scenarios.yaml",
                "design_library_path": "backend/prompts/design/library.yaml",
            },
        )()
        application.state.llm = DummyLLM()
        yield

    # Заменяем БД: фабрика сессий + методы репозитория (без PostgreSQL).
    monkeypatch.setattr(
        "src.features.design.domain.services.session_factory",
        FakeSessionMaker,
    )
    monkeypatch.setattr(DesignScenariosRepository, "list_brief", _list_brief)
    monkeypatch.setattr(DesignScenariosRepository, "list_categories", _list_categories)
    monkeypatch.setattr(DesignScenariosRepository, "get", _get)
    monkeypatch.setattr(DesignScenariosRepository, "get_random", _get_random)
    monkeypatch.setattr(DesignScenariosRepository, "count", _count)

    app.router.lifespan_context = _lifespan
    with TestClient(app) as test_client:
        yield test_client


def test_design_config_returns_expanded_library(client):
    config = client.get("/api/design/config")
    assert config.status_code == 200

    payload = config.json()
    scenarios = payload["scenarios"]
    ids = {row["id"] for row in scenarios}
    # Детальные сценарии из scenarios.yaml
    assert {"url-shortener", "news-feed", "object-storage"} <= ids
    # Расширенная библиотека тем
    assert len(ids) >= 100
    # is_detailed выставляется только для сценариев с шагами
    by_id = {row["id"]: row for row in scenarios}
    assert by_id["url-shortener"]["is_detailed"] is True
    assert by_id["movie-seat-booking"]["is_detailed"] is False
    # Краткое описание рядом с названием
    assert by_id["movie-seat-booking"]["summary"]
    assert by_id["url-shortener"]["summary"]
    assert all("summary" in row for row in scenarios)

    category_ids = {cat["id"] for cat in payload["categories"]}
    assert {"cdn", "geo", "kafka", "pattern", "ecommerce"} <= category_ids
    assert payload["total_scenarios"] == len(ids)
    assert payload["levels"] == ["junior", "middle", "senior"]


def test_design_config_and_happy_path_with_hint_penalty(client):
    config = client.get("/api/design/config")
    assert config.status_code == 200

    started = client.post(
        "/api/design/start", json={"level": "junior", "scenario_id": "url-shortener"}
    )
    assert started.status_code == 200
    data = started.json()
    session_id, step = data["session_id"], data["step"]
    assert step["id"] == "clarify"

    hint = client.post("/api/design/hint", json={"session_id": session_id, "step_id": step["id"]})
    assert hint.status_code == 200
    assert hint.json()["penalty_applied_percent"] == 10

    answer = client.post(
        "/api/design/answer",
        json={
            "session_id": session_id,
            "step_id": step["id"],
            "user_answer": "Мой продуманный ответ",
        },
    )
    assert answer.status_code == 200
    assert answer.json()["score_percent"] == 70  # 80 от LLM минус штраф за подсказку
    assert client.app.state.llm.calls == 2  # невалидный JSON был повторён

    results = client.get(f"/api/design/results/{session_id}")
    assert results.status_code == 200
    payload = results.json()
    assert payload["summary"]["avg_percent"] == 70
    assert payload["details"][0]["title"] == "Уточнение требований"


def test_design_rejects_answer_for_non_current_step(client):
    started = client.post("/api/design/start", json={"level": "junior"}).json()
    response = client.post(
        "/api/design/answer",
        json={"session_id": started["session_id"], "step_id": "hla", "user_answer": "ответ"},
    )
    assert response.status_code == 404
    assert "текущий шаг" in response.json()["detail"]
