import { useState, useCallback } from "react";
import { chatApi } from "@/services/api";
import type { ChatState } from "./types";

const SESSION_KEY = "chat_session_id";

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function useChat() {
  const [state, setState] = useState<ChatState>({
    messages: [],
    input: "",
    isLoading: false,
    error: null,
    sessionId: getSessionId(),
  });

  const setInput = useCallback((input: string) => {
    setState((prev) => ({ ...prev, input }));
  }, []);

  const sendMessage = useCallback(async () => {
    const message = state.input.trim();
    if (!message || state.isLoading) return;

    setState((prev) => ({
      ...prev,
      input: "",
      isLoading: true,
      error: null,
      messages: [...prev.messages, { role: "user", content: message }],
    }));

    try {
      const response = await chatApi.send(message, state.sessionId);
      setState((prev) => ({
        ...prev,
        isLoading: false,
        messages: [
          ...prev.messages,
          { role: "user", content: message },
          { role: "assistant", content: response.answer },
        ],
      }));
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : "Ошибка отправки сообщения",
      }));
    }
  }, [state.input, state.isLoading, state.sessionId]);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    setInput,
    sendMessage,
    clearError,
  };
}
