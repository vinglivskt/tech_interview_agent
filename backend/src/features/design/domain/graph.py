"""LangGraph-машина режима «Системный дизайн».

Каждый сценарий компилируется в StateGraph:
- каждый шаг интервью — отдельная нода;
- нода «замирает» на ``interrupt()`` в ожидании ответа кандидата;
- ответ оценивается LLM (та же JSON-схема и ретраи, что и раньше);
- чекпоинтер (``thread_id = session_id``) хранит состояние интервью:
  в памяти (MemorySaver) или персистентно (AsyncPostgresSaver).

Этот модуль — единственный источник state-логики дизайна. ``DesignService``
использует граф как исполнителя, сохраняя прежние контракты API.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.core.config import Settings
from src.features.design.domain.scenarios import Scenario, Step

logger = logging.getLogger(__name__)

__all__ = [
    "DesignGraphState",
    "DesignGradedStep",
    "build_design_graph",
    "create_design_checkpointer",
    "format_step_info",
    "parse_score",
    "score_step",
]


async def create_design_checkpointer(settings: Settings) -> tuple[BaseCheckpointSaver, Callable[[], Awaitable[None]] | None]:
    """Создаёт чекпоинтер для графов дизайна.

    Возвращает ``(checkpointer, async_close)``. При ``DESIGN_CHECKPOINTER=postgres``
    и доступной БД инстанцируется ``AsyncPostgresSaver`` (таблицы создаются через
    ``setup()``); при любой ошибке — безопасный фолбэк на ``MemorySaver``
    (``async_close`` при этом ``None``).
    """
    kind = getattr(settings, "design_checkpointer", "postgres")
    if kind == "postgres" and getattr(settings, "database_url", ""):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            dsn = settings.database_url
            dsn = dsn.replace("postgresql+asyncpg", "postgresql").replace("+psycopg", "")
            cm = AsyncPostgresSaver.from_conn_string(dsn)
            saver = await cm.__aenter__()
            await saver.setup()

            async def _close() -> None:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    logger.warning("Ошибка при закрытии Postgres-чекпоинтера дизайна", exc_info=True)

            logger.info("Design-чекпоинтер: PostgreSQL (состояние переживает рестарт API)")
            return saver, _close
        except Exception:
            logger.exception("Не удалось инициализировать Postgres-чекпоинтер дизайна — используем MemorySaver")
    return MemorySaver(), None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _append(items: list[Any], update: list[Any]) -> list[Any]:
    """Редьюсер LangGraph: результат ноды/update добавляется к списку состояния."""
    return items + update


class DesignGraphState(TypedDict, total=False):
    """Состояние графа дизайн-интервью (персистится чекпоинтером)."""

    session_id: str
    scenario_id: str
    level: str
    step_ids: list[str]
    idx: int
    steps_answer_total: int
    answers: Annotated[list[dict[str, Any]], _append]
    hints: Annotated[list[str], _append]
    last_result: dict[str, Any]


# ---------------------------------------------------------------------------
# Результат скоринга одного шага
# ---------------------------------------------------------------------------


@dataclass
class DesignGradedStep:
    """Итог оценки одного шага интервью."""

    step_id: str
    user_answer: str
    score_percent: int
    rubric: dict[str, int]
    covered_points: list[str]
    missed_points: list[str]
    techlead_explanation: str
    hint_used: bool
    failure_questions: list[str] = field(default_factory=list)
    advanced_questions: list[str] = field(default_factory=list)
    next_step: dict | None = None
    is_last: bool = False


def format_step_info(scenario: Scenario, step: Step, *, first: bool = False) -> dict[str, str]:
    """Формирует публичный DTO-словарь шага для фронта."""
    if first:
        prompt = (
            f"Интервьюер: «Давайте спроектируем {scenario.title}. {scenario.summary} "
            "Пока не рисуйте архитектуру: сначала задайте вопросы, которые помогут зафиксировать задачу. "
            "Если данных не хватает — явно сформулируйте и обоснуйте свои допущения».\n\n"
            f"Ваш ход: {step.prompt}"
        )
    else:
        prompt = f"Интервьюер: «Хорошо, зафиксируем эти допущения. {step.prompt}»"
    return {"id": step.id, "title": step.title, "prompt": prompt}


def parse_score(
    text: str,
    max_expl_len: int,
) -> tuple[int, dict[str, int], list[str], list[str], str]:
    """Разбирает и валидирует JSON-ответ LLM со скорингом шага.

    Схема (не менять — совместимость со статистикой и промптами):
    ``{score_percent, rubric, covered_points, missed_points, techlead_explanation}``.
    """
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != {
        "score_percent",
        "rubric",
        "covered_points",
        "missed_points",
        "techlead_explanation",
    }:
        raise ValueError("Неверная JSON-схема оценки")
    if type(data["score_percent"]) is not int or not 0 <= data["score_percent"] <= 100:
        raise ValueError("Неверный score_percent")
    rubric_raw = data["rubric"]
    keys = {"reqs", "arch", "data", "scale", "tradeoffs"}
    if not isinstance(rubric_raw, dict) or set(rubric_raw) != keys:
        raise ValueError("Неверная рубрика")
    if any(type(value) is not int or not 0 <= value <= 100 for value in rubric_raw.values()):
        raise ValueError("Неверные значения рубрики")
    if not all(
        isinstance(data[key], list) and len(data[key]) <= 6
        for key in ("covered_points", "missed_points")
    ):
        raise ValueError("Неверные списки пунктов")
    if not isinstance(data["techlead_explanation"], str):
        raise ValueError("Неверное пояснение")
    explanation = data["techlead_explanation"].strip()[:max_expl_len]
    return (
        data["score_percent"],
        dict(rubric_raw),
        [str(item) for item in data["covered_points"]],
        [str(item) for item in data["missed_points"]],
        explanation,
    )


# ---------------------------------------------------------------------------
# Скоринг шага
# ---------------------------------------------------------------------------


async def score_step(
    llm: Any,
    *,
    scenario: Scenario,
    step: Step,
    user_answer: str,
    history: list[dict[str, Any]],
    hints_used: list[str],
    hint_penalty: int,
    max_tokens: int,
    max_expl_len: int,
) -> DesignGradedStep:
    """Оценивает один ответ кандидата через LLM.

    Повторяет поведение прежнего ``DesignService.answer``:
    - ретраи (до 3) при невалидном JSON с подсказкой «Предыдущий ответ невалиден…»;
    - деградация на ошибке (0%, пустая рубрика, стандартное пояснение);
    - штраф за использованную подсказку.
    """
    system = """Ты проводишь настоящий system design interview уровня Big Tech на русском языке.
