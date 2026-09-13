from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.db.database import session_factory
from src.db.repository import DesignScenariosRepository
from src.features.chat.providers.ollama import OllamaClient
from src.features.design.domain.graph import (
    build_design_graph,
    format_step_info,
)
from src.features.design.domain.models import DesignLevel
from src.features.design.domain.scenarios import (
    Scenario,
    Step,
    build_dynamic_steps,
    load_scenarios,
    scenario_from_db_row,
)


@dataclass
class DesignStepRecord:
    step_id: str
    user_answer: str
    score_percent: int
    rubric: dict[str, int]
    covered_points: list[str]
    missed_points: list[str]
    techlead_explanation: str
    hint_used: bool = False


@dataclass
class DesignSession:
    session_id: str
    level_requested: str
    scenario_id: str
    steps_order: list[str]
    current_index: int = 0
    answers: list[DesignStepRecord] = field(default_factory=list)
    hinted_steps: set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    # Расширения: эволюция и failure_questions для UI
    scenario_meta: dict = field(default_factory=dict)


class DesignSessionStore:
    def __init__(self, max_sessions: int = 300, ttl_seconds: int = 60 * 60 * 6) -> None:
        self.max_sessions = max_sessions
        self.ttl = ttl_seconds
        self.store: OrderedDict[str, tuple[float, DesignSession]] = OrderedDict()

    def _prune(self) -> None:
        now = time.time()
        expired = [sid for sid, (ts, _) in self.store.items() if now - ts > self.ttl]
        for sid in expired:
            self.store.pop(sid, None)

    def get(self, session_id: str) -> DesignSession | None:
        self._prune()
        entry = self.store.get(session_id)
        if not entry:
            return None
        ts, sess = entry
        if time.time() - ts > self.ttl:
            self.store.pop(session_id, None)
            return None
        self.store.move_to_end(session_id)
        return sess

    def save(self, session: DesignSession) -> None:
        self._prune()
        self.store[session.session_id] = (time.time(), session)
        self.store.move_to_end(session.session_id)
        while len(self.store) > self.max_sessions:
            self.store.popitem(last=False)


# Гарантированный общий чекпоинтер для всех экземпляров DesignService
# (сервисы создаются per-request, но графы обязаны разделять состояние).
_DEFAULT_CHECKPOINTER = MemorySaver()


def _encode_session_id(scenario_id: str) -> str:
    """Формат ``design_{scenario_id}_{8 hex}``: scenario_id восстанавливается rsplit."""
    return f"design_{scenario_id}_{uuid.uuid4().hex[:8]}"


def _scenario_id_from_session(session_id: str) -> str:
    """Достаёт scenario_id из session_id; для внешних/чужих id — ValueError."""
    core = session_id[len("design_") :] if session_id.startswith("design_") else ""
    parts = core.rsplit("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Сессия не найдена или истекла")
    return parts[0]


