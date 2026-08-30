import React from "react";
import { Button, Markdown } from "@/components/ui";
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
  onAnswerChange,
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
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← На главную
        </Button>
        <h1 className={styles.title}>Интервью</h1>
        {statsButton}
      </header>

      <p className={styles.subtitle} style={{ color: "var(--muted)", marginBottom: "1rem" }}>
        Вверху — текущий вопрос. Ниже — поле для вашего ответа и результаты проверки.
      </p>

      <div className={styles.questionCard}>
        <div className={styles.questionBadge}>Вопрос №{questionNumber}</div>
        <div className={styles.questionText}>
          {questionText ? (
            <Markdown content={questionText} />
          ) : isLoading ? (
            "Загружаем вопрос…"
          ) : error ? (
            `Не удалось загрузить вопрос: ${error}`
          ) : (
            "Вопрос пока не загружен. Нажмите «Следующий вопрос» или обновите страницу."
          )}
        </div>
      </div>

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
      />

      <div className={styles.row}>
        <Button onClick={onSend} disabled={isLoading || !isQuestionReady || !userAnswer.trim()} loading={isLoading}>
          Отправить
        </Button>
        <span className={styles.status}>{statusText}</span>
      </div>

      <div className={`${styles.output} ${isAnswerEmpty ? styles.empty : ""} ${error ? styles.error : ""}`}>
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
          variant="success"
          onClick={onSave}
          disabled={isLoading || !answer}
        >
          💾 Сохранить в Word
        </Button>
        {onReset && (
          <Button variant="success" onClick={onReset} disabled={isLoading}>
            Следующий вопрос
          </Button>
        )}
      </div>

      {saveStatus && (
        <div className={`${styles.saveStatus} ${saveStatus.startsWith("❌") ? styles.error : ""}`}>{saveStatus}</div>
      )}
    </div>
  );
};

export default ChatPresentation;
