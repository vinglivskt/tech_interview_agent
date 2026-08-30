"""FastAPI dependencies: current user identification by `X-Username` header.

В MVP-режиме аутентификации нет — пользователь идентифицируется по имени.
Имя нормализуется (`strip + lower`), при первом обращении создаётся запись в `users`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.db.models import User
from src.db.repository import UsersRepository, normalize_username


@dataclass
class CurrentUser:
    """Контейнер с пользователем и его первичным ключом."""

    user: User
    username: str  # нормализованное


def decode_username_header(value: str | None) -> str:
    """Decodes the percent-encoded username sent in an HTTP-safe header."""
    return unquote(value or "").strip()


def _extract_username(
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
    username: Annotated[str | None, Header(alias="Username")] = None,
) -> str:
    """Достаёт имя пользователя из заголовков `X-Username` / `Username`."""
    raw = decode_username_header(x_username or username)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не передано имя пользователя (заголовок X-Username). Сначала представьтесь на главной странице.",
        )
    if len(raw) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Имя пользователя слишком длинное (макс. 128 символов).",
        )
    return raw


async def get_current_user(
    raw_name: Annotated[str, Depends(_extract_username)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    """Возвращает текущего пользователя (создаёт, если отсутствует)."""
    repo = UsersRepository(session)
    try:
        user = await repo.get_or_create(raw_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    username, _ = normalize_username(raw_name)
    return CurrentUser(user=user, username=username)


__all__ = ["CurrentUser", "decode_username_header", "get_current_user"]
