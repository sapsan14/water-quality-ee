/**
 * h2oatlas-og — Cloudflare Worker that renders 1200×630 Open Graph PNGs
 * for h2oatlas.ee per-place share previews.
 *
 * Routes:
 *   GET /og?place=<id>   → PNG (cached 1h on edge, 24h in browser)
 *   GET /og              → default brand card
 *   GET / or /health     → text/plain health check
 *
 * Why a separate Worker (not a Next route)?
 * The Cloudflare Pages bundle has a hard 1 MB compressed limit. WASM
 * rasterizers (resvg, satori) push us over it, so we keep image generation
 * in its own Worker that's deployed independently and cached aggressively.
 */
import { ImageResponse } from "workers-og";

interface Env {
  OG_INDEX_URL: string;
}

type OgEntry = {
  name: string;
  county: string | null;
  risk_level: "low" | "medium" | "high" | "unknown";
  status: "compliant" | "violation" | "unknown";
};

type OgIndex = { places?: Record<string, OgEntry> };

const RISK_PILL: Record<OgEntry["risk_level"], { fg: string; bg: string; label: string }> = {
  low: { fg: "#0b3f81", bg: "#bbf7d0", label: "Low risk" },
  medium: { fg: "#7c2d12", bg: "#fde68a", label: "Medium risk" },
  high: { fg: "#7f1d1d", bg: "#fecaca", label: "High risk" },
  unknown: { fg: "#1f2937", bg: "#e5e7eb", label: "Risk: unknown" },
};

const STATUS_LABEL: Record<OgEntry["status"], string> = {
  compliant: "Compliant",
  violation: "Violation",
  unknown: "Status n/a",
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pickShort(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max - 1).trimEnd() + "…";
}

async function loadEntry(env: Env, id: string): Promise<OgEntry | null> {
  // Cache the og-index JSON for 1h to avoid hammering the static asset on
  // every miss — the index is updated weekly when the snapshot rebuilds.
  const cache = caches.default;
  const cacheKey = new Request(`${env.OG_INDEX_URL}#worker-cache`);
  let cached = await cache.match(cacheKey);
  if (!cached) {
    const fresh = await fetch(env.OG_INDEX_URL, {
      cf: { cacheTtl: 3600, cacheEverything: true },
    });
    if (!fresh.ok) return null;
    cached = new Response(await fresh.arrayBuffer(), {
      headers: {
        "content-type": "application/json",
        "cache-control": "public, max-age=3600",
      },
    });
    await cache.put(cacheKey, cached.clone());
  }
  const data = (await cached.json()) as OgIndex;
  return data.places?.[id] ?? null;
}

const COMMON_BG = "linear-gradient(135deg, #0f6efd 0%, #17b0ff 100%)";

// satori-html (used by workers-og) is strict: whitespace between sibling
// tags becomes a text node, which trips Satori's "display:flex required for
// >1 children" check. Keep HTML on a single line to avoid stray text nodes.

function defaultCardHtml(): string {
  return (
    `<div style="width:1200px;height:630px;display:flex;flex-direction:column;background:${COMMON_BG};color:white;font-family:'Inter',sans-serif;padding:60px 80px;">` +
      `<div style="display:flex;flex-direction:column;justify-content:center;flex:1;">` +
        `<div style="display:flex;font-size:96px;font-weight:800;letter-spacing:-2px;">H2O Atlas</div>` +
        `<div style="display:flex;font-size:40px;margin-top:8px;color:#dff4ff;">Water Quality Map of Estonia</div>` +
        `<div style="display:flex;font-size:24px;margin-top:16px;color:#bbe6ff;">Terviseamet open data · ML risk assessment</div>` +
      `</div>` +
      `<div style="display:flex;justify-content:flex-end;font-size:28px;opacity:0.85;">h2oatlas.ee</div>` +
    `</div>`
  );
}

function placeCardHtml(entry: OgEntry): string {
  const pill = RISK_PILL[entry.risk_level] ?? RISK_PILL.unknown;
  const statusLabel = STATUS_LABEL[entry.status] ?? STATUS_LABEL.unknown;
  const name = escapeHtml(pickShort(entry.name || "—", 60));
  const county = entry.county ? escapeHtml(pickShort(entry.county, 40)) : "";

  const countyLine = county
    ? `<div style="display:flex;font-size:36px;margin-top:18px;color:#dff4ff;">${county}</div>`
    : "";

  return (
    `<div style="width:1200px;height:630px;display:flex;flex-direction:column;background:${COMMON_BG};color:white;font-family:'Inter',sans-serif;padding:56px 72px;">` +
      `<div style="display:flex;align-items:center;justify-content:space-between;">` +
        `<div style="display:flex;align-items:center;">` +
          `<div style="display:flex;width:60px;height:60px;border-radius:14px;background:white;align-items:center;justify-content:center;color:#0f6efd;font-size:30px;font-weight:800;margin-right:16px;">H₂O</div>` +
          `<div style="display:flex;font-size:36px;font-weight:700;letter-spacing:-1px;">H2O Atlas</div>` +
        `</div>` +
        `<div style="display:flex;align-items:center;background:${pill.bg};color:${pill.fg};padding:10px 22px;border-radius:999px;font-size:26px;font-weight:700;">${pill.label}</div>` +
      `</div>` +
      `<div style="display:flex;flex-direction:column;justify-content:center;flex:1;margin-top:40px;">` +
        `<div style="display:flex;font-size:76px;font-weight:800;line-height:1.05;letter-spacing:-2px;">${name}</div>` +
        countyLine +
        `<div style="display:flex;font-size:28px;margin-top:24px;color:#bbe6ff;">Latest sample: ${statusLabel}</div>` +
      `</div>` +
      `<div style="display:flex;justify-content:space-between;align-items:center;font-size:24px;opacity:0.85;">` +
        `<div style="display:flex;">Terviseamet open data · ML risk assessment</div>` +
        `<div style="display:flex;font-weight:700;">h2oatlas.ee</div>` +
      `</div>` +
    `</div>`
  );
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("h2oatlas-og worker ok", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    if (url.pathname !== "/og") {
      return new Response("not found", { status: 404 });
    }

    const placeId = url.searchParams.get("place");
    let html: string;
    if (!placeId) {
      html = defaultCardHtml();
    } else {
      const entry = await loadEntry(env, placeId);
      html = entry ? placeCardHtml(entry) : defaultCardHtml();
    }

    return new ImageResponse(html, {
      width: 1200,
      height: 630,
      // Cache aggressively: per-place card depends only on snapshot version
      // (callers append `&v=<sha>`), so once rendered we can serve forever.
      headers: {
        "cache-control": "public, max-age=86400, s-maxage=86400, immutable",
      },
    });
  },
};
