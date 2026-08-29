import React from 'react';
import {
  QuizSetupPresentation,
  QuizQuestionPresentation,
  QuizAnswerPresentation,
  QuizResultsPresentation,
} from './presentation';
import { useQuiz } from './useQuiz';

export const QuizContainer: React.FC = () => {
  const quiz = useQuiz();

  switch (quiz.view) {
    case 'setup':
      return (
        <QuizSetupPresentation
          level={quiz.level}
          onLevelChange={quiz.setLevel}
          onStart={quiz.startQuiz}
          isLoading={quiz.isLoading}
        />
      );
    case 'question':
      return quiz.currentQuestion ? (
        <QuizQuestionPresentation
          question={quiz.currentQuestion}
          selectedOption={quiz.selectedOption}
          onSelectOption={quiz.selectOption}
          onSubmit={quiz.submitAnswer}
          onBack={quiz.goBack}
          isLoading={quiz.isLoading}
        />
      ) : null;
    case 'answer':
      return quiz.currentQuestion && quiz.lastAnswer ? (
        <QuizAnswerPresentation
          question={quiz.currentQuestion}
          selectedOption={quiz.selectedOption}
          answer={quiz.lastAnswer}
          onNext={quiz.nextQuestion}
          onBack={quiz.goBack}
        />
      ) : null;
    case 'results':
      return quiz.results ? (
        <QuizResultsPresentation
          results={quiz.results}
          onRestart={quiz.restart}
          onBack={quiz.goBack}
        />
      ) : null;
    default:
      return null;
  }
};

export default QuizContainer;
