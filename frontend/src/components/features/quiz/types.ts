import type { QuizQuestion, QuizAnswerResponse, QuizResultsResponse } from '@/types';

export type QuizView = 'setup' | 'question' | 'answer' | 'results';

export interface QuizState {
  view: QuizView;
  level: 'junior' | 'middle' | 'senior';
  sessionId: string | null;
  currentQuestion: QuizQuestion | null;
  selectedOption: number | null;
  lastAnswer: QuizAnswerResponse | null;
  results: QuizResultsResponse | null;
  isLoading: boolean;
  error: string | null;
}

export interface QuizSetupViewProps {
  level: 'junior' | 'middle' | 'senior';
  onLevelChange: (level: 'junior' | 'middle' | 'senior') => void;
  onStart: () => void;
  isLoading: boolean;
}

export interface QuizQuestionViewProps {
  question: QuizQuestion;
  selectedOption: number | null;
  onSelectOption: (index: number) => void;
  onSubmit: () => void;
  onBack: () => void;
  isLoading: boolean;
}

export interface QuizAnswerViewProps {
  question: QuizQuestion;
  selectedOption: number | null;
  answer: QuizAnswerResponse;
  onNext: () => void;
  onBack: () => void;
}

export interface QuizResultsViewProps {
  results: QuizResultsResponse;
  onRestart: () => void;
  onBack: () => void;
}
