import React from "react";
import { ChatPresentation } from "./presentation";
import { useChat } from "./useChat";

export const ChatContainer: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const chat = useChat();

  return (
    <ChatPresentation
      questionNumber={chat.questionNumber}
      questionText={chat.questionText}
      answer={chat.answer}
      isAnswerEmpty={chat.isAnswerEmpty}
      userAnswer={chat.userAnswer}
      statusText={chat.statusText}
      saveStatus={chat.saveStatus}
      isLoading={chat.isLoading}
      error={chat.error}
      onAnswerChange={chat.setUserAnswer}
      onSend={chat.sendAnswer}
      onSave={chat.saveToWord}
      onBack={onBack}
    />
  );
};

export default ChatContainer;
