import React from "react";
import { Button, Card, Markdown, Spinner } from "@/components/ui";
import type {
  DesignSetupViewProps,
  DesignQuestionViewProps,
  DesignAnswerViewProps,
  DesignResultsViewProps,
} from "./types";
import styles from "./design.module.scss";

export const DesignSetupPresentation: React.FC<DesignSetupViewProps> = ({
  config,
  level,
  selectedScenarioId,
  onLevelChange,
  onScenarioSelect,
  onStart,
  onBack,
  isLoading,
  error,
}) => {
  if (!config) {
    return (
      <div className={styles.loadingContainer}>
        <Spinner size="large" />
        <p>Загрузка конфигурации...</p>
      </div>
    );
  }

  const filteredScenarios = config.scenarios.filter((s) => s.level === level);

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
      </header>

      <Card className={styles.setupCard}>
        <h2 className={styles.title}>Проектирование системы</h2>
        <p className={styles.subtitle}>Штраф за подсказку: {config.hint_penalty_percent}%</p>

        <div className={styles.section}>
          <h3>Уровень сложности</h3>
          <div className={styles.levelGrid}>
            {config.levels.map((l) => (
              <div
                key={l}
                className={`${styles.levelCard} ${level === l ? styles.selected : ""}`}
                onClick={() => onLevelChange(l)}
              >
                <h4>{l.charAt(0).toUpperCase() + l.slice(1)}</h4>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.section}>
          <h3>Сценарий</h3>
          {filteredScenarios.length === 0 ? (
            <p className={styles.noScenarios}>Нет сценариев для этого уровня</p>
          ) : (
            <div className={styles.scenariosList}>
              {filteredScenarios.map((scenario) => (
                <div
                  key={scenario.id}
                  className={`${styles.scenarioCard} ${selectedScenarioId === scenario.id ? styles.selected : ""}`}
                  onClick={() => onScenarioSelect(scenario.id)}
                >
                  <h4>{scenario.title}</h4>
                </div>
              ))}
            </div>
          )}
        </div>

        {error && <div className={styles.error}>{error}</div>}

        <Button onClick={onStart} loading={isLoading} disabled={isLoading || !selectedScenarioId}>
          Начать проектирование
        </Button>
      </Card>
    </div>
  );
};

export const DesignQuestionPresentation: React.FC<DesignQuestionViewProps> = ({
  scenario,
  step,
  stepIndex,
  totalSteps,
  userAnswer,
  hint,
  onAnswerChange,
  onSubmit,
  onGetHint,
  onBack,
  isLoading,
}) => (
  <div className={styles.container}>
    <header className={styles.header}>
      <Button variant="secondary" onClick={onBack}>
        ← На главную
      </Button>
      <div className={styles.progress}>
        Шаг {stepIndex + 1} из {totalSteps}
      </div>
    </header>

    <Card className={styles.questionCard}>
      <div className={styles.scenarioInfo}>{scenario.title}</div>

      <div className={styles.stepBadge}>Шаг {stepIndex + 1}</div>
      <p className={styles.stepDescription}>{step.description}</p>

      {step.requirements.length > 0 && (
        <div className={styles.requirements}>
          <h4>Требования:</h4>
          <ul>
            {step.requirements.map((req, i) => (
              <li key={i}>{req}</li>
            ))}
          </ul>
        </div>
      )}

      {hint && (
        <div className={styles.hint}>
          <h4>Подсказка:</h4>
          <Markdown content={hint} />
        </div>
      )}

      <div className={styles.answerArea}>
        <label>Ваше решение:</label>
        <textarea
          value={userAnswer}
          onChange={(e) => onAnswerChange(e.target.value)}
          placeholder="Опишите ваш подход к решению..."
          rows={8}
          disabled={isLoading}
        />
      </div>

      <div className={styles.actions}>
        <Button onClick={onSubmit} disabled={!userAnswer.trim() || isLoading} loading={isLoading}>
          Отправить
        </Button>
        <Button variant="secondary" onClick={onGetHint} disabled={isLoading || !!hint}>
          Подсказка
        </Button>
      </div>
    </Card>
  </div>
);

export const DesignAnswerPresentation: React.FC<DesignAnswerViewProps> = ({
  scenario,
  step,
  stepIndex,
  userAnswer,
  answer,
  onNext,
  onBack,
}) => (
  <div className={styles.container}>
    <header className={styles.header}>
      <Button variant="secondary" onClick={onBack}>
        ← На главную
      </Button>
    </header>

    <Card className={styles.answerCard}>
      <div className={styles.scoreBar}>
        <div className={styles.scoreFill} style={{ width: `${answer.score_percent}%` }} />
        <span className={styles.scoreText}>{answer.score_percent}% покрыто</span>
      </div>

      <div className={styles.scenarioInfo}>{scenario.title}</div>
      <div className={styles.stepBadge}>Шаг {stepIndex + 1}</div>
      <p className={styles.stepDescription}>{step.description}</p>

      <div className={styles.answerSection}>
        <strong>Ваш ответ:</strong>
        <p className={styles.userAnswer}>{userAnswer}</p>
      </div>

      <div className={styles.explanation}>
        <strong>Разбор:</strong>
        <Markdown content={answer.techlead_explanation} />
      </div>

      {answer.covered_points.length > 0 && (
        <div className={styles.pointsSection}>
          <h4>✓ Раскрыто:</h4>
          <ul>
            {answer.covered_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      {answer.missed_points.length > 0 && (
        <div className={styles.pointsSection + " " + styles.missed}>
          <h4>✗ Пропущено:</h4>
          <ul>
            {answer.missed_points.map((point, i) => (
              <li key={i}>{point}</li>
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

      <Button onClick={onNext}>{answer.is_last ? "Посмотреть результаты" : "Следующий шаг →"}</Button>
    </Card>
  </div>
);

export const DesignResultsPresentation: React.FC<DesignResultsViewProps> = ({ results, onRestart, onBack }) => {
  const verdictBadge = results.verdict_level
    ? results.verdict_level.charAt(0).toUpperCase() + results.verdict_level.slice(1)
    : "N/A";

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
      </header>

      <Card className={styles.resultsCard}>
        <h2 className={styles.resultsTitle}>Результаты проектирования</h2>

        <div className={styles.verdictBadge}>{verdictBadge}</div>

        <div className={styles.summary}>
          <Markdown content={results.summary} />
        </div>

        {results.strengths.length > 0 && (
          <div className={styles.feedbackSection}>
            <h4>Сильные стороны:</h4>
            <ul>
              {results.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
        )}

        {results.weaknesses.length > 0 && (
          <div className={styles.feedbackSection + " " + styles.weaknesses}>
            <h4>Области для улучшения:</h4>
            <ul>
              {results.weaknesses.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <h3 className={styles.detailsTitle}>Детализация по шагам</h3>
        <div className={styles.resultsList}>
          {results.details.map((detail, i) => (
            <div key={i} className={styles.resultItem}>
              <h4>{detail.step}</h4>
              <p>Ваш ответ: {detail.user_answer}</p>
              <p>Оценка: {detail.score}%</p>
              <p className={styles.detailExplanation}>{detail.explanation}</p>
            </div>
          ))}
        </div>

        <div className={styles.resultsActions}>
          <Button onClick={onRestart}>Начать заново</Button>
        </div>
      </Card>
    </div>
  );
};

export default DesignSetupPresentation;