Оцени только текущий ответ кандидата, но учитывай весь контекст сценария и его предыдущие решения.
Не награждай за перечисление технологий без причинно-следственной связи. Награждай за уточнение допущений,
оценки нагрузки, последовательность запросов, отказные сценарии и явные trade-offs. Не требуй деталей,
которые не относятся к текущему шагу. В `techlead_explanation` дай 2–4 конкретных предложения: что уже
звучит убедительно, один наиболее важный пробел и как его закрыть на интервью. Не пересказывай ответ.
Верни строго один JSON-объект без Markdown и без других ключей:
{score_percent:int 0..100, rubric:{reqs:int,arch:int,data:int,scale:int,tradeoffs:int},
covered_points:[str максимум 6], missed_points:[str максимум 6], techlead_explanation:str}.
Все значения rubric — целые 0..100; неиспользуемые категории ставь в 0."""

    user = (
        f"Сценарий: {scenario.title}. {scenario.summary}\n"
        f"Категория: {scenario.category}; основной паттерн: {scenario.primary_pattern or '—'}.\n"
        f"Факты, известные интервьюеру: requirements={json.dumps(scenario.requirements, ensure_ascii=False)}, "
        f"NFR={json.dumps(scenario.nfr, ensure_ascii=False)}, constraints={json.dumps(scenario.constraints, ensure_ascii=False)}, "
        f"baseline_load={json.dumps(scenario.baseline_load, ensure_ascii=False)}\n"
        f"Текущий шаг: {step.title}. Вопрос интервьюера: {step.prompt}\n"
        f"Критерии текущего шага: {json.dumps(step.expected_points, ensure_ascii=False)}; веса: {step.rubric_weights}\n"
        f"Предыдущие ответы: {json.dumps(history, ensure_ascii=False)}\n"
        f"Ответ кандидата: {user_answer}"
    )

    hint_used = step.id in hints_used

    try:
        last_error: Exception | None = None
        for attempt in range(3):
            retry = (
                ""
                if attempt == 0
                else " Предыдущий ответ невалиден: верни только JSON строго по указанной схеме."
            )
            text = await llm.generate(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            try:
                score, rubric, covered, missed, expl = parse_score(text, max_expl_len)
                break
            except Exception as exc:
                last_error = exc
                user += retry
        else:
            raise last_error or ValueError("Невалидный ответ LLM")
    except Exception:
        score, rubric, covered, missed, expl = (
            0,
            {},
            [],
            [],
            "Не удалось получить валидную оценку ответа.",
        )

    if hint_used:
        score = max(0, score - hint_penalty)

    return DesignGradedStep(
        step_id=step.id,
        user_answer=user_answer,
        score_percent=score,
        rubric=rubric,
        covered_points=covered,
        missed_points=missed,
        techlead_explanation=expl,
        hint_used=hint_used,
    )


# ---------------------------------------------------------------------------
# Ноды и сборка графа
# ---------------------------------------------------------------------------


def make_step_node(
    *,
    step: Step,
    scenario: Scenario,
    settings: Settings,
    llm: Any,
) -> Callable[[DesignGraphState], Awaitable[dict[str, Any]]]:
    """Фабрика ноды для одного шага интервью.

    Нода первым делом вызывает ``interrupt()`` — граф «замирает», пока
    ``/design/answer`` не вернёт ``Command(resume=user_answer)``.
    Затем происходи скоринг и обновление состояния.
    """
    hint_penalty = int(getattr(settings, "design_hint_penalty_percent", 10))
    max_tokens = int(getattr(settings, "design_max_tokens", 800))
    max_expl_len = int(getattr(settings, "design_max_explanation_len", 600))

    async def node(state: DesignGraphState) -> dict[str, Any]:
        user_answer = str(interrupt("Ожидание ответа кандидата на шаг") or "").strip()
        if not user_answer:
            raise ValueError("Ответ не должен быть пустым")

        history = [
            {
                "step_id": answer["step_id"],
                "answer": answer["user_answer"],
                "score": answer["score_percent"],
            }
            for answer in state.get("answers", [])
        ]

        graded = await score_step(
            llm,
            scenario=scenario,
            step=step,
            user_answer=user_answer,
            history=history,
            hints_used=state.get("hints", []),
            hint_penalty=hint_penalty,
            max_tokens=max_tokens,
            max_expl_len=max_expl_len,
        )

        answered = state.get("idx", 0) + 1
        is_last = answered >= state.get("steps_answer_total", len(scenario.steps))
        next_step_info = None
        if not is_last:
            nxt = scenario.steps[answered]
            next_step_info = format_step_info(scenario, nxt)

        graded.failure_questions = list(scenario.failure_questions or [])
        graded.advanced_questions = list(scenario.advanced_questions or [])
        graded.next_step = next_step_info
        graded.is_last = is_last

        record = {
            "step_id": graded.step_id,
            "user_answer": graded.user_answer,
            "score_percent": graded.score_percent,
            "rubric": graded.rubric,
            "covered_points": graded.covered_points,
            "missed_points": graded.missed_points,
            "techlead_explanation": graded.techlead_explanation,
            "hint_used": graded.hint_used,
        }

        return {
            "answers": [record],
            "idx": answered,
            "last_result": {
                "score_percent": graded.score_percent,
                "rubric": graded.rubric,
                "covered_points": graded.covered_points,
                "missed_points": graded.missed_points,
                "techlead_explanation": graded.techlead_explanation,
                "hint_used": graded.hint_used,
                "next_step": graded.next_step,
                "is_last": graded.is_last,
                "failure_questions": graded.failure_questions,
                "advanced_questions": graded.advanced_questions,
            },
        }

    return node


def build_design_graph(
    scenario: Scenario,
    settings: Settings,
    llm: Any,
    checkpointer: BaseCheckpointSaver,
) -> Any:
    """Компилирует StateGraph сценария: нода на каждый шаг, линейная «лесенка».

    ``checkpointer`` принимает и MemorySaver, и AsyncPostgresSaver.
    Возвращает скомпилированный граф LangGraph.
    """
    steps = scenario.steps
    if not steps:
        raise ValueError("У сценария нет шагов")

    builder = StateGraph(DesignGraphState)
    for st in steps:
        builder.add_node(st.id, make_step_node(step=st, scenario=scenario, settings=settings, llm=llm))

    builder.add_edge(START, steps[0].id)
    for prev, nxt in zip(steps, steps[1:], strict=False):
        builder.add_edge(prev.id, nxt.id)
    builder.add_edge(steps[-1].id, END)

    return builder.compile(checkpointer=checkpointer)