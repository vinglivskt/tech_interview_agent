import React, { useState } from "react";
import { QuizSetupView, QuizQuestionView, QuizResultsView } from "./presentation";
import { useQuiz } from "./useQuiz";
import { StatsButton } from "@/components/features/_shared/StatsButton";
import { StatsView } from "@/components/features/_shared/StatsView";

interface Props {
  onBack?: () => void;
}

export const QuizContainer: React.FC<Props> = ({ onBack }) => {
  const quiz = useQuiz();
  const [showStats, setShowStats] = useState(false);

  if (showStats) {
    return <StatsView mode="quiz" onBack={() => setShowStats(false)} title="Тестирование" />;
  }

  const handleBack = onBack ?? quiz.goBack;

  const statsButton = <StatsButton onClick={() => setShowStats(true)} />;

  switch (quiz.view) {
    case "setup":
      return (
        <QuizSetupView
          level={quiz.level}
          onLevelChange={quiz.setLevel}
          onStart={quiz.startQuiz}
          isLoading={quiz.isLoading}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      );
    case "question":
      return quiz.question ? (
        <QuizQuestionView
          question={quiz.question}
          selectedOption={quiz.selectedOption}
          onSelectOption={quiz.selectOption}
          onSubmit={quiz.submitAnswer}
          onBack={handleBack}
          onShowStats={statsButton}
          isLoading={quiz.isLoading}
        />
      ) : null;
    case "results":
      return quiz.results ? (
        <QuizResultsView
          results={quiz.results}
          onRestart={quiz.restart}
          onBack={handleBack}
          onShowStats={statsButton}
        />
      ) : null;
    default:
      return null;
  }
};

export default QuizContainer;
