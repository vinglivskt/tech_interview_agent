import asyncio
import json

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from src.features.design.domain.graph import (
    build_design_graph,
    create_design_checkpointer,
    format_step_info,
    parse_score,
    score_step,
)
from src.features.design.domain.scenarios import Scenario, Step


def _settings(**kwargs):
    defaults = {
        "design_hint_penalty_percent": 10,
        "design_max_tokens": 800,
        "design_max_explanation_len": 600,
        "design_graph_max_cache": 10,
        "design_checkpointer": "memory",
        "database_url": "",
    }
    defaults.update(kwargs)
    return type("Settings", (), defaults)()


def _scenario() -> Scenario:
    return Scenario(
        id="unit",
        title="Unit Test",
        level="middle",
        summary="Test scenario.",
        requirements=[],
        nfr=[],
        constraints=[],
        baseline_load={},
        topics=[],
        steps=[
            Step(
                id="step1",
                title="Step 1",
                prompt="First?",
                expected_points=["A"],
                rubric_weights={"reqs": 1.0},
            ),
            Step(
                id="step2",
                title="Step 2",
                prompt="Second?",
                expected_points=["B"],
                rubric_weights={"reqs": 1.0},
            ),
        ],
        acceptance_criteria=[],
        failure_questions=["Что при отказе?"],
        advanced_questions=["А если 10x?"],
    )


class OkLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        return json.dumps(
            {
                "score_percent": 90,
                "rubric": {"reqs": 90, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0},
                "covered_points": ["a"],
                "missed_points": ["b"],
                "techlead_explanation": "Ок.",
            }
        )


class BadThenGoodLLM:
    """Первый вызов — невалидный JSON, второй — валидный (проверка ретрая)."""

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
                "covered_points": [],
                "missed_points": [],
                "techlead_explanation": "Решение после ретрая.",
            }
        )


def test_format_step_info_first():
    scen = _scenario()
    info = format_step_info(scen, scen.steps[0], first=True)
    assert info["id"] == "step1"
    assert info["title"] == "Step 1"
    assert "Пока не рисуйте архитектуру" in info["prompt"]
    assert "Ваш ход: First?" in info["prompt"]


def test_format_step_info_non_first():
    scen = _scenario()
    info = format_step_info(scen, scen.steps[1], first=False)
    assert info["id"] == "step2"
    assert "Хорошо, зафиксируем эти допущения" in info["prompt"]


def test_parse_score_valid():
    text = json.dumps(
        {
            "score_percent": 75,
            "rubric": {"reqs": 75, "arch": 70, "data": 60, "scale": 80, "tradeoffs": 50},
            "covered_points": ["req A", "arch HLA"],
            "missed_points": ["retry"],
            "techlead_explanation": "Хороший вариант.",
        }
    )
    score, rubric, covered, missed, expl = parse_score(text, 600)
    assert score == 75
    assert set(rubric) == {"reqs", "arch", "data", "scale", "tradeoffs"}
    assert covered == ["req A", "arch HLA"]
    assert missed == ["retry"]
    assert expl == "Хороший вариант."


def test_parse_score_invalid_missing_keys():
    with pytest.raises(ValueError):
        parse_score('{"score_percent": 50}', 600)


async def _score_ok() -> None:
    llm = OkLLM()
    scen = _scenario()
    res = await score_step(
        llm,
        scenario=scen,
        step=scen.steps[0],
        user_answer="Answer",
        history=[],
        hints_used=[],
        hint_penalty=10,
        max_tokens=800,
        max_expl_len=600,
    )
    assert res.score_percent == 90
    assert res.covered_points == ["a"]
    assert llm.calls == 1
    assert res.hint_used is False


async def _score_retry() -> None:
    llm = BadThenGoodLLM()
    scen = _scenario()
    res = await score_step(
        llm,
        scenario=scen,
        step=scen.steps[0],
        user_answer="Answer",
        history=[],
        hints_used=[],
        hint_penalty=10,
        max_tokens=800,
        max_expl_len=600,
    )
    assert llm.calls == 2
    assert res.score_percent == 80


async def _score_hint_penalty() -> None:
    llm = OkLLM()
    scen = _scenario()
    res = await score_step(
        llm,
        scenario=scen,
        step=scen.steps[0],
        user_answer="Answer",
        history=[],
        hints_used=["step1"],
        hint_penalty=10,
        max_tokens=800,
        max_expl_len=600,
    )
    assert res.score_percent == 80
    assert res.hint_used is True


