from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings


@dataclass
class Step:
    id: str
    title: str
    prompt: str
    expected_points: list[str]
    rubric_weights: dict[str, float]
    hint: str | None = None


@dataclass
class Scenario:
    id: str
    title: str
    level: str
    summary: str
    requirements: list[str]
    nfr: list[str]
    constraints: list[str]
    baseline_load: dict[str, Any]
    topics: list[str]
    steps: list[Step]
    acceptance_criteria: list[str]


def _parse_frontmatter(content: str) -> list[dict[str, Any]]:
    """Парсит frontmatter из MD файла (YAML между ---)."""
    parts = content.split("---")
    if len(parts) < 3:
        # Нет frontmatter, пробуем распарсить как чистый YAML
        return yaml.safe_load(content) or []
    # parts[0] - пусто или текст до первого ---, parts[1] - frontmatter, parts[2] - контент
    frontmatter = parts[1].strip()
    data = yaml.safe_load(frontmatter)
    return data.get("scenarios", []) if isinstance(data, dict) else data or []


def load_scenarios(settings: Settings) -> list[Scenario]:
    path = Path(getattr(settings, "design_scenarios_path", "prompts/design/scenarios.md"))
    if not path.exists():
        return []
    raw = _parse_frontmatter(path.read_text(encoding="utf-8"))
    out: list[Scenario] = []
    for s in raw:
        steps = [
            Step(
                id=x["id"],
                title=x["title"],
                prompt=x["prompt"],
                expected_points=list(x.get("expected_points", [])),
                rubric_weights=dict(x.get("rubric_weights", {})),
                hint=x.get("hint"),
            )
            for x in s.get("steps", [])
        ]
        out.append(
            Scenario(
                id=s["id"],
                title=s["title"],
                level=s["level"],
                summary=s.get("summary", ""),
                requirements=list(s.get("requirements", [])),
                nfr=list(s.get("nfr", [])),
                constraints=list(s.get("constraints", [])),
                baseline_load=dict(s.get("baseline_load", {})),
                topics=list(s.get("topics", [])),
                steps=steps,
                acceptance_criteria=list(s.get("acceptance_criteria", [])),
            )
        )
    return out
