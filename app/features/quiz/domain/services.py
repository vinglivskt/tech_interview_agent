# Сервисная логика quiz-режима: сессии, генерация вопросов, проверка ответов.
from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from app.core.config import Settings
from app.features.chat.domain.interview_docx import InterviewQA, load_interview_qa
from app.features.chat.providers.ollama import OllamaClient

from .quiz_generator import generate_wrong_answers

logger = logging.getLogger(__name__)

# Общее количество вопросов в квизе
TOTAL_QUESTIONS = 20

# Распределение сложности: вопросы 1-7 = easy, 8-14 = medium, 15-20 = hard
_EASY_COUNT = 7
_MEDIUM_COUNT = 7
# Остальные 6 — hard


@dataclass
class QuizQuestion:
    """
    Один вопрос квиза с вариантами ответов.
    """

    question_id: str
    question_text: str
    options: list[str]  # 4 варианта (уже перемешаны)
    correct_index: int  # индекс правильного ответа после перемешивания
    correct_answer: str  # текст правильного ответа (для объяснения)
    explanation: str  # объяснение ответа


@dataclass
class QuizAnswerRecord:
    """
    Запись об одном ответе пользователя в квизе.
    """

    question_text: str
    user_answer: str
    correct_answer: str
    is_correct: bool
    explanation: str


@dataclass
class QuizSession:
    """
    Сессия квиза: хранит вопросы, текущий прогресс и ответы пользователя.
    """

    session_id: str
    questions: list[QuizQuestion]
    current_index: int = 0
    answers: list[QuizAnswerRecord] = field(default_factory=list)
    level: str = "middle"
    created_at: float = field(default_factory=time.time)
    _pending_qa: list[InterviewQA] = field(default_factory=list)


class QuizSessionStore:
    """
    Хранилище сессий квиза в памяти (TTL-кеш, аналог SessionStore для чата).
    """

    def __init__(self, max_sessions: int = 500, ttl_seconds: int = 60 * 60 * 6) -> None:
        self.max_sessions = max_sessions
        self.ttl = ttl_seconds
        self.store: OrderedDict[str, tuple[float, QuizSession]] = OrderedDict()

    def _prune(self) -> None:
        """Удаляет просроченные сессии."""
        now = time.time()
        expired = [sid for sid, (ts, _) in self.store.items() if now - ts > self.ttl]
        for sid in expired:
            self.store.pop(sid, None)

    def get(self, session_id: str) -> QuizSession | None:
        """Возвращает сессию по идентификатору (или None)."""
        self._prune()
        entry = self.store.get(session_id)
        if entry is None:
            return None
        ts, session = entry
        if time.time() - ts > self.ttl:
            self.store.pop(session_id, None)
            return None
        self.store.move_to_end(session_id)
        return session

    def save(self, session: QuizSession) -> None:
        """Сохраняет/обновляет сессию в хранилище."""
        self._prune()
        self.store[session.session_id] = (time.time(), session)
        self.store.move_to_end(session.session_id)
        while len(self.store) > self.max_sessions:
            self.store.popitem(last=False)


def _normalize_option(text: str, target_len: int) -> str:
    """
    Приводит вариант ответа к целевой длине.
    Обрезает длинные ответы и немного расширяет короткие.
    """
    text = text.strip()

    if len(text) > target_len * 1.3:
        # Обрезаем до target_len, сохраняя целые слова
        cut = text[:target_len]
        last_space = cut.rfind(" ")
        if last_space > target_len * 0.7:
            text = cut[:last_space]
        else:
            text = cut

    return text.strip()


