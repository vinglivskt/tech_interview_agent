import React from "react";
import { DesignSetupView, DesignQuestionView, DesignAnswerView, DesignResultsView } from "./presentation";
import { useDesign } from "./useDesign";

export const DesignContainer: React.FC = () => {
  const design = useDesign();

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
          onBack={design.goBack}
          isLoading={design.isLoading}
          error={design.error}
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
          onBack={design.goBack}
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
          onBack={design.goBack}
        />
      ) : null;
    case "results":
      return design.results ? (
        <DesignResultsView results={design.results} onRestart={design.restart} onBack={design.goBack} />
      ) : null;
    default:
      return null;
  }
};

export default DesignContainer;
