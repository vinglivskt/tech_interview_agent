import React from "react";
import { Button, Markdown } from "@/components/ui";
import styles from "./sobes.module.css";

export const SobesSetupView: React.FC<{
  config: {
    topics: string[];
    counts_by_level: Record<string, [number, number]>;
    pass_threshold: number;
  } | null;
  level: "junior" | "middle" | "senior";
  selectedTopics: string[];
  onLevelChange: (level: "junior" | "middle" | "senior") => void;
  onTopicToggle: (topic: string) => void;
  onStart: () => void;
  onBack: () => void;
  isLoading: boolean;
  error: string | null;
  onShowStats?: React.ReactNode;
}> = ({
  config,
  level,
  selectedTopics,
  onLevelChange,
  onTopicToggle,
  onStart,
  onBack,
  isLoading,
  error,
  onShowStats,
}) => {
  if (!config) {
    return (
      <div className={styles.container}>
        <header className={styles.header}>
          <Button variant="secondary" onClick={onBack}>
            ← На главную
          </Button>
          {onShowStats}
        </header>
        <div className={styles.loadingContainer}>Загрузка конфигурации...</div>
      </div>
    );
  }

  const countsByLevel = config.counts_by_level || {};
  const rng = (l: string) => {
    const range = countsByLevel[l];
    return range ? `${range[0]}–${range[1]}` : "?";
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        <h1 className={styles.title}>Собеседование</h1>
        {onShowStats}
      </header>

      <div className={styles.setupCard}>
        <p className={styles.subtitle}>
          Выберите уровень и темы. Система подберёт вопросы по темам и будет двигаться от простого к сложному.
        </p>

        <label className={styles.label} htmlFor="sobes-level">
          Уровень
        </label>
        <select
          id="sobes-level"
          className={styles.select}
          value={level}
          onChange={(e) => onLevelChange(e.target.value as "junior" | "middle" | "senior")}
        >
          <option value="junior">Junior</option>
          <option value="middle">Middle</option>
          <option value="senior">Senior</option>
        </select>

        <div className={styles.section} style={{ marginTop: "0.9rem" }}>
          <label>Темы</label>
          <div className={styles.topicsGrid}>
            {config.topics.map((topic) => (
              <div
                key={topic}
                className={`${styles.topicCard} ${selectedTopics.includes(topic) ? styles.selected : ""}`}
                onClick={() => onTopicToggle(topic)}
              >
                <span className={styles.topicCheck}>{selectedTopics.includes(topic) ? "✓" : ""}</span>
                <span>{topic}</span>
              </div>
            ))}
          </div>
          <div className={styles.meta}>
            Вопросов: junior {rng("junior")}, middle {rng("middle")}, senior {rng("senior")}. Порог засчёта:{" "}
            {config.pass_threshold}%
          </div>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        <div className={styles.row} style={{ marginTop: "1rem" }}>
          <Button
            variant="success"
            onClick={onStart}
            disabled={isLoading || selectedTopics.length === 0}
            loading={isLoading}
          >
            {isLoading ? "Готовим вопросы…" : "Начать собеседование"}
          </Button>
        </div>
      </div>
    </div>
  );
};

