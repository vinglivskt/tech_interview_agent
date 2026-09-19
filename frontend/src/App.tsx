import React, { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import {
  IconChat,
  IconQuiz,
  IconSobes,
  IconArch,
  IconStats,
  IconArrowRight,
} from "@/components/ui/icons";
import { AppShell } from "@/components/layout/AppShell";
import { WelcomeModal } from "@/components/ui/WelcomeModal";
import { UserProvider, useUser } from "@/components/state/UserContext";
import { setApiUsername } from "@/services/api";
import {
  ChatContainer,
  QuizContainer,
  SobesContainer,
  DesignContainer,
  QuestionEntryContainer,
  DesignScenarioEntryContainer,
  LibraryView,
} from "@/components/features";
import { StatsView } from "@/components/features/_shared/StatsView";
import type { AppMode } from "@/types";
import styles from "./App.module.css";

type View = AppMode | "home" | "stats-overview" | "library" | "question-entry" | "design-scenario-entry";

const MODES: {
  id: AppMode;
  title: string;
  description: string;
  icon: React.FC<{ size?: number; className?: string }>;
  eyebrow: string;
}[] = [
  {
    id: "chat",
    title: "Интервью",
    description: "Свободный диалог с ассистентом. Задавайте вопросы, получайте ответы с ссылками на базу знаний.",
    icon: IconChat, eyebrow: "Практика с RAG",
  },
  {
    id: "quiz",
    title: "Тестирование",
    description: "20 вопросов с вариантами ответов. Проверьте свои знания и узнайте свой уровень.",
    icon: IconQuiz, eyebrow: "20 вопросов",
  },
  {
    id: "sobes",
    title: "Собеседование",
    description: "15–25 вопросов по темам, свободные ответы, оценка в процентах и финальный вердикт.",
    icon: IconSobes, eyebrow: "Открытые ответы",
  },
  {
    id: "design",
    title: "Системный дизайн",
    description: "Проектируйте систему пошагово и получите оценку по архитектурной рубрике.",
    icon: IconArch, eyebrow: "Архитектурное мышление",
  },
];

const Inner: React.FC = () => {
  const [view, setView] = useState<View>("home");
  const { username, isInitialized } = useUser();

  useEffect(() => {
    setApiUsername(username);
  }, [username]);

  if (!isInitialized) {
    return null;
  }

  const handleBack = () => setView("home");
  const handleLibraryBack = () => setView("library");
  let content: React.ReactNode;
  if (view === "chat") content = <ChatContainer onBack={handleBack} />;
  else if (view === "quiz") content = <QuizContainer onBack={handleBack} />;
  else if (view === "sobes") content = <SobesContainer onBack={handleBack} />;
  else if (view === "design") content = <DesignContainer onBack={handleBack} />;
  else if (view === "question-entry") content = <QuestionEntryContainer onBack={handleLibraryBack} />;
  else if (view === "design-scenario-entry") content = <DesignScenarioEntryContainer onBack={handleLibraryBack} />;
  else if (view === "library") content = (
    <LibraryView onBack={handleBack} onSelect={(target) => setView(target)} />
  );
  else if (view === "stats-overview") content = <StatsView mode="overall" onBack={handleBack} />;
  else content = (
    <section className={styles.home} aria-labelledby="home-title">
      <header className={styles.homeHeader}>
        <div className={styles.hero}>
          <p className={styles.kicker}>{username ? `Добро пожаловать, ${username}` : "Личный workspace для подготовки"}</p>
          <h1 id="home-title" className={styles.heroTitle}>Подготовка к техническому интервью</h1>
          <p className={styles.heroSubtitle}>Четыре формата тренировки — статистика и слабые места сохраняются автоматически.</p>
        </div>
        <div className={styles.homeActions}>
          <button type="button" onClick={() => setView("stats-overview")} className={styles.statsCta}>
            <IconStats size={16} /> Открыть общую статистику
          </button>
        </div>
      </header>

        <div className={styles.modeGrid}>
          {MODES.map((modeItem) => (
            <Card key={modeItem.id} hoverable onClick={() => setView(modeItem.id)} className={styles.modeCard}>
              <span className={styles.modeIcon} aria-hidden="true">{<modeItem.icon size={19} />}</span>
              <span className={styles.modeEyebrow}>{modeItem.eyebrow}</span>
              <h3 className={styles.modeTitle}>{modeItem.title}</h3>
              <p className={styles.modeDescription}>{modeItem.description}</p>
              <span className={styles.modeCta}>Открыть режим <IconArrowRight size={14} className={styles.modeCtaIcon} /></span>
            </Card>
          ))}
        </div>
    </section>
  );

  const shellView =
    view === "question-entry" || view === "design-scenario-entry" ? "library" : view;
  return <AppShell activeView={shellView} onNavigate={setView}>{content}</AppShell>;
};

export const App: React.FC = () => {
  return (
    <UserProvider>
      <WelcomeModal />
      <Inner />
    </UserProvider>
  );
};

export default App;
