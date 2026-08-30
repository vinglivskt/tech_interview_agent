# API-роутер для quiz-режима.
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from src.core.deps import decode_username_header
from src.db.writer import persist_quiz_answer
from src.features.quiz.domain.models import (
    QuizAnswerRequest,
    QuizAnswerResponse,
    QuizQuestionResponse,
    QuizQuestionResult,
    QuizResultsResponse,
    QuizStartRequest,
)
from src.features.quiz.domain.services import QuizService, QuizSessionStore

router = APIRouter()

# Глобальное хранилище сессий квиза (инициализируется при старте)
_quiz_session_store: QuizSessionStore | None = None


def get_quiz_session_store() -> QuizSessionStore:
    """Возвращает (или создаёт) глобальное хранилище сессий квиза."""
    global _quiz_session_store
    if _quiz_session_store is None:
        _quiz_session_store = QuizSessionStore()
    return _quiz_session_store


def _opt_username(
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
    username_h: Annotated[str | None, Header(alias="Username")] = None,
) -> str | None:
    """Опциональное имя пользователя (для записи статистики)."""
    raw = decode_username_header(x_username or username_h)
    return raw or None


def _build_question_response(
    session_id: str,
    question,
    question_number: int,
    total_questions: int,
) -> QuizQuestionResponse:
    """
    Преобразует QuizQuestion в QuizQuestionResponse (без раскрытия правильного ответа).
    """
    return QuizQuestionResponse(
        session_id=session_id,
        question_id=question.question_id,
        question_text=question.question_text,
        options=question.options,
        question_number=question_number,
        total_questions=total_questions,
    )


@router.post("/quiz/start", response_model=QuizQuestionResponse)
async def start_quiz(
    request: Request,
    body: QuizStartRequest,
):
    """
    Эндпоинт для старта нового квиза.
    Создаёт сессию, генерирует вопросы и возвращает первый вопрос.
    """
    settings = request.app.state.settings
    llm = request.app.state.llm
    session_store = get_quiz_session_store()

    quiz_service = QuizService(settings, llm, session_store)

    try:
        session, first_question = await quiz_service.start_quiz(body.level)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _build_question_response(
        session_id=session.session_id,
        question=first_question,
        question_number=1,
        total_questions=20,
    )


@router.post("/quiz/answer", response_model=QuizAnswerResponse)
async def submit_answer(
    request: Request,
    body: QuizAnswerRequest,
    background: BackgroundTasks,
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
):
    """
    Эндпоинт для отправки ответа на вопрос квиза.
    Возвращает правильность, объяснение и следующий вопрос (если есть).
    Если передан `X-Username`, ответ дополнительно пишется в статистику пользователя.
    """
    settings = request.app.state.settings
    llm = request.app.state.llm
    session_store = get_quiz_session_store()

    quiz_service = QuizService(settings, llm, session_store)

    try:
        (
            is_correct,
            correct_index,
            explanation,
            next_question,
            is_last,
        ) = await quiz_service.submit_answer(
            body.session_id,
            body.question_id,
            body.selected_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Формируем ответ
    next_response = None
    session = session_store.get(body.session_id)
    if next_question is not None and session is not None:
        next_response = _build_question_response(
            session_id=body.session_id,
            question=next_question,
            question_number=session.current_index + 1,
            total_questions=20,
        )

    # Запись в статистику (фоновая задача; не блокирует ответ пользователю)
    username = _opt_username(x_username)
    if username and session is not None:
        current_question = next(
            (q for q in session.questions if q.question_id == body.question_id),
            None,
        )
        if current_question is not None:
            user_answer_text = (
                current_question.options[body.selected_index]
                if 0 <= body.selected_index < len(current_question.options)
                else ""
            )
            background.add_task(
                persist_quiz_answer,
                username=username,
                external_session_id=body.session_id,
                question_text=current_question.question_text,
                user_answer=user_answer_text,
                correct_answer=current_question.correct_answer,
                is_correct=is_correct,
                explanation=explanation,
                level=session.level,
            )

    return QuizAnswerResponse(
        is_correct=is_correct,
        correct_index=correct_index,
        explanation=explanation,
        next_question=next_response,
        is_last=is_last,
    )


@router.get("/quiz/results/{session_id}", response_model=QuizResultsResponse)
async def get_results(
    request: Request,
    session_id: str,
):
    """
    Эндпоинт для получения итоговых результатов квиза.
    """
    settings = request.app.state.settings
    llm = request.app.state.llm
    session_store = get_quiz_session_store()

    quiz_service = QuizService(settings, llm, session_store)

    try:
        total_score, total_questions, level, answers = quiz_service.get_results(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    results = [
        QuizQuestionResult(
            question_text=record.question_text,
            user_answer=record.user_answer,
            correct_answer=record.correct_answer,
            is_correct=record.is_correct,
            explanation=record.explanation,
        )
        for record in answers
    ]

    return QuizResultsResponse(
        total_score=total_score,
        total_questions=total_questions,
        level=level,  # type: ignore[arg-type]
        results=results,
    )
