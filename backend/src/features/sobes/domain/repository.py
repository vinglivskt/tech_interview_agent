from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.config import Settings
from src.features.chat.domain.interview_docx import InterviewQA, load_interview_qa

CACHE_VERSION = 1


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_qa(settings: Settings) -> tuple[list[InterviewQA], str]:
    docx_path = Path(settings.interview_docx_path)
    if not docx_path.exists():
        return [], ""
    items = load_interview_qa(docx_path)
    return items, _file_sha256(docx_path)


def load_cached_index(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cached_index(cache_path: Path, payload: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload["_cache_version"] = CACHE_VERSION
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def as_plain_dict(obj: Any) -> Any:
    try:
        return asdict(obj)
    except Exception:
        return obj
