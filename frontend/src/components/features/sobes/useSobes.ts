import { useState, useCallback, useEffect } from "react";
import { sobesApi } from "@/services/api";
import type { SobesConfig, SobesQuestion, SobesAnswer, SobesResults, SobesView } from "./types";

export function useSobes() {
  const [view, setView] = useState<SobesView>("setup");
  const [config, setConfig] = useState<SobesConfig | null>(null);
  const [level, setLevel] = useState<"junior" | "middle" | "senior">("middle");
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState<SobesQuestion | null>(null);
  const [questionIndex, setQuestionIndex] = useState(1);
  const [totalPlanned, setTotalPlanned] = useState(0);
  const [userAnswer, setUserAnswer] = useState("");
  const [lastAnswer, setLastAnswer] = useState<SobesAnswer | null>(null);
  const [results, setResults] = useState<SobesResults | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextQuestion, setNextQuestion] = useState<SobesQuestion | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const data = await sobesApi.getConfig();
      setConfig(data);
      setSelectedTopics(data.topics);
    } catch {
      setError("Не удалось загрузить темы");
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const toggleTopic = useCallback((topic: string) => {
    setSelectedTopics((prev) => (prev.includes(topic) ? prev.filter((t) => t !== topic) : [...prev, topic]));
  }, []);

  const startSobes = useCallback(async () => {
    if (selectedTopics.length === 0) return;

    setIsLoading(true);
    setError(null);
    // Полный сброс state от предыдущего запуска, чтобы не показывать
    // старые разборы (в том числе чужих режимов — chat/quiz/design).
    setSessionId(null);
    setQuestion(null);
    setQuestionIndex(1);
    setTotalPlanned(0);
    setUserAnswer("");
    setLastAnswer(null);
    setNextQuestion(null);
    setResults(null);
    try {
      const data = await sobesApi.start(level, selectedTopics);
      setSessionId(data.session_id);
      setQuestion(data.question);
      setTotalPlanned(data.total_planned);
      setQuestionIndex(1);
      setView("question");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка запуска");
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [level, selectedTopics]);

  const submitAnswer = useCallback(async () => {
    if (!sessionId || !question || !userAnswer.trim()) return;

    setIsLoading(true);
    // Сбрасываем предыдущий разбор, чтобы на экране не висел старый,
    // если запрос упадёт.
    setLastAnswer(null);
    try {
      const data = await sobesApi.answer(sessionId, question.id, userAnswer);
      setLastAnswer(data);
      setView("answer");

      if (data.is_last || !data.next_question) {
        // Will show results button
      } else {
        setNextQuestion(data.next_question);
      }
    } catch (err) {
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
      // Возвращаем пользователя к вопросу, чтобы он мог попробовать ещё раз,
      // а не висел старый разбор от предыдущего ответа.
      setView("question");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, question, userAnswer]);

  const nextQuestionHandler = useCallback(async () => {
    if (lastAnswer?.is_last || !lastAnswer?.next_question) {
      // Load results
      if (sessionId) {
        try {
          const data = await sobesApi.getResults(sessionId);
          setResults(data);
          setLastAnswer(null);
          setNextQuestion(null);
          setView("results");
        } catch (err) {
          alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
        }
      }
      return;
    }

    if (nextQuestion) {
      setQuestion(nextQuestion);
      setQuestionIndex((prev) => prev + 1);
      setUserAnswer("");
      setLastAnswer(null);
      setNextQuestion(null);
      setView("question");
    }
  }, [lastAnswer, nextQuestion, sessionId]);

  const skipQuestion = useCallback(async () => {
    if (!sessionId) return;

    setIsLoading(true);
    try {
      const data = await sobesApi.skip(sessionId);
      if (data.is_last || !data.next_question) {
        if (sessionId) {
          const resultsData = await sobesApi.getResults(sessionId);
          setResults(resultsData);
          setLastAnswer(null);
          setNextQuestion(null);
          setView("results");
        }
      } else {
        setQuestion(data.next_question);
        setQuestionIndex((prev) => prev + 1);
        setUserAnswer("");
        setLastAnswer(null);
        setNextQuestion(null);
        setView("question");
      }
    } catch (err) {
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const repeatQuestion = useCallback(async () => {
    if (!sessionId) return;

    try {
      const data = await sobesApi.repeat(sessionId);
      setQuestion(data.question);
      setUserAnswer("");
      setLastAnswer(null);
      setNextQuestion(null);
      setView("question");
    } catch (err) {
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    }
  }, [sessionId]);

  const goBack = useCallback(() => {
    setView("setup");
    setQuestion(null);
    setUserAnswer("");
    setLastAnswer(null);
    setResults(null);
  }, []);

  const restart = useCallback(() => {
    setView("setup");
    setQuestion(null);
    setUserAnswer("");
    setLastAnswer(null);
    setResults(null);
    setSessionId(null);
  }, []);

  return {
    view,
    config,
    level,
    setLevel,
    selectedTopics,
    toggleTopic,
    startSobes,
    question,
    questionIndex,
    totalPlanned,
    userAnswer,
    setUserAnswer,
    lastAnswer,
    results,
    isLoading,
    error,
    submitAnswer,
    nextQuestion: nextQuestionHandler,
    skipQuestion,
    repeatQuestion,
    goBack,
    restart,
  };
}
