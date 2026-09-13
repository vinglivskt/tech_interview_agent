import asyncio
import json

import pytest
from langgraph.checkpoint.memory import MemorySaver
from src.features.design.domain.services import DesignService, DesignSessionStore

from tests.unit.design.conftest import FakeSessionMaker


def _settings(**kwargs):
    defaults = {
        "design_levels": ["junior", "middle", "senior"],
        "design_hint_penalty_percent": 10,
        "design_pass_threshold_percent": 50,
        "design_max_explanation_len": 600,
        "design_max_tokens": 800,
        "design_scenarios_path": "backend/prompts/design/scenarios.yaml",
        "design_library_path": "backend/prompts/design/library.yaml",
        "design_graph_max_cache": 10,
    }
    defaults.update(kwargs)
    return type("Settings", (), defaults)()


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


def _service(llm=None, checkpointer=None) -> DesignService:
    return DesignService(
        _settings(),
        llm or DummyLLM(),
        DesignSessionStore(),
        db_session_factory=FakeSessionMaker(),
        checkpointer=checkpointer,
    )


async def _start_returns_session_id() -> None:
    svc = _service()
    sess, scenario_info, step_info = await svc.start("senior", "url-shortener")
    assert sess.session_id.startswith("design_url-shortener_")
    assert len(sess.steps_order) == 6
    assert scenario_info["id"] == "url-shortener"
    assert step_info["id"] == "clarify"
    assert step_info["title"] == "Уточнение требований"
    assert "Пока не рисуйте архитектуру" in step_info["prompt"]


async def _answer_wrong_step() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    with pytest.raises(ValueError, match="Можно отвечать только на текущий шаг сценария"):
        await svc.answer(sess.session_id, sess.steps_order[1], "Ответ не на тот шаг")


async def _answer_normal() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    step1 = sess.steps_order[0]
    score, rubric, covered, missed, expl, next_step, is_last, fq, aq = await svc.answer(
        sess.session_id, step1, "Мой первый ответ"
    )
    assert score == 80
    assert rubric["reqs"] == 80
    assert next_step is not None
    assert next_step["id"] == sess.steps_order[1]
    assert is_last is False
    assert aq == []


async def _hint_then_answer_penalty() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    step1 = sess.steps_order[0]
    _, penalty = await svc.hint(sess.session_id, step1)
    assert penalty == 10
    score, _, _, _, _, _, _, _, _ = await svc.answer(sess.session_id, step1, "Ответ с подсказкой")
    assert score == 70


async def _results_after_two_answers() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    for step_id in sess.steps_order[:2]:
        await svc.answer(sess.session_id, step_id, "Ответ")
    summary, by_rubric, strengths, weaknesses, details, verdict = await svc.results(sess.session_id)
    assert summary == {"steps": 6, "passed": 2, "avg_percent": 80}
    assert by_rubric["reqs"] == 80
    assert len(details) == 2
    assert details[0]["step_id"] == sess.steps_order[0]
    assert verdict == "junior"  # 80 баллов, но pass-доля 2/6 → junior (формулы прежние)


async def _results_empty() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    summary, _, strengths, weaknesses, details, verdict = await svc.results(sess.session_id)
    assert summary == {"steps": 6, "passed": 0, "avg_percent": 0}
    assert details == []
    assert verdict == "junior"


async def _answer_empty_rejected() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    with pytest.raises(ValueError, match="Ответ не должен быть пустым"):
        await svc.answer(sess.session_id, sess.steps_order[0], "   ")


async def _malformed_session_rejected() -> None:
    svc = _service()
    with pytest.raises(ValueError, match="Сессия не найдена или истекла"):
        await svc.answer("random-session", "clarify", "Ответ")


async def _unknown_scenario_rejected() -> None:
    svc = _service()
    with pytest.raises(ValueError, match="не найден"):
        await svc.answer("design_no-such-scenario_00000000", "clarify", "Ответ")


async def _completed_session_rejected() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    for step_id in sess.steps_order:
        await svc.answer(sess.session_id, step_id, "Ответ")
    with pytest.raises(ValueError, match="Все шаги сценария уже отвечены"):
        await svc.answer(sess.session_id, sess.steps_order[0], "Ещё один")


async def _step_persist_context() -> None:
    svc = _service()
    sess, _, _ = await svc.start("senior", "url-shortener")
    step1 = sess.steps_order[0]
    await svc.hint(sess.session_id, step1)
    ctx = await svc.step_persist_context(sess.session_id, step1)
    assert ctx == {
        "scenario_id": "url-shortener",
        "step_title": "Уточнение требований",
        "hint_used": True,
        "level": "senior",
    }


async def _resume_across_service_instances() -> None:
    checkpointer = MemorySaver()
    svc1 = _service(checkpointer=checkpointer)
    svc2 = _service(checkpointer=checkpointer)
    sess, _, _ = await svc1.start("senior", "url-shortener")
    await svc1.answer(sess.session_id, sess.steps_order[0], "Первый шаг")
    score, _, _, _, _, _, _, _, _ = await svc2.answer(sess.session_id, sess.steps_order[1], "Второй шаг")
    assert score == 80
    # Итоги видны из второго инстанса тоже
    summary, _, _, _, details, _ = await svc2.results(sess.session_id)
    assert summary["passed"] == 2
    assert len(details) == 2


def test_start_returns_session_id():
    asyncio.run(_start_returns_session_id())


def test_answer_wrong_step():
    asyncio.run(_answer_wrong_step())


def test_answer_normal():
    asyncio.run(_answer_normal())


def test_hint_then_answer_penalty():
    asyncio.run(_hint_then_answer_penalty())


def test_results_after_two_answers():
    asyncio.run(_results_after_two_answers())


def test_results_empty():
    asyncio.run(_results_empty())


def test_answer_empty_rejected():
    asyncio.run(_answer_empty_rejected())


def test_malformed_session_rejected():
    asyncio.run(_malformed_session_rejected())


def test_unknown_scenario_rejected(fake_db):
    asyncio.run(_unknown_scenario_rejected())


def test_completed_session_rejected():
    asyncio.run(_completed_session_rejected())


def test_step_persist_context():
    asyncio.run(_step_persist_context())


def test_resume_across_service_instances():
    asyncio.run(_resume_across_service_instances())