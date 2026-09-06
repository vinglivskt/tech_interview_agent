"""Repository layer: thin wrappers over SQLAlchemy session for stats.

Зачем нужен отдельный слой:
- централизует SQL и валидацию категорий;
- позволяет BackgroundTasks вызывать запись без знания моделей;
- упрощает юнит-тестирование (легко подменить на in-memory).

Все методы принимают `AsyncSession` явно — это удобно как для FastAPI Depends,
так и для фоновых задач, где мы открываем сессию вручную через `session_factory()`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AnswerCategory,
    ChatMessage,
    DesignAnswer,
    DesignScenario,
    Feature,
    FeatureSession,
    QuizAnswer,
    SobesAnswer,
    User,
)

logger = logging.getLogger(__name__)


def normalize_username(name: str) -> tuple[str, str]:
    """Возвращает (username, display_name) — нормализованное и отображаемое имя."""
    raw = (name or "").strip()
    if not raw:
        raise ValueError("Username must not be empty")
    display = raw
    username = raw.lower()
    return username, display


@dataclass
class StatsBreakdown:
    """Агрегированные счётчики по категориям для одной фичи."""

    feature: Feature
    total: int
    correct: int
    partial: int
    incorrect: int

    @property
    def accuracy_percent(self) -> float:
        """Точность: правильные + половина частично правильных, в процентах."""
        if self.total == 0:
            return 0.0
        score = self.correct + 0.5 * self.partial
        return round(score * 100.0 / self.total, 1)

    @property
    def pass_rate_percent(self) -> float:
        """Просто процент «зачтённых» ответов (correct + partial)."""
        if self.total == 0:
            return 0.0
        return round((self.correct + self.partial) * 100.0 / self.total, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature.value,
            "total": self.total,
            "correct": self.correct,
            "partial": self.partial,
            "incorrect": self.incorrect,
            "accuracy_percent": self.accuracy_percent,
            "pass_rate_percent": self.pass_rate_percent,
        }


class UsersRepository:
    """Операции с пользователями."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, raw_name: str) -> User:
        """Возвращает существующего или создаёт нового пользователя по нормализованному имени."""
        username, display = normalize_username(raw_name)
        result = await self.session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is not None:
            # touch last_seen
            user.last_seen_at = datetime.utcnow()
            await self.session.flush()
            return user

        user = User(username=username, display_name=display)
        self.session.add(user)
        await self.session.flush()
        return user


class SessionsRepository:
    """Операции с сессиями фич."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        user_id: uuid.UUID,
        feature: Feature,
        external_id: str,
        level: str | None = None,
        extra: dict | None = None,
    ) -> FeatureSession:
        """Возвращает существующую или создаёт новую запись о сессии."""
        result = await self.session.execute(
            select(FeatureSession).where(
                and_(
                    FeatureSession.feature == feature,
                    FeatureSession.external_id == external_id,
                    FeatureSession.user_id == user_id,
                )
            )
        )
        sess = result.scalar_one_or_none()
        if sess is not None:
            return sess

        sess = FeatureSession(
            user_id=user_id,
            feature=feature,
            external_id=external_id,
            level=level,
            extra=extra,
        )
        self.session.add(sess)
        await self.session.flush()
        return sess

    async def mark_ended(self, session_pk: uuid.UUID) -> None:
        await self.session.execute(
            update(FeatureSession).where(FeatureSession.id == session_pk).values(ended_at=datetime.utcnow())
        )


def categorize(score_percent: int, pass_threshold: int) -> AnswerCategory:
    """Возвращает категорию ответа по проценту и порогу."""
    if score_percent <= 0:
        return AnswerCategory.INCORRECT
    if score_percent >= pass_threshold:
        return AnswerCategory.CORRECT
    return AnswerCategory.PARTIAL


class QuizAnswersRepository:
    """Запись и чтение ответов квиза."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        session_pk: uuid.UUID | None,
        question_text: str,
        user_answer: str,
        correct_answer: str,
        is_correct: bool,
        explanation: str = "",
        level: str | None = None,
    ) -> QuizAnswer:
        category = AnswerCategory.CORRECT if is_correct else AnswerCategory.INCORRECT
        record = QuizAnswer(
            user_id=user_id,
            session_pk=session_pk,
            question_text=question_text,
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            category=category,
            explanation=explanation,
            level=level,
        )
        self.session.add(record)
        await self.session.flush()
        return record


