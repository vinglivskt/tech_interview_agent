import React from 'react';
import {
  SobesSetupPresentation,
  SobesQuestionPresentation,
  SobesAnswerPresentation,
  SobesResultsPresentation,
} from './presentation';
import { useSobes } from './useSobes';

export const SobesContainer: React.FC = () => {
  const sobes = useSobes();

  switch (sobes.view) {
    case 'setup':
      return (
        <SobesSetupPresentation
          config={sobes.config}
          level={sobes.level}
          selectedTopics={sobes.selectedTopics}
          onLevelChange={sobes.setLevel}
          onTopicToggle={sobes.toggleTopic}
          onStart={sobes.startSobes}
          onBack={sobes.goBack}
          isLoading={sobes.isLoading}
          error={sobes.error}
        />
      );
    case 'question':
      return sobes.currentQuestion ? (
        <SobesQuestionPresentation
          question={sobes.currentQuestion}
          userAnswer={sobes.userAnswer}
          onAnswerChange={sobes.setUserAnswer}
          onSubmit={sobes.submitAnswer}
          onSkip={sobes.skipQuestion}
          onRepeat={sobes.repeatQuestion}
          onBack={sobes.goBack}
          isLoading={sobes.isLoading}
          questionNumber={sobes.currentQuestion.number}
          totalPlanned={10}
        />
      ) : null;
    case 'answer':
      return sobes.currentQuestion && sobes.lastAnswer ? (
        <SobesAnswerPresentation
          question={sobes.currentQuestion}
          userAnswer={sobes.userAnswer}
          answer={sobes.lastAnswer}
          onNext={sobes.nextQuestion}
          onBack={sobes.goBack}
        />
      ) : null;
    case 'results':
      return sobes.results ? (
        <SobesResultsPresentation
          results={sobes.results}
          onRestart={sobes.restart}
          onBack={sobes.goBack}
        />
      ) : null;
    default:
      return null;
  }
};

export default SobesContainer;
