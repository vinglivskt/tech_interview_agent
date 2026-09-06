from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.core.config import Settings


@dataclass
class Step:
    id: str
    title: str
    prompt: str
    expected_points: list[str]
    rubric_weights: dict[str, float]
    hint: str | None = None


@dataclass
class EvolutionLevel:
    """Промежуточная стадия эволюции архитектуры (Level 1..N)."""

    id: str
    name: str
    summary: str
    diagram: str
    prompts: list[str] = field(default_factory=list)


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
    # Новые поля расширения
    category: str = ""
    tags: list[str] = field(default_factory=list)
    evolution: list[EvolutionLevel] = field(default_factory=list)
    failure_questions: list[str] = field(default_factory=list)
    advanced_questions: list[str] = field(default_factory=list)
    primary_pattern: str = ""


def _parse_step(raw: dict[str, Any]) -> Step:
    return Step(
        id=raw["id"],
        title=raw["title"],
        prompt=raw["prompt"],
        expected_points=list(raw.get("expected_points", [])),
        rubric_weights=dict(raw.get("rubric_weights", {})),
        hint=raw.get("hint"),
    )


def _parse_evolution(raw: Any) -> list[EvolutionLevel]:
    if not raw:
        return []
    out: list[EvolutionLevel] = []
    for item in raw:
        out.append(
            EvolutionLevel(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                summary=str(item.get("summary", "")),
                diagram=str(item.get("diagram", "")),
                prompts=[str(p) for p in item.get("prompts", []) or []],
            )
        )
    return out


def _parse_scenario(raw: dict[str, Any]) -> Scenario:
    return Scenario(
        id=raw["id"],
        title=raw["title"],
        level=raw["level"],
        summary=raw.get("summary", ""),
        requirements=list(raw.get("requirements", [])),
        nfr=list(raw.get("nfr", [])),
        constraints=list(raw.get("constraints", [])),
        baseline_load=dict(raw.get("baseline_load", {})),
        topics=list(raw.get("topics", [])),
        steps=[_parse_step(x) for x in raw.get("steps", [])],
        acceptance_criteria=list(raw.get("acceptance_criteria", [])),
        category=str(raw.get("category", "")),
        tags=[str(t) for t in raw.get("tags", []) or []],
        evolution=_parse_evolution(raw.get("evolution")),
        failure_questions=[str(q) for q in raw.get("failure_questions", []) or []],
        advanced_questions=[str(q) for q in raw.get("advanced_questions", []) or []],
        primary_pattern=str(raw.get("primary_pattern", "")),
    )