class SobesAnswersRepository:
    """Запись и чтение ответов собеседования."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        session_pk: uuid.UUID | None,
        question_text: str,
        topic: str,
        user_answer: str,
        reference_answer: str = "",
        score_percent: int,
        is_counted: bool,
        pass_threshold: int,
        techlead_explanation: str = "",
        covered_points: list[str] | None = None,
        missed_points: list[str] | None = None,
        level: str | None = None,
    ) -> SobesAnswer:
        category = categorize(score_percent, pass_threshold)
        record = SobesAnswer(
            user_id=user_id,
            session_pk=session_pk,
            question_text=question_text,
            topic=topic,
            user_answer=user_answer,
            reference_answer=reference_answer,
            score_percent=score_percent,
            is_counted=is_counted,
            category=category,
            techlead_explanation=techlead_explanation,
            covered_points=covered_points,
            missed_points=missed_points,
            level=level,
        )
        self.session.add(record)
        await self.session.flush()
        return record


class DesignAnswersRepository:
    """Запись и чтение ответов системного дизайна."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        session_pk: uuid.UUID | None,
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
    ) -> DesignAnswer:
        category = categorize(score_percent, pass_threshold)
        record = DesignAnswer(
            user_id=user_id,
            session_pk=session_pk,
            scenario_id=scenario_id,
            step_id=step_id,
            step_title=step_title,
            user_answer=user_answer,
            score_percent=score_percent,
            rubric=rubric,
            category=category,
            covered_points=covered_points,
            missed_points=missed_points,
            techlead_explanation=techlead_explanation,
            hint_used=hint_used,
            level=level,
        )
        self.session.add(record)
        await self.session.flush()
        return record


