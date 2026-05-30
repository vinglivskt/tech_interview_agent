"""Logging configuration.

Kept intentionally minimal; extend with structlog/json logging if needed.
"""

import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level)
