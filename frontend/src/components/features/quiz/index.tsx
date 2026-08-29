import React from "react";
import { QuizSetupView, QuizQuestionView, QuizResultsView } from "./presentation";
import { useQuiz } from "./useQuiz";

export const QuizContainer: React.FC = () => {
  const quiz = useQuiz();

  switch (quiz.view) {
    case "setup":
      return (
        <QuizSetupView
          level={quiz.level}
          onLevelChange={quiz.setLevel}
          onStart={quiz.startQuiz}
          isLoading={quiz.isLoading}
        />
      );
    case "question":
      return quiz.question ? (
        <QuizQuestionView
          question={quiz.question}
          selectedOption={quiz.selectedOption}
          onSelectOption={quiz.selectOption}
          onSubmit={quiz.submitAnswer}
          onBack={quiz.goBack}
          isLoading={quiz.isLoading}
        />
      ) : null;
    case "results":
      return quiz.results ? (
        <QuizResultsView results={quiz.results} onRestart={quiz.restart} onBack={quiz.goBack} />
      ) : null;
    default:
      return null;
  }
};

export default QuizContainer;