class ChatMessagesRepository:
    """Запись сообщений чата."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        session_pk: uuid.UUID | None,
        session_key: str,
        role: str,
        content: str,
        meta: dict | None = None,
    ) -> ChatMessage:
        record = ChatMessage(
            user_id=user_id,
            session_pk=session_pk,
            session_key=session_key,
            role=role,
            content=content,
            meta=meta,
        )
        self.session.add(record)
        await self.session.flush()
        return record


class StatsRepository:
    """Агрегированная статистика для пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _counts(self, model: type, user_id: uuid.UUID) -> dict[AnswerCategory, int]:
        result = await self.session.execute(
            select(model.category, func.count()).where(model.user_id == user_id).group_by(model.category)
        )
        rows = result.all()
        out = {cat: 0 for cat in AnswerCategory}
        for cat, count in rows:
            out[cat] = int(count)
        return out

    async def breakdown(self, user_id: uuid.UUID, feature: Feature) -> StatsBreakdown:
        if feature is Feature.QUIZ:
            model = QuizAnswer
        elif feature is Feature.SOBES:
            model = SobesAnswer
        elif feature is Feature.DESIGN:
            model = DesignAnswer
        elif feature is Feature.CHAT:
            # В чате оценка хранится в ``meta`` сообщений ассистента.
            # Считаем оценённые диалоги (те, где ассистент выставил блок оценки
            # или пользователь явно отказался отвечать).
            result = await self.session.execute(
                select(ChatMessage.meta, ChatMessage.role).where(
                    (ChatMessage.user_id == user_id) & (ChatMessage.role == "assistant")
                )
            )
            correct = partial = incorrect = no_grade = 0
            for meta, _role in result.all():
                if not isinstance(meta, dict):
                    # Совсем старые сообщения без meta — считаем «без оценки».
                    no_grade += 1
                    continue
                if not meta.get("has_grade") and not meta.get("is_decline"):
                    no_grade += 1
                    continue
                cat = meta.get("category")
                if cat == AnswerCategory.CORRECT.value:
                    correct += 1
                elif cat == AnswerCategory.PARTIAL.value:
                    partial += 1
                elif cat == AnswerCategory.INCORRECT.value:
                    incorrect += 1
                else:
                    no_grade += 1
            total = correct + partial + incorrect
            return StatsBreakdown(
                feature=feature,
                total=total,
                correct=correct,
                partial=partial,
                incorrect=incorrect,
            )
        else:
            raise ValueError(f"Unknown feature: {feature}")

        counts = await self._counts(model, user_id)
        total = sum(counts.values())
        return StatsBreakdown(
            feature=feature,
            total=total,
            correct=counts[AnswerCategory.CORRECT],
            partial=counts[AnswerCategory.PARTIAL],
            incorrect=counts[AnswerCategory.INCORRECT],
        )

    async def list_recent(
        self,
        user_id: uuid.UUID,
        feature: Feature,
        *,
        only_incorrect: bool = False,
        only_partial: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Any]:
        if feature is Feature.CHAT:
            result = await self.session.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == user_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

        if feature is Feature.QUIZ:
            model = QuizAnswer
        elif feature is Feature.SOBES:
            model = SobesAnswer
        elif feature is Feature.DESIGN:
            model = DesignAnswer
        else:
            raise ValueError(f"Unknown feature: {feature}")

        stmt = select(model).where(model.user_id == user_id)
        if only_incorrect:
            stmt = stmt.where(model.category == AnswerCategory.INCORRECT)
        if only_partial:
            stmt = stmt.where(model.category == AnswerCategory.PARTIAL)
        stmt = stmt.order_by(model.answered_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_chat_pairs(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Возвращает последние N пар user/assistant для чат-режима.

        Каждая пара содержит оценку из ``meta`` сообщения ассистента
        (score_percent, category, level, ...). Если ассистент не выставил
        оценку (например, при «не знаю» в chat-промте) — поля остаются None.
        """
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit * 2)
        )
        rows = list(reversed(result.scalars().all()))
        pairs: list[dict[str, Any]] = []
        i = 0
        while i < len(rows) and len(pairs) < limit:
            if rows[i].role == "user" and i + 1 < len(rows) and rows[i + 1].role == "assistant":
                meta = rows[i + 1].meta or {}
                pairs.append(
                    {
                        "user_message": rows[i].content,
                        "assistant_answer": rows[i + 1].content,
                        "created_at": rows[i].created_at.isoformat(),
                        "score_percent": meta.get("score_percent"),
                        "category": meta.get("category"),
                        "is_decline": meta.get("is_decline"),
                        "has_grade": meta.get("has_grade"),
                        "comprehension": meta.get("comprehension"),
                        "depth": meta.get("depth"),
                        "accuracy": meta.get("accuracy"),
                        "level": meta.get("level"),
                    }
                )
                i += 2
            else:
                i += 1
        return pairs

    async def clear_feature(self, user_id: uuid.UUID, feature: Feature) -> int:
        """Удаляет все записи пользователя в указанном режиме.

        Возвращает количество удалённых строк.
        """
        from sqlalchemy import delete

        if feature is Feature.CHAT:
            model = ChatMessage
        elif feature is Feature.QUIZ:
            model = QuizAnswer
        elif feature is Feature.SOBES:
            model = SobesAnswer
        elif feature is Feature.DESIGN:
            model = DesignAnswer
        else:
            raise ValueError(f"Unknown feature: {feature}")

        result = await self.session.execute(delete(model).where(model.user_id == user_id))
        await self.session.commit()
        return int(result.rowcount or 0)


class DesignScenariosRepository:
    """Репозиторий сценариев системного дизайна (долговременное хранилище в PostgreSQL)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count(self) -> int:
        """Возвращает общее число сценариев в БД."""
        result = await self.session.execute(select(func.count(DesignScenario.id)))
        return int(result.scalar_one() or 0)

    async def list_brief(self, *, level: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
        """Возвращает краткие карточки сценариев (id, title, level, category, primary_pattern)."""
        stmt = select(
            DesignScenario.id,
            DesignScenario.title,
            DesignScenario.level,
            DesignScenario.category,
            DesignScenario.primary_pattern,
            DesignScenario.summary,
            DesignScenario.is_detailed,
        )
        if level:
            stmt = stmt.where(DesignScenario.level == level)
        if category:
            stmt = stmt.where(DesignScenario.category == category)
        stmt = stmt.order_by(DesignScenario.category, DesignScenario.title)
        result = await self.session.execute(stmt)
        return [
            {
                "id": row.id,
                "title": row.title,
                "level": row.level,
                "category": row.category,
                "primary_pattern": row.primary_pattern,
                "summary": row.summary or "",
                "is_detailed": bool(row.is_detailed),
            }
            for row in result.all()
        ]

    async def list_categories(self) -> list[dict[str, Any]]:
        """Возвращает список категорий со счётчиком сценариев (отсортирован по убыванию)."""
        stmt = (
            select(DesignScenario.category, func.count(DesignScenario.id))
            .group_by(DesignScenario.category)
            .order_by(func.count(DesignScenario.id).desc(), DesignScenario.category)
        )
        result = await self.session.execute(stmt)
        return [{"id": row[0], "count": int(row[1])} for row in result.all()]

    async def get(self, scenario_id: str) -> DesignScenario | None:
        """Возвращает ORM-сценарий по id или None."""
        result = await self.session.execute(select(DesignScenario).where(DesignScenario.id == scenario_id))
        return result.scalar_one_or_none()

    async def get_random(
        self,
        *,
        level: str | None = None,
        category: str | None = None,
        exclude_ids: Sequence[str] = (),
    ) -> DesignScenario | None:
        """Возвращает случайный сценарий по фильтрам (исключая ``exclude_ids``)."""
        stmt = select(DesignScenario)
        if level:
            stmt = stmt.where(DesignScenario.level == level)
        if category:
            stmt = stmt.where(DesignScenario.category == category)
        if exclude_ids:
            stmt = stmt.where(DesignScenario.id.notin_(list(exclude_ids)))
        stmt = stmt.order_by(func.random()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_many(self, rows: list[dict[str, Any]]) -> int:
        """Вставляет/обновляет сценарии. Возвращает количество обработанных строк."""
        if not rows:
            return 0
        # Нормализация JSON-полей
        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized.append(
                {
                    "id": str(row["id"]),
                    "title": str(row["title"]),
                    "level": str(row["level"]),
                    "category": str(row.get("category", "basics")),
                    "primary_pattern": str(row.get("primary_pattern", "")),
                    "summary": str(row.get("summary", "")),
                    "requirements": list(row.get("requirements", []) or []),
                    "nfr": list(row.get("nfr", []) or []),
                    "constraints": list(row.get("constraints", []) or []),
                    "baseline_load": dict(row.get("baseline_load", {}) or {}),
                    "topics": list(row.get("topics", []) or []),
                    "tags": list(row.get("tags", []) or []),
                    "steps": list(row.get("steps", []) or []),
                    "acceptance_criteria": list(row.get("acceptance_criteria", []) or []),
                    "evolution": list(row.get("evolution", []) or []),
                    "failure_questions": list(row.get("failure_questions", []) or []),
                    "advanced_questions": list(row.get("advanced_questions", []) or []),
                    "is_detailed": bool(row.get("is_detailed", False)),
                }
            )
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(DesignScenario).values(normalized)
        stmt = stmt.on_conflict_do_update(
            index_elements=[DesignScenario.id],
            set_={
                "title": stmt.excluded.title,
                "level": stmt.excluded.level,
                "category": stmt.excluded.category,
                "primary_pattern": stmt.excluded.primary_pattern,
                "summary": stmt.excluded.summary,
                "requirements": stmt.excluded.requirements,
                "nfr": stmt.excluded.nfr,
                "constraints": stmt.excluded.constraints,
                "baseline_load": stmt.excluded.baseline_load,
                "topics": stmt.excluded.topics,
                "tags": stmt.excluded.tags,
                "steps": stmt.excluded.steps,
                "acceptance_criteria": stmt.excluded.acceptance_criteria,
                "evolution": stmt.excluded.evolution,
                "failure_questions": stmt.excluded.failure_questions,
                "advanced_questions": stmt.excluded.advanced_questions,
                "is_detailed": stmt.excluded.is_detailed,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(stmt)
        return len(normalized)


__all__ = [
    "ChatMessagesRepository",
    "DesignAnswersRepository",
    "DesignScenariosRepository",
    "QuizAnswersRepository",
    "SessionsRepository",
    "SobesAnswersRepository",
    "StatsBreakdown",
    "StatsRepository",
    "UsersRepository",
    "normalize_username",
]
