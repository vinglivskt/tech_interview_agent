"""Core config module.

VSA migration note: historically settings lived in `app/config.py`.
This module re-exports `Settings` and `get_settings` to provide the new import path.
"""

from __future__ import annotations

from app.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
