import React from "react";
import { Button, Markdown } from "@/components/ui";
import { FeatureHeader } from "@/components/features/_shared/FeatureHeader";
import type { ChatViewProps } from "./types";
import styles from "./chat.module.css";

export const ChatPresentation: React.FC<ChatViewProps> = ({
  questionNumber,
  questionText,
  isQuestionReady,
  answer,
  isAnswerEmpty,
  userAnswer,
  statusText,
  saveStatus,
  isLoading,
  error,
  customQuestion,
  isCustomMode,
  suggestSave,
  onAnswerChange,
  onCustomQuestionChange,
  onEnterCustomMode,
  onCancelCustomMode,
  onSubmitCustomQuestion,
  onSend,
  onSave,
  onBack,
  onReset,
  statsButton,
}) => {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className={styles.container}>
      <FeatureHeader onBack={onBack} title="Интервью" right={statsButton} />

      <p className={styles.subtitle}>
        Вверху — текущий вопрос. Ниже — поле для вашего ответа и результаты проверки.
      </p>

      {isCustomMode ? (
        // === Режим ввода своего вопроса ===
        <div className={styles.questionCard}>
          <div className={styles.questionBadge}>Свой вопрос</div>
          <div className={styles.questionText}>
            <p className={styles.customHelp}>
              Введите свой вопрос. Если он есть в базе — получите ответ из RAG. Если нет — ассистент ответит на основе
              своих знаний, и вы сможете сохранить вопрос в документ.
            </p>
          </div>

          <label className={styles.label} htmlFor="custom-question">
            Ваш вопрос
          </label>
          <textarea
            id="custom-question"
            className={styles.textarea}
            value={customQuestion}
            onChange={(e) => onCustomQuestionChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (customQuestion.trim() && !isLoading) onSubmitCustomQuestion();
              }
            }}
            placeholder="Например: Какие типы тестов вы бы использовали для каждого слоя архитектуры?"
            disabled={isLoading}
            maxLength={4000}
          />

          <div className={styles.row}>
            <Button onClick={onSubmitCustomQuestion} disabled={!customQuestion.trim() || isLoading} loading={isLoading}>
              Получить ответ
            </Button>
            <Button variant="secondary" onClick={onCancelCustomMode} disabled={isLoading}>
              Отмена
            </Button>
          </div>
        </div>
      ) : (
        // === Обычный режим: вопрос из базы ===
        <div className={styles.questionCard}>
          <div className={styles.questionBadge}>Вопрос №{questionNumber}</div>
          <div className={styles.questionText}>
            {questionText ? (
              <Markdown content={questionText} />
            ) : isLoading ? (
              <div className={styles.questionLoading}>
              <div className={styles.questionSkeleton} aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <p>Загружаем вопрос…</p>
            </div>
            ) : error ? (
              `Не удалось загрузить вопрос: ${error}`
            ) : (
              "Вопрос пока не загружен. Нажмите «Следующий вопрос» или обновите страницу."
            )}
          </div>
        </div>
      )}

      {/* Подсказка, что можно сохранить вопрос в docx */}
      {suggestSave && answer && (
        <div className={styles.saveStatus}>
          💡 Этого вопроса нет в базе. Сохраните его в Word, чтобы он попал в RAG для будущих тренировок.
        </div>
      )}

      {/* Кнопка «Задать свой вопрос» — только когда НЕ в режиме custom */}
      {!isCustomMode && (
        <div className={styles.row}>
          <Button variant="secondary" onClick={onEnterCustomMode} disabled={isLoading}>
            Задать свой вопрос
          </Button>
        </div>
      )}

      {/* Поле ответа — только в обычном режиме */}
      {!isCustomMode && (
        <>
          <label className={styles.label} htmlFor="msg">
            Ваш ответ
          </label>
          <textarea
            id="msg"
            className={styles.textarea}
            value={userAnswer}
            onChange={(e) => onAnswerChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ваш ответ… (Ctrl/Cmd+Enter — отправить)"
            disabled={isLoading}
            maxLength={8000}
          />

          <div className={styles.row}>
            <Button onClick={onSend} disabled={isLoading || !isQuestionReady || !userAnswer.trim()} loading={isLoading}>
              Отправить
            </Button>
            <span className={styles.status} aria-live="polite">
              {statusText}
            </span>
          </div>
        </>
      )}

      <div className={`${styles.output} ${isAnswerEmpty ? styles.empty : ""} ${error ? styles.error : ""}`} role="status">
        {error ? (
          <Markdown content={`Ошибка: ${error}`} />
        ) : answer ? (
          <Markdown content={answer} />
        ) : (
          "Ответ ассистента появится здесь."
        )}
      </div>

      <div className={styles.row}>
        <Button
          className={`${styles.saveBtn} ${saveStatus ? styles.visible : ""}`}
          variant={suggestSave ? "success" : "secondary"}
          onClick={onSave}
          disabled={isLoading || !answer}
        >
          {suggestSave ? "💾 Сохранить в Word" : "💾 Сохранить"}
        </Button>
        {onReset && !isCustomMode && (
          <Button variant="success" onClick={onReset} disabled={isLoading}>
            Следующий вопрос
          </Button>
        )}
      </div>

      {saveStatus && (
        <div
          className={`${styles.saveStatus} ${styles.visible} ${
            saveStatus.startsWith("❌") ? styles.error : ""
          }`}
          role="status"
        >
          {saveStatus}
        </div>
      )}
    </div>
  );
};

export default ChatPresentation;
