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


def load_scenarios(settings: Settings) -> list[Scenario]:
    path = Path(getattr(settings, "design_scenarios_path", "prompts/design/scenarios.yaml"))
    if not path.exists():
        return []
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(raw_data, dict):
        raw = raw_data.get("scenarios", [])
    else:
        raw = raw_data if isinstance(raw_data, list) else []
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
