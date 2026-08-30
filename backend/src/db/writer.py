"""Helpers to persist answer records from FastAPI BackgroundTasks.

Используется в роутерах так:

    from fastapi import BackgroundTasks
    from src.db.writer import persist_quiz_answer, persist_sobes_answer, persist_design_answer, persist_chat_message

    @router.post("/quiz/answer")
    async def submit(..., background: BackgroundTasks):
        ...
        background.add_task(
            persist_quiz_answer,
            username=current.username,
            ...
        )

При ошибках БД пишем в лог и НЕ падаем — основной ответ пользователю уже ушёл.
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.database import session_factory
from src.db.models import Feature
from src.db.repository import (
    ChatMessagesRepository,
    DesignAnswersRepository,
    QuizAnswersRepository,
    SessionsRepository,
    SobesAnswersRepository,
    UsersRepository,
)

logger = logging.getLogger(__name__)


async def _open_and_commit(coro_factory) -> None:
    """Открывает сессию, выполняет корутину с переданной сессией и коммитит."""
    factory = session_factory()
    try:
        async with factory() as session:
            try:
                await coro_factory(session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    except Exception as exc:  # pragma: no cover - лог-уровень
        logger.exception("Failed to persist stats record: %s", exc)


async def persist_quiz_answer(
    *,
    username: str,
    external_session_id: str,
    question_text: str,
    user_answer: str,
    correct_answer: str,
    is_correct: bool,
    explanation: str = "",
    level: str | None = None,
) -> None:
    """Сохраняет ответ квиза в БД (без блокировки основного запроса)."""

    async def _work(session) -> None:
        users = UsersRepository(session)
        user = await users.get_or_create(username)
        sessions = SessionsRepository(session)
        fs = await sessions.get_or_create(
            user_id=user.id,
            feature=Feature.QUIZ,
            external_id=external_session_id,
            level=level,
        )
        quiz = QuizAnswersRepository(session)
        await quiz.add(
            user_id=user.id,
            session_pk=fs.id,
            question_text=question_text,
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            explanation=explanation,
            level=level,
        )

    await _open_and_commit(_work)


async def persist_sobes_answer(
    *,
    username: str,
    external_session_id: str,
    question_text: str,
    topic: str,
    user_answer: str,
    reference_answer: str,
    score_percent: int,
    is_counted: bool,
    pass_threshold: int,
    techlead_explanation: str = "",
    covered_points: list[str] | None = None,
    missed_points: list[str] | None = None,
    level: str | None = None,
) -> None:
    """Сохраняет ответ sobes в БД."""

    async def _work(session) -> None:
        users = UsersRepository(session)
        user = await users.get_or_create(username)
        sessions = SessionsRepository(session)
        fs = await sessions.get_or_create(
            user_id=user.id,
            feature=Feature.SOBES,
            external_id=external_session_id,
            level=level,
        )
        repo = SobesAnswersRepository(session)
        await repo.add(
            user_id=user.id,
            session_pk=fs.id,
            question_text=question_text,
            topic=topic,
            user_answer=user_answer,
            reference_answer=reference_answer,
            score_percent=score_percent,
            is_counted=is_counted,
            pass_threshold=pass_threshold,
            techlead_explanation=techlead_explanation,
            covered_points=covered_points,
            missed_points=missed_points,
            level=level,
        )

    await _open_and_commit(_work)


async def persist_design_answer(
    *,
    username: str,
    external_session_id: str,
    scenario_id: str,
    step_id: str,
    step_title: str = "",
    user_answer: str,
    score_percent: int,
    rubric: dict[str, int] | None = None,
    pass_threshold: int,
    covered_points: list[str] | None = None,
    missed_points: list[str] | None = None,
    techlead_explanation: str = "",
    hint_used: bool = False,
    level: str | None = None,
) -> None:
    """Сохраняет ответ design в БД."""

    async def _work(session) -> None:
        users = UsersRepository(session)
        user = await users.get_or_create(username)
        sessions = SessionsRepository(session)
        fs = await sessions.get_or_create(
            user_id=user.id,
            feature=Feature.DESIGN,
            external_id=external_session_id,
            level=level,
            extra={"scenario_id": scenario_id},
        )
        repo = DesignAnswersRepository(session)
        await repo.add(
            user_id=user.id,
            session_pk=fs.id,
            scenario_id=scenario_id,
            step_id=step_id,
            step_title=step_title,
            user_answer=user_answer,
            score_percent=score_percent,
            rubric=rubric,
            pass_threshold=pass_threshold,
            covered_points=covered_points,
            missed_points=missed_points,
            techlead_explanation=techlead_explanation,
            hint_used=hint_used,
            level=level,
        )

    await _open_and_commit(_work)


async def persist_chat_message(
    *,
    username: str,
    session_key: str,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Сохраняет сообщение чата в БД."""

    async def _work(session) -> None:
        users = UsersRepository(session)
        user = await users.get_or_create(username)
        sessions = SessionsRepository(session)
        fs = await sessions.get_or_create(
            user_id=user.id,
            feature=Feature.CHAT,
            external_id=session_key,
        )
        repo = ChatMessagesRepository(session)
        await repo.add(
            user_id=user.id,
            session_pk=fs.id,
            session_key=session_key,
            role=role,
            content=content,
            meta=meta,
        )

    await _open_and_commit(_work)


__all__ = [
    "persist_chat_message",
    "persist_design_answer",
    "persist_quiz_answer",
    "persist_sobes_answer",
]
