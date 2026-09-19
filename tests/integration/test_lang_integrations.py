"""Интеграционные (HTTP-уровень) тесты трёх Lang-внедрений.

Харнесс повторяет схему `test_design_api.py` / `test_sobes_api.py`: реальное
FastAPI-приложение + lifespan-патч (фейк-settings, DummyLLM, фейки репозиториев
и session-фабрик) — без PostgreSQL/Qdrant/Ollama/сети.

Что проверяем на уровне реальных роутеров и сервесов:

- **LangChain structured output** — флаг ``llm_structured_output=true`` доходит от
  settings (lifespan) до точек вызова: sobes-scoring (``ScoreResult``), дизайн-нода
  (``DesignScore``), классификация (``ClassificationRows`` — ``ClassifyBatch``).
  ``DummyLLM.generate`` при этом **не** вызывается (structured-путь), а при
  ``None`` от ``generate_structured`` — фолбэк на legacy ``generate(format="json")``;
- **LangChain ``format="json"`` (1A)** — при выключенном structured legacy-путь
  обязан передавать ``format="json"`` в payload;
- **LangSmith-трейс** — ``metadata`` (feature + ``session_id``) и ``tags`` доходят
  до ``generate``/``generate_structured`` из реального роутера (иначе ленивая
  трассировка в LangSmith не смогла бы их записать);
- **LangGraph design** — шаг скорингуется в ноде графа, structured включается по
  настройкам (как в ``test_design_api``, но со ``spy``-структурным путём).
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, TypeAdapter, field_validator

from backend.src.core.structured import ClassifyWarehouse
from backend.src.main import app


class ScoreResult(BaseModel):
    score_percent: int = Field(default=0, ge=0, le=100)

    @field_validator("score_percent")
    @classmethod
    def _clamp(cls, v: int) -> int:
        return min(100, max(0, v))


class DesignScore(BaseModel):
    score_percent: int = Field(default=0, ge=0, le=100)
    rubric: dict[str, int] = Field(
        default_factory=lambda: {
            "reqs": 0,
            "arch": 0,
            "data": 0,
            "scale": 0,
            "tradeoffs": 0,
        }
    )
    covered_points: list[str] = Field(default_factory=list)
    missed_points: list[str] = Field(default_factory=list)
    techlead_explanation: str = ""

    def to_legacy_tuple(self, max_expl_len: int) -> tuple[int, dict[str, int], list[str], list[str], str]:
        return (
            self.score_percent,
            self.rubric,
            self.covered_points,
            self.missed_points,
            self.techlead_explanation[:max_expl_len],
        )


class ClassificationRow(BaseModel):
    topic: str
    level: str = "middle"
    difficulty_score: float = Field(default=0.0, ge=0.0, le=1.0)


# Пакетная схема классификации — то же, что src/core/structured.ClassificationBatch.
ClassifyBatch = TypeAdapter(list[ClassificationRow])


class DummyLLM:
    """Спай: ведёт лог generate/generate_structured-вызовов, чтобы проверить,
    какая ветка реально сработала на уровне API."""

    def __init__(self) -> None:
        self.generate_calls: list[dict] = []
        self.structured_calls: list[dict] = []
        self._fail_structured = False

    def set_structured_failure(self, *, fail: bool) -> None:
        self._fail_structured = fail

    async def generate(self, messages, **kwargs):
        self.generate_calls.append({"kwargs": kwargs})
        system = messages[0]["content"].lower() if messages else ""
        if "классификатор" in system:
            user = messages[-1]["content"]
            m = re.search(r"(\[.*\])", user, re.S)
            arr = []
            if m:
                try:
                    arr = json.loads(m.group(1))
                except Exception:
                    arr = []
            out = [
                {
                    "topic": "python",
                    "level": "middle",
                    "difficulty_score": 0.3,
                }
                for _ in arr
            ]
            return json.dumps(out, ensure_ascii=False)
        return json.dumps(
            {
                "score_percent": 80,
                "rubric": {"reqs": 80, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0},
                "covered_points": ["a"],
                "missed_points": [],
                "techlead_explanation": "Норм.",
            },
            ensure_ascii=False,
        )

    async def generate_structured(self, messages, *, schema, **kwargs):
        self.structured_calls.append(
            {
                "schema": schema,
                "kwargs": {k: v for k, v in kwargs.items() if k not in ("metadata", "tags")},
                "metadata": kwargs.get("metadata"),
                "tags": kwargs.get("tags"),
            }
        )
        if self._fail_structured:
            return None
        if schema is ScoreResult:
            return ScoreResult(score_percent=80)
        if schema is ClassifyBatch:
            return [ClassificationRow(topic="python", level="middle", difficulty_score=0.3)]
        if schema is DesignScore:
            return DesignScore(
                score_percent=80,
                rubric={"reqs": 80, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0},
                covered_points=["a"],
                missed_points=[],
                techlead_explanation="Норм.",
            )
        return None


class FakeSessionMaker:
    def __call__(self):
        return self


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Комбинированный lifespan: sobes + design с патченными репозиториями/сессией."""

    async def _list_brief(_self, **kwargs):
        return [
            {
                "id": "movie-seat-booking",
                "title": "Movie Seat Booking",
                "level": "middle",
                "category": "ecommerce",
                "primary_pattern": "event-driven + state machine",
                "summary": "Резервирование мест в кинотеатре.",
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

    # --- репозитории sobes -> in-memory ---
    async def _sobes_list_all(_self, **kwargs):
        return []
    async def _sobes_get_random(_self, **kwargs):
        return None
    async def _sobes_count(_self, **kwargs):
        return 98

    # API-слой использует backend fixtures-патог; изолируем от сети.
    app.state._integration_testing = True

    @asynccontextmanager
    async def _lifespan(application):
        application.state.settings = SimpleNamespace(
            # base
            chat_max_message_length=4000,
            cors_allow_origins=["*"],
            session_store_max_sessions=10,
            session_history_limit=20,
            ingest_interval_hours=9999,
            interview_top_k=5,
            # sobes
            sobes_topics=["python", "db"],
            sobes_counts_by_level={"junior": [1, 1]},
            sobes_pass_threshold_percent=50,
            sobes_cache_path=str(tmp_path / "sobes_cache.json"),
            sobes_max_explanation_len=300,
            # design
            design_levels=["junior", "middle", "senior"],
            design_hint_penalty_percent=10,
            design_pass_threshold_percent=50,
            design_max_explanation_len=600,
            design_max_tokens=800,
            design_scenarios_path="backend/prompts/design/scenarios.yaml",
            design_library_path="backend/prompts/design/library.yaml",
            # LangChain: структурный вывод (то, что тестируем)
            llm_structured_output=True,
            langsmith_tracing=False,
        )
        application.state.llm = DummyLLM()
        yield

    app.router.lifespan_context = _lifespan
    import src.core.interfaces.llm as _llm  # noqa: F401  (импорт для патча ниже)

    with TestClient(app) as test_client:
        test_client.app.state.llm = DummyLLM()  # ensure instance at request-time
        yield test_client
