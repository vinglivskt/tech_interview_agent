import React from 'react';
import { Button, Markdown, Spinner } from '@/components/ui';
import type { ChatViewProps } from './types';
import styles from './chat.module.scss';

export const ChatPresentation: React.FC<ChatViewProps> = ({
  messages,
  input,
  isLoading,
  error,
  onInputChange,
  onSend,
  onBack,
}) => {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
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
        <h1 className={styles.title}>Чат с ассистентом</h1>
      </header>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.empty}>
            <p>Задайте вопрос по Python или подготовке к собеседованию</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`${styles.message} ${styles[msg.role]}`}>
            <div className={styles.messageContent}>
              <Markdown content={msg.content} />
            </div>
          </div>
        ))}
        {isLoading && (
          <div className={`${styles.message} ${styles.assistant}`}>
            <div className={styles.messageContent}>
              <Spinner />
              <span className={styles.loadingText}>Думаю...</span>
            </div>
          </div>
        )}
        {error && (
          <div className={styles.error}>
            <span>{error}</span>
          </div>
        )}
      </div>

      <div className={styles.inputArea}>
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Введите ваш вопрос..."
          rows={3}
          disabled={isLoading}
        />
        <Button onClick={onSend} loading={isLoading} disabled={!input.trim()}>
          Отправить
        </Button>
      </div>
    </div>
  );
};

export default ChatPresentation;
