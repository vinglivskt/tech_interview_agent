import type { ChatMessage } from "@/types";
export type { ChatMessage };

export interface ChatState {
  messages: ChatMessage[];
  input: string;
  isLoading: boolean;
  error: string | null;
  sessionId: string;
}

export interface ChatViewProps {
  messages: ChatMessage[];
  input: string;
  isLoading: boolean;
  error: string | null;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onBack: () => void;
}

export interface ChatContainerProps {
  onBack: () => void;
}
