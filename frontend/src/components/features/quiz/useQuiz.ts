import { useState, useCallback } from 'react';
import { quizApi } from '@/services/api';
import type { QuizState } from './types';

export function useQuiz() {
  const [state, setState] = useState<QuizState>({
    view: 'setup',
    level: 'junior',
    sessionId: null,
    currentQuestion: null,
    selectedOption: null,
    lastAnswer: null,
    results: null,
    isLoading: false,
    error: null,
  });

  const setLevel = useCallback((level: 'junior' | 'middle' | 'senior') => {
    setState((prev) => ({ ...prev, level }));
  }, []);

  const startQuiz = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const question = await quizApi.start(state.level);
      setState((prev) => ({
        ...prev,
        view: 'question',
        isLoading: false,
        sessionId: question.session_id,
        currentQuestion: question,
        selectedOption: null,
        lastAnswer: null,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка запуска квиза',
      }));
    }
  }, [state.level]);

  const selectOption = useCallback((index: number) => {
    setState((prev) => ({ ...prev, selectedOption: index }));
  }, []);

  const submitAnswer = useCallback(async () => {
    if (!state.currentQuestion || state.selectedOption === null || !state.sessionId) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const answer = await quizApi.answer(
        state.sessionId,
        state.currentQuestion.question_id,
        state.selectedOption
      );
      setState((prev) => ({
        ...prev,
        view: 'answer',
        isLoading: false,
        lastAnswer: answer,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка отправки ответа',
      }));
    }
  }, [state.currentQuestion, state.selectedOption, state.sessionId]);

  const nextQuestion = useCallback(async () => {
    const nextQ = state.lastAnswer?.next_question;
    if (state.lastAnswer?.is_last || !nextQ) {
      await loadResults();
      return;
    }

    setState((prev) => ({
      ...prev,
      view: 'question',
      currentQuestion: nextQ,
      selectedOption: null,
      lastAnswer: null,
    }));
  }, [state.lastAnswer]);

  const loadResults = useCallback(async () => {
    if (!state.sessionId) return;
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const results = await quizApi.getResults(state.sessionId);
      setState((prev) => ({
        ...prev,
        view: 'results',
        isLoading: false,
        results,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка загрузки результатов',
      }));
    }
  }, [state.sessionId]);

  const restart = useCallback(() => {
    setState({
      view: 'setup',
      level: 'junior',
      sessionId: null,
      currentQuestion: null,
      selectedOption: null,
      lastAnswer: null,
      results: null,
      isLoading: false,
      error: null,
    });
  }, []);

  const goBack = useCallback(() => {
    restart();
  }, [restart]);

  return {
    ...state,
    setLevel,
    startQuiz,
    selectOption,
    submitAnswer,
    nextQuestion,
    restart,
    goBack,
  };
}
