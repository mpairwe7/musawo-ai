export default function Loading() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100dvh",
        background: "var(--bg-dark)",
        color: "var(--text-1)",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <p style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>Musawo AI</p>
        <p style={{ opacity: 0.6 }}>Loading health navigator...</p>
      </div>
    </div>
  );
}
