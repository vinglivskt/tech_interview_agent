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
    hinted_steps: set[str] = field(default_factory=set)
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

    @staticmethod
    def _step_info(scenario: Scenario, step: Step, *, first: bool = False) -> dict[str, str]:
        if first:
            prompt = (
                f"Интервьюер: «Давайте спроектируем {scenario.title}. {scenario.summary} "
                "Пока не рисуйте архитектуру: сначала задайте вопросы, которые помогут зафиксировать задачу. "
                "Я отвечу на разумные допущения в следующем раунде».\n\n"
                f"Ваш ход: {step.prompt}"
            )
        else:
            prompt = f"Интервьюер: «Хорошо, зафиксируем эти допущения. {step.prompt}»"
        return {"id": step.id, "title": step.title, "prompt": prompt}

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
        step_info = self._step_info(scenario, first, first=True)
        return session, scenario_info, step_info

    async def hint(self, session_id: str, step_id: str) -> tuple[str, int]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        self._assert_current_step(sess, step_id)
        scen = self._pick_scenario(sess.level_requested, sess.scenario_id)
        step = self._get_step(scen, step_id)
        sess.hinted_steps.add(step_id)
        self._store.save(sess)
        penalty = int(getattr(self._settings, "design_hint_penalty_percent", 10))
        return step.hint or "Подумай о функциональных и нефункциональных требованиях, затем нарисуй HLA.", penalty

    @staticmethod
    def _assert_current_step(sess: DesignSession, step_id: str) -> None:
        if sess.current_index >= len(sess.steps_order):
            raise ValueError("Все шаги сценария уже отвечены")
        if sess.steps_order[sess.current_index] != step_id:
            raise ValueError("Можно отвечать только на текущий шаг сценария")

    def _parse_score(self, text: str) -> tuple[int, dict[str, int], list[str], list[str], str]:
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {
            "score_percent", "rubric", "covered_points", "missed_points", "techlead_explanation"
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
        if not all(isinstance(data[key], list) and len(data[key]) <= 6 for key in ("covered_points", "missed_points")):
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
    ) -> tuple[int, dict, list[str], list[str], str, dict | None, bool]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        if not user_answer.strip():
            raise ValueError("Ответ не должен быть пустым")
        self._assert_current_step(sess, step_id)
        scen = self._pick_scenario(sess.level_requested, sess.scenario_id)
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
                retry = "" if attempt == 0 else " Предыдущий ответ невалиден: верни только JSON строго по указанной схеме."
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
            score, rubric, covered, missed, expl = 0, {}, [], [], "Не удалось получить валидную оценку ответа."

        hint_used = step.id in sess.hinted_steps
        if hint_used:
            score = max(0, score - int(getattr(self._settings, "design_hint_penalty_percent", 10)))

        # записать и продвинуться
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
                "title": self._get_step(self._pick_scenario(sess.level_requested, sess.scenario_id), a.step_id).title,
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
