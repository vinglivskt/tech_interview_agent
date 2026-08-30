import { useState, useCallback } from "react";
import { quizApi } from "@/services/api";

type QuizView = "setup" | "question" | "results";

interface QuizQuestion {
  session_id: string;
  question_id: string;
  question_text: string;
  // Бэкенд отдаёт варианты ответа простым массивом строк; индекс = порядковый номер.
  options: string[];
  question_number: number;
  total_questions: number;
}

interface QuizResults {
  total_score: number;
  total_questions: number;
  level: string;
  results: {
    question_text: string;
    user_answer: string;
    correct_answer: string;
    is_correct: boolean;
    explanation: string;
  }[];
}

export function useQuiz() {
  const [view, setView] = useState<QuizView>("setup");
  const [level, setLevel] = useState<"junior" | "middle" | "senior">("middle");
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [results, setResults] = useState<QuizResults | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startQuiz = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    // Полный сброс state от предыдущего запуска, чтобы не показывать
    // старые вопросы и результаты.
    setQuestion(null);
    setSelectedOption(null);
    setResults(null);
    try {
      const data = await quizApi.start(level);
      setQuestion(data);
      setView("question");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка запуска квиза");
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [level]);

  const selectOption = useCallback((index: number) => {
    setSelectedOption(index);
  }, []);

  const submitAnswer = useCallback(async () => {
    if (selectedOption === null || !question) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await quizApi.answer(question.session_id, question.question_id, selectedOption);

      if (data.is_last || !data.next_question) {
        // Load results
        const resultsData = await quizApi.getResults(question.session_id);
        setResults(resultsData);
        setView("results");
      } else {
        setQuestion(data.next_question);
        setSelectedOption(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Неизвестная ошибка");
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [selectedOption, question]);

  const goBack = useCallback(() => {
    setView("setup");
    setQuestion(null);
    setSelectedOption(null);
    setResults(null);
  }, []);

  const restart = useCallback(() => {
    setView("setup");
    setQuestion(null);
    setSelectedOption(null);
    setResults(null);
  }, []);

  return {
    view,
    level,
    setLevel,
    question,
    selectedOption,
    selectOption,
    results,
    isLoading,
    error,
    startQuiz,
    submitAnswer,
    goBack,
    restart,
  };
}
