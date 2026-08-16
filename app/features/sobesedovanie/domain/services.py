from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from app.core.config import Settings
from app.features.chat.domain.interview_docx import InterviewQA
from app.features.chat.providers.ollama import OllamaClient

from .classification import ClassifiedQA, classify_batch
from .models import (
    SobesAnswerRecord,
    SobesLevel,
    SobesQuestion,
    SobesQuestionDTO,
    SobesSession,
)
from .repository import as_plain_dict, load_cached_index, load_qa, save_cached_index
from .scoring import score_free_answer
from .selection import select_questions


@dataclass
class ClassifiedIndex:
    doc_hash: str
    items: list[ClassifiedQA]


class SobesSessionStore:
    def __init__(self, max_sessions: int = 500, ttl_seconds: int = 60 * 60 * 6) -> None:
        self.max_sessions = max_sessions
        self.ttl = ttl_seconds
        self.store: OrderedDict[str, tuple[float, SobesSession]] = OrderedDict()

    def _prune(self) -> None:
        now = time.time()
        expired = [sid for sid, (ts, _) in self.store.items() if now - ts > self.ttl]
        for sid in expired:
            self.store.pop(sid, None)

    def get(self, session_id: str) -> SobesSession | None:
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

    def save(self, session: SobesSession) -> None:
        self._prune()
        self.store[session.session_id] = (time.time(), session)
        self.store.move_to_end(session.session_id)
        while len(self.store) > self.max_sessions:
            self.store.popitem(last=False)


async def _ensure_classified_index(
    settings: Settings,
    llm: OllamaClient,
) -> ClassifiedIndex:
    items, doc_hash = load_qa(settings)
    cache_path = Path(settings.sobes_cache_path)
    cached = load_cached_index(cache_path)

    if cached and cached.get("doc_hash") == doc_hash:
        try:
            rows = cached["items"]
            parsed = [
                ClassifiedQA(
                    number=int(r["number"]),
                    question=str(r["question"]),
                    answer=str(r.get("answer", "")),
                    topic=str(r.get("topic", "other")),
                    level=str(r.get("level", "middle")),
                    difficulty_score=float(r.get("difficulty_score", 0.5)),
                )
                for r in rows
            ]
            return ClassifiedIndex(doc_hash=doc_hash, items=parsed)
        except Exception:
            pass

    # нет валидного кэша — классифицируем заново
    classified = await classify_batch(llm, items, settings.sobes_topics)
    payload = {
        "doc_hash": doc_hash,
        "items": [as_plain_dict(x) for x in classified],
    }
    save_cached_index(cache_path, payload)
    return ClassifiedIndex(doc_hash=doc_hash, items=classified)


from pathlib import Path  # noqa: E402


