import React, { FormEvent, useState } from "react";
import { FeatureHeader } from "@/components/features/_shared/FeatureHeader";
import { Button } from "@/components/ui";
import { IconCheck, IconWarn, IconError } from "@/components/ui/icons";
import { chatApi } from "@/services/api";
import styles from "./question-entry.module.css";

interface Props {
  onBack: () => void;
}

type StatusKind = "success" | "warn" | "error" | null;

export const QuestionEntryContainer: React.FC<Props> = ({ onBack }) => {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [statusKind, setStatusKind] = useState<StatusKind>(null);

  const saveQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!question.trim() || !answer.trim() || isSaving) return;

    setIsSaving(true);
    setStatus("");
    setStatusKind(null);
    try {
      const result = await chatApi.saveQA(question.trim(), answer.trim());
      if (result.status === "saved") {
        setStatus(`Вопрос сохранён в Word под №${result.number}`);
        setStatusKind("success");
        setQuestion("");
        setAnswer("");
      } else {
        setStatus("Такой вопрос уже есть в базе");
        setStatusKind("warn");
      }
    } catch (error) {
      setStatus(`Не удалось сохранить: ${error instanceof Error ? error.message : "неизвестная ошибка"}`);
      setStatusKind("error");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main className={styles.container}>
      <FeatureHeader onBack={onBack} title="Внесение вопросов" backLabel="К пополнению базы" />
      <div className={styles.intro}>
        <p>
          Добавьте новый вопрос и готовый ответ. Если вопрос уже есть в файле, новая запись не будет создана.
        </p>
      </div>

      <form className={styles.form} onSubmit={saveQuestion}>
        <label htmlFor="new-question">Название вопроса</label>
        <textarea
          id="new-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Например: Как работает GIL в Python?"
          maxLength={8000}
          disabled={isSaving}
          required
        />

        <label htmlFor="new-answer">Ответ на вопрос</label>
        <textarea
          id="new-answer"
          className={styles.answer}
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          placeholder="Введите полный, проверенный ответ…"
          maxLength={30000}
          disabled={isSaving}
          required
        />

        <div className={styles.actions}>
          <Button type="submit" variant="success" loading={isSaving} disabled={!question.trim() || !answer.trim()}>
            Сохранить в Word
          </Button>
          {status && (
            <p className={`${styles.status} ${statusKind ? styles[statusKind] : ""}`} role="status">
              {statusKind === "success" && <IconCheck size={16} className={styles.statusIcon} />}
              {statusKind === "warn" && <IconWarn size={16} className={styles.statusIcon} />}
              {statusKind === "error" && <IconError size={16} className={styles.statusIcon} />}
              {status}
            </p>
          )}
        </div>
      </form>
    </main>
  );
};

export default QuestionEntryContainer;