"""Конфигурация логирования.

Минималистичная настройка; при необходимости расширяйте через structlog/json.
"""

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """
    Настраивает базовое логирование для приложения.
    :param level: уровень логирования (по умолчанию INFO)
    """
    logging.basicConfig(level=level)
