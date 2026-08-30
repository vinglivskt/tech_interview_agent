import React from "react";
import { Button, Markdown } from "@/components/ui";
import { FeatureHeader } from "@/components/features/_shared/FeatureHeader";
import styles from "./design.module.css";

export const DesignSetupView: React.FC<{
  config: {
    levels: string[];
    scenarios: { id: string; title: string; level: string }[];
    hint_penalty_percent: number;
  } | null;
  level: string;
  selectedScenarioId: string;
  onLevelChange: (level: string) => void;
  onScenarioSelect: (scenarioId: string) => void;
  onStart: () => void;
  onBack: () => void;
  isLoading: boolean;
  error: string | null;
  onShowStats?: React.ReactNode;
}> = ({
  config,
  level,
  selectedScenarioId,
  onLevelChange,
  onScenarioSelect,
  onStart,
  onBack,
  isLoading,
  error,
  onShowStats,
}) => {
  if (!config) {
    return (
      <div className={styles.container}>
        <FeatureHeader onBack={onBack} right={onShowStats} />
        <div className={styles.loadingContainer}>Загрузка конфигурации...</div>
      </div>
    );
  }

  const filteredScenarios = config.scenarios.filter((s) => s.level === level);

  return (
    <div className={styles.container}>
      <FeatureHeader onBack={onBack} title="Системный дизайн" right={onShowStats} />

      <div className={styles.setupCard}>
        <p className={styles.subtitle}>Выберите уровень и сценарий. Можно оставить автоматический выбор.</p>

        <label className={styles.label} htmlFor="design-level">
          Уровень
        </label>
        <select
          id="design-level"
          className={styles.select}
          value={level}
          onChange={(e) => onLevelChange(e.target.value)}
        >
          {config.levels.map((l) => (
            <option key={l} value={l}>
              {l.charAt(0).toUpperCase() + l.slice(1)}
            </option>
          ))}
        </select>

        <label className={styles.label} htmlFor="design-scenario" style={{ marginTop: "0.9rem" }}>
          Сценарий
        </label>
        <select
          id="design-scenario"
          className={styles.select}
          value={selectedScenarioId}
          onChange={(e) => onScenarioSelect(e.target.value)}
        >
          <option value="">Любой подходящий</option>
          {filteredScenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>

        <div className={styles.meta} style={{ marginTop: "0.5rem" }}>
          Подсказка снижает балл шага на {config.hint_penalty_percent}%.
        </div>

        {error && <div className={styles.error}>{error}</div>}

        <div className={styles.row} style={{ marginTop: "1rem" }}>
          <Button variant="success" onClick={onStart} disabled={isLoading} loading={isLoading}>
            {isLoading ? "Готовим сценарий…" : "Начать проектирование"}
          </Button>
        </div>
      </div>
    </div>
  );
};

export const DesignQuestionView: React.FC<{
  scenario: { title: string };
  step: { id: string; title: string; prompt: string };
  stepIndex: number;
  totalSteps: number;
  userAnswer: string;
  hint: string | null;
  isLoading: boolean;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  onGetHint: () => void;
  onShowStats?: React.ReactNode;
  onBack: () => void;
}> = ({
  scenario,
  step,
  stepIndex,
  totalSteps,
  userAnswer,
  hint,
  isLoading,
  onAnswerChange,
  onSubmit,
  onGetHint,
  onBack,
  onShowStats,
}) => {
  const progressPercent = totalSteps ? Math.round(((stepIndex - 1) / totalSteps) * 100) : 0;

  return (
    <div className={styles.container}>
      <FeatureHeader onBack={onBack} center={`Шаг ${stepIndex} из ${totalSteps}`} right={onShowStats} />

      <div className={styles.progressBar}>
        <div className={styles.progressBarFill} style={{ width: `${progressPercent}%` }} />
      </div>

      <div className={styles.questionCard}>
        <div className={styles.scenarioInfo}>{scenario.title}</div>
        <div className={styles.stepBadge}>Шаг {stepIndex}</div>
        <p className={styles.stepDescription}>{step.prompt || step.title}</p>

        <div className={styles.row}>
          <Button variant="secondary" onClick={onGetHint} disabled={isLoading || !!hint}>
            Подсказка (−10%)
          </Button>
        </div>

        {hint && (
          <div className={styles.hint}>
            <h4>Подсказка:</h4>
            <Markdown content={hint} />
          </div>
        )}

        <label className={styles.label} htmlFor="design-answer">
          Ваше решение
        </label>
        <textarea
          id="design-answer"
          className={styles.textarea}
          value={userAnswer}
          onChange={(e) => onAnswerChange(e.target.value)}
          placeholder="Опишите решение… (Ctrl/Cmd+Enter — отправить)"
          disabled={isLoading}
        />

        <div className={styles.actions}>
          <Button onClick={onSubmit} disabled={!userAnswer.trim() || isLoading} loading={isLoading}>
            Ответить
          </Button>
        </div>
      </div>
    </div>
  );
};

export const DesignAnswerView: React.FC<{
  scenario: { title: string };
  step: { title: string };
  stepIndex: number;
  userAnswer: string;
  answer: {
    score_percent: number;
    techlead_explanation: string;
    covered_points: string[];
    missed_points: string[];
    rubric: string[];
    is_last: boolean;
  };
  onNext: () => void;
  onBack: () => void;
  onShowStats?: React.ReactNode;
}> = ({ scenario, step, stepIndex, userAnswer, answer, onNext, onBack, onShowStats }) => {
  return (
    <div className={styles.container}>
      <FeatureHeader onBack={onBack} right={onShowStats} />

      <div className={styles.answerCard}>
        <div className={styles.scoreBar}>
          <div className={styles.scoreFill} style={{ width: `${answer.score_percent}%` }} />
        </div>
        <span className={styles.scoreText}>Оценка: {answer.score_percent}%</span>

        <div className={styles.scenarioInfo}>{scenario.title}</div>
        <div className={styles.stepBadge}>Шаг {stepIndex}</div>
        <p className={styles.stepDescription}>{step.title}</p>

        <div className={styles.answerSection}>
          <strong>Ваш ответ:</strong>
          <p className={styles.userAnswer}>{userAnswer}</p>
        </div>

        <div className={styles.explanation}>
          <strong>Разбор:</strong>
          <Markdown content={`## Оценка: ${answer.score_percent}%\n\n${answer.techlead_explanation}`} />
        </div>

        {answer.covered_points.length > 0 && (
          <div className={styles.pointsSection}>
            <h4>✓ Раскрыто:</h4>
            <ul>
              {answer.covered_points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}

        {answer.missed_points.length > 0 && (
          <div className={`${styles.pointsSection} ${styles.missed}`}>
            <h4>✗ Упущено:</h4>
            <ul>
              {answer.missed_points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}

        {answer.rubric.length > 0 && (
          <div className={styles.rubric}>
            <h4>Рубрика:</h4>
            <ul>
              {answer.rubric.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        <div className={styles.row} style={{ marginTop: "1.5rem" }}>
          <Button onClick={onNext}>{answer.is_last ? "Посмотреть результаты →" : "Следующий шаг →"}</Button>
        </div>
      </div>
    </div>
  );
};

export const DesignResultsView: React.FC<{
  results: {
    summary: string;
    summary_detail?: { passed: number; steps: number; avg_percent: number };
    by_rubric: Record<string, number>;
    strengths: string[];
    weaknesses: string[];
    verdict_level: string;
    details: { title: string; user_answer: string; score_percent: number; explanation: string }[];
  };
  onRestart: () => void;
  onBack: () => void;
  onShowStats?: React.ReactNode;
}> = ({ results, onRestart, onBack, onShowStats }) => {
  const summaryText = results.summary_detail
    ? `${results.summary_detail.passed}/${results.summary_detail.steps} — ${results.summary_detail.avg_percent}%`
    : results.summary;

  const rubricText = Object.entries(results.by_rubric || {})
    .map(([k, v]) => `${k}: ${v}%`)
    .join(" · ");

  return (
    <div className={styles.container}>
      <FeatureHeader onBack={onBack} right={onShowStats} />

      <div className={styles.resultsCard}>
        <div className={styles.verdictBadge}>
          {summaryText} — Вердикт: {results.verdict_level}
        </div>

        <div className={styles.feedbackSection}>
          <strong>Сильные:</strong> {results.strengths.join(", ") || "—"}
        </div>
        <div className={`${styles.feedbackSection} ${styles.weaknesses}`}>
          <strong>Слабые:</strong> {results.weaknesses.join(", ") || "—"}
        </div>

        <h2 style={{ marginTop: "1rem", fontSize: "1.1rem" }}>Рубрика</h2>
        <div className={styles.output}>{rubricText}</div>

        <h2 style={{ marginTop: "1rem", fontSize: "1.1rem" }}>Детали</h2>
        <div className={styles.resultsList}>
          {results.details.map((d, idx) => (
            <div key={idx} className={styles.resultItem}>
              <h4>
                {d.title} — {d.score_percent}%
              </h4>
              <p>Ваш ответ: {d.user_answer}</p>
              <p>{d.explanation}</p>
            </div>
          ))}
        </div>

        <div className={styles.resultsActions}>
          <Button onClick={onBack}>На главную</Button>
          <Button variant="secondary" onClick={onRestart}>
            Пройти ещё раз
          </Button>
        </div>
      </div>
    </div>
  );
};

export default DesignSetupView;
