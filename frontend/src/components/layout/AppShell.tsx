import React from "react";
import { ThemeToggle } from "@/components/ui";
import { IconHome, IconChat, IconQuiz, IconSobes, IconArch, IconProgress, IconTerminal, IconPlus } from "@/components/ui/icons";
import { useUser } from "@/components/state/UserContext";
import styles from "./AppShell.module.css";

type ShellView = "home" | "chat" | "quiz" | "sobes" | "design" | "stats-overview" | "library";

interface AppShellProps {
  activeView: ShellView;
  onNavigate: (view: ShellView) => void;
  children: React.ReactNode;
}

const NAVIGATION: Array<{
  id: Exclude<ShellView, "stats-overview">;
  label: string;
  icon: React.FC<{ size?: number; className?: string }>;
}> = [
  { id: "home", label: "Обзор", icon: IconHome },
  { id: "chat", label: "Диалог", icon: IconChat },
  { id: "quiz", label: "Квиз", icon: IconQuiz },
  { id: "sobes", label: "Устный опрос", icon: IconSobes },
  { id: "design", label: "Архитектура", icon: IconArch },
];

const MOBILE_EXTRA: Array<{ id: ShellView; label: string; icon: React.FC<{ size?: number; className?: string }> }> = [
  { id: "library", label: "База", icon: IconPlus },
];

export const AppShell: React.FC<AppShellProps> = ({ activeView, onNavigate, children }) => {
  const { username } = useUser();

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Основная навигация">
        <button type="button" className={styles.brand} onClick={() => onNavigate("home")} aria-label="На главную">
          <span className={styles.brandMark} aria-hidden="true"><IconTerminal size={15} /></span>
          <span>Interview Lab</span>
        </button>

        <nav className={styles.navList} aria-label="Режимы подготовки">
          {NAVIGATION.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`${styles.navItem} ${activeView === item.id ? styles.active : ""}`}
              onClick={() => onNavigate(item.id)}
              aria-current={activeView === item.id ? "page" : undefined}
            >
              <span className={styles.navIcon} aria-hidden="true">{<item.icon size={18} />}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <button
            type="button"
            className={`${styles.statsLink} ${activeView === "library" ? styles.active : ""}`}
            onClick={() => onNavigate("library")}
            aria-current={activeView === "library" ? "page" : undefined}
          >
            <span className={styles.navIcon} aria-hidden="true"><IconPlus size={18} /></span> Пополнение базы
          </button>
          <button
            type="button"
            className={`${styles.statsLink} ${activeView === "stats-overview" ? styles.active : ""}`}
            onClick={() => onNavigate("stats-overview")}
            aria-current={activeView === "stats-overview" ? "page" : undefined}
          >
            <span className={styles.navIcon} aria-hidden="true"><IconProgress size={18} /></span> Мой прогресс
          </button>
          <div className={styles.profileRow}>
            <span className={styles.avatar} aria-hidden="true">{username?.slice(0, 1).toUpperCase() || "?"}</span>
            <span className={styles.profileName}>{username || "Гость"}</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      <main className={styles.main}>{children}</main>

      <nav className={styles.mobileNav} aria-label="Быстрая навигация">
        {NAVIGATION.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`${styles.mobileItem} ${activeView === item.id ? styles.active : ""}`}
            onClick={() => onNavigate(item.id)}
            aria-current={activeView === item.id ? "page" : undefined}
          >
            <span aria-hidden="true">{<item.icon size={19} />}</span>
            <span>{item.label}</span>
          </button>
        ))}
        {MOBILE_EXTRA.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`${styles.mobileItem} ${activeView === item.id ? styles.active : ""}`}
            onClick={() => onNavigate(item.id)}
            aria-current={activeView === item.id ? "page" : undefined}
          >
            <span aria-hidden="true">{<item.icon size={19} />}</span>
            <span>{item.label}</span>
          </button>
        ))}
        <span className={styles.mobileTheme}>
          <ThemeToggle />
        </span>
      </nav>
    </div>
  );
};
