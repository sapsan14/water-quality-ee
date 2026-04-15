"use client";

import { useEffect, useState } from "react";
import Dashboard from "./Dashboard";
import { loadSnapshot } from "../lib/snapshot-client";
import type { FrontendSnapshot } from "../lib/types";

/**
 * Client-side loader for the frontend snapshot. Kept as a thin wrapper so
 * Dashboard itself stays synchronous (it already dereferences `snapshot.*`
 * in ~50 places). The perf win comes from moving the JSON out of the RSC
 * payload — not from refactoring Dashboard.
 */
export default function DashboardLoader() {
  const [snapshot, setSnapshot] = useState<FrontendSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    loadSnapshot()
      .then((data) => {
        if (alive) setSnapshot(data);
      })
      .catch((err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <div className="panel" role="alert" aria-live="assertive">
        <h2 className="title" style={{ fontSize: "1.2rem" }}>
          Failed to load water quality data
        </h2>
        <p className="hint">{error}</p>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setError(null);
            loadSnapshot()
              .then((d) => setSnapshot(d))
              .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!snapshot) {
    // Matches the shape of app/loading.tsx so the transition feels seamless.
    return (
      <div className="panel" aria-busy="true" aria-live="polite">
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
    );
  }

  return <Dashboard snapshot={snapshot} />;
}
