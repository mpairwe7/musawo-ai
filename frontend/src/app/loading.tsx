export default function Loading() {
  return (
    <div className="app" style={{ minHeight: "100dvh" }}>
      {/* Skeleton header */}
      <div className="header" style={{ opacity: 0.6 }}>
        <div className="header-left">
          <div className="skeleton" style={{ width: 28, height: 28, borderRadius: "50%" }} />
          <div>
            <div className="skeleton skeleton-line" style={{ width: 100, height: 16 }} />
            <div className="skeleton skeleton-line" style={{ width: 160, height: 10, marginTop: 4 }} />
          </div>
        </div>
      </div>

      {/* Skeleton mode selector */}
      <div className="mode-selector" style={{ opacity: 0.5 }}>
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton skeleton-card" style={{ height: 64 }} />
        ))}
      </div>

      {/* Skeleton empty state */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "1rem", paddingBottom: "4rem" }}>
        <div className="skeleton" style={{ width: 80, height: 80, borderRadius: "50%" }} />
        <div className="skeleton skeleton-line" style={{ width: 180, height: 20 }} />
        <div className="skeleton skeleton-line" style={{ width: 280, height: 14 }} />
        <div className="skeleton skeleton-line" style={{ width: 240, height: 14 }} />
      </div>
    </div>
  );
}
