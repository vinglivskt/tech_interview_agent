import { useState, useCallback, useEffect } from 'react';
import { sobesApi } from '@/services/api';
import type { SobesState } from './types';

export function useSobes() {
  const [state, setState] = useState<SobesState>({
    view: 'setup',
    config: null,
    level: 'junior',
    selectedTopics: [],
    sessionId: null,
    currentQuestion: null,
    userAnswer: '',
    lastAnswer: null,
    results: null,
    isLoading: false,
    error: null,
  });

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const config = await sobesApi.getConfig();
      setState((prev) => ({
        ...prev,
        config,
        selectedTopics: config.topics.map((t) => t.id),
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Ошибка загрузки конфигурации',
      }));
    }
  }, []);

  const setLevel = useCallback((level: 'junior' | 'middle' | 'senior') => {
    setState((prev) => ({ ...prev, level }));
  }, []);

  const toggleTopic = useCallback((topicId: string) => {
    setState((prev) => ({
      ...prev,
      selectedTopics: prev.selectedTopics.includes(topicId)
        ? prev.selectedTopics.filter((t) => t !== topicId)
        : [...prev.selectedTopics, topicId],
    }));
  }, []);

  const startSobes = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const response = await sobesApi.start(state.level, state.selectedTopics);
      setState((prev) => ({
        ...prev,
        view: 'question',
        isLoading: false,
        sessionId: response.session_id,
        currentQuestion: response.question,
        userAnswer: '',
        lastAnswer: null,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка запуска сессии',
      }));
    }
  }, [state.level, state.selectedTopics]);

  const setUserAnswer = useCallback((answer: string) => {
    setState((prev) => ({ ...prev, userAnswer: answer }));
  }, []);

  const submitAnswer = useCallback(async () => {
    if (!state.currentQuestion || !state.sessionId || !state.userAnswer.trim()) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const answer = await sobesApi.answer(
        state.sessionId,
        state.currentQuestion.id,
        state.userAnswer
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
  }, [state.currentQuestion, state.sessionId, state.userAnswer]);

  const nextQuestion = useCallback(async () => {
    if (!state.sessionId) return;

    const nextQ = state.lastAnswer?.next_question;
    if (state.lastAnswer?.is_last || !nextQ) {
      await loadResults();
      return;
    }

    setState((prev) => ({
      ...prev,
      view: 'question',
      currentQuestion: nextQ,
      userAnswer: '',
      lastAnswer: null,
    }));
  }, [state.lastAnswer, state.sessionId]);

  const skipQuestion = useCallback(async () => {
    if (!state.sessionId) return;

    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const response = await sobesApi.skip(state.sessionId);
      if (response.is_last || !response.next_question) {
        await loadResults();
      } else {
        setState((prev) => ({
          ...prev,
          view: 'question',
          currentQuestion: response.next_question,
          userAnswer: '',
          lastAnswer: null,
          isLoading: false,
        }));
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка пропуска вопроса',
      }));
    }
  }, [state.sessionId]);

  const repeatQuestion = useCallback(async () => {
    if (!state.sessionId) return;

    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const response = await sobesApi.repeat(state.sessionId);
      setState((prev) => ({
        ...prev,
        view: 'question',
        currentQuestion: response.question,
        userAnswer: '',
        lastAnswer: null,
        isLoading: false,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка повтора вопроса',
      }));
    }
  }, [state.sessionId]);

  const loadResults = useCallback(async () => {
    if (!state.sessionId) return;
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const results = await sobesApi.getResults(state.sessionId);
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
    setState((prev) => ({
      ...prev,
      view: 'setup',
      sessionId: null,
      currentQuestion: null,
      userAnswer: '',
      lastAnswer: null,
      results: null,
      error: null,
    }));
  }, []);

  const goBack = useCallback(() => {
    restart();
  }, [restart]);

  return {
    ...state,
    setLevel,
    toggleTopic,
    startSobes,
    setUserAnswer,
    submitAnswer,
    nextQuestion,
    skipQuestion,
    repeatQuestion,
    restart,
    goBack,
  };
}
