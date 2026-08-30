import React, { useState } from "react";
import { Button } from "@/components/ui";
import { useUser } from "@/components/state/UserContext";
import styles from "./WelcomeModal.module.css";

interface WelcomeModalProps {
  onSuccess?: () => void;
}

export const WelcomeModal: React.FC<WelcomeModalProps> = ({ onSuccess }) => {
  const { setUsername, username } = useUser();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (username) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) {
      setError("Введите имя");
      return;
    }
    if (trimmed.length > 128) {
      setError("Имя слишком длинное (макс. 128 символов)");
      return;
    }
    setError(null);
    setUsername(trimmed);
    onSuccess?.();
  };

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true">
      <div className={styles.modal}>
        <h1 className={styles.title}>🐍 Python Interview Assistant</h1>
        <p className={styles.subtitle}>
          Личный помощник для подготовки к собеседованиям по Python.
        </p>
        <p className={styles.description}>
          Чтобы мы могли сохранять вашу статистику ответов между сессиями — представьтесь.
          Это нужно для того, чтобы вы могли вернуться и посмотреть, над какими темами стоит
          поработать ещё.
        </p>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label htmlFor="username-input" className={styles.label}>
            Ваше имя
          </label>
          <input
            id="username-input"
            type="text"
            className={styles.input}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Например, Алексей"
            autoFocus
            maxLength={128}
          />
          {error && <p className={styles.error}>{error}</p>}
          <Button type="submit" variant="success" className={styles.submit}>
            Начать
          </Button>
        </form>
        <p className={styles.hint}>
          Имя используется только как ключ для группировки ваших ответов. Без пароля и регистрации.
        </p>
      </div>
    </div>
  );
};

export default WelcomeModal;
