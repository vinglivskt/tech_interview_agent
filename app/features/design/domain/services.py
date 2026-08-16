from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from app.core.config import Settings
from app.features.chat.providers.ollama import OllamaClient

from .models import DesignLevel
from .scenarios import Scenario, Step, load_scenarios


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
    created_at: float = field(default_factory=time.time)


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
    def __init__(self, settings: Settings, llm: OllamaClient, store: DesignSessionStore | None = None) -> None:
        self._settings = settings
        self._llm = llm
        self._store = store or DesignSessionStore()
        self._scenarios: list[Scenario] | None = None

    def _ensure_scenarios(self) -> list[Scenario]:
        if self._scenarios is None:
            self._scenarios = load_scenarios(self._settings)
        return self._scenarios

    def _pick_scenario(self, level: str, scenario_id: str | None) -> Scenario:
        scenarios = self._ensure_scenarios()
        if scenario_id:
            for s in scenarios:
                if s.id == scenario_id:
                    return s
            raise ValueError(f"Сценарий {scenario_id} не найден")
        # pick first matching level, fallback to any
        for s in scenarios:
            if s.level == level:
                return s
        if not scenarios:
            raise ValueError("Сценарии не найдены")
        return scenarios[0]

    def _get_step(self, scenario: Scenario, step_id: str) -> Step:
        for st in scenario.steps:
            if st.id == step_id:
                return st
        raise ValueError(f"Шаг {step_id} не найден в сценарии {scenario.id}")

    async def start(self, level: DesignLevel, scenario_id: str | None) -> tuple[DesignSession, dict, dict]:
        scenario = self._pick_scenario(level, scenario_id)
        if not scenario.steps:
            raise ValueError("У сценария нет шагов")
        session = DesignSession(
            session_id=f"design_{uuid.uuid4().hex}",
            level_requested=level,
            scenario_id=scenario.id,
            steps_order=[st.id for st in scenario.steps],
        )
        self._store.save(session)
        first = scenario.steps[0]
        scenario_info = {
            "id": scenario.id,
            "title": scenario.title,
            "level": scenario.level,
            "summary": scenario.summary,
        }
        step_info = {"id": first.id, "title": first.title, "prompt": first.prompt}
        return session, scenario_info, step_info

    async def hint(self, session_id: str, step_id: str) -> tuple[str, int]:
        scen = self._pick_scenario(self._store.get(session_id).level_requested, self._store.get(session_id).scenario_id)  # type: ignore
        step = self._get_step(scen, step_id)
        penalty = int(getattr(self._settings, "design_hint_penalty_percent", 10))
        return step.hint or "Подумай о функциональных и нефункциональных требованиях, затем нарисуй HLA.", penalty

    async def answer(
        self, session_id: str, step_id: str, user_answer: str
    ) -> tuple[int, dict, list[str], list[str], str, dict | None, bool]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        scen = self._pick_scenario(sess.level_requested, sess.scenario_id)
        step = self._get_step(scen, step_id)

        system = (
            "Ты системный архитектор/интервьюер. Оцени шаг системного дизайна по рубрике. "
            "Верни строго один JSON-объект по схеме: {score_percent:int 0..100, rubric:{reqs:int,arch:int,data:int,scale:int,tradeoffs:int}, "
            "covered_points:[str], missed_points:[str], techlead_explanation:str}."
        )
        user = (
            f"Шаг: {step.title}\nЗадание: {step.prompt}\nОжидаемые пункты: {json.dumps(step.expected_points, ensure_ascii=False)}\n"
            f"Ответ пользователя: {user_answer}"
        )
        try:
            text = await self._llm.generate(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=getattr(self._settings, "design_max_tokens", 800),
            )
            data = json.loads(text)
            score = int(max(0, min(100, int(data.get("score_percent", 0)))))
            rubric = {k: int(max(0, min(100, int(v)))) for k, v in (data.get("rubric", {}) or {}).items()}
            covered = [str(x) for x in data.get("covered_points", [])][:6]
            missed = [str(x) for x in data.get("missed_points", [])][:6]
            expl = str(data.get("techlead_explanation", "")).strip()
        except Exception:
            score, rubric, covered, missed, expl = 0, {}, [], [], "Ответ не соответствует ожиданиям по шагу"

        # штраф за подсказку, если использовалась
        # (если предыдущий вызов hint пометил шаг — здесь можно расширить хранение, пока пропустим и применим при results)

        # записать и продвинуться
        rec = DesignStepRecord(
            step_id=step.id,
            user_answer=user_answer,
            score_percent=score,
            rubric=rubric,
            covered_points=covered,
            missed_points=missed,
            techlead_explanation=expl,
            hint_used=False,
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
            next_step_info = {"id": nxt.id, "title": nxt.title, "prompt": nxt.prompt}
        return score, rubric, covered, missed, expl, next_step_info, is_last

    def results(self, session_id: str) -> tuple[dict, dict, list[str], list[str], list[dict], str]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        total = len(sess.steps_order)
        passed = sum(
            1 for a in sess.answers if a.score_percent >= getattr(self._settings, "design_pass_threshold_percent", 50)
        )
        avg = int(round(sum(a.score_percent for a in sess.answers) / max(1, len(sess.answers))))
        # агрегировать рубрику
        keys = ["reqs", "arch", "data", "scale", "tradeoffs"]
        acc = {k: [] for k in keys}
        for a in sess.answers:
            for k in keys:
                acc[k].append(int(a.rubric.get(k, 0)))
        by_rubric = {k: int(round(sum(v) / max(1, len(v)))) for k, v in acc.items()}
        strengths = sorted(keys, key=lambda k: by_rubric[k], reverse=True)[:3]
        weaknesses = sorted(keys, key=lambda k: by_rubric[k])[:3]
        details = [
            {
                "step_id": a.step_id,
                "title": a.step_id,
                "score_percent": a.score_percent,
                "rubric": a.rubric,
                "explanation": a.techlead_explanation,
            }
            for a in sess.answers
        ]
        # вердикт
        if avg <= 60 or passed / max(1, total) <= 0.6:
            verdict = "junior"
        elif avg <= 80:
            verdict = "middle"
        else:
            verdict = "senior"
        summary = {"steps": total, "passed": passed, "avg_percent": avg}
        return summary, by_rubric, strengths, weaknesses, details, verdict