export const SobesQuestionView: React.FC<{
  question: {
    id: string;
    number: number;
    text: string;
    topic: string;
    level: string;
    topic_hint?: string;
  };
  questionIndex: number;
  totalPlanned: number;
  userAnswer: string;
  isLoading: boolean;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
  onRepeat: () => void;
  onBack: () => void;
  onShowStats?: React.ReactNode;
}> = ({
  question,
  questionIndex,
  totalPlanned,
  userAnswer,
  isLoading,
  onAnswerChange,
  onSubmit,
  onSkip,
  onRepeat,
  onBack,
  onShowStats,
}) => {
  const progressPercent = totalPlanned
    ? Math.max(0, Math.min(100, Math.round(((questionIndex - 1) / totalPlanned) * 100)))
    : 0;
  const levelNames: Record<string, string> = { junior: "Junior", middle: "Middle", senior: "Senior" };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        <div className={styles.progress}>
          Вопрос {questionIndex} из {totalPlanned}
        </div>
        {onShowStats}
      </header>

      <div className={styles.progressBar}>
        <div className={styles.progressBarFill} style={{ width: `${progressPercent}%` }} />
      </div>

      <div className={styles.questionCard}>
        <div className={styles.questionMeta}>
          <span className={styles.questionNumber}>Вопрос №{question.number}</span>
          <span>
            Тема: {question.topic} · Уровень: {levelNames[question.level] || question.level}
          </span>
        </div>

        {question.topic_hint && (
          <div className={styles.topicHint}>
            <strong>Подсказка:</strong> {question.topic_hint}
          </div>
        )}

        <p className={styles.questionText}>{question.text}</p>

        <label className={styles.label} htmlFor="sobes-answer">
          Ваш ответ
        </label>
        <textarea
          id="sobes-answer"
          className={styles.textarea}
          value={userAnswer}
          onChange={(e) => onAnswerChange(e.target.value)}
          placeholder="Ваш ответ… (Ctrl/Cmd+Enter — отправить)"
          disabled={isLoading}
        />

        <div className={styles.actions}>
          <Button variant="secondary" onClick={onRepeat} disabled={isLoading}>
            Повторить вопрос
          </Button>
          <Button variant="secondary" onClick={onSkip} disabled={isLoading}>
            Пропустить
          </Button>
          <Button onClick={onSubmit} disabled={!userAnswer.trim() || isLoading} loading={isLoading}>
            Отправить ответ
          </Button>
        </div>
      </div>
    </div>
  );
};

export const SobesAnswerView: React.FC<{
  question: { text: string };
  userAnswer: string;
  answer: {
    score_percent: number;
    techlead_explanation: string;
    covered_points: string[];
    missed_points: string[];
    is_last: boolean;
  };
  onNext: () => void;
  onBack: () => void;
  onShowStats?: React.ReactNode;
}> = ({ question, userAnswer, answer, onNext, onBack, onShowStats }) => {
  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        {onShowStats}
      </header>

      <div className={styles.answerCard}>
        <div className={styles.scoreBar}>
          <div className={styles.scoreFill} style={{ width: `${answer.score_percent}%` }} />
        </div>
        <span className={styles.scoreText}>Оценка: {answer.score_percent}%</span>

        <h3 className={styles.questionText}>{question.text}</h3>

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

        <div className={styles.row} style={{ marginTop: "1.5rem" }}>
          <Button onClick={onNext}>{answer.is_last ? "Посмотреть результаты →" : "Следующий вопрос →"}</Button>
        </div>
      </div>
    </div>
  );
};

export const SobesResultsView: React.FC<{
  results: {
    verdict_level: string;
    summary: string;
    summary_detail?: { counted: number; total: number; avg_percent: number };
    strengths: string[];
    weaknesses: string[];
    details: { question_text: string; topic: string; score_percent: number; explanation: string }[];
  };
  onRestart: () => void;
  onBack: () => void;
  onShowStats?: React.ReactNode;
}> = ({ results, onRestart, onBack, onShowStats }) => {
  const summaryText = results.summary_detail
    ? `${results.summary_detail.counted}/${results.summary_detail.total} — ${results.summary_detail.avg_percent}%`
    : results.summary;

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        {onShowStats}
      </header>

      <div className={styles.resultsCard}>
        <div className={styles.verdictBadge}>
          {summaryText} — Вердикт: {results.verdict_level}
        </div>

        <h2 style={{ marginTop: "1rem", fontSize: "1.1rem" }}>Сильные и слабые стороны</h2>
        <div className={styles.feedbackSection}>
          <strong>Сильные:</strong> {results.strengths.join(", ") || "—"}
        </div>
        <div className={`${styles.feedbackSection} ${styles.weaknesses}`}>
          <strong>Слабые:</strong> {results.weaknesses.join(", ") || "—"}
        </div>

        <h2 style={{ marginTop: "1rem", fontSize: "1.1rem" }}>Детали</h2>
        <div className={styles.resultsList}>
          {results.details.map((d, idx) => (
            <div key={idx} className={styles.resultItem}>
              <h4>
                Вопрос {idx + 1}: {d.question_text}
              </h4>
              <p>Тема: {d.topic}</p>
              <p>Процент: {d.score_percent}%</p>
              <p>Комментарий: {d.explanation}</p>
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

export default SobesSetupView;
