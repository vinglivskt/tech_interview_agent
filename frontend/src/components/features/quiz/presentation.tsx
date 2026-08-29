import React from "react";
import { Button, Card, Markdown } from "@/components/ui";
import type { QuizSetupViewProps, QuizQuestionViewProps, QuizAnswerViewProps, QuizResultsViewProps } from "./types";
import styles from "./quiz.module.scss";

const LEVEL_NAMES: Record<string, string> = {
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
};

export const QuizSetupPresentation: React.FC<QuizSetupViewProps> = ({ level, onLevelChange, onStart, isLoading }) => (
  <Card className={styles.setupCard}>
    <h2 className={styles.title}>Настройка квиза</h2>
    <p className={styles.subtitle}>Выберите уровень сложности</p>

    <div className={styles.levelGrid}>
      {(["junior", "middle", "senior"] as const).map((l) => (
        <div
          key={l}
          className={`${styles.levelCard} ${level === l ? styles.selected : ""}`}
          onClick={() => onLevelChange(l)}
        >
          <h3>{LEVEL_NAMES[l]}</h3>
          <p>
            {l === "junior" && "Базовые вопросы для начинающих"}
            {l === "middle" && "Вопросы для разработчика с опытом"}
            {l === "senior" && "Глубокие вопросы для senior"}
          </p>
        </div>
      ))}
    </div>

    <Button onClick={onStart} loading={isLoading} disabled={isLoading}>
      Начать квиз
    </Button>
  </Card>
);

export const QuizQuestionPresentation: React.FC<QuizQuestionViewProps> = ({
  question,
  selectedOption,
  onSelectOption,
  onSubmit,
  onBack,
  isLoading,
}) => (
  <div className={styles.container}>
    <header className={styles.header}>
      <Button variant="secondary" onClick={onBack}>
        ← На главную
      </Button>
      <div className={styles.progress}>
        {question.question_number} / {question.total_questions}
      </div>
    </header>

    <Card className={styles.questionCard}>
      <div className={styles.questionBadge}>Вопрос {question.question_number}</div>
      <p className={styles.questionText}>{question.question_text}</p>

      <div className={styles.options}>
        {question.options.map((opt) => (
          <div
            key={opt.index}
            className={`${styles.option} ${selectedOption === opt.index ? styles.selected : ""}`}
            onClick={() => onSelectOption(opt.index)}
          >
            <input
              type="radio"
              name="quiz-option"
              checked={selectedOption === opt.index}
              onChange={() => onSelectOption(opt.index)}
            />
            <label>{opt.text}</label>
          </div>
        ))}
      </div>

      <Button onClick={onSubmit} disabled={selectedOption === null} loading={isLoading}>
        Ответить
      </Button>
    </Card>
  </div>
);

export const QuizAnswerPresentation: React.FC<QuizAnswerViewProps> = ({
  question,
  selectedOption,
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
      <div className={`${styles.resultBadge} ${answer.is_correct ? styles.correct : styles.wrong}`}>
        {answer.is_correct ? "✓ Правильно!" : "✗ Неправильно"}
      </div>

      <p className={styles.questionText}>{question.question_text}</p>

      <div className={styles.answerSection}>
        <strong>Ваш ответ:</strong>
        <span className={answer.is_correct ? styles.correctText : styles.wrongText}>
          {question.options.find((o) => o.index === selectedOption)?.text}
        </span>
      </div>

      {!answer.is_correct && (
        <div className={styles.answerSection}>
          <strong>Правильный ответ:</strong>
          <span className={styles.correctText}>
            {question.options.find((o) => o.index === answer.correct_index)?.text}
          </span>
        </div>
      )}

      <div className={styles.explanation}>
        <strong>Пояснение:</strong>
        <Markdown content={answer.explanation} />
      </div>

      <Button onClick={onNext}>{answer.is_last ? "Посмотреть результаты" : "Следующий вопрос →"}</Button>
    </Card>
  </div>
);

export const QuizResultsPresentation: React.FC<QuizResultsViewProps> = ({ results, onRestart, onBack }) => {
  const percentage = Math.round((results.total_score / results.total_questions) * 100);

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
      </header>

      <Card className={styles.resultsCard}>
        <h2 className={styles.resultsTitle}>Результаты квиза</h2>

        <div className={styles.scoreSection}>
          <div className={styles.bigScore}>{percentage}%</div>
          <div className={styles.scoreDetails}>
            {results.total_score} из {results.total_questions} правильно
          </div>
          <div className={styles.levelBadge}>{LEVEL_NAMES[results.level]}</div>
        </div>

        <div className={styles.resultsList}>
          {results.results.map((result, i) => (
            <div key={i} className={`${styles.resultItem} ${result.is_correct ? styles.correct : styles.wrong}`}>
              <h4>{result.question_text}</h4>
              <p>Ваш ответ: {result.user_answer}</p>
              {!result.is_correct && <p>Правильный: {result.correct_answer}</p>}
              <p className={styles.explanationText}>{result.explanation}</p>
            </div>
          ))}
        </div>

        <div className={styles.resultsActions}>
          <Button onClick={onRestart}>Пройти ещё раз</Button>
        </div>
      </Card>
    </div>
  );
};

export default QuizSetupPresentation;
