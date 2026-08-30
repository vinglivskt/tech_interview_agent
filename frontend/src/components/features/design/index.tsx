import React, { useState } from "react";
import { DesignSetupView, DesignQuestionView, DesignAnswerView, DesignResultsView } from "./presentation";
import { useDesign } from "./useDesign";
import { StatsButton } from "@/components/features/_shared/StatsButton";
import { StatsView } from "@/components/features/_shared/StatsView";

interface Props {
  onBack?: () => void;
}

export const DesignContainer: React.FC<Props> = ({ onBack }) => {
  const design = useDesign();
  const [showStats, setShowStats] = useState(false);

  if (showStats) {
    return <StatsView mode="design" onBack={() => setShowStats(false)} title="Системный дизайн" />;
  }

  const handleBack = onBack ?? design.goBack;
  const statsButton = <StatsButton onClick={() => setShowStats(true)} />;

  switch (design.view) {
    case "setup":
      return (
        <DesignSetupView
          config={design.config}
          level={design.level}
          selectedScenarioId={design.selectedScenarioId}
          onLevelChange={design.setLevel}
          onScenarioSelect={design.selectScenario}
          onStart={design.startDesign}
          onBack={handleBack}
          isLoading={design.isLoading}
          error={design.error}
          onShowStats={statsButton}
        />
      );
    case "question":
      return design.step && design.scenario ? (
        <DesignQuestionView
          scenario={design.scenario}
          step={design.step}
          stepIndex={design.stepIndex}
          totalSteps={design.totalSteps}
          userAnswer={design.userAnswer}
          hint={design.hint}
          isLoading={design.isLoading}
          onAnswerChange={design.setUserAnswer}
          onSubmit={design.submitAnswer}
          onGetHint={design.getHint}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    case "answer":
      return design.step && design.scenario && design.lastAnswer ? (
        <DesignAnswerView
          scenario={design.scenario}
          step={design.step}
          stepIndex={design.stepIndex}
          userAnswer={design.userAnswer}
          answer={design.lastAnswer}
          onNext={design.nextStep}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    case "results":
      return design.results ? (
        <DesignResultsView
          results={design.results}
          onRestart={design.restart}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    default:
      return null;
  }
};

export default DesignContainer;