def test_score_step_ok():
    asyncio.run(_score_ok())


def test_score_step_retry():
    asyncio.run(_score_retry())


def test_score_step_hint_penalty():
    asyncio.run(_score_hint_penalty())


async def _graph_flow() -> None:
    llm = OkLLM()
    scen = _scenario()
    checkpointer = MemorySaver()
    graph = build_design_graph(scen, _settings(), llm, checkpointer)
    session_id = "design_unit_12344321"
    cfg = {"configurable": {"thread_id": session_id}}

    await graph.ainvoke(
        {
            "session_id": session_id,
            "scenario_id": scen.id,
            "level": "middle",
            "step_ids": [s.id for s in scen.steps],
            "idx": 0,
            "steps_answer_total": 2,
        },
        cfg,
    )
    started = (await graph.aget_state(cfg)).values
    assert started["idx"] == 0
    assert started["session_id"] == session_id

    # Первый шаг: граф «замер» на interrupt() и ждёт ответа
    await graph.ainvoke(Command(resume="first answer"), cfg)
    after1 = (await graph.aget_state(cfg)).values
    assert after1["idx"] == 1
    assert len(after1["answers"]) == 1
    assert after1["answers"][0]["score_percent"] == 90
    assert after1["answers"][0]["step_id"] == "step1"
    assert after1["last_result"]["is_last"] is False
    assert after1["last_result"]["next_step"]["id"] == "step2"
    assert after1["last_result"]["failure_questions"] == ["Что при отказе?"]

    # Второй (последний) шаг
    await graph.ainvoke(Command(resume="second answer"), cfg)
    after2 = (await graph.aget_state(cfg)).values
    assert after2["idx"] == 2
    assert len(after2["answers"]) == 2
    assert after2["last_result"]["is_last"] is True
    assert after2["last_result"]["next_step"] is None
    assert after2["answers"][1]["step_id"] == "step2"

    # Состояние в чекпоинтере: никакой pending-ноды
    snapshot = await graph.aget_state(cfg)
    assert not snapshot.next


def test_graph_full_flow():
    asyncio.run(_graph_flow())


async def _graph_update_state() -> None:
    llm = OkLLM()
    scen = _scenario()
    checkpointer = MemorySaver()
    graph = build_design_graph(scen, _settings(), llm, checkpointer)
    session_id = "design_unit_87654321"
    cfg = {"configurable": {"thread_id": session_id}}
    await graph.ainvoke(
        {
            "session_id": session_id,
            "scenario_id": scen.id,
            "level": "middle",
            "step_ids": [s.id for s in scen.steps],
            "idx": 0,
            "steps_answer_total": 2,
        },
        cfg,
    )
    # Подсказка через update_state во время паузы
    await graph.aupdate_state(cfg, {"hints": ["step1"]})
    state = (await graph.aget_state(cfg)).values
    assert state["hints"] == ["step1"]
    # Ответ с подсказкой учитывает её
    await graph.ainvoke(Command(resume="with hint"), cfg)
    after = (await graph.aget_state(cfg)).values
    assert after["hints"] == ["step1"]
    assert after["answers"][0]["score_percent"] == 80


def test_graph_update_state_hint():
    asyncio.run(_graph_update_state())


async def _graph_empty_steps() -> None:
    empty = Scenario(
        id="empty",
        title="Empty",
        level="middle",
        summary="",
        requirements=[],
        nfr=[],
        constraints=[],
        baseline_load={},
        topics=[],
        steps=[],
        acceptance_criteria=[],
    )
    with pytest.raises(Exception, match="нет шагов"):
        build_design_graph(empty, _settings(), OkLLM(), MemorySaver())


def test_graph_empty_steps_raises():
    asyncio.run(_graph_empty_steps())


async def _fallback_memory() -> None:
    last_checkpointer, close = await create_design_checkpointer(
        _settings(design_checkpointer="postgres", database_url="postgresql+asyncpg://bad:bad@localhost:1/nodb")
    )
    assert type(last_checkpointer) is MemorySaver
    assert close is None


def test_create_design_checkpointer_fallback_memory():
    asyncio.run(_fallback_memory())


async def _explicit_memory() -> None:
    checkpointer, close = await create_design_checkpointer(
        _settings(design_checkpointer="memory", database_url="postgresql+asyncpg://x:x@localhost:1/x")
    )
    assert type(checkpointer) is MemorySaver
    assert close is None


def test_create_design_checkpointer_memory_config():
    asyncio.run(_explicit_memory())