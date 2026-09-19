import React from "react";
import { Card } from "@/components/ui";
import { FeatureHeader } from "@/components/features/_shared/FeatureHeader";
import { IconQuestion, IconScenario, IconArrowRight } from "@/components/ui/icons";
import type { LibraryTarget } from "@/types";
import styles from "./library.module.css";

interface Props {
  onBack: () => void;
  onSelect: (target: LibraryTarget) => void;
}

const OPTIONS: Array<{
  id: LibraryTarget;
  icon: React.FC<{ size?: number; className?: string }>;
  eyebrow: string;
  title: string;
  description: string;
}> = [
  {
    id: "question-entry",
    icon: IconQuestion,
    eyebrow: "База вопросов",
    title: "Внесение вопросов",
    description: "Добавить вопрос и ответ в файл интервью",
  },
  {
    id: "design-scenario-entry",
    icon: IconScenario,
    eyebrow: "Библиотека сценариев",
    title: "Сценарий системного дизайна",
    description: "Добавить новую задачу в YAML-библиотеку сценариев",
  },
];

export const LibraryView: React.FC<Props> = ({ onBack, onSelect }) => (
  <main className={styles.container}>
    <FeatureHeader onBack={onBack} title="Пополнение базы" />
    <p className={styles.intro}>
      Добавляйте материалы в базу знаний. Здесь появятся и следующие режимы пополнения.
    </p>
    <div className={styles.grid}>
      {OPTIONS.map((item) => (
        <Card key={item.id} hoverable onClick={() => onSelect(item.id)} className={styles.panel}>
          <span className={styles.icon} aria-hidden="true">{<item.icon size={19} />}</span>
          <span className={styles.eyebrow}>{item.eyebrow}</span>
          <h3 className={styles.title}>{item.title}</h3>
          <p className={styles.description}>{item.description}</p>
          <span className={styles.cta}>
            Открыть <IconArrowRight size={14} className={styles.ctaIcon} />
          </span>
        </Card>
      ))}
    </div>
  </main>
);

export default LibraryView;