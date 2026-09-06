import json

import pytest
from src.db.repository import DesignScenariosRepository
from src.features.design.domain.services import DesignSessionStore


class FakeSessionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSessionMaker:
    """Имитирует ``async_sessionmaker``: вызов возвращает контекст сессии.

    Позволяет прогонять ``DesignService`` без реального PostgreSQL.
    """

    def __init__(self) -> None:
        self.opened = 0

    def __call__(self) -> FakeSessionContext:
        self.opened += 1
        return FakeSessionContext()


class DummyLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        return json.dumps(
            {
                "score_percent": 80,
                "rubric": {"reqs": 80, "arch": 80, "data": 80, "scale": 80, "tradeoffs": 80},
                "covered_points": ["ключевой пункт"],
                "missed_points": ["одна деталь"],
                "techlead_explanation": "Корректное решение.",
            }
        )


# Карточки, которые «лежат в БД», но отсутствуют в YAML-библиотеке,
# чтобы в тестах чётко разделять источник: БД vs YAML-слой.
DB_BRIEF = [
    {
        "id": "custom-cache-layer",
        "title": "Custom Cache Layer",
        "level": "middle",
        "category": "realtime",
        "primary_pattern": "write-through + read-through cache",
        "summary": "Проектируем кэширующий слой между API и БД.",
        "is_detailed": False,
    },
    {
        "id": "movie-seat-booking",
        "title": "Movie Seat Booking",
        "level": "middle",
        "category": "ecommerce",
        "primary_pattern": "event-driven + state machine",
        "summary": "Резервирование мест в кинотеатре с конкурентным доступом.",
        "is_detailed": False,
    },
]


def _db_row(brief: dict) -> dict:
    return {
        **brief,
        "summary": f"Проектируем {brief['title']}.",
        "requirements": ["Функциональное требование"],
        "nfr": ["NFR: SLO 99.9%"],
        "constraints": ["Ограничение: бюджет compute"],
        "baseline_load": {"rps": 1000},
        "topics": ["cache", "ttl"],
        "steps": [],
        "acceptance_criteria": ["Критерий приёмки"],
        "tags": [],
        "evolution": [],
        "failure_questions": ["Что происходит при отказе ключевого компонента?"],
        "advanced_questions": [],
    }


async def _fake_list_brief(self, **kwargs):
    return [dict(b) for b in DB_BRIEF]


async def _fake_list_categories(self, **kwargs):
    return [{"id": "ecommerce", "count": 1}, {"id": "realtime", "count": 1}]


async def _fake_get(self, scenario_id, **kwargs):
    for brief in DB_BRIEF:
        if brief["id"] == scenario_id:
            return _db_row(brief)
    return None


async def _fake_get_random(self, *, level=None, category=None, exclude_ids=()):
    pool = [
        b
        for b in DB_BRIEF
        if (level is None or b["level"] == level)
        and (category is None or b["category"] == category)
    ]
    if not pool:
        return None
    return _db_row(pool[0])


async def _fake_count(self, **kwargs):
    return len(DB_BRIEF)


@pytest.fixture
def make_settings():
    def _make(**overrides):
        defaults = {
            "design_levels": ["junior", "middle", "senior"],
            "design_hint_penalty_percent": 10,
            "design_pass_threshold_percent": 50,
            "design_max_explanation_len": 600,
            "design_max_tokens": 800,
            "design_scenarios_path": "backend/prompts/design/scenarios.yaml",
            "design_library_path": "backend/prompts/design/library.yaml",
        }
        defaults.update(overrides)
        return type("Settings", (), defaults)()

    return _make


@pytest.fixture
def llm():
    return DummyLLM()


@pytest.fixture
def fake_db(monkeypatch):
    """Подменяет сессионную фабрику и методы репозитория — БД не нужна."""
    monkeypatch.setattr(DesignScenariosRepository, "list_brief", _fake_list_brief)
    monkeypatch.setattr(DesignScenariosRepository, "list_categories", _fake_list_categories)
    monkeypatch.setattr(DesignScenariosRepository, "get", _fake_get)
    monkeypatch.setattr(DesignScenariosRepository, "get_random", _fake_get_random)
    monkeypatch.setattr(DesignScenariosRepository, "count", _fake_count)
    return FakeSessionMaker()


@pytest.fixture
def service(fake_db, make_settings, llm):
    from src.features.design.domain.services import DesignService

    return DesignService(make_settings(), llm, DesignSessionStore(), db_session_factory=fake_db)
