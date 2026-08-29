import React, { useState } from "react";
import { Card } from "@/components/ui";
import { ChatContainer, QuizContainer, SobesContainer, DesignContainer } from "@/components/features";
import type { AppMode } from "@/types";
import styles from "./App.module.css";

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

export const App: React.FC = () => {
  const [mode, setMode] = useState<AppMode>("home");

  const handleBack = () => setMode("home");

  if (mode === "chat") {
    return <ChatContainer onBack={handleBack} />;
  }

  if (mode === "quiz") {
    return <QuizContainer />;
  }

  if (mode === "sobes") {
    return <SobesContainer />;
  }

  if (mode === "design") {
    return <DesignContainer />;
  }

  // Home view
  return (
    <div className={styles.app}>
      <div className={styles.home}>
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>Python Interview Assistant</h1>
          <p className={styles.heroSubtitle}>Выберите режим работы</p>
        </div>

        <div className={styles.modeGrid}>
          {MODES.map((modeItem) => (
            <Card key={modeItem.id} hoverable onClick={() => setMode(modeItem.id)} className={styles.modeCard}>
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

export default App;
