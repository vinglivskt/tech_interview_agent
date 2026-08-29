import React from 'react';
import { Button, Card, Markdown, Spinner } from '@/components/ui';
import type {
  SobesSetupViewProps,
  SobesQuestionViewProps,
  SobesAnswerViewProps,
  SobesResultsViewProps,
} from './types';
import styles from './sobes.module.scss';

const LEVEL_NAMES: Record<string, string> = {
  junior: 'Junior',
  middle: 'Middle',
  senior: 'Senior',
};

export const SobesSetupPresentation: React.FC<SobesSetupViewProps> = ({
  config,
  level,
  selectedTopics,
  onLevelChange,
  onTopicToggle,
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

  const countsByLevel = config.counts_by_level || {};

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
      </header>

      <Card className={styles.setupCard}>
        <h2 className={styles.title}>Подготовка к собеседованию</h2>
        <p className={styles.subtitle}>
          Порог прохождения: {config.pass_threshold}%
        </p>

        <div className={styles.section}>
          <h3>Уровень сложности</h3>
          <div className={styles.levelGrid}>
            {(['junior', 'middle', 'senior'] as const).map((l) => (
              <div
                key={l}
                className={`${styles.levelCard} ${level === l ? styles.selected : ''}`}
                onClick={() => onLevelChange(l)}
              >
                <h4>{LEVEL_NAMES[l]}</h4>
                <p>{countsByLevel[l] || 0} вопросов</p>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.section}>
          <h3>Темы</h3>
          <div className={styles.topicsGrid}>
            {config.topics.map((topic) => (
              <div
                key={topic.id}
                className={`${styles.topicCard} ${
                  selectedTopics.includes(topic.id) ? styles.selected : ''
                }`}
                onClick={() => onTopicToggle(topic.id)}
              >
                <span className={styles.topicCheck}>
                  {selectedTopics.includes(topic.id) ? '✓' : ''}
                </span>
                <span>{topic.name}</span>
              </div>
            ))}
          </div>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        <Button
          onClick={onStart}
          loading={isLoading}
          disabled={isLoading || selectedTopics.length === 0}
        >
          Начать подготовку
        </Button>
      </Card>
    </div>
  );
};

export const SobesQuestionPresentation: React.FC<SobesQuestionViewProps> = ({
  question,
  userAnswer,
  onAnswerChange,
  onSubmit,
  onSkip,
  onRepeat,
  onBack,
  isLoading,
  questionNumber,
  totalPlanned,
}) => (
  <div className={styles.container}>
    <header className={styles.header}>
      <Button variant="secondary" onClick={onBack}>
        ← На главную
      </Button>
      <div className={styles.progress}>
        {questionNumber} / {totalPlanned}
      </div>
    </header>

    <Card className={styles.questionCard}>
      {question.topic_hint && (
        <div className={styles.topicHint}>
          <strong>Тема:</strong> {question.topic_hint}
        </div>
      )}

      <div className={styles.questionMeta}>
        <span className={styles.questionNumber}>Вопрос {question.number}</span>
        <span className={styles.questionTopic}>{question.topic}</span>
      </div>

      <p className={styles.questionText}>{question.text}</p>

      <div className={styles.answerArea}>
        <label>Ваш ответ:</label>
        <textarea
          value={userAnswer}
          onChange={(e) => onAnswerChange(e.target.value)}
          placeholder="Введите ваш ответ..."
          rows={6}
          disabled={isLoading}
        />
      </div>

      <div className={styles.actions}>
        <Button
          variant="secondary"
          onClick={onSubmit}
          disabled={!userAnswer.trim() || isLoading}
          loading={isLoading}
        >
          Проверить
        </Button>
        <Button variant="secondary" onClick={onSkip} disabled={isLoading}>
          Пропустить
        </Button>
        <Button variant="secondary" onClick={onRepeat} disabled={isLoading}>
          Повторить
        </Button>
      </div>
    </Card>
  </div>
);

export const SobesAnswerPresentation: React.FC<SobesAnswerViewProps> = ({
  question,
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
        <div
          className={styles.scoreFill}
          style={{ width: `${answer.score_percent}%` }}
        />
        <span className={styles.scoreText}>
          {answer.score_percent}% покрыто
        </span>
      </div>

      <h3 className={styles.questionTitle}>{question.text}</h3>

      <div className={styles.answerSection}>
        <strong>Ваш ответ:</strong>
        <p className={styles.userAnswer}>{userAnswer}</p>
      </div>

      <div className={styles.explanation}>
        <strong>Разбор от HR:</strong>
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
        <div className={styles.pointsSection + ' ' + styles.missed}>
          <h4>✗ Пропущено:</h4>
          <ul>
            {answer.missed_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      <Button onClick={onNext}>
        {answer.is_last ? 'Посмотреть результаты' : 'Следующий вопрос →'}
      </Button>
    </Card>
  </div>
);

export const SobesResultsPresentation: React.FC<SobesResultsViewProps> = ({
  results,
  onRestart,
  onBack,
}) => {
  const levelBadge = results.verdict_level
    ? LEVEL_NAMES[results.verdict_level] || results.verdict_level
    : 'N/A';

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
      </header>

      <Card className={styles.resultsCard}>
        <h2 className={styles.resultsTitle}>Результаты собеседования</h2>

        <div className={styles.verdictBadge}>{levelBadge}</div>

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
          <div className={styles.feedbackSection + ' ' + styles.weaknesses}>
            <h4>Области для улучшения:</h4>
            <ul>
              {results.weaknesses.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <h3 className={styles.detailsTitle}>Детализация по вопросам</h3>
        <div className={styles.resultsList}>
          {results.details.map((detail, i) => (
            <div
              key={i}
              className={`${styles.resultItem} ${
                detail.is_correct ? styles.correct : styles.wrong
              }`}
            >
              <p className={styles.detailQuestion}>{detail.question}</p>
              <p>Ваш ответ: {detail.user_answer}</p>
              {!detail.is_correct && (
                <>
                  <p className={styles.correctAnswer}>
                    Ожидалось: {detail.correct_answer}
                  </p>
                  <p className={styles.detailExplanation}>
                    {detail.explanation}
                  </p>
                </>
              )}
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

export default SobesSetupPresentation;
