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
  });

  const hasLoadedQuestion = useRef(false);

  const loadRandomQuestion = useCallback(async () => {
    if (hasLoadedQuestion.current && state.questionText && !state.isCustomMode) return;

    setState((prev) => ({
      ...prev,
      isLoading: true,
      answer: "",
      isAnswerEmpty: true,
      statusText: "Генерация вопроса…",
      saveStatus: "",
      error: null,
    }));

    try {
      const data = await chatApi.getRandomQuestion();
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
      // При своём вопросе отправляем напрямую (без формата интервью),
      // чтобы получить прямой ответ, а не Evaluate-discussion.
      const data = await chatApi.send(customQuestion.trim(), sessionId);
      hasLoadedQuestion.current = true;
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

      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        answer: data.answer,
        isAnswerEmpty: false,
        lastAnswer: data.answer,
        lastQuestion: prev.lastQuestion,
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
          saveStatus: `✅ Сохранено как вопрос №${data.number}`,
        }));
      } else if (data.status === "skipped") {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          saveStatus: "⚠️ Такой вопрос уже есть в базе",
        }));
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        saveStatus: `❌ Ошибка: ${err instanceof Error ? err.message : "Неизвестная ошибка"}`,
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
    loadRandomQuestion,
    resetConversation,
  };
}
