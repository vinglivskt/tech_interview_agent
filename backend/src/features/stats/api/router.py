"""Stats API router.

Эндпоинты:
- GET /api/users/me                — профиль текущего пользователя
- GET /api/stats/overview          — агрегаты по всем 4 режимам
- GET /api/stats/{feature}         — агрегаты по одному режиму
- GET /api/stats/{feature}/answers — список последних ответов
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.deps import CurrentUser, get_current_user
from src.db.database import get_session, is_db_available
from src.db.models import ChatMessage, DesignAnswer, Feature, QuizAnswer, SobesAnswer
from src.db.repository import StatsRepository

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_db() -> None:
    if not await is_db_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL недоступна. Перезапустите сервис или проверьте docker compose.",
        )


@router.get("/users/me")
async def get_me(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Профиль текущего пользователя по заголовку `X-Username`."""
    await _require_db()
    return {
        "id": str(current.user.id),
        "username": current.username,
        "display_name": current.user.display_name,
        "created_at": current.user.created_at.isoformat(),
        "last_seen_at": current.user.last_seen_at.isoformat(),
    }


@router.get("/stats/overview")
async def stats_overview(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Сводная статистика по всем 4 режимам для текущего пользователя."""
    await _require_db()
    repo = StatsRepository(session)
    breakdown = {}
    for feat in (Feature.QUIZ, Feature.SOBES, Feature.DESIGN, Feature.CHAT):
        breakdown[feat.value] = (await repo.breakdown(current.user.id, feat)).to_dict()
    return {
        "user": {
            "id": str(current.user.id),
            "username": current.username,
            "display_name": current.user.display_name,
        },
        "features": breakdown,
    }


@router.get("/stats/{feature}")
async def stats_for_feature(
    feature: Feature,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Статистика по одному режиму."""
    await _require_db()
    repo = StatsRepository(session)
    bd = await repo.breakdown(current.user.id, feature)
    return bd.to_dict()


@router.get("/stats/{feature}/answers")
async def list_recent_answers(
    feature: Feature,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    only_incorrect: bool = Query(default=False),
    only_partial: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Список последних ответов пользователя в выбранном режиме."""
    await _require_db()

    if feature is Feature.CHAT:
        # В чате нет правильности, но можно показать пары сообщений
        repo = StatsRepository(session)
        pairs = await repo.list_chat_pairs(current.user.id, limit=limit)
        return {
            "feature": feature.value,
            "pairs": pairs,
            "total": len(pairs),
        }

    repo = StatsRepository(session)
    rows = await repo.list_recent(
        current.user.id,
        feature,
        only_incorrect=only_incorrect,
        only_partial=only_partial,
        limit=limit,
        offset=offset,
    )

    serialized: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_answer_row(row, feature)
        serialized.append(item)

    return {
        "feature": feature.value,
        "answers": serialized,
        "limit": limit,
        "offset": offset,
    }


def _serialize_answer_row(row: Any, feature: Feature) -> dict[str, Any]:
    """Преобразует ORM-объект ответа в JSON-словарь для UI."""
    if feature is Feature.QUIZ and isinstance(row, QuizAnswer):
        return {
            "id": str(row.id),
            "category": row.category.value,
            "question_text": row.question_text,
            "user_answer": row.user_answer,
            "correct_answer": row.correct_answer,
            "is_correct": row.is_correct,
            "explanation": row.explanation,
            "level": row.level,
            "answered_at": row.answered_at.isoformat(),
        }
    if feature is Feature.SOBES and isinstance(row, SobesAnswer):
        return {
            "id": str(row.id),
            "category": row.category.value,
            "question_text": row.question_text,
            "topic": row.topic,
            "user_answer": row.user_answer,
            "reference_answer": row.reference_answer,
            "score_percent": row.score_percent,
            "is_counted": row.is_counted,
            "techlead_explanation": row.techlead_explanation,
            "covered_points": row.covered_points or [],
            "missed_points": row.missed_points or [],
            "level": row.level,
            "answered_at": row.answered_at.isoformat(),
        }
    if feature is Feature.DESIGN and isinstance(row, DesignAnswer):
        return {
            "id": str(row.id),
            "category": row.category.value,
            "scenario_id": row.scenario_id,
            "step_id": row.step_id,
            "step_title": row.step_title,
            "user_answer": row.user_answer,
            "score_percent": row.score_percent,
            "rubric": row.rubric or {},
            "techlead_explanation": row.techlead_explanation,
            "covered_points": row.covered_points or [],
            "missed_points": row.missed_points or [],
            "hint_used": row.hint_used,
            "level": row.level,
            "answered_at": row.answered_at.isoformat(),
        }
    if feature is Feature.CHAT and isinstance(row, ChatMessage):
        return {
            "id": str(row.id),
            "role": row.role,
            "content": row.content,
            "created_at": row.created_at.isoformat(),
        }
    return {"id": str(getattr(row, "id", "")), "raw": str(row)}


__all__ = ["router"]
