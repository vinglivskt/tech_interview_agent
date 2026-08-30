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
  onAnswerChange: (value: string) => void;
  onSend: () => void;
  onSave: () => void;
  onBack: () => void;
  onReset?: () => void;
  statsButton?: ReactNode;
}

export interface ChatContainerProps {
  onBack: () => void;
}
