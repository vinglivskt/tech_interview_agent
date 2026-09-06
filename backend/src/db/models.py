"""ORM models for user statistics.

Модели:
- `User` — пользователь, идентифицируемый по нормализованному имени.
- `FeatureSession` — запись о сессии конкретного режима (chat/quiz/sobes/design),
  чтобы связать разрозненные ответы в одну сессию.
- `QuizAnswer`, `SobesAnswer`, `DesignAnswer`, `ChatMessage` — фактические ответы,
  по одной таблице на режим (чтобы не городить JSON-блобы и сохранить строгую типизацию).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Feature(enum.StrEnum):
    """Поддерживаемые режимы работы."""

    CHAT = "chat"
    QUIZ = "quiz"
    SOBES = "sobes"
    DESIGN = "design"


class AnswerCategory(enum.StrEnum):
    """Категория ответа (вычисляется при записи)."""

    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


def _utc_now() -> datetime:
    return datetime.utcnow()


class User(Base):
    """Пользователь, идентифицируемый по нормализованному имени."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    sessions: Mapped[list[FeatureSession]] = relationship(
        "FeatureSession", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User username={self.username!r}>"


class FeatureSession(Base):
    """Сессия работы в одном из режимов."""

    __tablename__ = "feature_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "feature", "external_id", name="uq_feature_sessions_user_feature_external"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature: Mapped[Feature] = mapped_column(SAEnum(Feature, name="feature_enum"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="sessions")


class QuizAnswer(Base):
    """Ответ на вопрос квиза (4 варианта, бинарная оценка)."""

    __tablename__ = "quiz_answers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_pk: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category: Mapped[AnswerCategory] = mapped_column(
        SAEnum(AnswerCategory, name="answer_category_enum"), nullable=False, index=True
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class SobesAnswer(Base):
    """Ответ на вопрос устного собеседования (свободная форма, % оценка)."""

    __tablename__ = "sobes_answers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_pk: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    is_counted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category: Mapped[AnswerCategory] = mapped_column(
        SAEnum(AnswerCategory, name="answer_category_enum"), nullable=False, index=True
    )
    techlead_explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    covered_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missed_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class DesignAnswer(Base):
    """Ответ на шаг системного дизайна."""

    __tablename__ = "design_answers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_pk: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scenario_id: Mapped[str] = mapped_column(String(128), nullable=False)
    step_id: Mapped[str] = mapped_column(String(128), nullable=False)
    step_title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    rubric: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    category: Mapped[AnswerCategory] = mapped_column(
        SAEnum(AnswerCategory, name="answer_category_enum"), nullable=False, index=True
    )
    covered_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missed_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    techlead_explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hint_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class ChatMessage(Base):
    """Сообщение пользователя/ассистента в чат-режиме (без оценки правильности)."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_pk: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class ApiRequestLog(Base):
    """Лог запросов пользователя (для отладки и аналитики)."""

    __tablename__ = "api_request_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(256), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class DesignScenario(Base):
    """Карточка сценария системного дизайна.

    Долговременное хранилище в PostgreSQL. Полные сценарии с пошаговыми
    ``steps`` (URL Shortener, News Feed, Object Storage) остаются в YAML —
    они перекрывают (``override``) карточки из БД по ``id``. Карточки без
    ``steps`` используются как «темы» с эволюцией архитектуры: ``DesignService``
    генерирует для них динамические шаги.
    """

    __tablename__ = "design_scenarios"
    __table_args__ = (
        Index("ix_design_scenarios_level", "level"),
        Index("ix_design_scenarios_category", "category"),
        Index("ix_design_scenarios_pattern", "primary_pattern"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_pattern: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requirements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    nfr: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    baseline_load: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evolution: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failure_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    advanced_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_detailed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


__all__ = [
    "AnswerCategory",
    "ApiRequestLog",
    "ChatMessage",
    "DesignAnswer",
    "DesignScenario",
    "Feature",
    "FeatureSession",
    "QuizAnswer",
    "SobesAnswer",
    "User",
]
