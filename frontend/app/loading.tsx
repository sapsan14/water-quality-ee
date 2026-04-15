export default function Loading() {
  return (
    <main className="page">
      {/* Desktop-only: on mobile `.desktopOnly` is display:none via
          `@media (max-width: 900px)`, so users only see the blank page
          background during the route-segment Suspense fallback instead
          of a desktop-styled "Loading water quality dashboard..." panel
          flashing before the mobile shell hydrates. */}
      <div className="panel desktopOnly" aria-busy="true" aria-live="polite">
        <h2 className="title" style={{ fontSize: "1.2rem" }}>
          Loading water quality dashboard...
        </h2>
        <p className="hint">Fetching precomputed snapshot and preparing map layers.</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.7rem", marginTop: "1rem" }}>
          <div className="stat">
            <div className="k">Visible</div>
            <div className="v">...</div>
          </div>
          <div className="stat">
            <div className="k">High risk</div>
            <div className="v">...</div>
          </div>
          <div className="stat">
            <div className="k">Low risk</div>
            <div className="v">...</div>
          </div>
        </div>
      </div>
    </main>
  );
}
