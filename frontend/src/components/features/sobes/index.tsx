import React, { useState } from "react";
import { SobesSetupView, SobesQuestionView, SobesAnswerView, SobesResultsView } from "./presentation";
import { useSobes } from "./useSobes";
import { StatsButton } from "@/components/features/_shared/StatsButton";
import { StatsView } from "@/components/features/_shared/StatsView";

interface Props {
  onBack?: () => void;
}

export const SobesContainer: React.FC<Props> = ({ onBack }) => {
  const sobes = useSobes();
  const [showStats, setShowStats] = useState(false);

  if (showStats) {
    return <StatsView mode="sobes" onBack={() => setShowStats(false)} title="Собеседование" />;
  }

  const handleBack = onBack ?? sobes.goBack;
  const statsButton = <StatsButton onClick={() => setShowStats(true)} />;

  switch (sobes.view) {
    case "setup":
      return (
        <SobesSetupView
          config={sobes.config}
          level={sobes.level}
          selectedTopics={sobes.selectedTopics}
          onLevelChange={sobes.setLevel}
          onTopicToggle={sobes.toggleTopic}
          onStart={sobes.startSobes}
          onBack={handleBack}
          isLoading={sobes.isLoading}
          error={sobes.error}
          onShowStats={statsButton}
        />
      );
    case "question":
      return sobes.question ? (
        <SobesQuestionView
          question={sobes.question}
          questionIndex={sobes.questionIndex}
          totalPlanned={sobes.totalPlanned}
          userAnswer={sobes.userAnswer}
          isLoading={sobes.isLoading}
          onAnswerChange={sobes.setUserAnswer}
          onSubmit={sobes.submitAnswer}
          onSkip={sobes.skipQuestion}
          onRepeat={sobes.repeatQuestion}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    case "answer":
      return sobes.question && sobes.lastAnswer ? (
        <SobesAnswerView
          question={sobes.question}
          userAnswer={sobes.userAnswer}
          answer={sobes.lastAnswer}
          onNext={sobes.nextQuestion}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    case "results":
      return sobes.results ? (
        <SobesResultsView
          results={sobes.results}
          onRestart={sobes.restart}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    default:
      return null;
  }
};

export default SobesContainer;
