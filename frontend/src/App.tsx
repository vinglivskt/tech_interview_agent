import React, { useState } from "react";
import { Card } from "@/components/ui";
import { ChatContainer, QuizContainer, SobesContainer, DesignContainer } from "@/components/features";
import type { AppMode } from "@/types";
import styles from "./App.module.scss";

const MODES: { id: AppMode; title: string; description: string; icon: string }[] = [
  {
    id: "chat",
    title: "Чат с ассистентом",
    description: "Задавайте вопросы по Python и получайте развёрнутые ответы",
    icon: "💬",
  },
  {
    id: "quiz",
    title: "Квиз",
    description: "Проверьте свои знания в интерактивном тестировании",
    icon: "📝",
  },
  {
    id: "sobes",
    title: "Собеседование",
    description: "Практикуйте ответы на вопросы с оценкой покрытия тем",
    icon: "🎯",
  },
  {
    id: "design",
    title: "Проектирование",
    description: "Разрабатывайте архитектуру систем шаг за шагом",
    icon: "🏗️",
  },
];

const HomePresentation: React.FC<{ onSelect: (mode: AppMode) => void }> = ({ onSelect }) => (
  <div className={styles.home}>
    <div className={styles.hero}>
      <h1 className={styles.heroTitle}>Tech Interview Agent</h1>
      <p className={styles.heroSubtitle}>Подготовка к техническим собеседованиям с использованием AI</p>
    </div>

    <div className={styles.modeGrid}>
      {MODES.map((mode) => (
        <Card key={mode.id} hoverable onClick={() => onSelect(mode.id)} className={styles.modeCard}>
          <span className={styles.modeIcon}>{mode.icon}</span>
          <h3 className={styles.modeTitle}>{mode.title}</h3>
          <p className={styles.modeDescription}>{mode.description}</p>
        </Card>
      ))}
    </div>

    <div className={styles.features}>
      <h2 className={styles.featuresTitle}>Возможности</h2>
      <div className={styles.featuresGrid}>
        <div className={styles.feature}>
          <h3>📚 RAG-поиск</h3>
          <p>Ответы на основе базы знаний</p>
        </div>
        <div className={styles.feature}>
          <h3>🎓 Ollama</h3>
          <p>Локальные LLM модели</p>
        </div>
        <div className={styles.feature}>
          <h3>📊 Qdrant</h3>
          <p>Векторная база данных</p>
        </div>
      </div>
    </div>
  </div>
);

export const App: React.FC = () => {
  const [mode, setMode] = useState<AppMode>("home");

  const handleBack = () => setMode("home");

  return (
    <div className={styles.app}>
      {mode === "home" && <HomePresentation onSelect={setMode} />}
      {mode === "chat" && <ChatContainer onBack={handleBack} />}
      {mode === "quiz" && <QuizContainer />}
      {mode === "sobes" && <SobesContainer />}
      {mode === "design" && <DesignContainer />}
    </div>
  );
};

export default App;
