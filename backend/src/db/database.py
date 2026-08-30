"""Async engine, session factory and FastAPI dependency for DB."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings
from src.db.base import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    """
    Создаёт async-движок SQLAlchemy для PostgreSQL.

    Вызывается один раз при старте приложения из lifespan.
    """
    global _engine, _session_factory, AsyncSessionLocal

    if _engine is not None:
        return _engine

    url = settings.database_url
    echo = bool(getattr(settings, "database_echo", False))

    _engine = create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    # Обратная совместимость: alias для уже-импортированных модулей.
    AsyncSessionLocal = _session_factory  # type: ignore[assignment]  # noqa: N806
    logger.info("Database engine initialised: %s", url.split("@")[-1])
    return _engine


async def dispose_engine() -> None:
    """Закрывает пул соединений (вызывается в конце lifespan)."""
    global _engine, _session_factory, AsyncSessionLocal
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    AsyncSessionLocal = None


def get_engine() -> AsyncEngine:
    """Возвращает инициализированный движок (или кидает ошибку, если не инициализирован)."""
    if _engine is None:
        raise RuntimeError("DB engine is not initialised; call init_engine() first")
    return _engine


async def create_all_tables() -> None:
    """
    Создаёт все таблицы (используется в MVP-режиме вместо отдельных миграций Alembic).

    Для продакшена предпочтительнее `alembic upgrade head`, но для простоты старта
    и поддержки `docker compose up` без дополнительных шагов — создаём таблицы
    автоматически при первом старте.
    """
    if _engine is None:
        raise RuntimeError("DB engine is not initialised")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_feature_session_constraint)


def _ensure_feature_session_constraint(sync_connection) -> None:
    """Safely updates the legacy session uniqueness constraint when needed.

    ``create_all`` intentionally does not alter existing tables.  This small,
    idempotent compatibility step keeps installations created before migration
    0002 consistent with the current ORM model.
    """
    inspector = inspect(sync_connection)
    constraints = {
        item["name"]: item.get("column_names", [])
        for item in inspector.get_unique_constraints("feature_sessions")
    }
    legacy_name = "uq_feature_sessions_feature_external"
    target_name = "uq_feature_sessions_user_feature_external"
    if legacy_name in constraints:
        sync_connection.exec_driver_sql(
            f'ALTER TABLE feature_sessions DROP CONSTRAINT "{legacy_name}"'
        )
    if target_name not in constraints:
        sync_connection.exec_driver_sql(
            "ALTER TABLE feature_sessions "
            "ADD CONSTRAINT uq_feature_sessions_user_feature_external "
            "UNIQUE (user_id, feature, external_id)"
        )


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency: выдаёт `AsyncSession` на время запроса.

    Использование:
        @router.get(...)
        async def handler(session: AsyncSession = Depends(get_session)):
            ...
    """
    if _session_factory is None:
        raise RuntimeError("DB session factory is not initialised")
    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Возвращает фабрику сессий (для использования в BackgroundTasks и репозиториях)."""
    if _session_factory is None:
        raise RuntimeError("DB session factory is not initialised")
    return _session_factory


async def is_db_available() -> bool:
    """Быстрая проверка доступности БД (для health-эндпоинтов)."""
    if _engine is None:
        return False
    try:
        async with _engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False
