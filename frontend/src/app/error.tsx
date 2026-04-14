"use client";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100dvh",
        background: "var(--bg-dark, #1a0f0a)",
        color: "var(--text-1, #f5e6d3)",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>
        Something went wrong
      </h2>
      <p style={{ opacity: 0.7, marginBottom: "1.5rem", maxWidth: "400px" }}>
        Musawo AI encountered an error. You can try again, or call the health
        hotline: <strong>0800 100 263</strong> for immediate help.
      </p>
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
        Try Again
      </button>
    </div>
  );
}
