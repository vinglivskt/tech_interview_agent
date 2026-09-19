from __future__ import annotations

import asyncio

import yaml
from src.features.design.domain.library_repository import append_design_scenario


def _save(path, title: str):
    return asyncio.run(
        append_design_scenario(
            path,
            title=title,
            summary="Сервис для проверки добавления пользовательского сценария.",
            level="middle",
            category="basics",
            requirements=["Создать сущность"],
            nfr=["p99 не более 100 мс"],
            constraints=["Без дубликатов"],
            acceptance_criteria=["Описана защита от гонок"],
            topics=["api", "db"],
        )
    )


def test_append_design_scenario_adds_valid_yaml_without_rewriting_existing_content(tmp_path):
    library = tmp_path / "library.yaml"
    library.write_text("scenarios:\n  - id: existing\n    title: Existing\n", encoding="utf-8")

    result = _save(library, "Новый сценарий")

    assert result["status"] == "saved"
    data = yaml.safe_load(library.read_text(encoding="utf-8"))
    assert len(data["scenarios"]) == 2
    scenario = data["scenarios"][-1]
    assert scenario["id"].startswith("custom-")
    assert scenario["title"] == "Новый сценарий"
    assert scenario["steps"] == []
    assert scenario["requirements"] == ["Создать сущность"]


def test_append_design_scenario_skips_same_title(tmp_path):
    library = tmp_path / "library.yaml"
    library.write_text("scenarios:\n  - id: existing\n    title: Новый сценарий\n", encoding="utf-8")

    result = _save(library, "  новый   сценарий ")

    assert result == {"status": "skipped", "reason": "already_exists"}
