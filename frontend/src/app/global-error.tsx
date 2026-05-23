"use client";

import { t } from "@/lib/i18n";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Global error renders outside React tree; cannot use hooks. Default to English.
  const locale = "en";

  return (
    <html lang="en">
      <body
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100dvh",
          background: "#0F0F0F",
          color: "#F0F0F0",
          padding: "2rem",
          textAlign: "center",
          fontFamily: "system-ui, -apple-system, sans-serif",
          margin: 0,
        }}
      >
        <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>
          {t("error_boundary_title", locale)}
        </h2>
        <p style={{ opacity: 0.7, marginBottom: "1.5rem", maxWidth: "400px" }}>
          {t("error_boundary_message", locale)}
        </p>
        <button
          onClick={reset}
          style={{
            padding: "0.75rem 2rem",
            borderRadius: "0.75rem",
            border: "none",
            background: "#22C55E",
            color: "white",
            cursor: "pointer",
            fontSize: "1rem",
          }}
        >
          {t("error_boundary_retry", locale)}
        </button>
      </body>
    </html>
  );
}
