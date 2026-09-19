"""Сохранение пользовательских сценариев в YAML-библиотеку системного дизайна."""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any

import yaml

_write_lock = asyncio.Lock()


def _items(value: list[str]) -> list[str]:
    """Очищает список строк, переданный формой."""
    return [item.strip() for item in value if item and item.strip()]


def _same_title(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    return normalize(left) == normalize(right)


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл библиотеки не найден: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get("scenarios", []) if isinstance(raw, dict) else []


async def append_design_scenario(
    path: Path,
    *,
    title: str,
    summary: str,
    level: str,
    category: str,
    requirements: list[str],
    nfr: list[str],
    constraints: list[str],
    acceptance_criteria: list[str],
    topics: list[str],
) -> dict[str, object]:
    """Добавляет минимальный сценарий в конец YAML, не переписывая существующую библиотеку."""
    async with _write_lock:
        scenarios = _load_scenarios(path)
        if any(_same_title(str(item.get("title", "")), title) for item in scenarios if isinstance(item, dict)):
            return {"status": "skipped", "reason": "already_exists"}

        scenario_id = f"custom-{uuid.uuid4().hex[:12]}"
        scenario = {
            "id": scenario_id,
            "title": title.strip(),
            "level": level,
            "category": category.strip() or "basics",
            "primary_pattern": "",
            "summary": summary.strip(),
            "requirements": _items(requirements),
            "nfr": _items(nfr),
            "constraints": _items(constraints),
            "baseline_load": {},
            "topics": _items(topics),
            "tags": ["custom"],
            "steps": [],
            "acceptance_criteria": _items(acceptance_criteria),
            "evolution": [],
            "failure_questions": [],
            "advanced_questions": [],
        }
        fragment = yaml.safe_dump(
            [scenario], allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000
        )
        indented = "\n".join(f"  {line}" if line else line for line in fragment.splitlines())
        with path.open("a", encoding="utf-8") as library:
            library.write(f"\n{indented}\n")

    return {"status": "saved", "id": scenario_id}
