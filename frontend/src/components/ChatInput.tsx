"use client";

import { forwardRef, memo, useCallback, useImperativeHandle, useRef, type KeyboardEvent } from "react";
import { useChatStore } from "@/store/useChatStore";
import { MicIcon, SendIcon } from "./Icons";

interface ChatInputProps {
  onSend: () => void;
  disabled?: boolean;
}

const PLACEHOLDERS: Record<string, string> = {
  en: "Describe your health concern...",
  lg: "Tegeeza ensonga y'obulamu bwo...",
  nyn: "Turebereze obuhaise bw'amagara gawe...",
  sw: "Eleza wasiwasi wako wa afya...",
};

export default memo(forwardRef<HTMLTextAreaElement, ChatInputProps>(function ChatInput({ onSend, disabled }, ref) {
  const message = useChatStore((s) => s.message);
  const setMessage = useChatStore((s) => s.setMessage);
  const locale = useChatStore((s) => s.locale);
  const speechState = useChatStore((s) => s.speechState);
  const setVoiceModalOpen = useChatStore((s) => s.setVoiceModalOpen);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => textareaRef.current!, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (message.trim() && !disabled) onSend();
      }
    },
    [message, disabled, onSend]
  );

  const openVoiceModal = useCallback(() => {
    setVoiceModalOpen(true);
  }, [setVoiceModalOpen]);

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setMessage(e.target.value.slice(0, 2000));
      const el = e.target;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    },
    [setMessage]
  );

  return (
    <div className="composer">
      <button
        className={`composer-btn mic-btn ${speechState === "listening" ? "listening" : ""}`}
        onClick={openVoiceModal}
        aria-label="Open voice input"
        type="button"
      >
        <MicIcon width={20} height={20} />
      </button>

      <textarea
        ref={textareaRef}
        className="composer-input"
        value={message}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder={PLACEHOLDERS[locale] || PLACEHOLDERS.en}
        rows={1}
        maxLength={2000}
        disabled={disabled}
        aria-label="Health question input"
      />

      <button
        className="composer-btn send-btn"
        onClick={onSend}
        disabled={!message.trim() || disabled}
        aria-label="Send message"
        type="button"
      >
        <SendIcon width={20} height={20} />
      </button>
    </div>
  );
}));
