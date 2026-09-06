"""Регрессионные тесты DesignService: работа с БД через фабрику сессий без PostgreSQL.

Проверяют исправление бага
``TypeError: 'async_sessionmaker' object does not support the asynchronous
context manager protocol`` — сервис должен открывать сессию через вызов
``async with self._db_session_factory()``, где фабрика — это инстанс
``async_sessionmaker`` (или его фейк).
"""

import asyncio

import pytest
from src.features.design.domain.services import DesignService, DesignSessionStore


def test_config_merges_db_and_yaml_without_db(fake_db, service):
    levels, scenarios, categories, total = asyncio.run(service.config())

    ids = {row["id"] for row in scenarios}
    assert "movie-seat-booking" in ids  # только из «БД»
    assert "url-shortener" in ids  # из YAML-слоя (библиотека + детальный сценарий)
    assert len(ids) >= 100
    assert total == len(ids)
    assert "senior" in levels
    assert any(c["id"] == "realtime" for c in categories)
    assert fake_db.opened == 2  # _db_scenarios_brief + _db_categories


def test_config_marks_detailed_only_scenarios_with_steps(service):
    _, scenarios, _, _ = asyncio.run(service.config())

    by_id = {row["id"]: row for row in scenarios}
    assert by_id["url-shortener"]["is_detailed"] is True  # детальные steps из YAML
    assert by_id["movie-seat-booking"]["is_detailed"] is False  # карточка из БД
    assert by_id["online-presence"]["is_detailed"] is False  # карточка библиотеки без steps


def test_config_includes_summary_for_every_scenario(service):
    _, scenarios, _, _ = asyncio.run(service.config())

    by_id = {row["id"]: row for row in scenarios}
    assert by_id["movie-seat-booking"]["summary"]  # summary карточки из «БД»
    assert by_id["url-shortener"]["summary"]  # summary детального YAML-сценария
    assert by_id["online-presence"]["summary"]  # summary карточки библиотеки
    assert all("summary" in row for row in scenarios)


def test_start_with_random_pick_from_db_builds_dynamic_steps(service):
    sess, scenario_info, step_info = asyncio.run(
        service.start("middle", None, category="realtime", random_pick=True)
    )

    assert scenario_info["id"] == "custom-cache-layer"
    assert sess.scenario_id == "custom-cache-layer"
    assert step_info["id"] == "clarify"
    assert sess.steps_order == ["clarify", "hla", "data", "scale", "tradeoffs", "failure"]


def test_start_with_library_scenario_by_id_builds_dynamic_steps(service):
    """Регрессия: выбор карточки из library.yaml (без steps) по id."""
    sess, scenario_info, step_info = asyncio.run(
        service.start("senior", "reddit-like")
    )

    assert scenario_info["id"] == "reddit-like"
    assert sess.scenario_id == "reddit-like"
    assert step_info["id"] == "clarify"
    assert sess.steps_order == [
        "clarify", "hla", "data", "scale", "tradeoffs", "failure", "advanced",
    ]


def test_start_with_db_only_id_resolves_and_builds_steps(service):
    sess, scenario_info, step_info = asyncio.run(service.start("middle", "movie-seat-booking"))

    assert scenario_info["id"] == "movie-seat-booking"
    assert sess.steps_order == ["clarify", "hla", "data", "scale", "tradeoffs", "failure"]


def test_default_factory_is_resolved_from_module(monkeypatch, make_settings, llm, fake_db):
    """Воспроизводит путь создания сервиса из роутера (без явного db_session_factory).

    Раньше здесь падал TypeError: 'async_sessionmaker' object does not support
    the asynchronous context manager protocol на шаге ``config()``.
    """
    from src.features.design.domain import services as services_module

    monkeypatch.setattr(services_module, "session_factory", lambda: fake_db)

    service = DesignService(make_settings(), llm, DesignSessionStore())
    levels, scenarios, _, total = asyncio.run(service.config())

    assert total == len(scenarios)
    assert len(scenarios) >= 100
    assert "senior" in levels
    assert "url-shortener" in {row["id"] for row in scenarios}


def test_list_all_scenarios_deduplicates_db_and_yaml(service):
    scenarios = asyncio.run(service.list_all_scenarios())

    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids))
    assert "movie-seat-booking" in ids
    assert len(ids) >= 100


def test_no_database_error_when_unknown_scenario_requested(service):
    with pytest.raises(ValueError):
        asyncio.run(service.start("middle", "unknown-scenario-id-xyz"))
