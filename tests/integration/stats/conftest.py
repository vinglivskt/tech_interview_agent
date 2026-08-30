"""Conftest for stats API tests.

Подменяем `StatsRepository` на in-memory реализацию, чтобы тестировать
API-слой без поднятия PostgreSQL. Чистая логика категоризации/агрегации
покрыта в `tests/unit/db/test_pure_logic.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.core.deps import CurrentUser
from src.db.models import AnswerCategory, Feature
from src.features.stats.api.router import router as stats_router

# --- In-memory фейк StatsRepository ---


@dataclass
class FakeAnswer:
    user_id: str
    category: AnswerCategory
    answered_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


class FakeStatsRepo:
    def __init__(self) -> None:
        self._answers: list[FakeAnswer] = []
        self._chat_messages: list[FakeAnswer] = []

    async def breakdown(self, user_id: str, feature: Feature) -> Any:
        if feature is Feature.CHAT:
            total = sum(1 for m in self._chat_messages if m.user_id == user_id)
            return _StatsBreakdown(feature=feature, total=total, correct=0, partial=0, incorrect=0)
        correct = partial = incorrect = 0
        for a in self._answers:
            if a.user_id != user_id:
                continue
            if a.payload.get("feature") != feature:
                continue
            if a.category is AnswerCategory.CORRECT:
                correct += 1
            elif a.category is AnswerCategory.PARTIAL:
                partial += 1
            else:
                incorrect += 1
        total = correct + partial + incorrect
        return _StatsBreakdown(
            feature=feature,
            total=total,
            correct=correct,
            partial=partial,
            incorrect=incorrect,
        )

    async def list_recent(
        self,
        user_id: str,
        feature: Feature,
        *,
        only_incorrect: bool = False,
        only_partial: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> list[FakeAnswer]:
        if feature is Feature.CHAT:
            return [m for m in self._chat_messages if m.user_id == user_id][offset : offset + limit]
        rows = [a for a in self._answers if a.user_id == user_id and a.payload.get("feature") == feature]
        if only_incorrect:
            rows = [a for a in rows if a.category is AnswerCategory.INCORRECT]
        if only_partial:
            rows = [a for a in rows if a.category is AnswerCategory.PARTIAL]
        rows = sorted(rows, key=lambda x: x.answered_at, reverse=True)
        return rows[offset : offset + limit]

    async def list_chat_pairs(self, user_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        msgs = [m for m in self._chat_messages if m.user_id == user_id]
        msgs = sorted(msgs, key=lambda x: x.answered_at)
        pairs: list[dict[str, Any]] = []
        i = 0
        while i < len(msgs) and len(pairs) < limit:
            if (
                msgs[i].payload.get("role") == "user"
                and i + 1 < len(msgs)
                and msgs[i + 1].payload.get("role") == "assistant"
            ):
                pairs.append(
                    {
                        "user_message": msgs[i].payload["content"],
                        "assistant_answer": msgs[i + 1].payload["content"],
                        "created_at": msgs[i].answered_at.isoformat(),
                    }
                )
                i += 2
            else:
                i += 1
        return pairs

    def add(self, user_id: str, feature: Feature, category: AnswerCategory, payload: dict[str, Any]) -> None:
        item = FakeAnswer(
            user_id=user_id, category=category, answered_at=datetime.now(UTC), payload={"feature": feature, **payload}
        )
        if feature is Feature.CHAT:
            self._chat_messages.append(item)
        else:
            self._answers.append(item)

    def bind_user(self, user_id: str) -> None:
        """Перепривязывает все существующие записи к указанному user_id (для удобства тестов)."""
        for a in self._answers:
            a.user_id = user_id
        for m in self._chat_messages:
            m.user_id = user_id


@dataclass
class _StatsBreakdown:
    feature: Feature
    total: int
    correct: int
    partial: int
    incorrect: int

    @property
    def accuracy_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.correct + 0.5 * self.partial) * 100.0 / self.total, 1)

    @property
    def pass_rate_percent(self) -> float:
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


@pytest.fixture
def fake_repo() -> FakeStatsRepo:
    return FakeStatsRepo()


@pytest.fixture
def test_user_id() -> str:
    return str(uuid4())


@pytest.fixture
def app_with_overrides(fake_repo: FakeStatsRepo, test_user_id: str):
    """Создаёт FastAPI с подменёнными зависимостями для stats router."""
    from src.core.deps import get_current_user as real_dep_user
    from src.db.database import get_session as real_dep_session

    app = FastAPI()
    app.include_router(stats_router, prefix="/api")

    # Подменяем сессию — возвращаем фейковый объект (router её не использует напрямую,
    # но транзитивно через репозиторий, который мы тоже подменяем)
    async def _fake_session() -> AsyncIterator[Any]:
        yield None

    async def _fake_user() -> CurrentUser:
        # Возвращаем простой объект с user.id и username — репозиторий обращается к .id,
        # а stats router для /me использует .user.id, .user.display_name, .user.created_at, .user.last_seen_at,
        # .username.
        now = datetime.now(UTC)
        return CurrentUser(
            user=_FakeUser(id=test_user_id, display_name="Tester", created_at=now, last_seen_at=now),  # type: ignore[arg-type]
            username="tester",
        )

    # Подменим StatsRepository внутри роутера: перепишем функцию через dependency_overrides
    # роутер использует `StatsRepository(session)` напрямую, поэтому проксируем через
    # get_session и заменим конструктор в тестах через monkeypatch.
    app.dependency_overrides[real_dep_session] = _fake_session
    app.dependency_overrides[real_dep_user] = _fake_user

    yield app, fake_repo


@dataclass
class _FakeUser:
    id: str
    display_name: str
    created_at: datetime
    last_seen_at: datetime


@pytest.fixture
def client(app_with_overrides, monkeypatch):
    """Возвращает TestClient и фейковый репозиторий для манипуляций."""
    app, repo = app_with_overrides

    # Подменяем конструктор StatsRepository, чтобы он возвращал наш фейк
    def _factory(_session: Any) -> FakeStatsRepo:
        return repo

    monkeypatch.setattr("src.features.stats.api.router.StatsRepository", _factory)

    # Подменяем is_db_available, чтобы роутер не возвращал 503
    async def _fake_available() -> bool:
        return True

    monkeypatch.setattr("src.features.stats.api.router.is_db_available", _fake_available)

    with TestClient(app) as c:
        yield c, repo