class QuizService:
    """
    Сервис для управления квиз-сессиями: старт, ответы, результаты.
    """

    def __init__(
        self,
        settings: Settings,
        llm: OllamaClient,
        session_store: QuizSessionStore | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._store = session_store or QuizSessionStore()

    def _load_questions_source(self) -> list[InterviewQA]:
        """
        Загружает вопросы/ответы из docx-файла.
        """
        docx_path = Path(self._settings.interview_docx_path)
        if not docx_path.exists():
            logger.warning("Файл docx не найден: %s", docx_path)
            return []
        return load_interview_qa(docx_path)

    def _select_questions_by_difficulty(
        self,
        all_qa: list[InterviewQA],
        level: str,
    ) -> list[InterviewQA]:
        """
        Выбирает 20 вопросов из базы с распределением по сложности.
        Вопросы 1-7 (easy): берём из первых 30% базы (более простые).
        Вопросы 8-14 (medium): из средних 40%.
        Вопросы 15-20 (hard): из последних 30% (более сложные).

        Уровень пользователя смещает пропорции:
        - junior: больше easy
        - senior: больше hard
        """
        if not all_qa:
            return []

        # Сортируем по номеру вопроса для детерминированности
        sorted_qa = sorted(all_qa, key=lambda q: q.number)
        n = len(sorted_qa)

        if n < TOTAL_QUESTIONS:
            # Если вопросов меньше 20 — берём все и дублируем случайные
            result = list(sorted_qa)
            rng = Random(42)
            while len(result) < TOTAL_QUESTIONS:
                result.append(rng.choice(sorted_qa))
            return result[:TOTAL_QUESTIONS]

        # Разбиваем базу на три части по сложности
        easy_end = max(1, int(n * 0.3))
        medium_end = max(easy_end + 1, int(n * 0.7))

        easy_pool = sorted_qa[:easy_end]
        medium_pool = sorted_qa[easy_end:medium_end]
        hard_pool = sorted_qa[medium_end:]

        # Определяем количество вопросов каждой сложности в зависимости от уровня
        if level == "junior":
            easy_count = 10
            medium_count = 7
            hard_count = 3
        elif level == "senior":
            easy_count = 3
            medium_count = 7
            hard_count = 10
        else:  # middle (default)
            easy_count = _EASY_COUNT
            medium_count = _MEDIUM_COUNT
            hard_count = TOTAL_QUESTIONS - _EASY_COUNT - _MEDIUM_COUNT

        rng = Random(uuid.uuid4().int % (2**32))

        selected: list[InterviewQA] = []
        selected.extend(rng.sample(easy_pool, min(easy_count, len(easy_pool))))
        selected.extend(rng.sample(medium_pool, min(medium_count, len(medium_pool))))
        selected.extend(rng.sample(hard_pool, min(hard_count, len(hard_pool))))

        # Если не хватило — добираем из оставшихся
        if len(selected) < TOTAL_QUESTIONS:
            remaining = [q for q in sorted_qa if q not in selected]
            needed = TOTAL_QUESTIONS - len(selected)
            if remaining:
                selected.extend(rng.sample(remaining, min(needed, len(remaining))))

        # Перемешиваем финальный список
        rng.shuffle(selected)
        return selected[:TOTAL_QUESTIONS]

    async def _build_quiz_question(
        self,
        qa: InterviewQA,
        question_index: int,
    ) -> QuizQuestion:
        """
        Формирует вопрос квиза: берёт ответ из базы как правильный,
        генерирует 3 неправильных через LLM, перемешивает варианты.
        """
        correct_answer = qa.answer.strip()

        # Если ответ слишком длинный — берём первое предложение
        if len(correct_answer) > 150:
            first_sentence = correct_answer.split(".")[0].strip()
            if len(first_sentence) > 50:
                correct_answer = first_sentence

        # Генерируем 3 неправильных ответа
        wrong_answers = await generate_wrong_answers(
            self._llm,
            qa.question,
            correct_answer,
        )

        # Сохраняем индекс правильного ответа ДО нормализации
        correct_idx_before = 0  # correct_answer всегда первый в списке

        # Приводим все варианты к одной длине
        all_options = [correct_answer] + wrong_answers[:3]
        target_len = min(len(correct_answer), 100)  # Целевая длина: не более 100 символов
        normalized = [_normalize_option(opt, target_len) for opt in all_options]

        # Обновляем correct_answer после нормализации
        correct_answer_normalized = normalized[correct_idx_before]

        # Перемешиваем сохраняя индекс
        indexed_options = list(enumerate(normalized))
        rng = Random(uuid.uuid4().int % (2**32))
        rng.shuffle(indexed_options)

        # Находим новый индекс правильного ответа
        correct_index = next(i for i, (_, opt) in enumerate(indexed_options) if opt == correct_answer_normalized)
        shuffled_options = [opt for _, opt in indexed_options]

        return QuizQuestion(
            question_id=f"q_{question_index}_{uuid.uuid4().hex[:8]}",
            question_text=qa.question,
            options=shuffled_options,
            correct_index=correct_index,
            correct_answer=correct_answer_normalized,
            explanation=f"Правильный ответ основан на ответе №{qa.number} из базы: {correct_answer_normalized}",
        )

    async def start_quiz(self, level: str) -> tuple[QuizSession, QuizQuestion]:
        """
        Создаёт новую сессию квиза и генерирует первый вопрос.
        Остальные вопросы генерируются по мере ответов пользователя.

        :param level: уровень сложности (junior/middle/senior)
        :return: кортеж (сессия, первый вопрос)
        """
        all_qa = self._load_questions_source()
        if not all_qa:
            raise ValueError("База вопросов пуста. Проверьте настройку interview_docx_path.")

        selected_qa = self._select_questions_by_difficulty(all_qa, level)

        # Генерируем только первый вопрос
        first_qa = selected_qa[0]
        first_question = await self._build_quiz_question(first_qa, 0)

        # Сохраняем источники для остальных вопросов (без генерации)
        session = QuizSession(
            session_id=f"quiz_{uuid.uuid4().hex}",
            questions=[first_question],
            level=level,
            _pending_qa=selected_qa[1:],  # остальные вопросы для генерации
        )
        self._store.save(session)

        return session, first_question

    async def _ensure_next_question(self, session: QuizSession) -> QuizQuestion | None:
        """
        Генерирует следующий вопрос если есть отложенные.
        """
        pending = getattr(session, "_pending_qa", [])
        if not pending:
            return None

        next_qa = pending.pop(0)
        next_question = await self._build_quiz_question(next_qa, len(session.questions))
        session.questions.append(next_question)
        self._store.save(session)
        return next_question

    async def submit_answer(
        self,
        session_id: str,
        question_id: str,
        selected_index: int,
    ) -> tuple[bool, int, str, QuizQuestion | None, bool]:
        """
        Обрабатывает ответ пользователя на вопрос.

        :param session_id: идентификатор сессии
        :param question_id: идентификатор вопроса
        :param selected_index: индекс выбранного варианта (0-3)
        :return: (is_correct, correct_index, explanation, next_question, is_last)
        :raises ValueError: если сессия или вопрос не найдены
        """
        session = self._store.get(session_id)
        if session is None:
            raise ValueError(f"Сессия {session_id} не найдена или истекла")

        # Находим текущий вопрос по question_id
        current_question = None
        for q in session.questions:
            if q.question_id == question_id:
                current_question = q
                break

        if current_question is None:
            raise ValueError(f"Вопрос {question_id} не найден в сессии")

        is_correct = selected_index == current_question.correct_index

        # Записываем ответ
        record = QuizAnswerRecord(
            question_text=current_question.question_text,
            user_answer=current_question.options[selected_index],
            correct_answer=current_question.correct_answer,
            is_correct=is_correct,
            explanation=current_question.explanation,
        )
        session.answers.append(record)
        session.current_index += 1
        self._store.save(session)

        # Определяем, есть ли следующий вопрос
        next_question = None
        is_last = session.current_index >= TOTAL_QUESTIONS
        if not is_last:
            # Генерируем следующий вопрос если ещё не сгенерирован
            if session.current_index < len(session.questions):
                next_question = session.questions[session.current_index]
            else:
                # Генерируем следующий вопрос
                next_question = await self._ensure_next_question(session)
                if next_question is None:
                    is_last = True

        return (
            is_correct,
            current_question.correct_index,
            current_question.explanation,
            next_question,
            is_last,
        )

    def _calculate_level(self, score: int, total: int) -> str:
        """
        Вычисляет итоговый уровень на основе процента правильных ответов.
        - 0-50%: junior
        - 51-75%: middle
        - 76-100%: senior
        """
        if total == 0:
            return "junior"
        percentage = score / total
        if percentage <= 0.5:
            return "junior"
        elif percentage <= 0.75:
            return "middle"
        else:
            return "senior"

    def get_results(self, session_id: str) -> tuple[int, int, str, list[QuizAnswerRecord]]:
        """
        Возвращает итоговые результаты квиза.

        :param session_id: идентификатор сессии
        :return: (total_score, total_questions, level, results)
        :raises ValueError: если сессия не найдена
        """
        session = self._store.get(session_id)
        if session is None:
            raise ValueError(f"Сессия {session_id} не найдена или истекла")

        total_score = sum(1 for a in session.answers if a.is_correct)
        # Вычисляем итоговый уровень на основе результатов
        final_level = self._calculate_level(total_score, TOTAL_QUESTIONS)
        return (
            total_score,
            len(session.questions),
            final_level,
            session.answers,
        )
