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
  const setSpeechState = useChatStore((s) => s.setSpeechState);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Forward ref so parent can focus the input
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

  const toggleVoice = useCallback(() => {
    if (!("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
      setSpeechState("unavailable");
      return;
    }

    if (speechState === "listening") {
      setSpeechState("idle");
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    const langMap: Record<string, string> = {
      en: "en-UG",
      lg: "lg-UG",
      nyn: "nyn-UG",
      sw: "sw-KE",
    };
    recognition.lang = langMap[locale] || "en-UG";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setMessage(message ? `${message} ${transcript}` : transcript);
      setSpeechState("idle");
    };

    recognition.onerror = () => setSpeechState("error");
    recognition.onend = () => setSpeechState("idle");

    setSpeechState("listening");
    recognition.start();
  }, [speechState, locale, message, setMessage, setSpeechState]);

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setMessage(e.target.value.slice(0, 2000));
      // Auto-resize
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
        onClick={toggleVoice}
        aria-label={speechState === "listening" ? "Stop listening" : "Start voice input"}
        aria-pressed={speechState === "listening"}
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
