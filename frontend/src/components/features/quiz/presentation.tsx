import React from "react";
import { Button, Markdown } from "@/components/ui";
import type { QuizViewProps } from "./types";
import styles from "./quiz.module.css";

const LEVEL_NAMES: Record<string, string> = {
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
};

export const QuizSetupView: React.FC<QuizViewProps> = ({
  level,
  onLevelChange,
  onStart,
  isLoading,
  onBack,
  onShowStats,
}) => {
  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack ?? (() => {})}>
          ← На главную
        </Button>
        <h1 className={styles.title}>Тестирование</h1>
        {onShowStats}
      </header>

      <div className={styles.setupCard}>
        <p className={styles.subtitle}>Выберите уровень сложности и начните тест из 20 вопросов</p>

        <label className={styles.label} htmlFor="quiz-level">
          Уровень
        </label>
        <select
          id="quiz-level"
          className={styles.select}
          value={level}
          onChange={(e) => onLevelChange(e.target.value as "junior" | "middle" | "senior")}
        >
          <option value="junior">Junior (лёгкие вопросы)</option>
          <option value="middle">Middle (средние вопросы)</option>
          <option value="senior">Senior (сложные вопросы)</option>
        </select>

        <div className={styles.row} style={{ marginTop: "1rem" }}>
          <Button variant="success" onClick={onStart} disabled={isLoading} loading={isLoading}>
            {isLoading ? "Начинаем…" : "Начать тест"}
          </Button>
        </div>
      </div>
    </div>
  );
};

export const QuizQuestionView: React.FC<{
  question: {
    question_text: string;
    question_number: number;
    total_questions: number;
    options: string[];
  };
  selectedOption: number | null;
  onSelectOption: (index: number) => void;
  onSubmit: () => void;
  onBack: () => void;
  isLoading: boolean;
  onShowStats?: React.ReactNode;
}> = ({ question, selectedOption, onSelectOption, onSubmit, onBack, isLoading, onShowStats }) => {
  const progressPercent = (question.question_number / question.total_questions) * 100;

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        <div className={styles.progress}>
          Вопрос {question.question_number} из {question.total_questions}
        </div>
        {onShowStats}
      </header>

      <div className={styles.progressBar}>
        <div className={styles.progressBarFill} style={{ width: `${progressPercent}%` }} />
      </div>

      <div className={styles.questionCard}>
        <div className={styles.questionBadge}>Вопрос {question.question_number}</div>
        <p className={styles.questionText}>{question.question_text}</p>

        <div className={styles.options}>
          {question.options.map((opt, idx) => (
            <div
              key={idx}
              className={`${styles.option} ${selectedOption === idx ? styles.selected : ""}`}
              onClick={() => onSelectOption(idx)}
            >
              <input
                type="radio"
                name="quiz-option"
                checked={selectedOption === idx}
                onChange={() => onSelectOption(idx)}
              />
              <label>{opt}</label>
            </div>
          ))}
        </div>

        <div className={styles.row} style={{ marginTop: "1rem" }}>
          <Button onClick={onSubmit} disabled={selectedOption === null || isLoading} loading={isLoading}>
            Далее →
          </Button>
        </div>
      </div>
    </div>
  );
};

export const QuizResultsView: React.FC<{
  results: {
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
  };
  onRestart: () => void;
  onBack: () => void;
  onShowStats?: React.ReactNode;
}> = ({ results, onRestart, onBack, onShowStats }) => {
  const escapeHtml = (text: string) => {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        {onShowStats}
      </header>

      <div className={styles.resultsCard}>
        <div className={styles.resultsScore}>
          <div className={styles.bigScore}>
            {results.total_score}/{results.total_questions}
          </div>
          <div className={styles.levelBadge}>Уровень: {LEVEL_NAMES[results.level] || results.level}</div>
        </div>

        <h2 style={{ margin: "1.5rem 0 1rem", fontSize: "1.1rem" }}>Подробные результаты</h2>

        <div className={styles.resultsList}>
          {results.results.map((r, idx) => (
            <div key={idx} className={`${styles.resultItem} ${r.is_correct ? styles.correct : styles.wrong}`}>
              <h4>
                Вопрос {idx + 1}: {escapeHtml(r.question_text)}
              </h4>
              <p>
                <span className={styles.label}>Ваш ответ:</span> {escapeHtml(r.user_answer)}
              </p>
              {!r.is_correct && (
                <>
                  <p>
                    <span className={styles.label}>Правильный ответ:</span> {escapeHtml(r.correct_answer)}
                  </p>
                  <div className={styles.label}>Объяснение:</div>
                  <Markdown content={r.explanation} />
                </>
              )}
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

export default QuizSetupView;
