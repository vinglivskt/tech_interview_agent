import { useState, useCallback, useEffect, useRef } from "react";
import { chatApi } from "@/services/api";

const SESSION_KEY = "interview_session_id";

export function formatInterviewAnswerRequest(question: string, answer: string): string {
  return [
    "Проверь мой ответ на вопрос технического интервью.",
    `Вопрос: ${question.trim()}`,
    `Мой ответ: ${answer.trim()}`,
    "Дай разбор ответа по правилам собеседования: что верно, что упущено, правильный ответ и оценку.",
  ].join("\n\n");
}

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export interface ChatState {
  questionNumber: string;
  questionText: string;
  answer: string;
  isAnswerEmpty: boolean;
  userAnswer: string;
  statusText: string;
  saveStatus: string;
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  lastQuestion: string;
  lastAnswer: string;
  customQuestion: string;
  isCustomMode: boolean;
  suggestSave: boolean;
  correctionDraft: string;
  isCorrectionOpen: boolean;
  correctionStatus: string;
}

export function useChat() {
  const [state, setState] = useState<ChatState>({
    questionNumber: "—",
    questionText: "",
    answer: "",
    isAnswerEmpty: true,
    userAnswer: "",
    statusText: "",
    saveStatus: "",
    isLoading: false,
    error: null,
    sessionId: getSessionId(),
    lastQuestion: "",
    lastAnswer: "",
    customQuestion: "",
    isCustomMode: false,
    suggestSave: false,
    correctionDraft: "",
    isCorrectionOpen: false,
    correctionStatus: "",
  });

  const hasLoadedQuestion = useRef(false);
  const loadSeqRef = useRef(0);

  const loadRandomQuestion = useCallback(async () => {
    if (hasLoadedQuestion.current && state.questionText && !state.isCustomMode) return;

    const seq = ++loadSeqRef.current;

    setState((prev) => ({
      ...prev,
      isLoading: true,
      answer: "",
      isAnswerEmpty: true,
      statusText: "Генерация вопроса…",
      saveStatus: "",
      correctionDraft: "",
      isCorrectionOpen: false,
      correctionStatus: "",
      error: null,
    }));

    try {
      const data = await chatApi.getRandomQuestion();
      // Устаревший ответ (напр. двойной вызов в StrictMode) — игнорируем.
      if (seq !== loadSeqRef.current) return;
      hasLoadedQuestion.current = true;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        questionNumber: String(data.number),
        questionText: data.question,
        lastQuestion: data.question,
        statusText: "",
        isCustomMode: false,
      }));
    } catch (err) {
      if (seq !== loadSeqRef.current) return;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        questionText: "",
        statusText: "",
        error: err instanceof Error ? err.message : "Не удалось загрузить вопрос",
      }));
    }
  }, [state.questionText, state.isCustomMode]);

  useEffect(() => {
    loadRandomQuestion();
  }, []);

  const setUserAnswer = useCallback((userAnswer: string) => {
    setState((prev) => ({ ...prev, userAnswer }));
  }, []);

  const setCustomQuestion = useCallback((customQuestion: string) => {
    setState((prev) => ({ ...prev, customQuestion }));
  }, []);

  const enterCustomMode = useCallback(() => {
    hasLoadedQuestion.current = true;
    setState((prev) => ({
      ...prev,
      questionNumber: "—",
      questionText: "",
      answer: "",
      isAnswerEmpty: true,
      userAnswer: "",
      saveStatus: "",
      error: null,
      isCustomMode: true,
      customQuestion: "",
      lastQuestion: "",
      suggestSave: false,
      correctionDraft: "",
      isCorrectionOpen: false,
      correctionStatus: "",
    }));
  }, []);

  const cancelCustomMode = useCallback(() => {
    hasLoadedQuestion.current = false;
    setState((prev) => ({
      ...prev,
      isCustomMode: false,
      customQuestion: "",
    }));
    loadRandomQuestion();
  }, [loadRandomQuestion]);

  const submitCustomQuestion = useCallback(async () => {
    const { customQuestion, sessionId, isLoading } = state;
    if (!customQuestion.trim() || isLoading) return;

    setState((prev) => ({
      ...prev,
      isLoading: true,
      statusText: "Загрузка…",
      error: null,
    }));

    try {
      // При своём вопросе отправляем с questionType=direct_question
      // чтобы получить прямой ответ без Evaluate-формата.
      const data = await chatApi.send(customQuestion.trim(), sessionId, "direct_question");
      hasLoadedQuestion.current = true;
      const meta = data.meta || {};
      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        answer: data.answer,
        isAnswerEmpty: false,
        lastQuestion: customQuestion.trim(),
        lastAnswer: data.answer,
        questionText: customQuestion.trim(),
        questionNumber: "—",
        userAnswer: "",
        isCustomMode: false,
        suggestSave: Boolean(meta.suggest_save),
        correctionDraft: "",
        isCorrectionOpen: false,
        correctionStatus: "",
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        error: err instanceof Error ? err.message : "Ошибка отправки",
      }));
    }
  }, [state]);

  const sendAnswer = useCallback(async () => {
    const { userAnswer, sessionId, lastQuestion, isLoading } = state;
    if (!userAnswer.trim() || !lastQuestion || isLoading) return;

    setState((prev) => ({
      ...prev,
      isLoading: true,
      statusText: "Отправка…",
      error: null,
    }));

    const message = formatInterviewAnswerRequest(lastQuestion, userAnswer);

    try {
      const data = await chatApi.send(message, sessionId);
      const meta = data.meta || {};

      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        answer: data.answer,
        isAnswerEmpty: false,
        lastAnswer: data.answer,
        lastQuestion: prev.lastQuestion,
        suggestSave: Boolean(meta.suggest_save),
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        error: err instanceof Error ? err.message : "Ошибка отправки",
      }));
    }
  }, [state]);

  const saveToWord = useCallback(async () => {
    const { lastQuestion, lastAnswer, sessionId, isLoading } = state;
    if (!lastQuestion || !lastAnswer || isLoading) return;

    setState((prev) => ({ ...prev, isLoading: true, saveStatus: "Сохранение…" }));

    try {
      const data = await chatApi.saveQA(lastQuestion, lastAnswer, sessionId);
      if (data.status === "saved") {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          saveStatus: `Сохранено как вопрос №${data.number}`,
        }));
      } else if (data.status === "skipped") {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          saveStatus: "Такой вопрос уже есть в базе",
        }));
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        saveStatus: `Ошибка: ${err instanceof Error ? err.message : "Неизвестная ошибка"}`,
      }));
    }
  }, [state]);

  const startQuestionCorrection = useCallback(async () => {
    const number = Number(state.questionNumber);
    if (!Number.isInteger(number) || number < 1 || !state.lastQuestion || !state.lastAnswer || state.isLoading) {
      return;
    }

    setState((prev) => ({
      ...prev,
      isLoading: true,
      isCorrectionOpen: true,
      correctionDraft: prev.lastQuestion,
      correctionStatus: "ИИ готовит более ясную формулировку…",
      error: null,
    }));

    try {
      const result = await chatApi.suggestQuestionCorrection(number, state.lastAnswer);
      setState((prev) => ({
        ...prev,
        isLoading: false,
        correctionDraft: result.suggestion,
        correctionStatus: "Проверьте предложение и при необходимости поправьте его перед сохранением.",
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        correctionDraft: prev.lastQuestion,
        correctionStatus: `Не удалось получить предложение. Можно исправить вопрос вручную. ${err instanceof Error ? err.message : ""}`,
      }));
    }
  }, [state]);

  const setCorrectionDraft = useCallback((correctionDraft: string) => {
    setState((prev) => ({ ...prev, correctionDraft }));
  }, []);

  const cancelQuestionCorrection = useCallback(() => {
    setState((prev) => ({
      ...prev,
      isCorrectionOpen: false,
      correctionDraft: "",
      correctionStatus: "",
    }));
  }, []);

  const saveQuestionCorrection = useCallback(async () => {
    const number = Number(state.questionNumber);
    const corrected = state.correctionDraft.trim();
    if (!Number.isInteger(number) || !corrected || !state.lastQuestion || state.isLoading) return;

    setState((prev) => ({ ...prev, isLoading: true, correctionStatus: "Сохраняю в Word и обновляю поиск…" }));
    try {
      const result = await chatApi.replaceQuestion(number, state.lastQuestion, corrected);
      if (result.status === "duplicate") {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          correctionStatus: `Такая формулировка уже есть у вопроса №${result.duplicate_number}. Измените текст и попробуйте ещё раз.`,
        }));
        return;
      }

      const savedQuestion = result.question || corrected;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        questionText: savedQuestion,
        lastQuestion: savedQuestion,
        isCorrectionOpen: false,
        correctionStatus:
          result.index_status === "stale"
            ? `Вопрос №${number} обновлён в Word. Поисковый индекс обновится позже.`
            : result.status === "unchanged"
              ? "Формулировка не изменилась."
              : `Вопрос №${number} обновлён в Word и поиске.`,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        correctionStatus: `Ошибка сохранения: ${err instanceof Error ? err.message : "Неизвестная ошибка"}`,
      }));
    }
  }, [state]);

  const resetConversation = useCallback(() => {
    hasLoadedQuestion.current = false;
    setState((prev) => ({
      ...prev,
      questionNumber: "—",
      questionText: "",
      answer: "",
      isAnswerEmpty: true,
      userAnswer: "",
      statusText: "",
      saveStatus: "",
      error: null,
      lastQuestion: "",
      lastAnswer: "",
      customQuestion: "",
      isCustomMode: false,
      suggestSave: false,
      correctionDraft: "",
      isCorrectionOpen: false,
      correctionStatus: "",
    }));
    loadRandomQuestion();
  }, [loadRandomQuestion]);

  return {
    ...state,
    setUserAnswer,
    setCustomQuestion,
    enterCustomMode,
    cancelCustomMode,
    submitCustomQuestion,
    sendAnswer,
    saveToWord,
    startQuestionCorrection,
    setCorrectionDraft,
    cancelQuestionCorrection,
    saveQuestionCorrection,
    loadRandomQuestion,
    resetConversation,
  };
}
