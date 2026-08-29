import json
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app


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


@pytest.fixture
def client():
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
                "design_scenarios_path": "prompts/design/scenarios.yaml",
            },
        )()
        application.state.llm = DummyLLM()
        yield

    app.router.lifespan_context = _lifespan
    with TestClient(app) as test_client:
        yield test_client


def test_design_config_and_happy_path_with_hint_penalty(client):
    config = client.get("/api/design/config")
    assert config.status_code == 200
    assert {row["id"] for row in config.json()["scenarios"]} == {"url-shortener", "news-feed", "object-storage"}

    started = client.post("/api/design/start", json={"level": "junior", "scenario_id": "url-shortener"})
    assert started.status_code == 200
    data = started.json()
    session_id, step = data["session_id"], data["step"]

    hint = client.post("/api/design/hint", json={"session_id": session_id, "step_id": step["id"]})
    assert hint.status_code == 200
    assert hint.json()["penalty_applied_percent"] == 10

    answer = client.post(
        "/api/design/answer",
        json={"session_id": session_id, "step_id": step["id"], "user_answer": "Мой продуманный ответ"},
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
