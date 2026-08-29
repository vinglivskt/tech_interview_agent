import { useState, useCallback, useEffect } from "react";
import { designApi } from "@/services/api";
import type { DesignConfig, DesignStep, DesignScenario, DesignAnswer, DesignResults, DesignView } from "./types";

export function useDesign() {
  const [view, setView] = useState<DesignView>("setup");
  const [config, setConfig] = useState<DesignConfig | null>(null);
  const [level, setLevel] = useState("middle");
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [scenario, setScenario] = useState<DesignScenario | null>(null);
  const [step, setStep] = useState<DesignStep | null>(null);
  const [stepIndex, setStepIndex] = useState(1);
  const [totalSteps, setTotalSteps] = useState(0);
  const [userAnswer, setUserAnswer] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [lastAnswer, setLastAnswer] = useState<DesignAnswer | null>(null);
  const [results, setResults] = useState<DesignResults | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const data = await designApi.getConfig();
      setConfig(data);
      if (data.levels.includes("middle")) {
        setLevel("middle");
      }
    } catch {
      setError("Не удалось загрузить сценарии");
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const selectScenario = useCallback((scenarioId: string) => {
    setSelectedScenarioId(scenarioId);
  }, []);

  const startDesign = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await designApi.start(level, selectedScenarioId);
      setSessionId(data.session_id);
      setScenario(data.scenario);
      setStep(data.step);
      setTotalSteps(data.total_steps);
      setStepIndex(1);
      setUserAnswer("");
      setHint(null);
      setLastAnswer(null);
      setView("question");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка запуска");
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [level, selectedScenarioId]);

  const getHint = useCallback(async () => {
    if (!sessionId || !step) return;

    setIsLoading(true);
    try {
      const data = await designApi.getHint(sessionId, step.id);
      setHint(`**Подсказка (штраф ${data.penalty_applied_percent}%):** ${data.hint}`);
    } catch (err) {
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, step]);

  const submitAnswer = useCallback(async () => {
    if (!sessionId || !step || !userAnswer.trim()) return;

    setIsLoading(true);
    try {
      const data = await designApi.answer(sessionId, step.id, userAnswer);
      setLastAnswer(data);

      if (data.is_last) {
        // Will load results
        const resultsData = await designApi.getResults(sessionId);
        setResults(resultsData);
        setView("answer");
      } else {
        setView("answer");
      }
    } catch (err) {
      alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, step, userAnswer]);

  const nextStep = useCallback(async () => {
    if (!lastAnswer) return;

    if (lastAnswer.is_last) {
      if (sessionId) {
        try {
          const resultsData = await designApi.getResults(sessionId);
          setResults(resultsData);
          setView("results");
        } catch (err) {
          alert("Ошибка: " + (err instanceof Error ? err.message : "Неизвестная ошибка"));
        }
      }
      return;
    }

    if (lastAnswer.next_step) {
      setStep(lastAnswer.next_step);
      setStepIndex((prev) => prev + 1);
      setUserAnswer("");
      setHint(null);
      setLastAnswer(null);
      setView("question");
    }
  }, [lastAnswer, sessionId]);

  const goBack = useCallback(() => {
    setView("setup");
    setStep(null);
    setUserAnswer("");
    setHint(null);
    setLastAnswer(null);
    setResults(null);
  }, []);

  const restart = useCallback(() => {
    setView("setup");
    setStep(null);
    setUserAnswer("");
    setHint(null);
    setLastAnswer(null);
    setResults(null);
    setSessionId(null);
    setScenario(null);
  }, []);

  return {
    view,
    config,
    level,
    setLevel,
    selectedScenarioId,
    selectScenario,
    startDesign,
    scenario,
    step,
    stepIndex,
    totalSteps,
    userAnswer,
    setUserAnswer,
    hint,
    lastAnswer,
    results,
    isLoading,
    error,
    getHint,
    submitAnswer,
    nextStep,
    goBack,
    restart,
  };
}
