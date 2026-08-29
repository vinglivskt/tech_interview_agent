import React from 'react';
import {
  DesignSetupPresentation,
  DesignQuestionPresentation,
  DesignAnswerPresentation,
  DesignResultsPresentation,
} from './presentation';
import { useDesign } from './useDesign';

export const DesignContainer: React.FC = () => {
  const design = useDesign();

  switch (design.view) {
    case 'setup':
      return (
        <DesignSetupPresentation
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
    case 'question':
      return design.currentStep && design.scenario ? (
        <DesignQuestionPresentation
          scenario={design.scenario}
          step={design.currentStep}
          stepIndex={design.stepIndex}
          totalSteps={design.totalSteps}
          userAnswer={design.userAnswer}
          hint={design.hint}
          onAnswerChange={design.setUserAnswer}
          onSubmit={design.submitAnswer}
          onGetHint={design.getHint}
          onBack={design.goBack}
          isLoading={design.isLoading}
        />
      ) : null;
    case 'answer':
      return design.currentStep && design.scenario && design.lastAnswer ? (
        <DesignAnswerPresentation
          scenario={design.scenario}
          step={design.currentStep}
          stepIndex={design.stepIndex}
          totalSteps={design.totalSteps}
          userAnswer={design.userAnswer}
          answer={design.lastAnswer}
          onNext={design.nextStep}
          onBack={design.goBack}
        />
      ) : null;
    case 'results':
      return design.results ? (
        <DesignResultsPresentation
          results={design.results}
          onRestart={design.restart}
          onBack={design.goBack}
        />
      ) : null;
    default:
      return null;
  }
};

export default DesignContainer;
