import { useState, useCallback, useEffect, useRef } from "react";
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

  // Use ref to track if question was loaded - avoids stale closure issues
  const hasLoadedQuestion = useRef(false);

  const loadRandomQuestion = useCallback(async () => {
    // Don't reload if we already have a question pending
    if (hasLoadedQuestion.current && state.questionText) return;

    setState((prev) => ({
      ...prev,
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
        questionNumber: String(data.number),
        questionText: data.question,
        lastQuestion: data.question,
        statusText: "",
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        questionText: "",
        statusText: "",
        error: err instanceof Error ? err.message : "Не удалось загрузить вопрос",
      }));
    }
  }, [state.questionText]);

  useEffect(() => {
    loadRandomQuestion();
  }, []); // Only on mount

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
    }));

    // If lastQuestion is empty, this is a NEW question (user types their own question)
    // Otherwise, this is an ANSWER to the previously loaded question
    const isNewQuestion = !lastQuestion;
    const message = isNewQuestion ? userAnswer : userAnswer;

    try {
      const data = await chatApi.send(message, sessionId);

      // After response:
      // - If was a new question, lastQuestion becomes that question
      // - If was an answer, lastQuestion stays the same (the question we're answering)
      setState((prev) => ({
        ...prev,
        isLoading: false,
        statusText: "",
        answer: data.answer,
        isAnswerEmpty: false,
        lastAnswer: data.answer,
        lastQuestion: isNewQuestion ? userAnswer : prev.lastQuestion,
        // Keep userAnswer so user can type follow-up
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
    }));
    // Load new random question
    loadRandomQuestion();
  }, [loadRandomQuestion]);

  return {
    ...state,
    setUserAnswer,
    sendAnswer,
    saveToWord,
    loadRandomQuestion,
    resetConversation,
  };
}
