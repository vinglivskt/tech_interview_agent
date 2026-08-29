import { useState, useCallback, useEffect } from "react";
import { chatApi } from "@/services/api";

const SESSION_KEY = "interview_session_id";

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
  });

  const loadRandomQuestion = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      answer: "",
      isAnswerEmpty: true,
      statusText: "",
      saveStatus: "",
      error: null,
    }));

    try {
      const data = await chatApi.getRandomQuestion();
      setState((prev) => ({
        ...prev,
        questionNumber: String(data.number),
        questionText: data.question,
        lastQuestion: data.question,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        questionText: "",
        error: err instanceof Error ? err.message : "Не удалось загрузить вопрос",
      }));
    }
  }, []);

  useEffect(() => {
    loadRandomQuestion();
  }, [loadRandomQuestion]);

  const setUserAnswer = useCallback((userAnswer: string) => {
    setState((prev) => ({ ...prev, userAnswer }));
  }, []);

  const sendAnswer = useCallback(async () => {
    const { userAnswer, sessionId, lastQuestion, isLoading } = state;
    if (!userAnswer.trim() || isLoading) return;

    setState((prev) => ({
      ...prev,
      isLoading: true,
      statusText: "Отправка…",
      error: null,
      answer: "",
      isAnswerEmpty: true,
      saveStatus: "",
    }));

    // If no question was loaded, treat the first message as the question
    const question = lastQuestion || userAnswer;
    const message = lastQuestion ? userAnswer : userAnswer;

    try {
      const data = await chatApi.send(message, sessionId);
      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        answer: data.answer,
        isAnswerEmpty: false,
        lastAnswer: data.answer,
        lastQuestion: question,
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

  return {
    ...state,
    setUserAnswer,
    sendAnswer,
    saveToWord,
    loadRandomQuestion,
  };
}
