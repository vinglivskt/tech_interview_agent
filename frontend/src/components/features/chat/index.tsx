import React, { useState } from "react";
import { ChatPresentation } from "./presentation";
import { useChat } from "./useChat";
import { StatsButton } from "@/components/features/_shared/StatsButton";
import { StatsView } from "@/components/features/_shared/StatsView";

interface Props {
  onBack?: () => void;
}

export const ChatContainer: React.FC<Props> = ({ onBack }) => {
  const chat = useChat();
  const [showStats, setShowStats] = useState(false);

  if (showStats) {
    return <StatsView mode="chat" onBack={() => setShowStats(false)} title="Интервью" />;
  }

  const handleBack = onBack ?? (() => {});
  const statsButton = <StatsButton onClick={() => setShowStats(true)} />;

  return (
    <>
      <ChatPresentation
        questionNumber={chat.questionNumber}
        questionText={chat.questionText}
        isQuestionReady={Boolean(chat.questionText)}
        answer={chat.answer}
        isAnswerEmpty={chat.isAnswerEmpty}
        userAnswer={chat.userAnswer}
        statusText={chat.statusText}
        saveStatus={chat.saveStatus}
        isLoading={chat.isLoading}
        error={chat.error}
        customQuestion={chat.customQuestion}
        isCustomMode={chat.isCustomMode}
        onAnswerChange={chat.setUserAnswer}
        onCustomQuestionChange={chat.setCustomQuestion}
        onEnterCustomMode={chat.enterCustomMode}
        onCancelCustomMode={chat.cancelCustomMode}
        onSubmitCustomQuestion={chat.submitCustomQuestion}
        onSend={chat.sendAnswer}
        onSave={chat.saveToWord}
        onBack={handleBack}
        onReset={chat.resetConversation}
        statsButton={statsButton}
      />
    </>
  );
};

export default ChatContainer;
