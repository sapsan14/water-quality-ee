import type { MetadataRoute } from "next";

// We deliberately read og-index.json (~hundreds of KB) rather than the full
// 7 MB snapshot — keeps build memory low and the sitemap fits well under
// Google's 50 MB / 50 000-URL limit. Only the top-N most interesting places
// are exposed: the goal is high-quality discovery for journalists / search
// users, not exhaustive crawling of every measurement site.

const SITE = "https://h2oatlas.ee";
const FETCH_BASE = process.env.OG_INDEX_FETCH_BASE || SITE;
const TOP_N = 200;
const RISK_RANK: Record<string, number> = { high: 0, medium: 1, unknown: 2, low: 3 };

type OgEntry = { name: string; county: string | null; risk_level: string; status: string };

async function loadIndex(): Promise<Record<string, OgEntry>> {
  try {
    const version = process.env.NEXT_PUBLIC_SNAPSHOT_VERSION || "dev";
    const res = await fetch(`${FETCH_BASE}/data/og-index.json?v=${version}`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return {};
    const json = (await res.json()) as { places?: Record<string, OgEntry> };
    return json.places ?? {};
  } catch {
    return {};
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const root: MetadataRoute.Sitemap = [
    { url: `${SITE}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
  ];

  const index = await loadIndex();
  const ranked = Object.entries(index)
    .sort(([, a], [, b]) => (RISK_RANK[a.risk_level] ?? 9) - (RISK_RANK[b.risk_level] ?? 9))
    .slice(0, TOP_N);

  const places: MetadataRoute.Sitemap = ranked.map(([id]) => ({
    url: `${SITE}/?place=${encodeURIComponent(id)}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  return [...root, ...places];
}
