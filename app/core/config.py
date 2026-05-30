"""Основной модуль конфигурации.

Примечание по миграции VSA: исторически настройки находились в `app/config.py`.
Этот модуль повторно экспортирует `Settings` и `get_settings` для предоставления нового пути импорта.
"""

from __future__ import annotations

from app.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
