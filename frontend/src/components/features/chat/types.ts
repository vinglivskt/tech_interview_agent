import type { ReactNode } from "react";

export interface ChatViewProps {
  questionNumber: string;
  questionText: string;
  isQuestionReady: boolean;
  answer: string;
  isAnswerEmpty: boolean;
  userAnswer: string;
  statusText: string;
  saveStatus: string;
  isLoading: boolean;
  error: string | null;
  customQuestion: string;
  isCustomMode: boolean;
  onAnswerChange: (value: string) => void;
  onCustomQuestionChange: (value: string) => void;
  onEnterCustomMode: () => void;
  onCancelCustomMode: () => void;
  onSubmitCustomQuestion: () => void;
  onSend: () => void;
  onSave: () => void;
  onBack: () => void;
  onReset?: () => void;
  statsButton?: ReactNode;
}

export interface ChatContainerProps {
  onBack: () => void;
}
