import React from 'react';
import { ChatPresentation } from './presentation';
import { useChat } from './useChat';
import type { ChatContainerProps } from './types';

export const ChatContainer: React.FC<ChatContainerProps> = ({ onBack }) => {
  const chatState = useChat();

  return (
    <ChatPresentation
      messages={chatState.messages}
      input={chatState.input}
      isLoading={chatState.isLoading}
      error={chatState.error}
      onInputChange={chatState.setInput}
      onSend={chatState.sendMessage}
      onBack={onBack}
    />
  );
};

export default ChatContainer;
