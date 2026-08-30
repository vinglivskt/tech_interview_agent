import React from "react";
import { Button } from "@/components/ui";
import styles from "./FeatureHeader.module.css";

interface Props {
  onBack: () => void;
  title?: string;
  /** Доп. элементы в центре (например, "Вопрос 3 из 20"). */
  center?: React.ReactNode;
  /** Слот справа (например, <StatsButton />). */
  right?: React.ReactNode;
}

/**
 * Единый хедер для всех фич: кнопка "← На главную" слева,
 * опциональный заголовок/прогресс в центре, слот для доп. кнопок справа.
 *
 * Заменяет копипасту <header className={styles.header}>...</header>
 * в quiz/sobes/design/chat. Локальные CSS-переменные хедера (.header, .title,
 * .progress) помечены как deprecated — мигрируйте на FeatureHeader.
 */
export const FeatureHeader: React.FC<Props> = ({ onBack, title, center, right }) => {
  return (
    <header className={styles.header}>
      <Button variant="secondary" onClick={onBack}>
        ← На главную
      </Button>
      {title && <h1 className={styles.title}>{title}</h1>}
      {center && <div className={styles.center}>{center}</div>}
      {right && <div className={styles.right}>{right}</div>}
    </header>
  );
};

export default FeatureHeader;