def _read_yaml(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(raw_data, dict):
        raw = raw_data.get("scenarios", [])
    else:
        raw = raw_data if isinstance(raw_data, list) else []
    return [item for item in raw if isinstance(item, dict)]


def load_scenarios(settings: Settings) -> list[Scenario]:
    """Загружает сценарии: сначала основной YAML, затем библиотеку (library.yaml).

    Полные сценарии из основного файла имеют приоритет над черновиками из библиотеки
    (мерж по ``id``). Так избегаем дрейфа определений и храним одно место правды для
    детальных ``steps``.
    """
    main_path = Path(getattr(settings, "design_scenarios_path", "prompts/design/scenarios.yaml"))
    library_path = Path(getattr(settings, "design_library_path", str(main_path.parent / "library.yaml")))

    main_raw = _read_yaml(main_path)
    library_raw = _read_yaml(library_path) if library_path != main_path else []

    by_id: dict[str, Scenario] = {}
    for raw in library_raw:
        scen = _parse_scenario(raw)
        by_id[scen.id] = scen
    for raw in main_raw:
        scen = _parse_scenario(raw)
        by_id[scen.id] = scen  # override

    return list(by_id.values())


def list_categories(scenarios: list[Scenario]) -> list[dict[str, Any]]:
    """Список категорий с количеством сценариев и кратким описанием."""
    titles: dict[str, str] = {
        "basics": "Базовые системы",
        "read-heavy": "Read-heavy нагрузка",
        "realtime": "Real-time",
        "queues": "Очереди и асинхронность",
        "distributed": "Distributed Systems",
        "db": "Database System Design",
        "kafka": "Kafka / Event-Driven",
        "ecommerce": "E-commerce",
        "search": "Search Systems",
        "social": "Социальные сети",
        "geo": "Геолокационные системы",
        "api": "API и Gateway",
        "reliability": "Надёжность и HA",
        "consistency": "Consistency и CAP",
        "observability": "Observability",
        "cdn": "CDN и Content Delivery",
        "security": "Security",
        "realworld": "Реальные системы",
        "pattern": "Паттерн-задачи",
    }
    counts: dict[str, int] = {}
    for scen in scenarios:
        cat = scen.category or "basics"
        counts[cat] = counts.get(cat, 0) + 1
    out: list[dict[str, Any]] = []
    for cat_id, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append({"id": cat_id, "title": titles.get(cat_id, cat_id.title()), "count": count})
    return out


def scenario_from_db_row(row: Any) -> Scenario:
    """Преобразует ORM-объект ``DesignScenario`` (или dict) в ``Scenario``.

    Принимает как ORM-инстанс, так и dict — удобно для тестов и для случая,
    когда данные пришли из SQL-запроса в виде словаря.
    """
    getter = (lambda key: getattr(row, key, None)) if not isinstance(row, dict) else (lambda key: row.get(key))

    def json_list(key: str, default: list | None = None) -> list:
        value = getter(key)
        if value is None:
            return list(default or [])
        if isinstance(value, list):
            return value
        return list(default or [])

    def json_dict(key: str, default: dict | None = None) -> dict:
        value = getter(key)
        if value is None:
            return dict(default or {})
        if isinstance(value, dict):
            return value
        return dict(default or {})

    raw_steps = json_list("steps")
    steps = [
        Step(
            id=str(item.get("id", "")),
            title=str(item.get("title", "")),
            prompt=str(item.get("prompt", "")),
            expected_points=[str(p) for p in item.get("expected_points", []) or []],
            rubric_weights=dict(item.get("rubric_weights", {}) or {}),
            hint=item.get("hint"),
        )
        for item in raw_steps
        if isinstance(item, dict) and item.get("id")
    ]
    evolution_raw = json_list("evolution")
    evolution = [
        EvolutionLevel(
            id=str(item.get("id", "")),
            name=str(item.get("name", "")),
            summary=str(item.get("summary", "")),
            diagram=str(item.get("diagram", "")),
            prompts=[str(p) for p in item.get("prompts", []) or []],
        )
        for item in evolution_raw
        if isinstance(item, dict)
    ]
    return Scenario(
        id=str(getter("id") or ""),
        title=str(getter("title") or ""),
        level=str(getter("level") or "middle"),
        summary=str(getter("summary") or ""),
        requirements=json_list("requirements"),
        nfr=json_list("nfr"),
        constraints=json_list("constraints"),
        baseline_load=json_dict("baseline_load"),
        topics=json_list("topics"),
        steps=steps,
        acceptance_criteria=json_list("acceptance_criteria"),
        category=str(getter("category") or "basics"),
        tags=json_list("tags"),
        evolution=evolution,
        failure_questions=json_list("failure_questions"),
        advanced_questions=json_list("advanced_questions"),
        primary_pattern=str(getter("primary_pattern") or ""),
    )


def build_dynamic_steps(scen: Scenario) -> list[Step]:
    """Генерирует шаги ``лестницы`` для сценария без явных ``steps``.

    Логика:
    - ``clarify`` → ``evolve-1..N`` (если есть ``evolution``) *или*
      ``hla`` → ``data`` → ``scale`` → ``tradeoffs`` (универсальная лесенка) →
      ``failure`` → ``advanced`` (senior).
    """
    out: list[Step] = []

    topics_hint = ", ".join(scen.topics[:4]) if scen.topics else "хранилище, кэш, очереди"
    load_hint = (
        f"Нагрузка: {scen.baseline_load}. " if scen.baseline_load else ""
    )

    # ------------------------------------------------------------------
    # 1. Уточнение требований
    # ------------------------------------------------------------------
    out.append(
        Step(
            id="clarify",
            title="Уточнение требований",
            prompt=(
                "Какие 5–8 вопросов вы зададите о продукте, масштабе, SLO и границах первой версии? "
                "После ответов кратко зафиксируйте свои допущения."
            ),
            expected_points=[
                "Функциональные требования",
                "NFR / SLO / доступность",
                "Границы и допущения",
            ],
            rubric_weights={"reqs": 0.7, "tradeoffs": 0.3},
            hint="Разделите требования на функциональные, NFR и то, что не входит в первую версию.",
        )
    )

    # ------------------------------------------------------------------
    # 2. Эволюция архитектуры ИЛИ универсальная лесенка
    # ------------------------------------------------------------------
    if scen.evolution:
        for index, level in enumerate(scen.evolution, start=1):
            out.append(
                Step(
                    id=f"evolve-{index}",
                    title=f"Уровень эволюции {index}: {level.name or level.id}",
                    prompt=(
                        f"{level.summary or 'Опишите архитектуру этого уровня.'} "
                        f"Архитектурная схема:\n{level.diagram or '(нет схемы)'}\n"
                        "Опишите write/read path, какие компоненты добавились и зачем, что может сломаться."
                    ),
                    expected_points=[
                        f"Обоснование перехода на уровень «{level.name or level.id}»",
                        "Компоненты и их роли",
                        "Что осталось узким местом",
                    ],
                    rubric_weights={"arch": 0.5, "scale": 0.3, "tradeoffs": 0.2},
                    hint=f"Сосредоточьтесь на том, что появилось нового: {level.name or level.id}.",
                )
            )
    else:
        # --- High-level архитектура ---
        out.append(
            Step(
                id="hla",
                title="High-level архитектура",
                prompt=(
                    f"Нарисуйте high-level схему решения ({scen.primary_pattern or 'на ваш выбор'}). "
                    f"Ключевые темы для обсуждения: {topics_hint}. "
                    "Пройдите по write path и read path, объяснив назначение каждого компонента."
                ),
                expected_points=[
                    "Основные компоненты и их роли",
                    "Write path и read path",
                    "Где используется кэш / очереди / реплики",
                ],
                rubric_weights={"arch": 0.7, "scale": 0.3},
                hint="Начните с клиентского запроса и проследите его путь до хранилища и обратно.",
            )
        )

        # --- Датамодель ---
        out.append(
            Step(
                id="data",
                title="Датамодель и хранилище",
                prompt=(
                    f"Выберите хранилище данных и покажите минимальную схему. "
                    f"Учтите ограничения: {', '.join(scen.constraints[:3]) if scen.constraints else 'консистентность, доступность'}. "
                    "Какие индексы, партиционирование или репликацию вы используете и почему?"
                ),
                expected_points=[
                    "Выбор хранилища и обоснование",
                    "Схема / модель данных",
                    "Индексы и партиционирование",
                ],
                rubric_weights={"data": 0.8, "tradeoffs": 0.2},
                hint="Сравните SQL vs NoSQL для конкретного кейса и назовите компромиссы.",
            )
        )

        # --- Масштабирование ---
        out.append(
            Step(
                id="scale",
                title="Масштабирование и отказоустойчивость",
                prompt=(
                    f"{load_hint}Нагрузка выросла в 10 раз — как меняются кэш, база и приложение? "
                    f"Какие метрики и алерты вы заведёте? "
                    f"Как защититесь от каскадных отказов?"
                ),
                expected_points=[
                    "Горизонтальное масштабирование компонентов",
                    "Кэширование и стратегия инвалидации",
                    "Метрики, алерты и план восстановления",
                ],
                rubric_weights={"scale": 0.8, "tradeoffs": 0.2},
                hint="Назовите конкретные пороги (QPS, latency, error rate) для алертов.",
            )
        )

        # --- Компромиссы ---
        out.append(
            Step(
                id="tradeoffs",
                title="Узкие места и компромиссы",
                prompt=(
                    "Назовите три наиболее рискованных места вашего дизайна. "
                    "Для каждого: что может сломаться, какие альтернативы рассматривались, "
                    "почему выбран именно этот вариант."
                ),
                expected_points=[
                    "Конкретные узкие места с обоснованием",
                    "Альтернативные подходы",
                    "Компромиссы: что получили vs что потеряли",
                ],
                rubric_weights={"tradeoffs": 0.7, "scale": 0.3},
                hint="Будьте честны — покажите, что понимаете слабые стороны решения.",
            )
        )

    # ------------------------------------------------------------------
    # 3. Отказные сценарии
    # ------------------------------------------------------------------
    if scen.failure_questions:
        joined = " ".join(f"«{q}»" for q in scen.failure_questions)
        out.append(
            Step(
                id="failure",
                title="Отказные сценарии и реакция системы",
                prompt=(
                    f"Ответьте на отказные вопросы интервьюера по вашему дизайну: {joined}"
                ),
                expected_points=[
                    "Конкретный сценарий отказа",
                    "Как система обнаружит проблему",
                    "План восстановления и компромиссы",
                ],
                rubric_weights={"scale": 0.5, "tradeoffs": 0.5},
                hint="Для каждого вопроса назовите детектор, реакцию и пользовательский эффект.",
            )
        )

    # ------------------------------------------------------------------
    # 4. Углублённые вопросы (senior)
    # ------------------------------------------------------------------
    if scen.level == "senior" and scen.advanced_questions:
        joined = " ".join(f"«{q}»" for q in scen.advanced_questions)
        out.append(
            Step(
                id="advanced",
                title="Углублённые вопросы (senior)",
                prompt=(
                    f"Разберите продвинутые аспекты вашего дизайна: {joined}"
                ),
                expected_points=[
                    "Глубокое понимание выбранного паттерна",
                    "Альтернативы и компромиссы",
                    "Границы применимости решения",
                ],
                rubric_weights={"arch": 0.3, "scale": 0.3, "tradeoffs": 0.4},
                hint="Не уходите в общие слова — покажите, что вы понимаете последствия выбора.",
            )
        )

    return out
