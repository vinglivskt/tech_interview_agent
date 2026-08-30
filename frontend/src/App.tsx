import React, { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { WelcomeModal } from "@/components/ui/WelcomeModal";
import { UserProvider, useUser } from "@/components/state/UserContext";
import { setApiUsername } from "@/services/api";
import { ChatContainer, QuizContainer, SobesContainer, DesignContainer } from "@/components/features";
import { StatsView } from "@/components/features/_shared/StatsView";
import type { AppMode } from "@/types";
import styles from "./App.module.css";

type View = AppMode | "home" | "stats-overview";

const MODES: { id: AppMode; title: string; description: string; icon: string }[] = [
  {
    id: "chat",
    title: "Интервью",
    description: "Свободный диалог с ассистентом. Задавайте вопросы, получайте ответы с ссылками на базу знаний.",
    icon: "💬",
  },
  {
    id: "quiz",
    title: "Тестирование",
    description: "20 вопросов с вариантами ответов. Проверьте свои знания и узнайте свой уровень.",
    icon: "📝",
  },
  {
    id: "sobes",
    title: "Собеседование",
    description: "15–25 вопросов по темам, свободные ответы, оценка в процентах и финальный вердикт.",
    icon: "🎯",
  },
  {
    id: "design",
    title: "Системный дизайн",
    description: "Проектируйте систему пошагово и получите оценку по архитектурной рубрике.",
    icon: "🏗️",
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
  if (view === "chat") return <ChatContainer onBack={handleBack} />;
  if (view === "quiz") return <QuizContainer onBack={handleBack} />;
  if (view === "sobes") return <SobesContainer onBack={handleBack} />;
  if (view === "design") return <DesignContainer onBack={handleBack} />;

  if (view === "stats-overview") {
    return <StatsView mode="overall" onBack={handleBack} />;
  }

  return (
    <div className={styles.app}>
      <div className={styles.home}>
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>Python Interview Assistant</h1>
          <p className={styles.heroSubtitle}>Выберите режим работы</p>
          {username && (
            <p className={styles.heroHint}>
              Привет, <strong>{username}</strong>! ·{" "}
              <button type="button" onClick={() => setView("stats-overview")} className={styles.linkButton}>
                Открыть общую статистику
              </button>
            </p>
          )}
        </div>

        <div className={styles.modeGrid}>
          {MODES.map((modeItem) => (
            <Card key={modeItem.id} hoverable onClick={() => setView(modeItem.id)} className={styles.modeCard}>
              <span className={styles.modeIcon}>{modeItem.icon}</span>
              <h3 className={styles.modeTitle}>{modeItem.title}</h3>
              <p className={styles.modeDescription}>{modeItem.description}</p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
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
