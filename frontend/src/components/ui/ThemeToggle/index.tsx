import React, { useContext } from "react";
import { ThemeContext } from "@/components/state/ThemeContext";
import styles from "./ThemeToggle.module.css";

const SunIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </svg>
);

const MoonIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

export const ThemeToggle: React.FC = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) return null;
  const { theme, toggleTheme } = ctx;
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={toggleTheme}
      aria-pressed={isDark}
      aria-label="Переключить тему"
      title={isDark ? "Включить светлую тему" : "Включить тёмную тему"}
    >
      <span className={styles.track}>
        <span className={styles.sunIcon} aria-hidden="true">
          <SunIcon />
        </span>
        <span className={styles.moonIcon} aria-hidden="true">
          <MoonIcon />
        </span>
        <span className={styles.knob} aria-hidden="true" />
      </span>
    </button>
  );
};

export default ThemeToggle;