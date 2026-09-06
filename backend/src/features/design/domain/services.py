from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.db.database import session_factory
from src.db.repository import DesignScenariosRepository
from src.features.chat.providers.ollama import OllamaClient
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
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._store = store or DesignSessionStore()
        if db_session_factory is None:
            db_session_factory = session_factory()
        self._db_session_factory = db_session_factory
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
        session = DesignSession(
            session_id=f"design_{uuid.uuid4().hex}",
            level_requested=level,
            scenario_id=scenario.id,
            steps_order=[st.id for st in scenario.steps],
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
        step_info = self._step_info(scenario, first, first=True)
        return session, scenario_info, step_info

    async def hint(self, session_id: str, step_id: str) -> tuple[str, int]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        self._assert_current_step(sess, step_id)
        scen = await self._scenario_by_id_for_session(sess)
        step = self._get_step(scen, step_id)
        sess.hinted_steps.add(step_id)
        self._store.save(sess)
        penalty = int(getattr(self._settings, "design_hint_penalty_percent", 10))
        return (
            step.hint
            or "Подумай о функциональных и нефункциональных требованиях, затем нарисуй HLA.",
            penalty,
        )

    async def _scenario_by_id_for_session(self, sess: DesignSession) -> Scenario:
        yaml_scen = self._yaml_scenario_by_id(sess.scenario_id)
        if yaml_scen is not None:
            return yaml_scen
        db_scen = await self._db_scenario_by_id(sess.scenario_id)
        if db_scen is None:
            raise ValueError(f"Сценарий {sess.scenario_id} не найден")
        if not db_scen.steps:
            db_scen.steps = build_dynamic_steps(db_scen)
        return db_scen

    @staticmethod
    def _assert_current_step(sess: DesignSession, step_id: str) -> None:
        if sess.current_index >= len(sess.steps_order):
            raise ValueError("Все шаги сценария уже отвечены")
        if sess.steps_order[sess.current_index] != step_id:
            raise ValueError("Можно отвечать только на текущий шаг сценария")

    @staticmethod
    def _step_info(scenario: Scenario, step: Step, *, first: bool = False) -> dict[str, str]:
        if first:
            prompt = (
                f"Интервьюер: «Давайте спроектируем {scenario.title}. {scenario.summary} "
                "Пока не рисуйте архитектуру: сначала задайте вопросы, которые помогут зафиксировать задачу. "
                "Если данных не хватает — явно сформулируйте и обоснуйте свои допущения».\n\n"
                f"Ваш ход: {step.prompt}"
            )
        else:
            prompt = f"Интервьюер: «Хорошо, зафиксируем эти допущения. {step.prompt}»"
        return {"id": step.id, "title": step.title, "prompt": prompt}

    @staticmethod
    def _get_step(scenario: Scenario, step_id: str) -> Step:
        for st in scenario.steps:
            if st.id == step_id:
                return st
        raise ValueError(f"Шаг {step_id} не найден в сценарии {scenario.id}")

    def _parse_score(self, text: str) -> tuple[int, dict[str, int], list[str], list[str], str]:
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {
            "score_percent",
            "rubric",
            "covered_points",
            "missed_points",
            "techlead_explanation",
        }:
            raise ValueError("Неверная JSON-схема оценки")
        if type(data["score_percent"]) is not int or not 0 <= data["score_percent"] <= 100:
            raise ValueError("Неверный score_percent")
        rubric_raw = data["rubric"]
        keys = {"reqs", "arch", "data", "scale", "tradeoffs"}
        if not isinstance(rubric_raw, dict) or set(rubric_raw) != keys:
            raise ValueError("Неверная рубрика")
        if any(type(value) is not int or not 0 <= value <= 100 for value in rubric_raw.values()):
            raise ValueError("Неверные значения рубрики")
        if not all(
            isinstance(data[key], list) and len(data[key]) <= 6
            for key in ("covered_points", "missed_points")
        ):
            raise ValueError("Неверные списки пунктов")
        if not isinstance(data["techlead_explanation"], str):
            raise ValueError("Неверное пояснение")
        max_len = int(getattr(self._settings, "design_max_explanation_len", 600))
        explanation = data["techlead_explanation"].strip()[:max_len]
        return (
            data["score_percent"],
            dict(rubric_raw),
            [str(item) for item in data["covered_points"]],
            [str(item) for item in data["missed_points"]],
            explanation,
        )

    async def answer(
        self, session_id: str, step_id: str, user_answer: str
    ) -> tuple[int, dict, list[str], list[str], str, dict | None, bool, list[str], list[str]]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        if not user_answer.strip():
            raise ValueError("Ответ не должен быть пустым")
        self._assert_current_step(sess, step_id)
        scen = await self._scenario_by_id_for_session(sess)
        step = self._get_step(scen, step_id)

        system = """Ты проводишь настоящий system design interview уровня Big Tech на русском языке.
Оцени только текущий ответ кандидата, но учитывай весь контекст сценария и его предыдущие решения.
Не награждай за перечисление технологий без причинно-следственной связи. Награждай за уточнение допущений,
оценки нагрузки, последовательность запросов, отказные сценарии и явные trade-offs. Не требуй деталей,
которые не относятся к текущему шагу. В `techlead_explanation` дай 2–4 конкретных предложения: что уже
звучит убедительно, один наиболее важный пробел и как его закрыть на интервью. Не пересказывай ответ.
Верни строго один JSON-объект без Markdown и без других ключей:
{score_percent:int 0..100, rubric:{reqs:int,arch:int,data:int,scale:int,tradeoffs:int},
covered_points:[str максимум 6], missed_points:[str максимум 6], techlead_explanation:str}.
Все значения rubric — целые 0..100; неиспользуемые категории ставь в 0."""
        history = [
            {"step_id": answer.step_id, "answer": answer.user_answer, "score": answer.score_percent}
            for answer in sess.answers
        ]
        user = (
            f"Сценарий: {scen.title}. {scen.summary}\n"
            f"Категория: {scen.category}; основной паттерн: {scen.primary_pattern or '—'}.\n"
            f"Факты, известные интервьюеру: requirements={json.dumps(scen.requirements, ensure_ascii=False)}, "
            f"NFR={json.dumps(scen.nfr, ensure_ascii=False)}, constraints={json.dumps(scen.constraints, ensure_ascii=False)}, "
            f"baseline_load={json.dumps(scen.baseline_load, ensure_ascii=False)}\n"
            f"Текущий шаг: {step.title}. Вопрос интервьюера: {step.prompt}\n"
            f"Критерии текущего шага: {json.dumps(step.expected_points, ensure_ascii=False)}; веса: {step.rubric_weights}\n"
            f"Предыдущие ответы: {json.dumps(history, ensure_ascii=False)}\n"
            f"Ответ кандидата: {user_answer}"
        )
        try:
            last_error: Exception | None = None
            for attempt in range(3):
                retry = (
                    ""
                    if attempt == 0
                    else " Предыдущий ответ невалиден: верни только JSON строго по указанной схеме."
                )
                text = await self._llm.generate(
                    [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.2,
                    max_tokens=getattr(self._settings, "design_max_tokens", 800),
                )
                try:
                    score, rubric, covered, missed, expl = self._parse_score(text)
                    break
                except Exception as exc:
                    last_error = exc
                    user += retry
            else:
                raise last_error or ValueError("Невалидный ответ LLM")
        except Exception:
            score, rubric, covered, missed, expl = (
                0,
                {},
                [],
                [],
                "Не удалось получить валидную оценку ответа.",
            )

        hint_used = step.id in sess.hinted_steps
        if hint_used:
            score = max(0, score - int(getattr(self._settings, "design_hint_penalty_percent", 10)))

        rec = DesignStepRecord(
            step_id=step.id,
            user_answer=user_answer,
            score_percent=score,
            rubric=rubric,
            covered_points=covered,
            missed_points=missed,
            techlead_explanation=expl,
            hint_used=hint_used,
        )
        sess.answers.append(rec)
        if sess.current_index < len(sess.steps_order):
            sess.current_index += 1
        self._store.save(sess)

        is_last = sess.current_index >= len(sess.steps_order)
        next_step_info = None
        if not is_last:
            nxt_id = sess.steps_order[sess.current_index]
            nxt = self._get_step(scen, nxt_id)
            next_step_info = self._step_info(scen, nxt)
        failure_questions = list(sess.scenario_meta.get("failure_questions") or [])
        advanced_questions = list(sess.scenario_meta.get("advanced_questions") or [])
        return (
            score,
            rubric,
            covered,
            missed,
            expl,
            next_step_info,
            is_last,
            failure_questions,
            advanced_questions,
        )

    async def results(
        self, session_id: str
    ) -> tuple[dict, dict, list[str], list[str], list[dict], str]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        total = len(sess.steps_order)
        passed = sum(
            1
            for a in sess.answers
            if a.score_percent >= getattr(self._settings, "design_pass_threshold_percent", 50)
        )
        avg = int(round(sum(a.score_percent for a in sess.answers) / max(1, len(sess.answers))))
        keys = ["reqs", "arch", "data", "scale", "tradeoffs"]
        acc = {k: [] for k in keys}
        for a in sess.answers:
            for k in keys:
                acc[k].append(int(a.rubric.get(k, 0)))
        by_rubric = {k: int(round(sum(v) / max(1, len(v)))) for k, v in acc.items()}
        strengths = sorted(keys, key=lambda k: by_rubric[k], reverse=True)[:3]
        weaknesses = sorted(keys, key=lambda k: by_rubric[k])[:3]
        scen = await self._scenario_by_id_for_session(sess)
        details = [
            {
                "step_id": a.step_id,
                "title": self._get_step(scen, a.step_id).title,
                "score_percent": a.score_percent,
                "rubric": a.rubric,
                "explanation": a.techlead_explanation,
            }
            for a in sess.answers
        ]
        if avg <= 60 or passed / max(1, total) <= 0.6:
            verdict = "junior"
        elif avg <= 80:
            verdict = "middle"
        else:
            verdict = "senior"
        summary = {"steps": total, "passed": passed, "avg_percent": avg}
        return summary, by_rubric, strengths, weaknesses, details, verdict

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
