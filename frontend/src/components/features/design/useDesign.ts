import { useState, useCallback, useEffect } from 'react';
import { designApi } from '@/services/api';
import type { DesignState } from './types';

export function useDesign() {
  const [state, setState] = useState<DesignState>({
    view: 'setup',
    config: null,
    level: 'junior',
    selectedScenarioId: null,
    sessionId: null,
    scenario: null,
    currentStep: null,
    stepIndex: 0,
    totalSteps: 0,
    userAnswer: '',
    lastAnswer: null,
    hint: null,
    results: null,
    isLoading: false,
    error: null,
  });

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const config = await designApi.getConfig();
      setState((prev) => ({
        ...prev,
        config,
        level: config.levels[0] || 'junior',
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Ошибка загрузки конфигурации',
      }));
    }
  }, []);

  const setLevel = useCallback((level: string) => {
    setState((prev) => ({ ...prev, level }));
  }, []);

  const selectScenario = useCallback((scenarioId: string) => {
    setState((prev) => ({ ...prev, selectedScenarioId: scenarioId }));
  }, []);

  const startDesign = useCallback(async () => {
    if (!state.selectedScenarioId) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const response = await designApi.start(state.level, state.selectedScenarioId);
      setState((prev) => ({
        ...prev,
        view: 'question',
        isLoading: false,
        sessionId: response.session_id,
        scenario: response.scenario,
        currentStep: response.step,
        totalSteps: response.total_steps,
        stepIndex: 0,
        userAnswer: '',
        lastAnswer: null,
        hint: null,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка запуска дизайн-сессии',
      }));
    }
  }, [state.level, state.selectedScenarioId]);

  const setUserAnswer = useCallback((answer: string) => {
    setState((prev) => ({ ...prev, userAnswer: answer }));
  }, []);

  const getHint = useCallback(async () => {
    if (!state.sessionId || !state.currentStep) return;

    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const response = await designApi.getHint(state.sessionId, state.currentStep.step_id);
      setState((prev) => ({
        ...prev,
        isLoading: false,
        hint: response.hint,
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Ошибка получения подсказки',
      }));
    }
  }, [state.sessionId, state.currentStep]);

  const submitAnswer = useCallback(async () => {
    if (!state.currentStep || !state.sessionId || !state.userAnswer.trim()) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const answer = await designApi.answer(
        state.sessionId,
        state.currentStep.step_id,
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
  }, [state.currentStep, state.sessionId, state.userAnswer]);

  const nextStep = useCallback(async () => {
    if (!state.sessionId) return;

    const nextS = state.lastAnswer?.next_step;
    if (state.lastAnswer?.is_last || !nextS) {
      await loadResults();
      return;
    }

    setState((prev) => ({
      ...prev,
      view: 'question',
      currentStep: nextS,
      stepIndex: prev.stepIndex + 1,
      userAnswer: '',
      lastAnswer: null,
      hint: null,
    }));
  }, [state.lastAnswer, state.sessionId]);

  const loadResults = useCallback(async () => {
    if (!state.sessionId) return;
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const results = await designApi.getResults(state.sessionId);
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
      selectedScenarioId: null,
      sessionId: null,
      scenario: null,
      currentStep: null,
      stepIndex: 0,
      userAnswer: '',
      lastAnswer: null,
      hint: null,
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
    selectScenario,
    startDesign,
    setUserAnswer,
    getHint,
    submitAnswer,
    nextStep,
    restart,
    goBack,
  };
}
