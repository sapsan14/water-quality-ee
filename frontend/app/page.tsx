import type { Metadata } from "next";
import DashboardLoader from "./components/DashboardLoader";
import DataGapNotice from "./components/DataGapNotice";
import WebVitalsReporter from "./components/WebVitalsReporter";
import { buildOgImageUrl, buildPlacePageUrl, loadOgIndex } from "./lib/og-index";

// Edge runtime is required for `@cloudflare/next-on-pages` to render this
// route per-request — without it `searchParams` is treated as static and
// per-place social previews never differentiate.
export const runtime = "edge";

type SearchParams = Record<string, string | string[] | undefined>;

function pickPlaceId(searchParams: SearchParams): string | null {
  const raw = searchParams.place;
  if (!raw) return null;
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (!v || v.length === 0 || v.length > 200) return null;
  return v;
}

const STATUS_LABEL: Record<string, string> = {
  compliant: "вода соответствует норме",
  violation: "найдено нарушение",
  unknown: "статус неизвестен",
};

const RISK_LABEL: Record<string, string> = {
  low: "низкий риск",
  medium: "средний риск",
  high: "высокий риск",
  unknown: "риск неизвестен",
};

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}): Promise<Metadata> {
  const sp = await searchParams;
  const placeId = pickPlaceId(sp);
  if (!placeId) {
    // Root URL — let layout.tsx defaults handle title/description, but
    // pin a default og:image so previews never show empty card.
    return {
      openGraph: {
        images: [{ url: buildOgImageUrl(null), width: 1200, height: 630 }],
      },
      twitter: {
        card: "summary_large_image",
        images: [buildOgImageUrl(null)],
      },
    };
  }

  const index = await loadOgIndex();
  const entry = index.places[placeId];
  const canonical = buildPlacePageUrl(placeId);
  const ogImage = buildOgImageUrl(placeId);

  if (!entry) {
    // We know the place id but not its name yet (snapshot newer than
    // og-index). Still emit per-place URL + dynamic image — title falls
    // back to generic.
    return {
      title: `H2O Atlas — место #${placeId}`,
      alternates: { canonical },
      openGraph: {
        url: canonical,
        images: [{ url: ogImage, width: 1200, height: 630 }],
      },
      twitter: {
        card: "summary_large_image",
        images: [ogImage],
      },
    };
  }

  const where = entry.county ? `${entry.name} (${entry.county})` : entry.name;
  const status = STATUS_LABEL[entry.status] ?? STATUS_LABEL.unknown;
  const risk = RISK_LABEL[entry.risk_level] ?? RISK_LABEL.unknown;
  const description = `${where}: ${status}, ${risk}. Открытые данные Terviseamet и оценка риска ML — H2O Atlas.`;

  return {
    title: `${where} — H2O Atlas`,
    description,
    alternates: { canonical },
    openGraph: {
      title: `${where} — H2O Atlas`,
      description,
      url: canonical,
      images: [{ url: ogImage, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${where} — H2O Atlas`,
      description,
      images: [ogImage],
    },
  };
}

// The ~7 MB snapshot is now fetched client-side (see DashboardLoader +
// lib/snapshot-client). Keeping page.tsx as a lean server component means
// the RSC payload stays tiny, the snapshot file is cacheable at the CDN
// edge, and hydration starts seconds earlier on mobile networks.
export default function HomePage() {
  const currentYear = new Date().getFullYear();
  return (
    <main className="page">
      <WebVitalsReporter />
      <DataGapNotice />
      <DashboardLoader />
      <footer className="footerNote">
        <p>
          &copy; {currentYear} H2O Atlas &middot;{" "}
          <a href="https://github.com/sapsan14/water-quality-ee" target="_blank" rel="noreferrer">GitHub</a>
          {" "}&middot; TalTech Masin&otilde;pe 2026
        </p>
        <p className="footerSub">
          Data: <a href="https://vtiav.sm.ee" target="_blank" rel="noreferrer">Terviseamet</a> open data &middot; ML decision support, not medical advice
        </p>
      </footer>
    </main>
  );
}
