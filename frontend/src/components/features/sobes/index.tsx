import React from "react";
import { SobesSetupView, SobesQuestionView, SobesAnswerView, SobesResultsView } from "./presentation";
import { useSobes } from "./useSobes";

export const SobesContainer: React.FC = () => {
  const sobes = useSobes();

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
          onBack={sobes.goBack}
          isLoading={sobes.isLoading}
          error={sobes.error}
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
          onBack={sobes.goBack}
        />
      ) : null;
    case "answer":
      return sobes.question && sobes.lastAnswer ? (
        <SobesAnswerView
          question={sobes.question}
          userAnswer={sobes.userAnswer}
          answer={sobes.lastAnswer}
          onNext={sobes.nextQuestion}
          onBack={sobes.goBack}
        />
      ) : null;
    case "results":
      return sobes.results ? (
        <SobesResultsView results={sobes.results} onRestart={sobes.restart} onBack={sobes.goBack} />
      ) : null;
    default:
      return null;
  }
};

export default SobesContainer;