class SobesService:
    def __init__(self, settings: Settings, llm: OllamaClient, store: SobesSessionStore | None = None) -> None:
        self._settings = settings
        self._llm = llm
        self._store = store or SobesSessionStore()

    async def start(self, level: SobesLevel, topics: list[str] | None = None) -> tuple[SobesSession, SobesQuestionDTO]:
        index = await _ensure_classified_index(self._settings, self._llm)
        use_topics = topics or self._settings.sobes_topics

        selected, planned = select_questions(
            index.items,
            level=level,
            topics=use_topics,
            counts_cfg=self._settings.sobes_counts_by_level,
        )
        if not selected:
            raise ValueError("База вопросов пуста или не удалось подобрать вопросы под параметры.")

        sess = SobesSession(
            session_id=f"sobes_{uuid.uuid4().hex}",
            level_requested=level,
            planned_total=planned,
            questions=selected,
        )
        self._store.save(sess)

        first = selected[0]
        return sess, SobesQuestionDTO(
            id=first.id,
            number=first.number,
            text=first.text,
            topic=first.topic,
            level=first.level,  # type: ignore[arg-type]  # уровень вопроса по классификации
            difficulty_score=first.difficulty_score,
            topic_hint=(
                getattr(self._settings, "sobes_topic_hints", {}).get(first.topic)
                if getattr(self._settings, "sobes_show_topic_hint", True)
                else None
            ),
        )

    async def answer(
        self, session_id: str, question_id: str, user_answer: str
    ) -> tuple[int, bool, str, list[str], list[str], SobesQuestion | None, bool]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")

        # найдём текущий вопрос
        cur: SobesQuestion | None = None
        for q in sess.questions:
            if q.id == question_id:
                cur = q
                break
        if cur is None:
            # допускаем, что фронт мог не знать id — берём по индексу
            if 0 <= sess.current_index < len(sess.questions):
                cur = sess.questions[sess.current_index]
            else:
                raise ValueError("Вопрос не найден в сессии")

        # найдём референс-ответ из исходной базы по номеру
        all_qa, _doc_hash = load_qa(self._settings)
        ref: InterviewQA | None = next((x for x in all_qa if x.number == cur.number), None)
        reference_answer = ref.answer if ref else ""

        percent, counted, expl, covered, missed = await score_free_answer(
            self._llm,
            cur.text,
            reference_answer,
            user_answer,
            pass_threshold=self._settings.sobes_pass_threshold_percent,
            max_expl_len=self._settings.sobes_max_explanation_len,
        )

        # записать результат
        record = SobesAnswerRecord(
            question_id=cur.id,
            question_text=cur.text,
            topic=cur.topic,
            user_answer=user_answer,
            score_percent=percent,
            is_counted=counted,
            techlead_explanation=expl,
            covered_points=covered,
            missed_points=missed,
        )
        sess.answers.append(record)
        # продвинуться к следующему вопросу
        if sess.current_index < len(sess.questions):
            sess.current_index += 1
        self._store.save(sess)

        # следующий вопрос
        is_last = sess.current_index >= sess.planned_total or sess.current_index >= len(sess.questions)
        next_q = None if is_last else sess.questions[sess.current_index]
        return percent, counted, expl, covered, missed, next_q, is_last

    def results(self, session_id: str) -> tuple[str, str, dict, list[str], list[str], list[dict], list[dict]]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")

        total = max(1, min(sess.planned_total, len(sess.questions)))
        counted = sum(1 for a in sess.answers if a.is_counted)
        avg_percent = int(round(sum(a.score_percent for a in sess.answers) / max(1, len(sess.answers))))

        # по темам
        by_topic_acc: dict[str, list[int]] = {}
        for a in sess.answers:
            by_topic_acc.setdefault(a.topic, []).append(a.score_percent)
        by_topic = [
            {"topic": t, "avg_percent": int(round(sum(v) / len(v))), "count": len(v)} for t, v in by_topic_acc.items()
        ]
        by_topic.sort(key=lambda x: x["avg_percent"], reverse=True)

        strengths = [x["topic"] for x in by_topic[:3]]
        weaknesses = [x["topic"] for x in by_topic[-3:]]

        # вердикт
        p = avg_percent
        if p <= 60 or counted / total <= 0.6:
            verdict = "junior"
        elif p <= 80:
            verdict = "middle"
        else:
            verdict = "senior"

        details = [
            {
                "question_text": a.question_text,
                "topic": a.topic,
                "score_percent": a.score_percent,
                "explanation": a.techlead_explanation,
            }
            for a in sess.answers
        ]

        summary = {"counted": counted, "total": total, "avg_percent": avg_percent}
        return sess.level_requested, verdict, summary, strengths, weaknesses, by_topic, details

    def repeat(self, session_id: str) -> SobesQuestion:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        if not (0 <= sess.current_index < len(sess.questions)):
            # если вышли за предел — вернуть последний
            if not sess.questions:
                raise ValueError("В сессии нет вопросов")
            return sess.questions[-1]
        return sess.questions[sess.current_index]

    def skip(self, session_id: str) -> tuple[SobesQuestion | None, bool]:
        sess = self._store.get(session_id)
        if not sess:
            raise ValueError("Сессия не найдена или истекла")
        # сдвигаем индекс вперёд, не добавляя ответа
        sess.current_index += 1
        self._store.save(sess)
        is_last = sess.current_index >= sess.planned_total or sess.current_index >= len(sess.questions)
        next_q = None if is_last else sess.questions[sess.current_index]
        return next_q, is_last
