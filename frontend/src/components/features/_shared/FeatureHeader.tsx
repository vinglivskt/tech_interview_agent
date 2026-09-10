import React from "react";
import { Button, ThemeToggle } from "@/components/ui";
import styles from "./FeatureHeader.module.css";

interface Props {
  onBack: () => void;
  title?: string;
  /** Доп. элементы в центре (например, "Вопрос 3 из 20"). */
  center?: React.ReactNode;
  /** Слот справа (например, <StatsButton />). */
  right?: React.ReactNode;
}

export const FeatureHeader: React.FC<Props> = ({ onBack, title, center, right }) => {
  return (
    <header className={styles.header}>
      <Button variant="secondary" onClick={onBack}>
        ← На главную
      </Button>
      <div className={styles.middle}>
        {title && <h1 className={styles.title}>{title}</h1>}
        {center && <div className={styles.center}>{center}</div>}
      </div>
      <div className={styles.right}>
        <ThemeToggle />
        {right}
      </div>
    </header>
  );
};

export default FeatureHeader;