class DesignService:
    """Сервис режима «Системный дизайн».

    Источники сценариев:
    - PostgreSQL (`design_scenarios`) — долговременное хранилище;
    - YAML (`prompts/design/scenarios.yaml`) — override-слой для детальных
      сценариев с ``steps`` (URL Shortener, News Feed, Object Storage).
    """

    def __init__(
        self,
        settings: Settings,
        llm: OllamaClient,
        store: DesignSessionStore | None = None,
        db_session_factory: async_sessionmaker[AsyncSession] | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._store = store or DesignSessionStore()
        if db_session_factory is None:
            db_session_factory = session_factory()
        self._db_session_factory = db_session_factory
        # Кэш компилированных LangGraph-графов по scenario_id
        self._graphs: dict[str, Any] = {}
        self._graph_checkpointer = checkpointer or _DEFAULT_CHECKPOINTER
        # Кэш YAML-слоя: полные сценарии с steps
        self._yaml_scenarios: list[Scenario] | None = None

    # ---------------- источники сценариев ----------------

    def _load_yaml_scenarios(self) -> list[Scenario]:
        if self._yaml_scenarios is None:
            self._yaml_scenarios = load_scenarios(self._settings)
        return self._yaml_scenarios

    def _yaml_scenario_by_id(self, scenario_id: str) -> Scenario | None:
        for s in self._load_yaml_scenarios():
            if s.id == scenario_id:
                return s
        return None

    # ---------------- LangGraph-исполнитель ----------------

    async def _scenario_by_id(self, scenario_id: str) -> Scenario:
        yaml_scen = self._yaml_scenario_by_id(scenario_id)
        if yaml_scen is not None:
            if not yaml_scen.steps:
                yaml_scen.steps = build_dynamic_steps(yaml_scen)
            return yaml_scen
        db_scen = await self._db_scenario_by_id(scenario_id)
        if db_scen is None:
            raise ValueError(f"Сценарий {scenario_id} не найден")
        if not db_scen.steps:
            db_scen.steps = build_dynamic_steps(db_scen)
        return db_scen

    def _graph_for(self, scenario: Scenario) -> Any:
        graph = self._graphs.get(scenario.id)
        if graph is None:
            graph = build_design_graph(
                scenario,
                self._settings,
                self._llm,
                self._graph_checkpointer,
            )
            max_cache = int(getattr(self._settings, "design_graph_max_cache", 64))
            if max_cache > 0 and len(self._graphs) >= max_cache:
                self._graphs.clear()
            self._graphs[scenario.id] = graph
        return graph

    @staticmethod
    def _thread_config(session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

    async def _session_state(self, session_id: str, graph: Any, scenario_id: str) -> dict:
        snapshot = await graph.aget_state(self._thread_config(session_id))
        values = snapshot.values or {}
        if not values or values.get("scenario_id") != scenario_id:
            raise ValueError("Сессия не найдена или истекла")
        return values

    @staticmethod
    def _current_step_id(state: dict) -> str | None:
        step_ids = state.get("step_ids") or []
        idx = state.get("idx") or 0
        if idx >= len(step_ids):
            return None
        return step_ids[idx]

    async def _db_scenario_by_id(self, scenario_id: str) -> Scenario | None:
        async with self._db_session_factory() as session:
            repo = DesignScenariosRepository(session)
            row = await repo.get(scenario_id)
            if row is None:
                return None
            return scenario_from_db_row(row)

    async def _db_scenarios_brief(self) -> list[dict]:
        async with self._db_session_factory() as session:
            repo = DesignScenariosRepository(session)
            return await repo.list_brief()

    async def _db_categories(self) -> list[dict]:
        async with self._db_session_factory() as session:
            repo = DesignScenariosRepository(session)
            return await repo.list_categories()

    async def _db_random(
        self,
        level: str | None,
        category: str | None,
        exclude_ids: list[str],
    ) -> Scenario | None:
        async with self._db_session_factory() as session:
            repo = DesignScenariosRepository(session)
            row = await repo.get_random(level=level, category=category, exclude_ids=exclude_ids)
            if row is None:
                return None
            return scenario_from_db_row(row)

    async def _db_count(self) -> int:
        async with self._db_session_factory() as session:
            repo = DesignScenariosRepository(session)
            return await repo.count()

    async def list_all_scenarios(self) -> list[Scenario]:
        """Все сценарии: из БД + override-слой YAML (по id без дублей)."""
        out: dict[str, Scenario] = {}
        async with self._db_session_factory() as session:
            repo = DesignScenariosRepository(session)
            # Подтянем полные строки с большими JSON
            rows = await repo.list_brief()
        for row in rows:
            scen = await self._db_scenario_by_id(row["id"])
            if scen is not None:
                out[scen.id] = scen
        for s in self._load_yaml_scenarios():
            out[s.id] = s
        return list(out.values())

    # ---------------- публичные методы ----------------

    async def config(self) -> tuple[list[str], list[dict], list[dict], int]:
        levels = getattr(self._settings, "design_levels", ["junior", "middle", "senior"])

        # Сценарии: объединяем БД и YAML
        db_scenarios = await self._db_scenarios_brief()
        yaml_scenarios = self._load_yaml_scenarios()
        seen: set[str] = set()
        merged: list[dict] = []
        for s in db_scenarios:
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            merged.append(s)
        for s in yaml_scenarios:
            if s.id in seen:
                # Сценарий с детальными steps из YAML перекрывает карточку из БД.
                if s.steps:
                    merged = [m if m["id"] != s.id else {**m, "is_detailed": True, "summary": s.summary} for m in merged]
                continue
            seen.add(s.id)
            merged.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "level": s.level,
                    "category": s.category or "basics",
                    "primary_pattern": s.primary_pattern,
                    "summary": s.summary,
                    "is_detailed": bool(s.steps),
                }
            )

        # Категории: БД + YAML, считаем суммарно
        db_categories = {c["id"]: c["count"] for c in await self._db_categories()}
        for s in yaml_scenarios:
            cat = s.category or "basics"
            db_categories[cat] = db_categories.get(cat, 0) + 1
        category_titles = {
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
        categories = [
            {
                "id": cat_id,
                "title": category_titles.get(cat_id, cat_id.title()),
                "count": count,
            }
            for cat_id, count in sorted(db_categories.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

        return (
            list(levels),
            merged,
            categories,
            len(merged),
        )

    async def pick_scenario(
        self,
        level: DesignLevel,
        scenario_id: str | None,
        category: str | None,
        random_pick: bool,
    ) -> Scenario:
        """Выбор сценария по правилам приоритета."""
        # 1. Явный id — ищем сначала в YAML, потом в БД
        if scenario_id:
            yaml_scen = self._yaml_scenario_by_id(scenario_id)
            if yaml_scen is not None:
                if not yaml_scen.steps:
                    yaml_scen.steps = build_dynamic_steps(yaml_scen)
                return yaml_scen
            db_scen = await self._db_scenario_by_id(scenario_id)
            if db_scen is not None:
                # Если в БД нет steps — сгенерируем динамические
                if not db_scen.steps:
                    db_scen.steps = build_dynamic_steps(db_scen)
                return db_scen
            raise ValueError(f"Сценарий {scenario_id} не найден")

        # 2. Random — из БД по фильтрам
        if random_pick:
            db_scen = await self._db_random(level, category, exclude_ids=[])
            if db_scen is not None:
                if not db_scen.steps:
                    db_scen.steps = build_dynamic_steps(db_scen)
                return db_scen
            # fallback на YAML
            yaml_pool = [s for s in self._load_yaml_scenarios() if s.level == level]
            if yaml_pool:
                yaml_fallback = yaml_pool[0]
                if not yaml_fallback.steps:
                    yaml_fallback.steps = build_dynamic_steps(yaml_fallback)
                return yaml_fallback

        # 3. По уровню: сначала детальные из YAML, потом первый из БД
        yaml_match = next((s for s in self._load_yaml_scenarios() if s.level == level), None)
        if yaml_match is not None:
            if not yaml_match.steps:
                yaml_match.steps = build_dynamic_steps(yaml_match)
            return yaml_match

        db_scen = await self._db_random(level, category, exclude_ids=[])
        if db_scen is None:
            raise ValueError("Сценарии не найдены")
        if not db_scen.steps:
            db_scen.steps = build_dynamic_steps(db_scen)
        return db_scen

    async def start(
        self,
        level: DesignLevel,
        scenario_id: str | None,
        category: str | None = None,
        random_pick: bool = False,
    ) -> tuple[DesignSession, dict, dict]:
        scenario = await self.pick_scenario(level, scenario_id, category, random_pick)
        if not scenario.steps:
            raise ValueError("У сценария нет шагов")
        graph = self._graph_for(scenario)
        steps_order = [st.id for st in scenario.steps]
        session_id = _encode_session_id(scenario.id)
        initial: dict[str, Any] = {
            "session_id": session_id,
            "scenario_id": scenario.id,
            "level": level,
            "step_ids": steps_order,
            "idx": 0,
            "steps_answer_total": len(steps_order),
        }
        try:
            await graph.ainvoke(dict(initial), self._thread_config(session_id))
        except Exception as exc:
            raise ValueError("Не удалось начать интервью: состояние не подготовлено") from exc
        session = DesignSession(
            session_id=session_id,
            level_requested=level,
            scenario_id=scenario.id,
            steps_order=steps_order,
            scenario_meta={
                "category": scenario.category,
                "primary_pattern": scenario.primary_pattern,
                "failure_questions": scenario.failure_questions,
                "advanced_questions": scenario.advanced_questions,
                "evolution": [
                    {
                        "id": lv.id,
                        "name": lv.name,
                        "summary": lv.summary,
                        "diagram": lv.diagram,
                        "prompts": lv.prompts,
                    }
                    for lv in scenario.evolution
                ],
            },
        )
        self._store.save(session)
        first = scenario.steps[0]
        scenario_info = {
            "id": scenario.id,
            "title": scenario.title,
            "level": scenario.level,
            "summary": scenario.summary,
            "category": scenario.category,
            "primary_pattern": scenario.primary_pattern,
            "evolution": session.scenario_meta["evolution"],
            "failure_questions": scenario.failure_questions,
        }
        step_info = format_step_info(scenario, first, first=True)
        return session, scenario_info, step_info

    async def hint(self, session_id: str, step_id: str) -> tuple[str, int]:
        scenario = await self._scenario_by_id(_scenario_id_from_session(session_id))
        graph = self._graph_for(scenario)
        state = await self._session_state(session_id, graph, scenario.id)
        current = self._current_step_id(state)
        if current is None:
            raise ValueError("Все шаги сценария уже отвечены")
        if step_id != current:
            raise ValueError("Можно отвечать только на текущий шаг сценария")
        step = self._get_step(scenario, step_id)
        if step_id not in state.get("hints", []):
            await graph.aupdate_state(
                self._thread_config(session_id),
                {"hints": [step_id]},
            )
        penalty = int(getattr(self._settings, "design_hint_penalty_percent", 10))
        return (
            step.hint
            or "Подумай о функциональных и нефункциональных требованиях, затем нарисуй HLA.",
            penalty,
        )

    @staticmethod
    def _get_step(scenario: Scenario, step_id: str) -> Step:
        for st in scenario.steps:
            if st.id == step_id:
                return st
        raise ValueError(f"Шаг {step_id} не найден в сценарии {scenario.id}")

    async def answer(
        self, session_id: str, step_id: str, user_answer: str
    ) -> tuple[int, dict, list[str], list[str], str, dict | None, bool, list[str], list[str]]:
        if not user_answer.strip():
            raise ValueError("Ответ не должен быть пустым")
        scenario = await self._scenario_by_id(_scenario_id_from_session(session_id))
        graph = self._graph_for(scenario)
        state = await self._session_state(session_id, graph, scenario.id)
        current = self._current_step_id(state)
        if current is None:
            raise ValueError("Все шаги сценария уже отвечены")
        if step_id != current:
            raise ValueError("Можно отвечать только на текущий шаг сценария")
        await graph.ainvoke(
            Command(resume=user_answer.strip()),
            self._thread_config(session_id),
        )
        updated = await graph.aget_state(self._thread_config(session_id))
        last = (updated.values or {}).get("last_result") or {}
        return (
            last["score_percent"],
            last["rubric"],
            last["covered_points"],
            last["missed_points"],
            last["techlead_explanation"],
            last.get("next_step"),
            last["is_last"],
            last["failure_questions"],
            last["advanced_questions"],
        )

    async def results(
        self, session_id: str
    ) -> tuple[dict, dict, list[str], list[str], list[dict], str]:
        scenario = await self._scenario_by_id(_scenario_id_from_session(session_id))
        graph = self._graph_for(scenario)
        state = await self._session_state(session_id, graph, scenario.id)
        answers = state.get("answers", [])
        total = len(state.get("step_ids", []))
        passed = sum(
            1
            for a in answers
            if a["score_percent"] >= getattr(self._settings, "design_pass_threshold_percent", 50)
        )
        avg = int(round(sum(a["score_percent"] for a in answers) / max(1, len(answers))))
        keys = ["reqs", "arch", "data", "scale", "tradeoffs"]
        acc = {k: [] for k in keys}
        for a in answers:
            for k in keys:
                acc[k].append(int(a.get("rubric", {}).get(k, 0)))
        by_rubric = {k: int(round(sum(v) / max(1, len(v)))) for k, v in acc.items()}
        strengths = sorted(keys, key=lambda k: by_rubric[k], reverse=True)[:3]
        weaknesses = sorted(keys, key=lambda k: by_rubric[k])[:3]
        details = [
            {
                "step_id": a["step_id"],
                "title": self._get_step(scenario, a["step_id"]).title,
                "score_percent": a["score_percent"],
                "rubric": a.get("rubric", {}),
                "explanation": a["techlead_explanation"],
            }
            for a in answers
        ]
        if avg <= 60 or passed / max(1, total) <= 0.6:
            verdict = "junior"
        elif avg <= 80:
            verdict = "middle"
        else:
            verdict = "senior"
        summary = {"steps": total, "passed": passed, "avg_percent": avg}
        return summary, by_rubric, strengths, weaknesses, details, verdict

    async def step_persist_context(self, session_id: str, step_id: str) -> dict:
        """Контекст persist-пути: scenario_id, заголовок шага, факт подсказки, уровень."""
        scenario = await self._scenario_by_id(_scenario_id_from_session(session_id))
        graph = self._graph_for(scenario)
        state = await self._session_state(session_id, graph, scenario.id)
        step = next((st for st in scenario.steps if st.id == step_id), None)
        return {
            "scenario_id": scenario.id,
            "step_title": step.title if step else "",
            "hint_used": step_id in state.get("hints", []),
            "level": state.get("level"),
        }

    async def scenario_detail(self, scenario_id: str) -> dict | None:
        """Полная карточка сценария для предпросмотра во фронте."""
        scen = self._yaml_scenario_by_id(scenario_id)
        if scen is None:
            scen = await self._db_scenario_by_id(scenario_id)
        if scen is None:
            return None
        return {
            "id": scen.id,
            "title": scen.title,
            "level": scen.level,
            "category": scen.category,
            "primary_pattern": scen.primary_pattern,
            "summary": scen.summary,
            "requirements": scen.requirements,
            "nfr": scen.nfr,
            "constraints": scen.constraints,
            "topics": scen.topics,
            "tags": scen.tags,
            "baseline_load": scen.baseline_load,
            "acceptance_criteria": scen.acceptance_criteria,
            "evolution": [
                {
                    "id": lv.id,
                    "name": lv.name,
                    "summary": lv.summary,
                    "diagram": lv.diagram,
                    "prompts": lv.prompts,
                }
                for lv in scen.evolution
            ],
            "failure_questions": scen.failure_questions,
            "advanced_questions": scen.advanced_questions,
        }
