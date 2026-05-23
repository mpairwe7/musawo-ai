"use client";

import { t } from "@/lib/i18n";
import { useChatStore } from "@/store/useChatStore";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Error boundaries may render before store hydrates; default to "en"
  let locale = "en";
  try {
    locale = useChatStore.getState().locale || "en";
  } catch {
    // store not available
  }

  const handleRetryLastMessage = () => {
    try {
      const state = useChatStore.getState();
      // Chat messages are in state.chat (the active session's messages)
      if (state.chat?.length) {
        const lastUserMsg = [...state.chat]
          .reverse()
          .find((m: { role: string }) => m.role === "user");
        if (lastUserMsg) {
          reset();
          return;
        }
      }
    } catch {
      // If store is unavailable, just reset normally
    }
    reset();
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100dvh",
        background: "var(--bg-dark, #0F0F0F)",
        color: "var(--text-1, #F0F0F0)",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>
        {t("error_boundary_title", locale)}
      </h2>
      <p style={{ opacity: 0.7, marginBottom: "1.5rem", maxWidth: "400px" }}>
        {t("error_boundary_message", locale)}
      </p>
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", justifyContent: "center" }}>
        <button
          onClick={reset}
          style={{
            padding: "0.75rem 2rem",
            borderRadius: "0.75rem",
            border: "none",
            background: "var(--accent-green, #2E7D32)",
            color: "white",
            cursor: "pointer",
            fontSize: "1rem",
          }}
        >
          {t("error_boundary_retry", locale)}
        </button>
        <button
          onClick={handleRetryLastMessage}
          style={{
            padding: "0.75rem 2rem",
            borderRadius: "0.75rem",
            border: "1px solid var(--glass-border, rgba(255,255,255,0.1))",
            background: "transparent",
            color: "var(--text-2, #ccc)",
            cursor: "pointer",
            fontSize: "0.9rem",
          }}
        >
          Retry last message
        </button>
      </div>
    </div>
  );
}
