import React, { FormEvent, useState } from "react";
import { FeatureHeader } from "@/components/features/_shared/FeatureHeader";
import { Button } from "@/components/ui";
import { IconCheck, IconWarn, IconError } from "@/components/ui/icons";
import { designApi } from "@/services/api";
import styles from "./design-scenario-entry.module.css";

interface Props {
  onBack: () => void;
}

const listFromText = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);

export const DesignScenarioEntryContainer: React.FC<Props> = ({ onBack }) => {
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [level, setLevel] = useState<"junior" | "middle" | "senior">("middle");
  const [category, setCategory] = useState("basics");
  const [requirements, setRequirements] = useState("");
  const [nfr, setNfr] = useState("");
  const [constraints, setConstraints] = useState("");
  const [criteria, setCriteria] = useState("");
  const [topics, setTopics] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [statusKind, setStatusKind] = useState<"success" | "warn" | "error" | null>(null);

  const saveScenario = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim() || !summary.trim() || isSaving) return;

    setIsSaving(true);
    setStatus("");
    setStatusKind(null);
    try {
      const result = await designApi.saveScenario({
        title: title.trim(), summary: summary.trim(), level, category: category.trim() || "basics",
        requirements: listFromText(requirements), nfr: listFromText(nfr), constraints: listFromText(constraints),
        acceptance_criteria: listFromText(criteria), topics: listFromText(topics),
      });
      if (result.status === "saved") {
        setStatus("Сценарий сохранён в библиотеку и доступен в режиме системного дизайна");
        setStatusKind("success");
        setTitle(""); setSummary(""); setRequirements(""); setNfr(""); setConstraints(""); setCriteria(""); setTopics("");
      } else {
        setStatus("Сценарий с таким названием уже есть в библиотеке");
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
      <FeatureHeader onBack={onBack} title="Новый сценарий дизайна" backLabel="К пополнению базы" />
      <p className={styles.intro}>Сценарий будет добавлен в YAML-библиотеку и сразу появится среди задач системного дизайна.</p>
      <form className={styles.form} onSubmit={saveScenario}>
        <label htmlFor="scenario-title">Название системы</label>
        <input id="scenario-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например: Сервис бронирования переговорных" maxLength={200} disabled={isSaving} required />
        <label htmlFor="scenario-summary">Описание задачи</label>
        <textarea id="scenario-summary" value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="Что должна делать система, для кого и в каких условиях?" maxLength={4000} disabled={isSaving} required />
        <div className={styles.twoColumns}>
          <div><label htmlFor="scenario-level">Уровень</label><select id="scenario-level" value={level} onChange={(event) => setLevel(event.target.value as typeof level)} disabled={isSaving}><option value="junior">Junior</option><option value="middle">Middle</option><option value="senior">Senior</option></select></div>
          <div><label htmlFor="scenario-category">Категория</label><input id="scenario-category" value={category} onChange={(event) => setCategory(event.target.value)} placeholder="basics, queues, db…" maxLength={64} disabled={isSaving} /></div>
        </div>
        <label htmlFor="scenario-requirements">Функциональные требования <small>По одному на строку</small></label>
        <textarea id="scenario-requirements" value={requirements} onChange={(event) => setRequirements(event.target.value)} placeholder="Создание бронирования\nОтмена бронирования" disabled={isSaving} />
        <label htmlFor="scenario-nfr">Нефункциональные требования <small>По одному на строку</small></label>
        <textarea id="scenario-nfr" value={nfr} onChange={(event) => setNfr(event.target.value)} placeholder="p99 не более 200 мс\nВысокая доступность" disabled={isSaving} />
        <label htmlFor="scenario-constraints">Ограничения <small>По одному на строку</small></label>
        <textarea id="scenario-constraints" value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="Нельзя допускать двойное бронирование" disabled={isSaving} />
        <label htmlFor="scenario-criteria">Критерии хорошего решения <small>По одному на строку</small></label>
        <textarea id="scenario-criteria" value={criteria} onChange={(event) => setCriteria(event.target.value)} placeholder="Идемпотентность операции\nТранзакционная защита от гонок" disabled={isSaving} />
        <label htmlFor="scenario-topics">Темы <small>По одной на строку</small></label>
        <textarea id="scenario-topics" value={topics} onChange={(event) => setTopics(event.target.value)} placeholder="api\ndb\nconsistency" disabled={isSaving} />
        <div className={styles.actions}><Button type="submit" variant="success" loading={isSaving} disabled={!title.trim() || !summary.trim()}>Сохранить сценарий</Button>{status && <p className={`${styles.status} ${statusKind ? styles[statusKind] : ""}`} role="status">{statusKind === "success" && <IconCheck size={16} className={styles.statusIcon} />}{statusKind === "warn" && <IconWarn size={16} className={styles.statusIcon} />}{statusKind === "error" && <IconError size={16} className={styles.statusIcon} />}{status}</p>}</div>
      </form>
    </main>
  );
};

export default DesignScenarioEntryContainer;
