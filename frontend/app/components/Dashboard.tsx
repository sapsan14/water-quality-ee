"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import LocalizedSubtitle from "./LocalizedSubtitle";
import { track } from "../lib/analytics";
import type { FrontendPlace, FrontendSnapshot } from "../lib/types";
import { pointInFeature, findCountyFeature } from "../lib/geo";

const MapClient = dynamic(() => import("./MapClient"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        width: "100%",
        height: "100%",
        /* Esri World Topo base tile color — matches the initial map
           appearance so there is no white flash before tiles load. */
        background: "#e8e0d8",
      }}
      aria-hidden="true"
    />
  ),
});

type Props = { snapshot: FrontendSnapshot };
type IconName =
  | "pin"
  | "unpin"
  | "close"
  | "alert"
  | "reset"
  | "filter-x"
  | "filters"
  | "locate"
  | "info"
  | "calendar"
  | "sun"
  | "moon"
  | "swim"
  | "pool"
  | "tap"
  | "drop"
  | "check-circle"
  | "x-circle"
  | "dash-circle"
  | "star"
  | "star-outline"
  | "signal"
  | "grid"
  | "globe"
  | "chevron-down";
type CyrillicFont = "ibm" | "manrope";
type ThemeMode = "light" | "dark";

const riskOrder: FrontendPlace["risk_level"][] = ["all", "low", "medium", "high", "unknown"] as never;
const officialOrder = ["all", "compliant", "violation", "unknown"] as const;
type Lang = "ru" | "et" | "en";
type TabKey = "alerts" | "domain" | "analytics" | "aboutModel" | "aboutService";
type MobilePanelState = "collapsed" | "half" | "full";
type MobileSheetMode = "place" | "filter";
const countyKey = (value: string | null | undefined) => (value || "").trim().toLowerCase();
const countyPretty = (value: string | null | undefined) =>
  (value || "")
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(" ");

type DomainKey = "supluskoha" | "veevark" | "joogivesi" | "basseinid";
type NormRule = { min?: number; max?: number; exact?: number; unit: string };

const NORM_RULES: Record<string, Partial<Record<DomainKey, NormRule>> & { default?: NormRule }> = {
  e_coli: {
    supluskoha: { max: 500, unit: "КОЕ/100 мл" },
    basseinid: { exact: 0, unit: "КОЕ/100 мл" },
    default: { max: 500, unit: "КОЕ/100 мл" }
  },
  enterococci: {
    supluskoha: { max: 200, unit: "КОЕ/100 мл" },
    default: { max: 200, unit: "КОЕ/100 мл" }
  },
  coliforms: { basseinid: { exact: 0, unit: "КОЕ/100 мл" } },
  pseudomonas: { basseinid: { exact: 0, unit: "КОЕ/100 мл" } },
  staphylococci: { basseinid: { max: 20, unit: "КОЕ/100 мл" } },
  ph: {
    basseinid: { min: 6.5, max: 8.5, unit: "pH" },
    veevark: { min: 6.5, max: 9.5, unit: "pH" },
    joogivesi: { min: 6.5, max: 9.5, unit: "pH" },
    default: { min: 6.0, max: 9.0, unit: "pH" }
  },
  nitrates: { default: { max: 50, unit: "mg/L" } },
  nitrites: { default: { max: 0.5, unit: "mg/L" } },
  ammonium: { default: { max: 0.5, unit: "mg/L" } },
  fluoride: { default: { max: 1.5, unit: "mg/L" } },
  manganese: { default: { max: 0.05, unit: "mg/L" } },
  iron: { default: { max: 0.2, unit: "mg/L" } },
  turbidity: {
    basseinid: { max: 0.5, unit: "NTU" },
    default: { max: 4.0, unit: "NTU" }
  },
  color: { default: { max: 20, unit: "mg Pt/L" } },
  chlorides: { default: { max: 250, unit: "mg/L" } },
  sulfates: { default: { max: 250, unit: "mg/L" } },
  free_chlorine: { basseinid: { min: 0.2, max: 0.6, unit: "mg/L" } },
  combined_chlorine: { basseinid: { max: 0.4, unit: "mg/L" } }
};

function fmtDate(value: string | null): string {
  if (!value) return "n/a";
  const raw = String(value).trim();
  const isoPrefix = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoPrefix) return isoPrefix[1];
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const toRad = (v: number) => (v * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusKm * c;
}


function lruet<T>(lang: Lang, ru: T, et: T, en: T): T {
  if (lang === "ru") return ru;
  if (lang === "et") return et;
  return en;
}

function Icon({ name }: { name: IconName }) {
  if (name === "pin") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 4.5h8l-1.4 4.2 2.7 2.8v1H13v6l-1 1-1-1v-6H6.7v-1l2.7-2.8L8 4.5Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "unpin") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M7 5h10l-1.6 4.3 2.6 2.7v1H13v5.7l-1 1-1-1V13H6v-1l2.6-2.7L7 5Zm-1.7 12.2 11.5-11.5 1.4 1.4L6.7 18.6l-1.4-1.4Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (name === "close") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6.7 5.3 12 10.6l5.3-5.3 1.4 1.4L13.4 12l5.3 5.3-1.4 1.4L12 13.4l-5.3 5.3-1.4-1.4L10.6 12 5.3 6.7l1.4-1.4Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "alert") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3 2.2 20h19.6L12 3Zm0 5.2c.6 0 1 .4 1 1v5.4a1 1 0 1 1-2 0V9.2c0-.6.4-1 1-1Zm0 10a1.2 1.2 0 1 1 0-2.4 1.2 1.2 0 0 1 0 2.4Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "filters") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7a1 1 0 0 1 1-1h2.3a2.5 2.5 0 0 1 4.8 0H19a1 1 0 1 1 0 2h-6.9a2.5 2.5 0 0 1-4.8 0H5a1 1 0 0 1-1-1Zm8 10a2.5 2.5 0 0 1-4.7 1H5a1 1 0 1 1 0-2h2.3a2.5 2.5 0 0 1 4.7 1Zm1-6a2.5 2.5 0 0 1 4.7-1H19a1 1 0 1 1 0 2h-1.3a2.5 2.5 0 0 1-4.7-1Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "filter-x") {
    // Funnel icon with a diagonal strike-through — "clear all filters"
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M4 5h16l-6 7v5l-4 2v-7L4 5Z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
          fill="none"
        />
        <path d="M5 19 19 5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "locate") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="3.5" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "info") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="10" fill="currentColor" opacity="0.15" />
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="12" cy="7.6" r="1.4" fill="currentColor" />
        <rect x="10.7" y="10.4" width="2.6" height="7.2" rx="1" fill="currentColor" />
      </svg>
    );
  }
  /* ── calendar (date) ────────────────────────────────────────── */
  if (name === "calendar") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.7" />
        <path d="M3 10h18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        <path d="M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "sun") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="4.2" fill="currentColor" />
        <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.1 5.1l1.7 1.7M17.2 17.2l1.7 1.7M5.1 18.9l1.7-1.7M17.2 6.8l1.7-1.7" />
        </g>
      </svg>
    );
  }
  if (name === "moon") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M21 13.5A9 9 0 1 1 10.5 3a7.2 7.2 0 0 0 10.5 10.5Z" fill="currentColor" />
      </svg>
    );
  }
  /* ── domain icons (from #29: table-text-to-icons) ───────────── */
  if (name === "swim") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="13.5" cy="4.5" r="1.8" fill="currentColor" />
        <path d="M12 7 9 12l4 2 1.5-2.5L16 14l3.5-1.5-2.5-5.5-5 0Z" fill="currentColor" />
        <path d="M3 18.5c1.4-1.4 3.6-1.4 5 0s3.6 1.4 5 0 3.6-1.4 5 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "pool") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M9 13V9l3-3 3 3v4" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        <path d="M3 16c1.4-1.4 3.6-1.4 5 0s3.6 1.4 5 0 3.6-1.4 5 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M3 20c1.4-1.4 3.6-1.4 5 0s3.6 1.4 5 0 3.6-1.4 5 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "tap") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M7 8h10v5H7z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
        <path d="M10 8V6h4v2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        <path d="M17 10.5h2.5v1.5H17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M12 13v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="12" cy="18" r="1.3" fill="currentColor" />
      </svg>
    );
  }
  if (name === "drop") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 3C12 3 5.5 10.5 5.5 15a6.5 6.5 0 0 0 13 0C18.5 10.5 12 3 12 3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      </svg>
    );
  }
  /* ── status icons ───────────────────────────────────────────── */
  if (name === "check-circle") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
        <path d="M8 12l3 3 5-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (name === "x-circle") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
        <path d="M9 9l6 6M15 9l-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  if (name === "dash-circle") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
        <path d="M8 12h8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  /* ── watchlist star ─────────────────────────────────────────── */
  if (name === "star") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 2.5l2.6 5.3 5.9.85-4.25 4.15 1 5.85L12 15.77l-5.25 2.88 1-5.85L3.5 8.65l5.9-.85L12 2.5Z" fill="currentColor" />
      </svg>
    );
  }
  if (name === "star-outline") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2.5l2.6 5.3 5.9.85-4.25 4.15 1 5.85L12 15.77l-5.25 2.88 1-5.85L3.5 8.65l5.9-.85L12 2.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    );
  }
  /* ── 2x2 grid (used as the "All" chip glyph) ────────────────── */
  if (name === "grid") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3.2" y="3.2" width="7.6" height="7.6" rx="1.6" stroke="currentColor" strokeWidth="1.7" />
        <rect x="13.2" y="3.2" width="7.6" height="7.6" rx="1.6" stroke="currentColor" strokeWidth="1.7" />
        <rect x="3.2" y="13.2" width="7.6" height="7.6" rx="1.6" stroke="currentColor" strokeWidth="1.7" />
        <rect x="13.2" y="13.2" width="7.6" height="7.6" rx="1.6" stroke="currentColor" strokeWidth="1.7" />
      </svg>
    );
  }
  /* ── globe (language) ───────────────────────────────────────── */
  if (name === "globe") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
        <path d="M3 12h18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        <path d="M12 3c2.5 2.8 3.8 5.9 3.8 9s-1.3 6.2-3.8 9c-2.5-2.8-3.8-5.9-3.8-9S9.5 5.8 12 3Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      </svg>
    );
  }
  /* ── chevron-down ───────────────────────────────────────────── */
  if (name === "chevron-down") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  /* ── signal bars (risk) ─────────────────────────────────────── */
  if (name === "signal") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="2" y="17" width="4" height="4" rx="0.8" fill="currentColor" />
        <rect x="8" y="12" width="4" height="9" rx="0.8" fill="currentColor" />
        <rect x="14" y="7" width="4" height="14" rx="0.8" fill="currentColor" />
        <rect x="20" y="2" width="3" height="19" rx="0.8" fill="currentColor" opacity="0.35" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4a8 8 0 1 1-5.7 2.3L4.9 7.7A10 10 0 1 0 12 2v2Zm-1 1 4 4-4 4V10H2V8h9V5Z" fill="currentColor" />
    </svg>
  );
}

export default function Dashboard({ snapshot }: Props) {
  const [lang, setLang] = useState<Lang>(() => {
    if (typeof window === "undefined") return "ru";
    const saved = window.localStorage.getItem("water.ui.lang");
    return saved === "ru" || saved === "et" || saved === "en" ? saved : "ru";
  });
  const [showLangDialog, setShowLangDialog] = useState(() => {
    if (typeof window === "undefined") return false;
    return !window.localStorage.getItem("water.ui.lang");
  });
  const [cyrillicFont, setCyrillicFont] = useState<CyrillicFont>(() => {
    if (typeof window === "undefined") return "ibm";
    const saved = window.localStorage.getItem("water.ui.cyrillic-font.v1");
    return saved === "ibm" || saved === "manrope" ? saved : "ibm";
  });
  // Theme is opt-in. Default light. Applied to <body data-theme>.
  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "light";
    const saved = window.localStorage.getItem("water.ui.theme.v1");
    return saved === "dark" ? "dark" : "light";
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [filtersPinned, setFiltersPinned] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    const saved = window.localStorage.getItem("water.ui.filters-pinned.v1");
    return saved !== "false"; // default to pinned (true)
  });
  const [infoOpen, setInfoOpen] = useState(false);
  const [infoPageOpen, setInfoPageOpen] = useState(false);
  const [infoPageTab, setInfoPageTab] = useState<TabKey>("analytics");
  const [toast, setToast] = useState<string | null>(null);
  // Transient count bubble shown when the user taps the Alerts / Near-me
  // chip icon on top of the map. `seq` keeps each invocation distinct so
  // repeated taps restart the fade-out animation.
  const [countBubble, setCountBubble] = useState<{ seq: number; text: string } | null>(null);
  const [infoTitle, setInfoTitle] = useState("");
  const [infoText, setInfoText] = useState("");
  const infoCloseBtnRef = useRef<HTMLButtonElement | null>(null);

  // Info modal accessibility: Escape to close, body scroll lock while open,
  // autofocus the close button, restore focus to the trigger on close.
  useEffect(() => {
    if (!infoOpen) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setInfoOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Defer focus until the button is mounted.
    const t = window.setTimeout(() => infoCloseBtnRef.current?.focus(), 0);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      window.clearTimeout(t);
      previouslyFocused?.focus?.();
    };
  }, [infoOpen]);
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState("all");
  const [risk, setRisk] = useState("all");
  const [county, setCounty] = useState("all");
  const [official, setOfficial] = useState<(typeof officialOrder)[number]>("all");
  const [alertsOnly, setAlertsOnly] = useState(false);
  const [sampleDateFrom, setSampleDateFrom] = useState("");
  const [sampleDateTo, setSampleDateTo] = useState("");
  const [minProb, setMinProb] = useState(0);
  const [minProbInput, setMinProbInput] = useState(0);
  const [nearbyOnly, setNearbyOnly] = useState(false);
  const [nearbyRadiusKm, setNearbyRadiusKm] = useState(10);
  const [userCoords, setUserCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // When a co-located cluster is tapped on mobile, its child place IDs
  // are stored here so the bottom sheet can show a pick-list instead of
  // trying to spiderfy (which collapses right back on touch devices).
  const [clusterPlaceIds, setClusterPlaceIds] = useState<string[] | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const raw = window.localStorage.getItem("water.watchlist.v1");
      if (!raw) return [];
      const parsed = JSON.parse(raw) as unknown;
      return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
    } catch {
      return [];
    }
  });
  // Initialize from matchMedia synchronously so first client render already
  // matches the viewport. Server still emits desktop markup, but the mobile
  // overlays (.gmSearchBar, .mobileBottomSheet) are hidden via pure CSS until
  // `@media (max-width: 900px)` matches, so users do not see the desktop UI
  // flash before the mobile shell appears.
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(max-width: 900px)").matches;
  });
  const [isMapFullscreen, setIsMapFullscreen] = useState(false);
  const [mobilePanelState, setMobilePanelState] = useState<MobilePanelState>("collapsed");
  const [sheetMode, setSheetMode] = useState<MobileSheetMode>("place");
  // County GeoJSON loaded at Dashboard level so both the `filtered` useMemo
  // (polygon-based county filtering) and MapClient (overlay rendering) share
  // a single fetch.
  const [countyGeoJson, setCountyGeoJson] = useState<GeoJSON.GeoJsonObject | null>(null);
  const mapPanelRef = useRef<HTMLElement | null>(null);
  const sheetDragStartY = useRef<number | null>(null);
  const sheetDragLastY = useRef<number | null>(null);
  const sheetDragLastTs = useRef<number | null>(null);
  const sheetDragVelocity = useRef(0);
  const [sheetDragOffset, setSheetDragOffset] = useState(0);
  const [sheetDragging, setSheetDragging] = useState(false);
  const mobileFullscreenInitializedRef = useRef(false);
  const [headerCompact, setHeaderCompact] = useState(false);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const langMenuRef = useRef<HTMLDivElement | null>(null);

  const tr = useMemo(
    () => ({
      ru: {
        filters: "Фильтры",
        pin: "Закрепить",
        unpin: "Открепить",
        openFilters: "Открыть фильтры",
        close: "Закрыть",
        search: "Поиск по месту/уезду",
        domain: "Домен",
        locationType: "Тип локации",
        county: "Уезд",
        risk: "Риск",
        official: "Официальный статус",
        minProb: "Мин. вероятность",
        alertsOnly: "Только алерты",
        nearMe: "Рядом со мной",
        nearRadius: "Радиус",
        clearNearMe: "Очистить геопозицию",
        geoDenied: "Геодоступ отклонён. Разрешите доступ к местоположению в браузере.",
        geoUnsupported: "Геолокация не поддерживается вашим браузером.",
        latestSampleDate: "Дата последней пробы",
        dateFrom: "С",
        dateTo: "По",
        resetDate: "Сбросить",
        latestSampleDateHint: "Если диапазон активен, точки без даты последней пробы скрываются.",
        clearFilters: "Сбросить фильтры",
        mapTitle: "Интерактивная карта качества воды",
        selectedPoint: "Выбранная точка",
        noSelectedPoint: "Кликните по маркеру или строке таблицы, чтобы увидеть детали точки.",
        measurements: "Показатели воды",
        history: "История",
        historyPlaceholder: "История по точке не найдена в текущем экспортированном наборе.",
        tabs: {
          alerts: "Алерты",
          domain: "Домены",
          analytics: "Диагностика",
          aboutModel: "О модели",
          aboutService: "О сервисе"
        },
        aboutModel:
          "ML-модели (LR, RF, GB, LightGBM) оценивают вероятность нарушения по лабораторным показателям. Это инструмент поддержки решений, а не медицинская рекомендация.",
        aboutService:
          "Сервис объединяет открытые данные Terviseamet, карту, аналитику и объяснения параметров воды для жителей, туристов и семей. Данные и модели обновляются автоматически: еженедельно (пн) и 1-го числа каждого месяца.",
        metricGuideTitle: "Как читать метрики: точно + интуитивно",
        metricGuide: {
          roc: {
            title: "1) ROC-AUC — разделение классов",
            precise:
              "ROC-кривая строится по всем порогам и показывает TPR (Recall для нарушений) против FPR (ложные тревоги). AUC — площадь под кривой: вероятность, что случайное нарушение получит более высокий риск, чем случайная норма. AUC=0.5 — случайно, AUC=1.0 — идеальное ранжирование.",
            intuitive:
              "Если взять одну плохую и одну хорошую пробу, ROC-AUC показывает, как часто модель ставит более высокий риск плохой пробе. Это метрика качества ранжирования, а не выбранного порога.",
            reading:
              "Ориентир: 0.5 — случайно; 0.7-0.8 — приемлемо; 0.8-0.9 — хорошо; >0.9 — очень хорошо. Но высокий AUC сам по себе не задаёт хороший порог решения."
          },
          pr: {
            title: "2) Precision / Recall — цена ошибок",
            precise:
              "Recall = TP/(TP+FN): доля найденных реальных нарушений. Precision = TP/(TP+FP): доля подтвержденных нарушений среди тревог модели. FN — самые опасные ошибки (пропущенное нарушение), FP — лишние проверки.",
            intuitive:
              "Recall отвечает: 'сколько опасных случаев мы не пропустили?'. Precision отвечает: 'сколько наших тревог реально опасны?'. Обычно при росте Recall падает Precision, поэтому выбирается компромиссный порог.",
            reading:
              "Для water safety обычно важнее высокий Recall (не пропустить нарушение). Если Recall высокий, а Precision низкий — больше ложных тревог; обратная ситуация даёт меньше тревог, но больше пропусков."
          },
          calibration: {
            title: "3) Calibration — доверие к вероятности",
            precise:
              "Калибровка проверяет согласованность вероятностей с частотами. Если модель выдает группу точек с P(нарушения)=0.70, то примерно 70% таких точек должны реально быть нарушениями. Оценивается reliability-диаграммой и Brier score (ниже — лучше).",
            intuitive:
              "Это тест 'честности процентов'. Хорошо откалиброванная модель говорит 20% только там, где риск действительно около 20%, и 80% — где риск действительно около 80%.",
            reading:
              "Если калибровка плохая, проценты нельзя понимать как прямую вероятность. Тогда P(нарушения) полезнее для ранжирования приоритетов, чем для буквального 'шанса в процентах'."
          },
          shap: {
            title: "4) SHAP — объяснение причин риска",
            precise:
              "SHAP раскладывает прогноз точки на вклад признаков относительно базового уровня риска: положительный вклад увеличивает риск, отрицательный уменьшает. Сумма вкладов + baseline соответствует итоговому score модели.",
            intuitive:
              "SHAP — это 'чек', из чего собрался риск. Например, высокий iron и color могли поднять риск, а нормальный pH — снизить. Это объяснение модели, а не доказательство причинно-следственной связи в природе.",
            reading:
              "Большой положительный вклад SHAP двигает прогноз к нарушению, отрицательный — к норме. Это интерпретация поведения модели, а не доказательство физической причины загрязнения."
          }
        }
      },
      et: {
        filters: "Filtrid",
        pin: "Kinnita",
        unpin: "Vabasta",
        openFilters: "Ava filtrid",
        close: "Sulge",
        search: "Otsi koha/maakonna järgi",
        domain: "Domeen",
        locationType: "Asukoha tüüp",
        county: "Maakond",
        risk: "Risk",
        official: "Ametlik staatus",
        minProb: "Min tõenäosus",
        alertsOnly: "Ainult häired",
        nearMe: "Minu lähedal",
        nearRadius: "Raadius",
        clearNearMe: "Tühjenda geopositsioon",
        geoDenied: "Asukohaluba on keelatud. Luba brauseris asukohale ligipääs.",
        geoUnsupported: "Geolokatsioon ei ole selles brauseris toetatud.",
        latestSampleDate: "Viimane proov kuupäev",
        dateFrom: "Alates",
        dateTo: "Kuni",
        resetDate: "Lähtesta",
        latestSampleDateHint: "Kui kuupäevavahemik on aktiivne, peidetakse punktid ilma viimase proovi kuupäevata.",
        clearFilters: "Tühjenda filtrid",
        mapTitle: "Interaktiivne veekvaliteedi kaart",
        selectedPoint: "Valitud punkt",
        noSelectedPoint: "Klõpsa markeril või tabeli real, et näha detailset infot.",
        measurements: "Vee näitajad",
        history: "Ajalugu",
        historyPlaceholder: "Selle punkti ajalugu pole eksporditud andmestikus saadaval.",
        tabs: {
          alerts: "Häired",
          domain: "Domeenid",
          analytics: "Diagnostika",
          aboutModel: "Mudelist",
          aboutService: "Teenusest"
        },
        aboutModel:
          "ML-mudelid (LR, RF, GB, LightGBM) hindavad rikkumise tõenäosust laborinäitajate põhjal. See on otsusetugi, mitte meditsiiniline soovitus.",
        aboutService:
          "Teenuses on koos Terviseameti avaandmed, kaart, analüütika ja selgitused vee parameetrite kohta. Andmed ja mudelid uuendatakse automaatselt: iganädalaselt (E) ja iga kuu 1. kuupäeval.",
        metricGuideTitle: "Mõõdikud: täpselt + intuitiivselt",
        metricGuide: {
          roc: {
            title: "1) ROC-AUC — klasside eristusvõime",
            precise:
              "ROC-kõver võrdleb TPR-i ja FPR-i kõigi lävede korral. AUC on pindala kõvera all: tõenäosus, et juhuslik rikkumine saab kõrgema riski kui juhuslik norm. 0.5 = juhuslik, 1.0 = ideaalne järjestus.",
            intuitive:
              "Kui võtta üks halb ja üks hea proov, ROC-AUC näitab, kui tihti mudel annab halvale proovile kõrgema riski.",
            reading:
              "0.5 = juhuslik; 0.7-0.8 = rahuldav; 0.8-0.9 = hea; >0.9 = väga hea. Kõrge AUC ei määra automaatselt head otsustusläve."
          },
          pr: {
            title: "2) Precision / Recall — vigade hind",
            precise:
              "Recall = TP/(TP+FN): kui palju päris rikkumistest leitakse. Precision = TP/(TP+FP): kui suur osa häiretest osutub päris rikkumiseks. FN on ohtlikud möödalaskmised, FP on lisakontroll.",
            intuitive:
              "Recall: 'mida me üles leidsime?'. Precision: 'kui usaldusväärsed on häired?'. Tavaliselt ühe kasv vähendab teist.",
            reading:
              "Veeohutuses eelistatakse tihti kõrgemat Recalli. Kõrge Recall + madal Precision = rohkem valehäireid; vastupidi = rohkem möödalaske."
          },
          calibration: {
            title: "3) Calibration — tõenäosuse usaldatavus",
            precise:
              "Kalibreeritus võrdleb mudeli tõenäosusi tegelike sagedustega. Kui mudel annab grupile P=0.70, peaks umbes 70% neist olema rikkumised. Hinnatakse reliability-kõvera ja Brier score'iga.",
            intuitive:
              "Kas mudeli protsendid on 'ausad': 20% tähendab päriselt umbes 20%, 80% tähendab umbes 80%.",
            reading:
              "Halva kalibreerituse korral ei maksa protsente võtta otsese tõenäosusena; neid tasub kasutada pigem järjestamiseks."
          },
          shap: {
            title: "4) SHAP — riski põhjendamine",
            precise:
              "SHAP jaotab üksikprognoosi tunnuste panusteks võrreldes baastasemega. Positiivne panus tõstab riski, negatiivne langetab. Panuste summa + baseline annab lõppscore'i.",
            intuitive:
              "SHAP on prognoosi 'lahtivõtt': mis näitajad riski tõstsid ja mis seda vähendasid. See pole põhjuslik tõestus.",
            reading:
              "Suur positiivne SHAP-panuse väärtus tõstab rikkumisriski, negatiivne vähendab. Tõlgenda mudeli selgitusena, mitte põhjusliku tõendusena."
          }
        }
      },
      en: {
        filters: "Filters",
        pin: "Pin",
        unpin: "Unpin",
        openFilters: "Open filters",
        close: "Close",
        search: "Search by place/county",
        domain: "Domain",
        locationType: "Location type",
        county: "County",
        risk: "Risk",
        official: "Official status",
        minProb: "Min probability",
        alertsOnly: "Alerts only",
        nearMe: "Near me",
        nearRadius: "Radius",
        clearNearMe: "Clear geolocation",
        geoDenied: "Geolocation access denied. Please allow location access in your browser.",
        geoUnsupported: "Geolocation is not supported in this browser.",
        latestSampleDate: "Latest sample date",
        dateFrom: "From",
        dateTo: "To",
        resetDate: "Reset",
        latestSampleDateHint: "If date range is active, points without latest sample date are hidden.",
        clearFilters: "Clear filters",
        mapTitle: "Interactive water quality map",
        selectedPoint: "Selected point",
        noSelectedPoint: "Click a marker or table row to see point details.",
        measurements: "Water measurements",
        history: "History",
        historyPlaceholder: "History for this point is not available in the current export.",
        tabs: {
          alerts: "Alerts",
          domain: "Domains",
          analytics: "Diagnostics",
          aboutModel: "About model",
          aboutService: "About service"
        },
        aboutModel:
          "ML models (LR, RF, GB, LightGBM) estimate violation probability from lab measurements. This is decision support, not medical advice.",
        aboutService:
          "The service combines Terviseamet open data, map, analytics, and explanations of water parameters for residents and visitors. Data and models are refreshed automatically: weekly (Mon) and on the 1st of each month.",
        metricGuideTitle: "How to read metrics: precise + intuitive",
        metricGuide: {
          roc: {
            title: "1) ROC-AUC — class separability",
            precise:
              "ROC curve compares TPR and FPR across all thresholds. AUC is area under the curve: probability that a random violation gets a higher risk than a random compliant sample.",
            intuitive:
              "If you take one bad and one good sample, ROC-AUC shows how often the model ranks the bad one higher.",
            reading:
              "Rule of thumb: 0.5 random, 0.7-0.8 fair, 0.8-0.9 good, >0.9 very good. High AUC alone does not set a decision threshold."
          },
          pr: {
            title: "2) Precision / Recall — error trade-off",
            precise:
              "Recall = TP/(TP+FN), Precision = TP/(TP+FP). FN are missed violations, FP are false alarms.",
            intuitive:
              "Recall asks: how many dangerous cases were found? Precision asks: how many alerts were truly dangerous?",
            reading:
              "For water safety, high Recall is often preferred. High Recall + low Precision means more false alarms."
          },
          calibration: {
            title: "3) Calibration — probability reliability",
            precise:
              "Calibration checks whether predicted probabilities match observed frequencies (reliability curve, Brier score).",
            intuitive:
              "A well-calibrated model means 80% predictions are truly near 80% in reality.",
            reading:
              "If calibration is weak, use probabilities mainly for prioritization/ranking rather than literal percentages."
          },
          shap: {
            title: "4) SHAP — risk explanation",
            precise:
              "SHAP decomposes a single prediction into feature contributions around a baseline risk.",
            intuitive:
              "It shows which parameters pushed risk up or down for this sample.",
            reading:
              "Interpret as model behavior explanation, not as causal proof of contamination source."
          }
        }
      }
    }),
    []
  );
  const t = tr[lang];
  const pushHeaderLang = (nextLang: "ru" | "et" | "en") => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("water.ui.lang", nextLang);
    window.dispatchEvent(new CustomEvent("water-ui-lang-changed", { detail: { lang: nextLang } }));
  };
  const chooseLang = (nextLang: Lang) => {
    setLang(nextLang);
    setShowLangDialog(false);
    pushHeaderLang(nextLang);
  };
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(t);
  }, [toast]);
  const expertModeText =
    lang === "ru"
      ? [
          "Что такое P(violation)",
          "- Это оценка вероятности нарушения санитарных норм для конкретной пробы по её лабораторным признакам.",
          "- Это не прогноз будущего качества воды и не официальный вердикт регулятора.",
          "- При слабой калибровке используйте значение прежде всего для ранжирования приоритетов.",
          "",
          "Что означают модели",
          "- LR (Logistic Regression): линейная модель, переводит взвешенную сумму признаков в вероятность через сигмоиду.",
          "- RF (Random Forest): ансамбль многих деревьев решений; итоговая вероятность — усреднение по деревьям.",
          "- GB (Gradient Boosting): деревья строятся последовательно, каждое исправляет ошибки предыдущих.",
          "- LGBM (LightGBM): быстрый и оптимизированный вариант gradient boosting на деревьях для больших данных.",
          "",
          "Почему вероятности различаются",
          "- Модели имеют разную архитектуру и по-разному обобщают паттерны.",
          "- Разница с RF показывает, насколько модель строже или мягче относительно эталонной RF-оценки.",
          "",
          "О горизонте предсказания",
          "- Предсказание относится к текущей/исторической записи пробы в данных.",
          "- Это не ответ на вопрос 'что будет через неделю/месяц'."
        ].join("\n")
      : lang === "et"
        ? [
          "Mis on P(rikkumine)",
          "- See on konkreetse proovi rikkumise tõenäosuse hinnang laborinäitajate põhjal.",
          "- See ei ole tuleviku vee kvaliteedi prognoos ega ametlik regulatiivne otsus.",
          "",
          "Mida mudelid tähendavad",
          "- LR (Logistic Regression): lineaarne mudel, mis teisendab tunnuste summa tõenäosuseks logistilise funktsiooniga.",
          "- RF (Random Forest): paljude otsustuspuude ansambel; tõenäosus on puude hinnangute keskmine.",
          "- GB (Gradient Boosting): puud ehitatakse järjest, iga järgmine parandab eelmiste vigu.",
          "- LGBM (LightGBM): kiire ja optimeeritud gradient boosting puupõhiste mudelite jaoks.",
          "",
          "Miks tõenäosused erinevad",
          "- Mudelitel on erinev arhitektuur ja erinev üldistusviis.",
          "- RF-iga võrdlus näitab, kas mudel on RF suhtes rangem või leebem.",
          "",
          "Prognoosi ajahorisont",
          "- Hinnang käib praeguse/ajaloolise proovi kirje kohta andmestikus.",
          "- See ei vasta küsimusele, mis juhtub veekvaliteediga järgmisel nädalal või kuul."
        ].join("\n")
        : [
          "What P(violation) means",
          "- It is a model-estimated probability of sanitary norm violation for this specific sample.",
          "- It is not a future forecast and not an official regulatory verdict.",
          "- If calibration is weak, use it primarily for prioritization/ranking.",
          "",
          "What models mean",
          "- LR (Logistic Regression): linear model mapping weighted features into probability via logistic function.",
          "- RF (Random Forest): ensemble of decision trees; final probability is averaged across trees.",
          "- GB (Gradient Boosting): trees are built sequentially, each correcting previous errors.",
          "- LGBM (LightGBM): fast optimized gradient boosting on trees.",
          "",
          "Why probabilities differ",
          "- Models have different inductive biases and generalization behavior.",
          "- Difference vs RF shows whether a model is stricter or softer than RF on the same sample.",
          "",
          "Prediction horizon",
          "- Prediction refers to the current/historical sample record in data.",
          "- It does not answer what will happen to water quality next week or month."
        ].join("\n");
  const renderInfoContent = (text: string) => {
    const lines = String(text || "").split("\n");
    const isRu = text.includes("Что означают модели");
    const isEt = text.includes("Mida mudelid tähendavad");
    const isEn = text.includes("What models mean");
    const showMiniTable = isRu || isEt || isEn;
    const modelRows = showMiniTable
      ? [
          {
            short: "LR",
            full: "Logistic Regression",
            principle: isRu ? "Линейная модель + логистическая функция для вероятности" : isEt ? "Lineaarne mudel + logistiline funktsioon tõenäosuse leidmiseks" : "Linear model + logistic function for probability",
            errorSensitivity: isRu ? "Чувствительна к пропущенным и плохо масштабированным признакам; стабильна на линейных паттернах" : isEt ? "Tundlik puuduvale/skaleerimata sisendile; stabiilne lineaarsete mustrite korral" : "Sensitive to missing/poorly scaled features; stable for linear patterns"
          },
          {
            short: "RF",
            full: "Random Forest",
            principle: isRu ? "Ансамбль решающих деревьев, усредняет оценки" : isEt ? "Otsustuspuude ansambel, mis keskmistab hinnanguid" : "Decision-tree ensemble averaging outputs",
            errorSensitivity: isRu ? "Устойчива к шуму и выбросам, но может сглаживать редкие сигналы" : isEt ? "Vastupidav mürale ja outlier'itele, kuid võib haruldasi signaale siluda" : "Robust to noise/outliers, may smooth rare signals"
          },
          {
            short: "GB",
            full: "Gradient Boosting",
            principle: isRu ? "Последовательные деревья исправляют ошибки предыдущих" : isEt ? "Järjestikused puud parandavad eelmiste mudelite vigu" : "Sequential trees correct previous errors",
            errorSensitivity: isRu ? "Сильнее ловит сложные зависимости, но чувствителен к переобучению без регуляризации" : isEt ? "Tabab keerukaid seoseid, kuid võib ilma regulatsioonita üle õppida" : "Captures complex patterns, but can overfit without regularization"
          },
          {
            short: "LGBM",
            full: "LightGBM",
            principle: isRu ? "Оптимизированный быстрый gradient boosting на деревьях" : isEt ? "Optimeeritud ja kiire puupõhine gradient boosting" : "Fast optimized gradient boosting on trees",
            errorSensitivity: isRu ? "Очень чувствителен к гиперпараметрам; быстрый, но требует контроля overfitting" : isEt ? "Väga tundlik hüperparameetritele; kiire, kuid vajab overfitting'u kontrolli" : "Sensitive to hyperparameters; fast but needs overfitting control"
          }
        ]
      : [];
    return (
      <div className="infoRich">
        {lines.map((line, idx) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={`i-${idx}`} className="infoSpacer" />;
          if (trimmed.startsWith("- ")) return <div key={`i-${idx}`} className="infoBullet">{trimmed.slice(2)}</div>;
          // Only short labels without punctuation act as real section
          // headings. Data lines (contain ":" or end with a period) render
          // as regular-weight body text so modals don't look shouty.
          const isHeading = !trimmed.includes(":") && !/[.!?]$/.test(trimmed) && trimmed.length <= 60;
          if (isHeading) return <div key={`i-${idx}`} className="infoHeading">{trimmed}</div>;
          return <div key={`i-${idx}`} className="infoLine">{trimmed}</div>;
        })}
        {modelRows.length > 0 ? (
          <div className="infoTableWrap">
            {(() => {
              const fullLabel = isRu ? "Название" : isEt ? "Täisnimi" : "Full name";
              const principleLabel = isRu ? "Принцип" : isEt ? "Põhimõte" : "Principle";
              const sensitivityLabel = isRu ? "Чувствительность к ошибкам" : isEt ? "Tundlikkus vigadele" : "Error sensitivity";
              return (
            <table className="table infoMiniTable">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>{fullLabel}</th>
                  <th>{principleLabel}</th>
                  <th>{sensitivityLabel}</th>
                </tr>
              </thead>
              <tbody>
                {modelRows.map((r) => (
                  <tr key={`mini-${r.short}`}>
                    <td>{r.short}</td>
                    <td data-label={fullLabel}>{r.full}</td>
                    <td data-label={principleLabel}>{r.principle}</td>
                    <td data-label={sensitivityLabel}>{r.errorSensitivity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
              );
            })()}
          </div>
        ) : null}
      </div>
    );
  };

  const paramInfo: Record<
    string,
    { ruLabel: string; etLabel: string; enLabel: string; ruDesc: string; etDesc: string; enDesc: string }
  > = {
    e_coli: {
      ruLabel: "E. coli (КОЕ/100 мл)", etLabel: "E. coli (PMÜ/100 ml)", enLabel: "E. coli (CFU/100 ml)",
      ruDesc: "Ключевой индикатор фекального загрязнения. Повышенные значения увеличивают риск кишечных инфекций и контактных заболеваний, особенно в открытой воде.",
      etDesc: "Fekaalreostuse põhiindikaator. Kõrged väärtused suurendavad seedetrakti infektsioonide ja kontakthaiguste riski, eriti avatud vees.",
      enDesc: "Key indicator of faecal contamination. Elevated values increase risk of intestinal infections and contact diseases, especially in open water."
    },
    enterococci: {
      ruLabel: "Энтерококки (КОЕ/100 мл)", etLabel: "Enterokokid (PMÜ/100 ml)", enLabel: "Enterococci (CFU/100 ml)",
      ruDesc: "Бактериальный индикатор для купальных зон и рекреационной воды. В сочетании с E. coli помогает оценить микробиологическую безопасность.",
      etDesc: "Bakteriaalne veekvaliteedi indikaator, eriti supluskohtades. Koos E. coliga aitab hinnata mikrobioloogilist ohutust.",
      enDesc: "Bacterial indicator for bathing and recreational water. Together with E. coli it helps assess microbiological safety."
    },
    coliforms: {
      ruLabel: "Колиформы (КОЕ/100 мл)", etLabel: "Kolibakterid (PMÜ/100 ml)", enLabel: "Coliforms (CFU/100 ml)",
      ruDesc: "Общий микробиологический индикатор санитарного состояния. Рост колиформ может указывать на проблемы в источнике или системе водоподготовки.",
      etDesc: "Üldine mikrobioloogiline näitaja vee sanitaarseisundi kohta. Kõrge tase viitab allikas- või töötlemisprobleemidele.",
      enDesc: "General microbiological indicator of sanitary conditions. Elevated coliforms may indicate issues in the water source or treatment system."
    },
    ph: {
      ruLabel: "pH", etLabel: "pH", enLabel: "pH",
      ruDesc: "Кислотность/щёлочность воды. Влияет на коррозию труб, эффективность дезинфекции и комфорт при контакте с водой. Норма для питьевой воды: 6.5–9.5.",
      etDesc: "Vee happelisus/leelisus. Mõjutab torutorrosiooni, desinfektsiooni tõhusust ja mugavust. Joogivee norm: 6.5–9.5.",
      enDesc: "Acidity/alkalinity of water. Affects pipe corrosion, disinfection efficiency and comfort. Drinking water norm: 6.5–9.5."
    },
    nitrates: {
      ruLabel: "Нитраты (мг/л)", etLabel: "Nitraadid (mg/l)", enLabel: "Nitrates (mg/L)",
      ruDesc: "Особенно важны для питьевой воды. Повышенные нитраты часто связаны с сельхоз-стоками и требуют усиленного контроля. Норма: ≤50 мг/л.",
      etDesc: "Eriti olulised joogivees. Kõrge tase on sageli seotud põllumajanduslike heitvetega. Norm: ≤50 mg/l.",
      enDesc: "Particularly important for drinking water. Elevated nitrates are often linked to agricultural run-off. Norm: ≤50 mg/L."
    },
    nitrites: {
      ruLabel: "Нитриты (мг/л)", etLabel: "Nitritid (mg/l)", enLabel: "Nitrites (mg/L)",
      ruDesc: "Маркер свежей биозагрязнённости и нестабильных процессов азотного цикла. В питьевой воде требует повышенного внимания. Норма: ≤0.5 мг/л.",
      etDesc: "Värske bioreostuse marker. Joogivees nõuab erilist tähelepanu. Norm: ≤0.5 mg/l.",
      enDesc: "Marker of fresh biological contamination and unstable nitrogen-cycle processes. Requires close attention in drinking water. Norm: ≤0.5 mg/L."
    },
    ammonium: {
      ruLabel: "Аммоний (мг/л)", etLabel: "Ammoonium (mg/l)", enLabel: "Ammonium (mg/L)",
      ruDesc: "Повышенный аммоний может указывать на органическое загрязнение или недостаточную очистку. Влияет на вкус/запах воды. Норма: ≤0.5 мг/л.",
      etDesc: "Kõrgenenud ammoonium võib viidata orgaanilisele reostusele. Mõjutab vee maitset ja lõhna. Norm: ≤0.5 mg/l.",
      enDesc: "Elevated ammonium may indicate organic contamination or insufficient treatment. Affects taste and odour. Norm: ≤0.5 mg/L."
    },
    turbidity: {
      ruLabel: "Мутность (NTU)", etLabel: "Hägusus (NTU)", enLabel: "Turbidity (NTU)",
      ruDesc: "Отражает количество взвешенных частиц. Повышенные значения могут маскировать микробные риски и снижать эффективность дезинфекции. Норма: ≤4 NTU (питьевая), ≤0.5 NTU (бассейн).",
      etDesc: "Peegeldab hõljuvate osakeste hulka. Kõrge hägusus varjab mikroobiohtu ja vähendab desinfektsiooni tõhusust.",
      enDesc: "Reflects suspended particles. Elevated turbidity can mask microbial risks and reduce disinfection effectiveness. Norm: ≤4 NTU (drinking), ≤0.5 NTU (pool)."
    },
    free_chlorine: {
      ruLabel: "Свободный хлор (мг/л)", etLabel: "Vaba kloor (mg/l)", enLabel: "Free chlorine (mg/L)",
      ruDesc: "Ключевой параметр для бассейнов/SPA: недостаток снижает дезинфекцию, избыток может раздражать кожу, глаза и дыхательные пути. Норма: 0.2–0.6 мг/л.",
      etDesc: "Basseinides/SPA-des kriitiliselt oluline: liiga vähe vähendab desinfektsiooni, liiga palju ärritab. Norm: 0.2–0.6 mg/l.",
      enDesc: "Critical for pools/SPA: too little reduces disinfection; excess irritates skin, eyes and airways. Norm: 0.2–0.6 mg/L."
    },
    combined_chlorine: {
      ruLabel: "Связанный хлор (мг/л)", etLabel: "Seotud kloor (mg/l)", enLabel: "Combined chlorine (mg/L)",
      ruDesc: "Хлорамины, образующиеся в бассейнах при реакции хлора с аммиаком из пота и мочи. Высокие значения дают запах «хлорки» и раздражение слизистых. Норма: ≤0.4 мг/л.",
      etDesc: "Basseinis tekkivad kloramiinid. Kõrged väärtused põhjustavad lõhna ja limaskesta ärritust. Norm: ≤0.4 mg/l.",
      enDesc: "Chloramines in pools from chlorine reacting with ammonia in sweat/urine. Cause the 'pool smell' and mucosal irritation. Norm: ≤0.4 mg/L."
    },
    iron: {
      ruLabel: "Железо (мг/л)", etLabel: "Raud (mg/l)", enLabel: "Iron (mg/L)",
      ruDesc: "Повышенное железо придаёт воде металлический привкус и ржавый оттенок, окрашивает сантехнику. Связано со старением труб или природными грунтовыми водами. Норма: ≤0.2 мг/л.",
      etDesc: "Kõrge rauasisaldus annab veele metalse maitse ja roostelise värvi. Seotud vananenud torude või põhjavee omapäraga. Norm: ≤0.2 mg/l.",
      enDesc: "Elevated iron gives a metallic taste and rusty tint, staining plumbing. Linked to ageing pipes or natural groundwater. Norm: ≤0.2 mg/L."
    },
    manganese: {
      ruLabel: "Марганец (мг/л)", etLabel: "Mangaan (mg/l)", enLabel: "Manganese (mg/L)",
      ruDesc: "Придаёт воде тёмную окраску и металлический вкус. Хроническое воздействие высоких доз может влиять на нервную систему. Норма: ≤0.05 мг/л.",
      etDesc: "Annab veele tumeda värvuse ja metalse maitse. Pikaaegne kõrge tase võib mõjutada närvisüsteemi. Norm: ≤0.05 mg/l.",
      enDesc: "Gives water a dark tint and metallic taste. Chronic exposure to high levels may affect the nervous system. Norm: ≤0.05 mg/L."
    },
    fluoride: {
      ruLabel: "Фторид (мг/л)", etLabel: "Fluoriid (mg/l)", enLabel: "Fluoride (mg/L)",
      ruDesc: "В небольших количествах защищает зубы от кариеса, но при избытке вызывает флюороз зубов и костей. Норма ЕС для питьевой воды: ≤1.5 мг/л.",
      etDesc: "Väikestes kogustes kaitseb hambaid, kuid ülemäärasus põhjustab fluoroosi. EL joogivee norm: ≤1.5 mg/l.",
      enDesc: "In small amounts protects teeth from decay, but excess causes dental and skeletal fluorosis. EU drinking water norm: ≤1.5 mg/L."
    },
    color: {
      ruLabel: "Цветность (мг Pt/л)", etLabel: "Värvus (mg Pt/l)", enLabel: "Colour (mg Pt/L)",
      ruDesc: "Измеряется по платиново-кобальтовой шкале. Высокая цветность обычно связана с гуминовыми веществами из торфяных почв — не токсично само по себе, но указывает на органику. Норма: ≤20 мг Pt/л.",
      etDesc: "Mõõdetakse plaatina-koobalt skaalal. Kõrge värvus viitab humiinainetele turbapinnasest. Norm: ≤20 mg Pt/l.",
      enDesc: "Measured on the platinum-cobalt scale. High colour typically indicates humic substances from peat soils — not directly toxic but signals organic matter. Norm: ≤20 mg Pt/L."
    },
    chlorides: {
      ruLabel: "Хлориды (мг/л)", etLabel: "Kloriidid (mg/l)", enLabel: "Chlorides (mg/L)",
      ruDesc: "Повышенные хлориды могут указывать на засоление, влияние морской воды, противогололёдные реагенты или промышленные стоки. Влияют на вкус воды и коррозию. Норма: ≤250 мг/л.",
      etDesc: "Kõrge kloriidide sisaldus viitab soolastumisele, merevee mõjule või tööstusheitmetele. Norm: ≤250 mg/l.",
      enDesc: "Elevated chlorides may indicate salinisation, seawater intrusion, de-icing agents or industrial discharge. Affect taste and pipe corrosion. Norm: ≤250 mg/L."
    },
    sulfates: {
      ruLabel: "Сульфаты (мг/л)", etLabel: "Sulfaadid (mg/l)", enLabel: "Sulfates (mg/L)",
      ruDesc: "Высокое содержание сульфатов может оказывать слабительный эффект при длительном употреблении. Влияют на вкус воды. Норма: ≤250 мг/л.",
      etDesc: "Kõrge sulfaadisisaldus võib pikaajalise tarbimise korral põhjustada lahtistit. Mõjutab vee maitset. Norm: ≤250 mg/l.",
      enDesc: "High sulfate content may have a laxative effect with prolonged consumption and affects taste. Norm: ≤250 mg/L."
    },
    pseudomonas: {
      ruLabel: "Pseudomonas aeruginosa (КОЕ/100 мл)", etLabel: "Pseudomonas aeruginosa (PMÜ/100 ml)", enLabel: "Pseudomonas aeruginosa (CFU/100 ml)",
      ruDesc: "Условно-патогенный микроорганизм. В бассейнах норма — 0 КОЕ/100 мл. Может вызывать инфекции кожи, глаз и ушей, особенно у иммунокомпрометированных лиц.",
      etDesc: "Oportunistlik patogeen. Basseinides norm: 0 PMÜ/100 ml. Võib põhjustada naha-, silma- ja kõrvainfektsioone.",
      enDesc: "Opportunistic pathogen; must be absent in pool water (0 CFU/100 ml). Can cause skin, eye and ear infections, especially in immunocompromised individuals."
    },
    staphylococci: {
      ruLabel: "Staphylococcus aureus (КОЕ/100 мл)", etLabel: "Staphylococcus aureus (PMÜ/100 ml)", enLabel: "Staphylococcus aureus (CFU/100 ml)",
      ruDesc: "Патогенная бактерия. В бассейнах норма ≤20 КОЕ/100 мл. Превышение указывает на антисанитарию и возможное заражение кожи и слизистых оболочек.",
      etDesc: "Patogeenne bakter. Basseinides norm ≤20 PMÜ/100 ml. Ületamine viitab sanitaarprobleemidele.",
      enDesc: "Pathogenic bacterium. Pool norm: ≤20 CFU/100 ml. Exceedance indicates unsanitary conditions and risk of skin/mucous membrane infections."
    },
    transparency: {
      ruLabel: "Прозрачность (м)", etLabel: "Läbipaistvus (m)", enLabel: "Transparency (m)",
      ruDesc: "Видимая глубина воды по шкале Секки в метрах. Используется для купальных зон. Снижение прозрачности указывает на цветение водорослей, взвесь или загрязнение.",
      etDesc: "Sekchi sügavus meetrites. Kasutatakse supluskohtades. Läbipaistvuse vähenemine viitab vetikate õitsengule või reostusele.",
      enDesc: "Secchi depth in metres. Used for bathing areas. Decreasing transparency indicates algal blooms, suspended matter or other contamination."
    },
    oxidizability: {
      ruLabel: "Окисляемость (мг O₂/л)", etLabel: "Oksüdeeritavus (mg O₂/l)", enLabel: "Oxidisability (mg O₂/L)",
      ruDesc: "Интегральный показатель содержания легкоокисляемых органических веществ (перманганатная окисляемость). Повышенные значения говорят о большей органической нагрузке и риске образования побочных продуктов хлорирования.",
      etDesc: "Integraalne näitaja kergesti oksüdeeruvate orgaaniliste ainete sisalduse kohta. Kõrged väärtused viitavad suuremale orgaanilisele koormusele ja kloorimise kõrvalsaaduste tekkeohule.",
      enDesc: "Integrated measure of easily oxidisable organic matter (permanganate oxidisability). Higher values mean greater organic load and a higher risk of chlorination by-products."
    },
    colonies_37c: {
      ruLabel: "Колонии при 37 °C (КОЕ/мл)", etLabel: "Kolooniad 37 °C juures (PMÜ/ml)", enLabel: "Colonies at 37 °C (CFU/mL)",
      ruDesc: "Общее микробное число при температуре тела — суммарная бактериальная нагрузка. Резкий рост указывает на сбой дезинфекции или формирование биоплёнки в системе; сам по себе не указывает на конкретный патоген.",
      etDesc: "Üldine mikroobide arv kehatemperatuuril — bakterite üldhulk. Järsk tõus viitab desinfektsiooni häirele või biokile tekkele; ei näita konkreetset patogeeni.",
      enDesc: "Heterotrophic plate count at body temperature — total bacterial load. A sharp rise indicates failing disinfection or biofilm growth; it does not point at a specific pathogen."
    }
  };

  const labelForParam = (key: string) => {
    const i = paramInfo[key];
    if (!i) return key;
    return lruet(lang, i.ruLabel, i.etLabel, i.enLabel);
  };

  const descForParam = (key: string) => {
    const i = paramInfo[key];
    if (!i)
      return lruet(
        lang,
        "Лабораторный параметр качества воды. Важность зависит от типа точки (питьевая вода, бассейн, открытая вода) и нормативов.",
        "Laboratoorne veekvaliteedi näitaja. Tähendus sõltub domeenist ja normidest.",
        "Laboratory water quality parameter. Its meaning depends on domain and applicable norms."
      );
    return lruet(lang, i.ruDesc, i.etDesc, i.enDesc);
  };

  const formatNum = (value: number) => Number(value.toFixed(3)).toString();

  const getNormRule = (param: string, domain: string): NormRule | null => {
    const def = NORM_RULES[param];
    if (!def) return null;
    return (def[domain as DomainKey] ?? def.default ?? null) as NormRule | null;
  };

  const normLabel = (rule: NormRule) => {
    if (typeof rule.exact === "number") return `${lruet(lang, "ровно", "täpselt", "exactly")} ${formatNum(rule.exact)} ${rule.unit}`;
    if (typeof rule.min === "number" && typeof rule.max === "number") {
      return `${formatNum(rule.min)}-${formatNum(rule.max)} ${rule.unit}`;
    }
    if (typeof rule.min === "number") return `>= ${formatNum(rule.min)} ${rule.unit}`;
    if (typeof rule.max === "number") return `<= ${formatNum(rule.max)} ${rule.unit}`;
    return rule.unit;
  };

  const assessNorm = (param: string, value: number, domain: string) => {
    const rule = getNormRule(param, domain);
    if (!rule) return { rule: null, violated: null as boolean | null };
    let violated = false;
    if (typeof rule.exact === "number") violated = value !== rule.exact;
    if (typeof rule.min === "number" && value < rule.min) violated = true;
    if (typeof rule.max === "number" && value > rule.max) violated = true;
    return { rule, violated };
  };

  const explainMeasurementNorm = (param: string, rawValue: number | string, place: FrontendPlace) => {
    const numericValue = typeof rawValue === "number" ? rawValue : Number(rawValue);
    const hasNumeric = Number.isFinite(numericValue);
    const base = descForParam(param);
    const rule = getNormRule(param, place.domain);
    if (!rule || !hasNumeric) {
      return `${base}\n\n${
        lruet(
          lang,
          "Для этого параметра в текущем домене в интерфейсе нет числового норматива.",
          "Selle näitaja jaoks pole antud domeenis liideses numbrilist normi.",
          "No numeric threshold is configured in the UI for this parameter in the current domain."
        )
      }`;
    }
    const verdict = assessNorm(param, numericValue, place.domain).violated;
    const verdictText =
      verdict === null
        ? lruet(lang, "Оценка по норме недоступна.", "Normi hinnang pole saadaval.", "Norm-based evaluation is unavailable.")
        : verdict
          ? lruet(lang, "Статус: ВЫХОД ЗА НОРМУ.", "Staatus: NORMIST VÄLJAS.", "Status: ABOVE THRESHOLD.")
          : lruet(lang, "Статус: в пределах нормы.", "Staatus: normi piires.", "Status: within threshold.");

    return `${base}\n\n${
      lruet(lang, "Норматив для этого домена", "Selle domeeni norm", "Norm for this domain")
    }: ${normLabel(rule)}\n${
      lruet(lang, "Фактическое значение", "Tegelik väärtus", "Actual value")
    }: ${formatNum(numericValue)} ${rule.unit}\n${verdictText}`;
  };

  const explainViolationFromMeasurements = (domain: string, measurements: Record<string, number>) => {
    const entries = Object.entries(measurements || {});
    const unknownNormParams: string[] = [];
    const violations = entries
      .map(([param, value]) => {
        const numericValue = typeof value === "number" ? value : Number(value);
        if (!Number.isFinite(numericValue)) return null;
        const assessed = assessNorm(param, numericValue, domain);
        if (!assessed.rule) {
          unknownNormParams.push(labelForParam(param));
          return null;
        }
        if (assessed.violated !== true) return null;
        return `- ${labelForParam(param)}: ${formatNum(numericValue)} ${assessed.rule.unit} (${lruet(lang, "норма", "norm", "norm")} ${normLabel(assessed.rule)})`;
      })
      .filter((x): x is string => Boolean(x));

    if (violations.length === 0) {
      const noMeasurements = entries.length === 0;
      const unknownPart =
        unknownNormParams.length > 0
          ? `\n${lruet(lang, "Параметры без встроенной нормы", "Parameetrid ilma sisseehitatud normita", "Parameters without built-in norm")}: ${unknownNormParams.slice(0, 6).join(", ")}${unknownNormParams.length > 6 ? "..." : ""}.`
          : "";
      return lruet(
        lang,
        `${noMeasurements ? "Для этой пробы в snapshot нет измерений, поэтому конкретный нарушенный параметр не определён." : "Официально отмечено нарушение, но среди доступных измерений нет явного выхода за встроенные пороги."}\nВозможны отсутствующие показатели, другие нормативы (по типу объекта) или ручная классификация инспектором.${unknownPart}`,
        `${noMeasurements ? "Selle proovi mõõtmised puuduvad snapshotis, seega rikkunud parameetrit ei saa määrata." : "Ametlik rikkumine on märgitud, kuid saadaolevates mõõtmistes ei leitud selget ületust sisseehitatud normide järgi."}${unknownPart}`,
        `${noMeasurements ? "No measurements are exported in snapshot for this sample, so a specific violated parameter cannot be determined." : "Official violation is marked, but available measurements show no explicit exceedance against built-in thresholds."} Missing indicators, other domain-specific norms, or manual inspector classification are possible.${unknownPart}`
      );
    }

    return `${lruet(lang, "Нарушены следующие параметры", "Rikutud parameetrid", "Violated parameters")}:\n${violations.join("\n")}`;
  };

  const explainViolation = (place: FrontendPlace) => explainViolationFromMeasurements(place.domain, place.measurements || {});

  const historyMeasurements = (place: FrontendPlace, idx: number): Record<string, number> => {
    const item = place.sample_history[idx];
    if (!item) return {};
    const direct = item.measurements || {};
    if (Object.keys(direct).length > 0) return direct;

    const itemDay = fmtDate(item.sample_date);
    const currentDay = fmtDate(place.sample_date);
    if (itemDay !== "n/a" && currentDay !== "n/a" && itemDay === currentDay) {
      const current = place.measurements || {};
      if (Object.keys(current).length > 0) return current;
    }

    const sibling = place.sample_history.find(
      (h) => fmtDate(h.sample_date) === itemDay && h.measurements && Object.keys(h.measurements).length > 0
    );
    return sibling?.measurements || {};
  };

  const explainHistoryMeasurements = (place: FrontendPlace, idx: number) => {
    const item = place.sample_history[idx];
    if (!item) return lruet(lang, "Запись истории не найдена.", "Ajaloo kirjet ei leitud.", "History record not found.");
    const rows = Object.entries(historyMeasurements(place, idx))
      .slice(0, 30)
      .map(([k, v]) => `- ${labelForParam(k)}: ${String(v)}`)
      .join("\n");
    if (!rows) return lruet(lang, "Для этой исторической пробы нет экспортированных измерений.", "Selle ajaloolise proovi mõõtmisi pole eksporditud.", "No exported measurements for this historical sample.");
    return `${lruet(lang, "Проба", "Proov", "Sample")}: ${fmtDate(item.sample_date)}\n${lruet(lang, "Показатели воды", "Vee näitajad", "Water measurements")}:\n${rows}`;
  };

  const severityLabel = (level: "good" | "warn" | "bad") => {
    return lruet(
      lang,
      level === "good" ? "ok" : level === "warn" ? "внимание" : "критично",
      level === "good" ? "ok" : level === "warn" ? "hoiatus" : "kriitiline",
      level === "good" ? "ok" : level === "warn" ? "warning" : "critical"
    );
  };
  const officialStatusText = (value: number | null) => {
    if (value === 1) return lruet(lang, "соответствует", "vastab", "compliant");
    if (value === 0) return lruet(lang, "нарушение", "rikkumine", "violation");
    return lruet(lang, "неизвестно", "teadmata", "unknown");
  };
  const placeKindLabel = (kind: string) => {
    const key = (kind || "other").toLowerCase();
    if (lang === "ru") {
      if (key === "swimming") return "Купальные воды";
      if (key === "pool_spa") return "Бассейн / SPA";
      if (key === "drinking_water") return "Питьевая вода (сеть)";
      if (key === "drinking_source") return "Источник питьевой воды";
      return "Другое";
    }
    if (lang === "et") {
      if (key === "swimming") return "Suplusvesi";
      if (key === "pool_spa") return "Bassein / SPA";
      if (key === "drinking_water") return "Joogivesi (võrk)";
      if (key === "drinking_source") return "Joogivee allikas";
      return "Muu";
    }
    if (key === "swimming") return "Open water";
    if (key === "pool_spa") return "Pool / SPA";
    if (key === "drinking_water") return "Drinking water (network)";
    if (key === "drinking_source") return "Drinking water source";
    return "Other";
  };

  const riskLabel = (r: string) => {
    if (r === "all") return lruet(lang, "Все", "Kõik", "All");
    if (r === "low") return lruet(lang, "Низкий", "Madal", "Low");
    if (r === "medium") return lruet(lang, "Средний", "Keskmine", "Medium");
    if (r === "high") return lruet(lang, "Высокий", "Kõrge", "High");
    return lruet(lang, "Неизвестно", "Teadmata", "Unknown");
  };

  const officialLabel = (s: string) => {
    if (s === "all") return lruet(lang, "Все", "Kõik", "All");
    if (s === "compliant") return lruet(lang, "Соответствует", "Vastab", "Compliant");
    if (s === "violation") return lruet(lang, "Нарушение", "Ei vasta", "Violation");
    return lruet(lang, "Неизвестно", "Teadmata", "Unknown");
  };

  const openInfo = (title: string, text: string) => {
    setInfoTitle(title);
    setInfoText(text);
    setInfoOpen(true);
  };

  const formatTimestamp = useCallback((raw: string | null | undefined): string | null => {
    if (!raw) return null;
    try {
      const dt = new Date(raw);
      if (Number.isNaN(dt.getTime())) return raw;
      return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) +
        " " + dt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false }) + " UTC";
    } catch {
      return raw;
    }
  }, []);

  const dataFetchedLabel = useMemo(() => formatTimestamp(snapshot.data_fetched_at ?? snapshot.generated_at), [snapshot.data_fetched_at, snapshot.generated_at, formatTimestamp]);
  const modelTrainedLabel = useMemo(() => formatTimestamp(snapshot.model_trained_at), [snapshot.model_trained_at, formatTimestamp]);

  const counties = useMemo(() => {
    const map = new Map<string, string>();
    snapshot.places.forEach((p) => {
      const raw = p.county || "Unknown";
      const key = countyKey(raw) || "unknown";
      if (!map.has(key)) map.set(key, countyPretty(raw) || "Unknown");
    });
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [snapshot.places]);

  const placeKinds = useMemo(() => {
    const vals = new Set<string>();
    snapshot.places.forEach((p) => vals.add(p.place_kind || "other"));
    return Array.from(vals).sort((a, b) => a.localeCompare(b));
  }, [snapshot.places]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    // When a county is selected, prefer geographic polygon containment so
    // every point physically inside that county is counted — even if its
    // `county` metadata field is empty or mismatched. Falls back to string
    // matching when the GeoJSON hasn't loaded yet.
    const countyFeature = county !== "all" ? findCountyFeature(county, countyGeoJson) : null;
    return snapshot.places.filter((p) => {
      if (segment !== "all") {
        if (p.place_kind !== segment) return false;
      }
      if (risk !== "all" && p.risk_level !== risk) return false;
      if (county !== "all") {
        if (countyFeature) {
          // Polygon-based: include any point geographically inside the county
          if (!pointInFeature(p.lon, p.lat, countyFeature)) return false;
        } else {
          // Fallback to string-based before GeoJSON loads
          if (countyKey(p.county || "Unknown") !== county) return false;
        }
      }
      if (official === "compliant" && p.official_compliant !== 1) return false;
      if (official === "violation" && p.official_compliant !== 0) return false;
      if (official === "unknown" && p.official_compliant !== null) return false;
      if (p.model_violation_prob !== null && p.model_violation_prob < minProb) return false;
      if (alertsOnly && !(p.risk_level === "high" || p.official_compliant === 0)) return false;
      if (nearbyOnly && userCoords) {
        if (distanceKm(userCoords.lat, userCoords.lon, p.lat, p.lon) > nearbyRadiusKm) return false;
      }
      if (sampleDateFrom || sampleDateTo) {
        const pointDate = fmtDate(p.sample_date);
        if (pointDate === "n/a") return false;
        if (sampleDateFrom && pointDate < sampleDateFrom) return false;
        if (sampleDateTo && pointDate > sampleDateTo) return false;
      }
      if (q && !p.search_text.includes(q)) return false;
      return true;
    });
  }, [snapshot.places, query, segment, risk, county, countyGeoJson, official, alertsOnly, nearbyOnly, userCoords, nearbyRadiusKm, minProb, sampleDateFrom, sampleDateTo]);
  const mapPlaces = useMemo(() => filtered.slice(0, isMobile ? 1200 : 3000), [filtered, isMobile]);

  // Counts restricted to what's currently rendered on the map (after the
  // other active filters). These feed the transient bubble shown when the
  // user taps the alerts / near-me icon on the mobile chip bar.
  const mapAlertsCount = useMemo(
    () => filtered.filter((p) => p.risk_level === "high" || p.official_compliant === 0).length,
    [filtered]
  );
  const mapNearMeCount = useMemo(() => {
    if (!userCoords) return null;
    return filtered.filter((p) => distanceKm(userCoords.lat, userCoords.lon, p.lat, p.lon) <= nearbyRadiusKm).length;
  }, [filtered, userCoords, nearbyRadiusKm]);

  // Auto-fit map to visible places whenever filters produce a meaningful subset.
  // Derived as a string key (no setState in effect) — FitBoundsOnVersion reacts to key changes.
  const fitBoundsKey = useMemo(() => {
    if (filtered.length === 0 || filtered.length === snapshot.places.length) return "";
    const firstId = filtered[0]?.id ?? "";
    const lastId = filtered[filtered.length - 1]?.id ?? "";
    // Include the search query so the map re-targets the first match every
    // time the user types — even if other filters keep the same set.
    return `${filtered.length}:${firstId}:${lastId}:${query.trim().toLowerCase()}`;
  }, [filtered, snapshot.places.length, query]);

  // When an active text search is in play, center on the FIRST match instead
  // of fitting all matches — that's what users expect on mobile when they
  // type a place name. Otherwise fit the full set as before.
  const fitBoundsPlaces = useMemo<[number, number][]>(() => {
    if (query.trim().length > 0 && filtered.length > 0) {
      return [[filtered[0].lat, filtered[0].lon]];
    }
    return filtered.map((p) => [p.lat, p.lon]);
  }, [filtered, query]);

  useEffect(() => {
    track("dashboard_open", { places_count: snapshot.places_count, has_model: snapshot.has_model_predictions });
  }, [snapshot.places_count, snapshot.has_model_predictions]);

  const toastFiredRef = useRef(false);
  useEffect(() => {
    if (!isMobile || toastFiredRef.current) return;
    toastFiredRef.current = true;
    const totalPlaces = snapshot.places.length;
    const totalViolations = snapshot.places.filter((p) => p.official_compliant === 0).length;
    const msg = lruet(
      lang,
      `${totalPlaces} точек · ${totalViolations} нарушений`,
      `${totalPlaces} punkti · ${totalViolations} rikkumist`,
      `${totalPlaces} points · ${totalViolations} violations`
    );
    const timer = setTimeout(() => setToast(msg), 300);
    return () => clearTimeout(timer);
  }, [isMobile, lang, snapshot.places]);

  useEffect(() => {
    pushHeaderLang(lang);
  }, [lang]);

  // Close the header language dropdown when clicking outside or pressing Esc.
  useEffect(() => {
    if (!langMenuOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!langMenuRef.current) return;
      if (!langMenuRef.current.contains(event.target as Node)) setLangMenuOpen(false);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setLangMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [langMenuOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("water.watchlist.v1", JSON.stringify(watchlist));
  }, [watchlist]);

  useEffect(() => {
    const t = setTimeout(() => setMinProb(minProbInput), 120);
    return () => clearTimeout(t);
  }, [minProbInput]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.classList.remove("cyr-ibm", "cyr-manrope");
    document.body.classList.add(cyrillicFont === "manrope" ? "cyr-manrope" : "cyr-ibm");
    if (typeof window !== "undefined") {
      window.localStorage.setItem("water.ui.cyrillic-font.v1", cyrillicFont);
    }
  }, [cyrillicFont]);

  // Persist + apply theme to <html data-theme>. Light is the implicit
  // default — the attribute is only set when dark is requested, which
  // mirrors the inline FOUC-avoidance script in layout.tsx.
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (theme === "dark") document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
    if (typeof window !== "undefined") {
      window.localStorage.setItem("water.ui.theme.v1", theme);
    }
  }, [theme]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 900px)");
    const apply = () => {
      const nextIsMobile = mq.matches;
      setIsMobile(nextIsMobile);
      if (nextIsMobile && !mobileFullscreenInitializedRef.current) {
        setIsMapFullscreen(true);
        setMobilePanelState("collapsed");
        mobileFullscreenInitializedRef.current = true;
      }
    };
    // First run — initial state may already be correct, but re-running
    // is cheap and ensures the fullscreen-init effect fires.
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  // Load county GeoJSON once. Shared with MapClient (via prop) so both
  // polygon-based county filtering in `filtered` and overlay rendering
  // use the same data without duplicate fetches.
  useEffect(() => {
    if (countyGeoJson) return;
    let alive = true;
    const idle = (cb: () => void) => {
      const ric = (window as unknown as { requestIdleCallback?: (fn: () => void, opts?: { timeout: number }) => number }).requestIdleCallback;
      if (typeof ric === "function") return ric(cb, { timeout: 2000 });
      return window.setTimeout(cb, 300);
    };
    const cancelIdle = (id: number) => {
      const cic = (window as unknown as { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback;
      if (typeof cic === "function") cic(id);
      else window.clearTimeout(id);
    };
    const handle = idle(() => {
      if (!alive) return;
      fetch("/data/estonia_counties_simplified.geojson", { cache: "force-cache" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (alive) setCountyGeoJson(d); })
        .catch(() => { if (alive) setCountyGeoJson(null); });
    });
    return () => { alive = false; cancelIdle(handle); };
  }, [countyGeoJson]);

  // Track the on-screen keyboard via VisualViewport so map focus calls
  // can offset the marker above the IME / bottom sheet.
  const [keyboardOffset, setKeyboardOffset] = useState(0);
  const [viewportHeight, setViewportHeight] = useState<number>(() =>
    typeof window === "undefined" ? 800 : window.innerHeight
  );
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onResize = () => setViewportHeight(window.innerHeight);
    onResize();
    window.addEventListener("resize", onResize);
    const vv = window.visualViewport;
    const onVvChange = () => {
      if (!vv) return;
      const diff = window.innerHeight - (vv.height + vv.offsetTop);
      setKeyboardOffset(diff > 80 ? diff : 0);
    };
    onVvChange();
    vv?.addEventListener("resize", onVvChange);
    vv?.addEventListener("scroll", onVvChange);
    return () => {
      window.removeEventListener("resize", onResize);
      vv?.removeEventListener("resize", onVvChange);
      vv?.removeEventListener("scroll", onVvChange);
    };
  }, []);

  // Combined "obscured pixels at the bottom" = sheet height + keyboard.
  // Used by the map to keep selected markers above sheet / IME.
  //
  // These constants MUST stay in sync with `.mobileBottomSheet` in
  // globals.css — otherwise FocusOnSelectedPoint will over/under-shoot and
  // the selected pin slides out of view when the sheet opens.
  //   - own height:           92dvh        (≈ 0.92 × innerHeight)
  //   - half translateY:      46% of own   (→ visible = 54% of own)
  //   - full translateY:      6rem + safe-area-inset-top
  //   - collapsed translateY: 100% - 84px - safe-area-inset-bottom
  // Previous values (0.5*vh for half, 0.55*vh for full, 72 for collapsed)
  // were ballpark — the "full" one was off by ~30 percentage points of vh,
  // hiding the pin behind the expanded sheet.
  const mobileBottomOverlayPx = useMemo(() => {
    if (!isMobile) return 0;
    const sheetOwnHeight = viewportHeight * 0.92;
    const sheetPx =
      mobilePanelState === "full"
        ? Math.max(0, Math.round(sheetOwnHeight - 96))
        : mobilePanelState === "half"
          ? Math.round(sheetOwnHeight * 0.54)
          : 84;
    return sheetPx + keyboardOffset;
  }, [isMobile, mobilePanelState, viewportHeight, keyboardOffset]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const onFullscreenChange = () => {
      setIsMapFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.classList.toggle("mapFullscreenActive", isMapFullscreen);
    return () => document.body.classList.remove("mapFullscreenActive");
  }, [isMapFullscreen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onScroll = () => setHeaderCompact(window.scrollY > 56);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    track("filters_changed", {
      segment,
      risk,
      county,
      official,
      alerts_only: alertsOnly,
      nearby_only: nearbyOnly,
      nearby_radius_km: nearbyOnly ? nearbyRadiusKm : null,
      min_prob: Number(minProb.toFixed(2)),
      sample_date_from: sampleDateFrom || null,
      sample_date_to: sampleDateTo || null,
      query_length: query.length,
      visible_count: filtered.length
    });
  }, [segment, risk, county, official, alertsOnly, nearbyOnly, nearbyRadiusKm, minProb, sampleDateFrom, sampleDateTo, query, filtered.length]);

  const low = filtered.filter((x) => x.risk_level === "low").length;
  const high = filtered.filter((x) => x.risk_level === "high").length;
  const violations = filtered.filter((x) => x.official_compliant === 0).length;

  const avgProb = useMemo(() => {
    const vals = filtered.map((x) => x.model_violation_prob).filter((v): v is number => v !== null);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }, [filtered]);

  const healthIndex = useMemo(() => {
    if (!filtered.length) return 0;
    const officialPassShare = filtered.filter((x) => x.official_compliant === 1).length / filtered.length;
    const modelSafety = avgProb === null ? 0.5 : 1 - avgProb;
    return Math.round((officialPassShare * 0.6 + modelSafety * 0.4) * 100);
  }, [filtered, avgProb]);

  const prognosis = lruet(
    lang,
    healthIndex >= 80 ? "Отлично" : healthIndex >= 65 ? "Стабильно" : healthIndex >= 45 ? "Нужен контроль" : "Критично",
    healthIndex >= 80 ? "Väga hea" : healthIndex >= 65 ? "Stabiilne" : healthIndex >= 45 ? "Vajab jälgimist" : "Kriitiline",
    healthIndex >= 80 ? "Excellent" : healthIndex >= 65 ? "Stable" : healthIndex >= 45 ? "Watch closely" : "Critical focus"
  );

  const domainStats = useMemo(() => {
    const counts: Record<string, { total: number; violations: number; highRisk: number }> = {};
    filtered.forEach((p) => {
      const key = p.domain;
      if (!counts[key]) counts[key] = { total: 0, violations: 0, highRisk: 0 };
      counts[key].total += 1;
      if (p.official_compliant === 0) counts[key].violations += 1;
      if (p.risk_level === "high") counts[key].highRisk += 1;
    });
    return Object.entries(counts).sort((a, b) => b[1].total - a[1].total);
  }, [filtered]);

  const topAlerts = useMemo(() => {
    return filtered
      .filter((p) => p.official_compliant === 0 || p.risk_level === "high")
      .sort((a, b) => {
        const ap = a.model_violation_prob ?? (a.risk_level === "high" ? 1 : 0);
        const bp = b.model_violation_prob ?? (b.risk_level === "high" ? 1 : 0);
        return bp - ap;
      })
      .slice(0, 8);
  }, [filtered]);

  const selectedPlace = useMemo(() => {
    if (!selectedId) return null;
    return snapshot.places.find((p) => p.id === selectedId) || null;
  }, [selectedId, snapshot.places]);

  // Resolved places for a tapped co-located cluster (bottom-sheet list).
  const clusterPlaces = useMemo(() => {
    if (!clusterPlaceIds || clusterPlaceIds.length === 0) return null;
    const idSet = new Set(clusterPlaceIds);
    return snapshot.places.filter((p) => idSet.has(p.id));
  }, [clusterPlaceIds, snapshot.places]);

  const watchlistPlaces = useMemo(() => {
    const byId = new Set(watchlist);
    return snapshot.places.filter((p) => byId.has(p.id));
  }, [watchlist, snapshot.places]);


  const quickInsights = useMemo(() => {
    const coverage = snapshot.diagnostics.model_coverage_share;
    const violation = snapshot.diagnostics.official_violation_share;
    const avg = avgProb;
    return [
      {
        key: "coverage",
        label: lruet(lang, "Покрытие модели", "Mudeli katvus", "Model coverage"),
        value: `${(coverage * 100).toFixed(1)}%`,
        level: coverage >= 0.9 ? "good" : coverage >= 0.6 ? "warn" : "bad",
        hint:
          lang === "ru"
            ? "Доля точек, где есть прогноз ML."
            : "Punktide osakaal, kus ML-prognoos on olemas."
      },
      {
        key: "official_violation",
        label: lruet(lang, "Офиц. нарушения", "Ametlikud rikkumised", "Official violations"),
        value: violation === null ? "n/a" : `${(violation * 100).toFixed(1)}%`,
        level: violation === null ? "warn" : violation <= 0.08 ? "good" : violation <= 0.15 ? "warn" : "bad",
        hint:
          lang === "ru"
            ? "Доля точек с официально зафиксированным нарушением."
            : "Ametliku rikkumisega punktide osakaal."
      },
      {
        key: "avg_model_risk",
        label: lruet(lang, "Средний риск модели", "Keskmine mudelirisk", "Average model risk"),
        value: avg === null ? "n/a" : avg.toFixed(2),
        level: avg === null ? "warn" : avg < 0.35 ? "good" : avg < 0.6 ? "warn" : "bad",
        hint:
          lang === "ru"
            ? "Средняя P(нарушения) по текущему фильтру."
            : "Keskmine P(rikkumine) aktiivse filtri all."
      }
    ] as const;
  }, [snapshot.diagnostics.model_coverage_share, snapshot.diagnostics.official_violation_share, avgProb, lang]);

  const parameterCards = useMemo(
    () => [
      {
        key: "e_coli",
        icon: "🧫",
        ruTitle: "E. coli",
        etTitle: "E. coli",
        ruImpact: "SHAP 0.312 — топ-5 предиктор",
        etImpact: "SHAP 0.312 — top-5 ennustaja",
        enImpact: "SHAP 0.312 — top-5 predictor",
        ruWhy:
          "Прямой маркер фекального загрязнения (норма: ≤500 КОЕ для купания, 0 для питьевой воды). При превышении риск кишечных инфекций резко растёт. В нашем корпусе (69 536 проб) e_coli > 500 практически гарантирует нарушение.",
        etWhy:
          "Otsene fekaalreostuse marker (norm: ≤500 PMÜ suplusvees, 0 joogivees). Ületamisel soolenakkuse risk kasvab järsult. 69 536 proovist e_coli > 500 tähendab peaaegu alati rikkumist.",
        enWhy:
          "Direct fecal contamination marker (norm: ≤500 CFU bathing, 0 drinking). Exceeding the threshold almost guarantees a violation in our 69,536-probe corpus."
      },
      {
        key: "enterococci",
        icon: "🧪",
        ruTitle: "Enterococci",
        etTitle: "Enterokokid",
        ruImpact: "Высокий для рекреации",
        etImpact: "Kõrge rekreatsioonivees",
        enImpact: "High for recreational water",
        ruWhy:
          "Ключевой микробиологический показатель EU Bathing Water Directive 2006/7/EC (норма: ≤200 КОЕ). Устойчивее E. coli к хлорированию — важный дополнительный индикатор в морской воде.",
        etWhy:
          "EL suplusvee direktiivi 2006/7/EC põhinäitaja (norm: ≤200 PMÜ). Kloorimisele vastupidavam kui E. coli — oluline lisaindikaator merevees.",
        enWhy:
          "Key indicator per EU Bathing Water Directive 2006/7/EC (norm: ≤200 CFU). More resistant to chlorination than E. coli — important complementary marker."
      },
      {
        key: "ph",
        icon: "⚖️",
        ruTitle: "pH",
        etTitle: "pH",
        ruImpact: "Системный параметр",
        etImpact: "Süsteemne parameeter",
        enImpact: "Systemic parameter",
        ruWhy:
          "Норма: 6.0–9.0 (купание), 6.5–8.5 (бассейн). Влияет на коррозию труб, эффективность хлора и комфорт. При pH < 6.5 хлор менее эффективен; при pH > 8.5 кожа и глаза раздражаются.",
        etWhy:
          "Norm: 6.0–9.0 (suplus), 6.5–8.5 (bassein). Mõjutab torude korrosiooni, kloori efektiivsust ja mugavust. pH < 6.5: kloor vähem efektiivne; pH > 8.5: naha ja silmade ärritus.",
        enWhy:
          "Norm: 6.0–9.0 (bathing), 6.5–8.5 (pools). Affects pipe corrosion, chlorine efficacy and comfort. Low pH reduces disinfection; high pH irritates skin and eyes."
      },
      {
        key: "nitrates",
        icon: "🌾",
        ruTitle: "Nitrates",
        etTitle: "Nitraadid",
        ruImpact: "Высокий для питьевой воды",
        etImpact: "Kõrge joogivees",
        enImpact: "High for drinking water",
        ruWhy:
          "Норма: ≤50 мг/л (EU 2020/2184). Поступают из удобрений и сточных вод. Опасны для младенцев (метгемоглобинемия). В нашем аудите нитраты — один из «периодических» параметров: измеряются квартально, не в каждой пробе.",
        etWhy:
          "Norm: ≤50 mg/l (EU 2020/2184). Pärinevad väetistest ja reoveest. Ohtlik imikutele (methemoglobineemia). Meie auditi järgi mõõdetakse nitraate kvartaalselt, mitte igas proovis.",
        enWhy:
          "Norm: ≤50 mg/l (EU 2020/2184). From fertilizers and wastewater. Dangerous for infants (methemoglobinemia). Our audit shows nitrates are measured quarterly, not in every probe."
      },
      {
        key: "free_chlorine",
        icon: "🏊",
        ruTitle: "Free chlorine",
        etTitle: "Vaba kloor",
        ruImpact: "Критичный в бассейнах",
        etImpact: "Basseinides kriitiline",
        enImpact: "Critical for pools",
        ruWhy:
          "Диапазон: 0.5–1.5 мг/л (Sotsiaalministri 49/2019, Lisa 4). Мало хлора → микробы; много → раздражение кожи и глаз. Наш аудит обнаружил, что прежний диапазон [0.2–0.6] был ошибочным — 288 ложных срабатываний исправлены.",
        etWhy:
          "Vahemik: 0.5–1.5 mg/l (Sotsiaalministri 49/2019, Lisa 4). Liiga vähe kloori → mikroobid; liiga palju → ärritus. Meie audit leidis, et varasem vahemik [0.2–0.6] oli vale — 288 valepositiivset parandatud.",
        enWhy:
          "Range: 0.5–1.5 mg/l (Estonian reg. 49/2019, Annex 4). Too low → pathogens; too high → irritation. Our audit found the previous [0.2–0.6] range was wrong — 288 false positives fixed."
      },
      {
        key: "turbidity",
        icon: "🌫️",
        ruTitle: "Turbidity",
        etTitle: "Hägusus",
        ruImpact: "Средний, усиливает другие риски",
        etImpact: "Keskmine, võimendab teisi riske",
        enImpact: "Medium, amplifies other risks",
        ruWhy:
          "Норма: ≤4 NTU (питьевая), ≤0.5 NTU (бассейн, в 8× строже). Мутная вода скрывает патогены и снижает эффективность UV/хлора. Чем выше мутность, тем менее надёжна дезинфекция.",
        etWhy:
          "Norm: ≤4 NTU (joogivesi), ≤0.5 NTU (bassein, 8× rangem). Hägune vesi varjab patogeene ja vähendab UV/kloori efektiivsust.",
        enWhy:
          "Norm: ≤4 NTU (drinking), ≤0.5 NTU (pool — 8x stricter). Turbid water hides pathogens and reduces UV/chlorine efficacy."
      },
      {
        key: "iron",
        icon: "🔩",
        ruTitle: "Iron",
        etTitle: "Raud",
        ruImpact: "SHAP 1.217 — #1 предиктор",
        etImpact: "SHAP 1.217 — #1 ennustaja",
        enImpact: "SHAP 1.217 — #1 predictor",
        ruWhy:
          "Норма: ≤0.2 мг/л. Самый сильный предиктор нарушений (SHAP 1.217). Частая причина несоответствий в сетях водоснабжения Эстонии — природное железо из подземных вод.",
        etWhy:
          "Norm: ≤0.2 mg/l. Tugevaim rikkumiste ennustaja (SHAP 1.217). Sage mittevastavuse põhjus Eesti veevärkides — looduslik raud põhjaveest.",
        enWhy:
          "Norm: ≤0.2 mg/l. Strongest violation predictor (SHAP 1.217). Frequent cause of non-compliance in Estonian water networks — natural iron from groundwater."
      },
      {
        key: "coliforms",
        icon: "🔬",
        ruTitle: "Coliforms",
        etTitle: "Kolibakterid",
        ruImpact: "SHAP 0.591 — топ-3 предиктор",
        etImpact: "SHAP 0.591 — top-3 ennustaja",
        enImpact: "SHAP 0.591 — top-3 predictor",
        ruWhy:
          "Норма: 0 КОЕ/100 мл (питьевая вода, EU 2020/2184). Широкая группа бактерий, включающая E. coli. Измеряется чаще всех параметров (1 439 из 2 196 точек). Обнаружение при отсутствии E. coli указывает на недостаточную дезинфекцию.",
        etWhy:
          "Norm: 0 PMÜ/100 ml (joogivesi, EU 2020/2184). Lai bakterirühm, hõlmab E. coli. Mõõdetakse sagedamini kui ükski teine parameeter. Positiivne tulemus ilma E. coli'ta viitab ebapiisavale desinfitseerimisele.",
        enWhy:
          "Norm: 0 CFU/100ml (drinking, EU 2020/2184). Broad bacterial group including E. coli. Most frequently measured parameter. Detection without E. coli indicates insufficient disinfection."
      }
    ],
    []
  );

  const toggleWatch = (id: string) => {
    setWatchlist((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const clearFilters = () => {
    setQuery("");
    setSegment("all");
    setRisk("all");
    setCounty("all");
    setOfficial("all");
    setAlertsOnly(false);
    setSampleDateFrom("");
    setSampleDateTo("");
    setMinProb(0);
    setMinProbInput(0);
    setNearbyOnly(false);
    setNearbyRadiusKm(10);
    setGeoError(null);
  };

  // Pop a short-lived count bubble above the map. Self-cleans after ~1.8s
  // so no extra interaction is needed — the user just sees "N alerts on map"
  // fade in and out.
  const countBubbleSeqRef = useRef(0);
  const showCountBubble = useCallback((text: string) => {
    const seq = ++countBubbleSeqRef.current;
    setCountBubble({ seq, text });
    window.setTimeout(() => {
      setCountBubble((cur) => (cur && cur.seq === seq ? null : cur));
    }, 1800);
  }, []);

  const activateNearMe = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoError(t.geoUnsupported);
      return;
    }
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserCoords({ lat: position.coords.latitude, lon: position.coords.longitude });
        setNearbyOnly(true);
      },
      () => {
        setGeoError(t.geoDenied);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  const selectPoint = useCallback((id: string) => {
    setSelectedId(id);
    setClusterPlaceIds(null); // clear cluster list when a specific place is picked
    if (isMobile) {
      setSheetMode("place");
      setMobilePanelState("half");
      // Map stays fullscreen — Google Maps style
    }
  }, [isMobile]);

  // Called when a co-located cluster is tapped on mobile. Shows the
  // cluster's children as a pick-list in the bottom sheet instead of
  // spiderfying (which collapses on touch-driven map moves).
  const handleClusterSelect = useCallback((ids: string[]) => {
    setClusterPlaceIds(ids);
    setSelectedId(null);
    if (isMobile) {
      setSheetMode("place");
      setMobilePanelState("half");
    }
  }, [isMobile]);

  const handleCountySelect = useCallback((c: string) => {
    setCounty((prev) => (countyKey(prev) === countyKey(c) ? "all" : countyKey(c)));
  }, []);

  const toggleMapFullscreen = useCallback(async () => {
    if (typeof document === "undefined") return;
    const target = mapPanelRef.current;
    if (!target) return;
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch {
        setIsMapFullscreen(false);
      }
      return;
    }
    if (isMapFullscreen) {
      setIsMapFullscreen(false);
      return;
    }
    if (target.requestFullscreen) {
      try {
        await target.requestFullscreen();
        return;
      } catch {
        // Fullscreen API can fail in some Android WebViews, fallback to CSS overlay.
      }
    }
    setIsMapFullscreen(true);
  }, [isMapFullscreen]);

  const cycleMobilePanelState = () => {
    setMobilePanelState((prev) => {
      if (prev === "collapsed") {
        // Only open if there's something to show (filter mode always has content)
        if (sheetMode === "filter" || selectedPlace) return "half";
        // No place selected in place mode → open filter instead
        setSheetMode("filter");
        return "half";
      }
      return prev === "half" ? "full" : "collapsed";
    });
  };

  // Auto-collapse sheet when in place mode but nothing is selected
  // (and no cluster list is open either).
  // Deferred via setTimeout to avoid calling setState synchronously in an effect body.
  useEffect(() => {
    if (mobilePanelState !== "collapsed" && sheetMode === "place" && !selectedPlace && !clusterPlaces) {
      const t = window.setTimeout(() => setMobilePanelState("collapsed"), 0);
      return () => window.clearTimeout(t);
    }
  }, [mobilePanelState, sheetMode, selectedPlace, clusterPlaces]);

  const onSheetPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    sheetDragStartY.current = e.clientY;
    sheetDragLastY.current = e.clientY;
    sheetDragLastTs.current = performance.now();
    sheetDragVelocity.current = 0;
    setSheetDragging(true);
    setSheetDragOffset(0);
  };

  const onSheetPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (sheetDragStartY.current === null) return;
    const delta = e.clientY - sheetDragStartY.current;
    const now = performance.now();
    if (sheetDragLastY.current !== null && sheetDragLastTs.current !== null) {
      const dy = e.clientY - sheetDragLastY.current;
      const dt = Math.max(1, now - sheetDragLastTs.current);
      sheetDragVelocity.current = dy / dt;
    }
    sheetDragLastY.current = e.clientY;
    sheetDragLastTs.current = now;
    setSheetDragOffset(delta);
  };

  const onSheetPointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    setSheetDragging(false);
    if (sheetDragStartY.current === null) {
      setSheetDragOffset(0);
      cycleMobilePanelState();
      return;
    }
    const delta = e.clientY - sheetDragStartY.current;
    const fling = sheetDragVelocity.current;
    sheetDragStartY.current = null;
    sheetDragLastY.current = null;
    sheetDragLastTs.current = null;
    sheetDragVelocity.current = 0;
    setSheetDragOffset(0);
    if (Math.abs(delta) < 14 && Math.abs(fling) < 0.4) {
      cycleMobilePanelState();
      return;
    }
    if (delta < -24 || fling < -0.65) {
      setMobilePanelState((prev) => (prev === "collapsed" ? "half" : "full"));
    } else if (delta > 24 || fling > 0.65) {
      setMobilePanelState((prev) => (prev === "full" ? "half" : "collapsed"));
    } else {
      cycleMobilePanelState();
    }
  };

  return (
    <div className={`dashboard ${filtersPinned ? "dashboardPinned" : ""}`}>
      {toast ? <div className="toastBanner">{toast}</div> : null}
      {countBubble ? (
        <div key={countBubble.seq} className="countBubble" aria-live="polite">
          {countBubble.text}
        </div>
      ) : null}

      {showLangDialog ? (
        <div className="langDialogBackdrop">
          <div className="langDialogCard panel">
            <p className="langDialogTitle">Choose language / Выберите язык</p>
            <p className="langDialogHint">Keel / Language / Язык</p>
            <div className="langDialogButtons">
              <button className="btn" onClick={() => chooseLang("et")}>Eesti</button>
              <button className="btn" onClick={() => chooseLang("ru")}>Русский</button>
              <button className="btn" onClick={() => chooseLang("en")}>English</button>
            </div>
          </div>
        </div>
      ) : null}

      <div className={`topBar unifiedTopBar desktopOnly ${headerCompact ? "compact" : ""}`}>
        <div className="brandBlock unifiedBrandBlock" style={{ display: "flex" }}>
          <Image src="/logo.svg" alt="H2O Atlas logo" className="brandLogo unifiedBrandLogo" width={36} height={36} priority />
          <div className="unifiedBrandText">
            <div className="unifiedBrandTitle">H2O Atlas</div>
            <p className="subtitle unifiedBrandSubtitle">
              <LocalizedSubtitle />
            </p>
          </div>
        </div>
        <div className="topBarControls">
          {/* Single info entry point — opens the floating info pane that
              hosts all three informational tabs (About Model / About
              Service / Diagnostics). Keeping the header lean prevents
              the buttons from competing with the map for attention. */}
          <button
            className="btn headerInfoNav headerInfoNavPrimary"
            onClick={() => { setInfoPageOpen(true); setInfoPageTab("aboutModel"); }}
          >
            <span className="headerInfoNavIcon" aria-hidden="true">
              <Icon name="info" />
            </span>
            {t.tabs.aboutModel}
          </button>
          <div className="headerDivider" aria-hidden="true" />
          {/* Language dropdown (replaces 3 flat ET/EN/RU pills) */}
          <div className="langDropdown" ref={langMenuRef}>
            <button
              type="button"
              className={`btn langDropdownBtn ${langMenuOpen ? "langDropdownBtnOpen" : ""}`}
              onClick={() => setLangMenuOpen((v) => !v)}
              aria-haspopup="listbox"
              aria-expanded={langMenuOpen}
              aria-label={lruet(lang, "Выбрать язык", "Vali keel", "Select language")}
              title={lruet(lang, "Выбрать язык", "Vali keel", "Select language")}
            >
              <span className="langDropdownGlobe" aria-hidden="true">
                <Icon name="globe" />
              </span>
              <span className="langDropdownCurrent">{lang.toUpperCase()}</span>
              <span className={`langDropdownChevron ${langMenuOpen ? "open" : ""}`} aria-hidden="true">
                <Icon name="chevron-down" />
              </span>
            </button>
            {langMenuOpen ? (
              <div className="langDropdownMenu" role="listbox">
                {(
                  [
                    { code: "et", label: "Eesti", short: "ET" },
                    { code: "en", label: "English", short: "EN" },
                    { code: "ru", label: "Русский", short: "RU" }
                  ] as const
                ).map((opt) => (
                  <button
                    key={`lang-opt-${opt.code}`}
                    type="button"
                    className={`langDropdownItem ${lang === opt.code ? "active" : ""}`}
                    role="option"
                    aria-selected={lang === opt.code}
                    onClick={() => {
                      setLang(opt.code);
                      pushHeaderLang(opt.code);
                      setLangMenuOpen(false);
                    }}
                  >
                    <span className="langDropdownItemShort">{opt.short}</span>
                    <span className="langDropdownItemLabel">{opt.label}</span>
                    {lang === opt.code ? (
                      <span className="langDropdownItemTick" aria-hidden="true">
                        <Icon name="check-circle" />
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* Mobile-only Google Maps-style search bar.
          Rendered unconditionally so the initial paint already matches the
          viewport. Visibility is controlled by `.gmSearchBar` (display:none
          by default → display:flex inside @media (max-width: 900px)). */}
      <>
          <div className="gmSearchBar">
            <button
              className="gmSearchMenuBtn"
              onClick={() => { setSheetMode("filter"); setMobilePanelState(mobilePanelState === "collapsed" ? "half" : mobilePanelState); }}
              aria-label={t.filters}
            >
              <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" aria-hidden="true">
                <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>
            <svg className="gmSearchIconSvg" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="22" y2="22"/>
            </svg>
            <input
              className="gmSearchInput"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={lruet(lang, "Поиск места...", "Otsi kohta...", "Search place...")}
              aria-label={lruet(lang, "Поиск места", "Otsi kohta", "Search place")}
              inputMode="search"
              enterKeyHint="search"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
            />
            {query ? (
              <button className="gmSearchClearBtn" onClick={() => setQuery("")} aria-label="Clear">
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            ) : null}
            <div className="gmSearchDivider" />
            <button
              className={`gmSearchLocateBtn ${nearbyOnly ? "active" : ""}`}
              onClick={activateNearMe}
              aria-label={t.nearMe}
            >
              <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="3" fill="currentColor" fillOpacity="0.35"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/><circle cx="12" cy="12" r="9"/>
              </svg>
            </button>
            <button
              className="gmSearchInfoBtn"
              onClick={() => { setInfoPageOpen(true); setInfoPageTab("aboutService"); }}
              aria-label="Info"
            >
              <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <circle cx="12" cy="12" r="10" fill="currentColor" opacity="0.18" />
                <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
                <circle cx="12" cy="7.6" r="1.4" fill="currentColor" />
                <rect x="10.7" y="10.4" width="2.6" height="7.2" rx="1.1" fill="currentColor" />
                <path d="M0 0z"/>
              </svg>
            </button>
          </div>
          {/* Domain filter chips — icon-only on mobile to keep the bar short
              and easy to tap. Each chip carries an aria-label/title with the
              localized name so screen readers and long-press tooltips still
              surface the meaning. */}
          <div className="gmChipBar" role="toolbar" aria-label={t.filters}>
            {(() => {
              const allLabel = lruet(lang, "Все", "Kõik", "All");
              const countText = lruet(
                lang,
                `Все точки: ${filtered.length}`,
                `Kõik punktid: ${filtered.length}`,
                `All points: ${filtered.length}`
              );
              return (
                <button
                  type="button"
                  className={`gmChip gmChipIcon ${segment === "all" ? "gmChipActive" : ""}`}
                  onClick={() => {
                    setSegment("all");
                    showCountBubble(countText);
                  }}
                  aria-label={allLabel}
                  aria-pressed={segment === "all"}
                  title={allLabel}
                  data-tooltip={allLabel}
                >
                  <Icon name="grid" />
                </button>
              );
            })()}
            {(["swimming", "pool_spa", "drinking_water", "drinking_source"] as const).map((k) => {
              const iconName: IconName =
                k === "swimming" ? "swim" : k === "pool_spa" ? "pool" : k === "drinking_water" ? "tap" : "drop";
              const label =
                k === "swimming"
                  ? lruet(lang, "Купальные", "Suplusvesi", "Swimming")
                  : k === "pool_spa"
                  ? lruet(lang, "Бассейны", "Basseinid", "Pools")
                  : k === "drinking_water"
                  ? lruet(lang, "Питьевая", "Joogivesi", "Drinking")
                  : lruet(lang, "Источники", "Allikad", "Sources");
              const domainCount = snapshot.places.filter((p) => p.place_kind === k).length;
              return (
                <button
                  key={`chip-${k}`}
                  type="button"
                  className={`gmChip gmChipIcon ${segment === k ? "gmChipActive" : ""}`}
                  onClick={() => {
                    const next = segment === k ? "all" : k;
                    setSegment(next);
                    showCountBubble(`${label}: ${domainCount}`);
                  }}
                  aria-label={label}
                  aria-pressed={segment === k}
                  title={label}
                  data-tooltip={label}
                >
                  <Icon name={iconName} />
                </button>
              );
            })}
            {(() => {
              // Mobile alerts icon: toggles the `alertsOnly` filter (parity
              // with the desktop chip bar). Active state reflects whether
              // the filter is currently on, and a count bubble flashes the
              // number of alerts currently visible on the map.
              const alertsLabel = alertsOnly
                ? lruet(lang, "Снять фильтр тревог", "Eemalda häirete filter", "Clear alerts filter")
                : lruet(lang, "Только тревоги", "Ainult häired", "Alerts only");
              return (
                <button
                  type="button"
                  className={`gmChip gmChipIcon gmChipAlert ${alertsOnly ? "gmChipActive" : ""}`}
                  onClick={() => {
                    setAlertsOnly((v) => !v);
                    showCountBubble(
                      lruet(
                        lang,
                        `Тревог на карте: ${mapAlertsCount}`,
                        `Häireid kaardil: ${mapAlertsCount}`,
                        `Alerts on map: ${mapAlertsCount}`
                      )
                    );
                  }}
                  aria-label={alertsLabel}
                  aria-pressed={alertsOnly}
                  title={alertsLabel}
                  data-tooltip={alertsLabel}
                >
                  <Icon name="alert" />
                </button>
              );
            })()}
            {(() => {
              // Mobile near-me icon: toggles `nearbyOnly` filter (parity
              // with the desktop chip bar). If the user hasn't granted
              // location yet, we request it first and show the appropriate
              // bubble; otherwise we toggle the filter and flash a count
              // bubble with how many points remain within the radius.
              const nearLabel = nearbyOnly
                ? lruet(lang, "Снять фильтр «рядом»", "Eemalda läheduse filter", "Clear near-me filter")
                : lruet(lang, "Рядом со мной", "Minu lähedal", "Near me");
              return (
                <button
                  type="button"
                  className={`gmChip gmChipIcon ${nearbyOnly ? "gmChipActive" : ""}`}
                  onClick={() => {
                    if (nearbyOnly) {
                      setNearbyOnly(false);
                      setGeoError(null);
                    } else if (userCoords) {
                      setNearbyOnly(true);
                      setGeoError(null);
                    } else {
                      activateNearMe();
                      showCountBubble(
                        lruet(
                          lang,
                          "Определяем местоположение…",
                          "Määrame asukohta…",
                          "Finding your location…"
                        )
                      );
                      return;
                    }
                    const n = mapNearMeCount ?? 0;
                    showCountBubble(
                      lruet(
                        lang,
                        `Рядом на карте: ${n}`,
                        `Läheduses kaardil: ${n}`,
                        `Near me on map: ${n}`
                      )
                    );
                  }}
                  aria-label={nearLabel}
                  aria-pressed={nearbyOnly}
                  title={nearLabel}
                  data-tooltip={nearLabel}
                >
                  <Icon name="locate" />
                </button>
              );
            })()}
            {risk !== "all" ? (
              <button
                type="button"
                className="gmChip gmChipIcon gmChipActive"
                onClick={() => setRisk("all")}
                aria-label={lruet(lang, "Сбросить риск", "Lähtesta risk", "Clear risk filter")}
                title={lruet(lang, "Сбросить риск", "Lähtesta risk", "Clear risk filter")}
                data-tooltip={lruet(lang, "Сбросить риск", "Lähtesta risk", "Clear risk filter")}
              >
                <Icon name="signal" />
              </button>
            ) : null}
            <button
              type="button"
              className="gmChip gmChipIcon gmChipClear"
              onClick={clearFilters}
              aria-label={t.clearFilters}
              title={t.clearFilters}
              data-tooltip={t.clearFilters}
            >
              <Icon name="filter-x" />
            </button>
          </div>
        </>

      {drawerOpen && !filtersPinned ? <div className="drawerBackdrop" onClick={() => setDrawerOpen(false)} /> : null}
      <aside className={`drawer panel ${drawerOpen || filtersPinned ? "open" : ""} ${filtersPinned ? "pinned" : ""}`}>
        <div className="drawerHeader">
          <h3 className="sectionTitle drawerSectionTitle">
            <span className="drawerTitleIcon" aria-hidden="true">
              <Icon name="filters" />
            </span>
            {t.filters}
          </h3>
          <div className="drawerHeaderActions">
            <button
              className={`btn btnSmall iconBtn drawerPinBtn ${filtersPinned ? "btnActive" : ""}`}
              onClick={() => {
                const next = !filtersPinned;
                if (typeof window !== "undefined") window.localStorage.setItem("water.ui.filters-pinned.v1", String(next));
                setFiltersPinned(next);
                if (!next) setDrawerOpen(true); // when unpinning, keep panel visible as floating
              }}
              aria-label={filtersPinned ? t.unpin : t.pin}
              title={filtersPinned ? t.unpin : t.pin}
            >
              <span className="btnIcon" aria-hidden="true">
                <Icon name={filtersPinned ? "unpin" : "pin"} />
              </span>
            </button>
            {!filtersPinned ? (
              <button className="btn btnSmall drawerDoneBtn" onClick={() => setDrawerOpen(false)} aria-label={t.close}>
                <span className="btnIcon" aria-hidden="true">
                  <Icon name="close" />
                </span>
                <span className="drawerDoneLabel">{lruet(lang, "Готово", "Valmis", "Done")}</span>
              </button>
            ) : null}
          </div>
        </div>
        {nearbyOnly && userCoords ? (
          <div className="nearbyPanel">
            <label htmlFor="nearby-radius">
              {t.nearRadius}: <b>{nearbyRadiusKm} km</b>
            </label>
            <input
              id="nearby-radius"
              type="range"
              min={1}
              max={50}
              step={1}
              value={nearbyRadiusKm}
              onChange={(e) => setNearbyRadiusKm(Number(e.target.value))}
            />
            <button
              type="button"
              className="btn btnSmall"
              onClick={() => {
                setUserCoords(null);
                setNearbyOnly(false);
                setGeoError(null);
              }}
            >
              {t.clearNearMe}
            </button>
          </div>
        ) : null}
        {geoError ? <p className="hint">{geoError}</p> : null}
        <div className="field drawerSearchField">
          <label htmlFor="search-input">{t.search}</label>
          <div className="drawerSearchWrap">
            <span className="drawerSearchIcon" aria-hidden="true">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <circle cx="9" cy="9" r="6" />
                <path d="m13.5 13.5 4 4" />
              </svg>
            </span>
            <input
              id="search-input"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={lruet(lang, "например: Tallinn, Harku, rand", "nt Tallinn, Harku, rand", "e.g. Tallinn, Harku, beach")}
              aria-label={lruet(
                lang,
                "Поиск мест по названию или уезду",
                "Otsi kohti nime või maakonna järgi",
                "Search places by location or county"
              )}
              inputMode="search"
              enterKeyHint="search"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
            />
            {query ? (
              <button
                type="button"
                className="drawerSearchClear"
                onClick={() => setQuery("")}
                aria-label={lruet(lang, "Очистить", "Tühjenda", "Clear")}
                title={lruet(lang, "Очистить", "Tühjenda", "Clear")}
              >
                <Icon name="close" />
              </button>
            ) : null}
          </div>
        </div>
        {isMobile ? (
          <>
            <div className="drawerLangRow">
              <span className="drawerLangLabel">{lruet(lang, "Язык", "Keel", "Language")}</span>
              <button className={`btn btnSmall ${lang === "ru" ? "btnActive" : ""}`} onClick={() => { setLang("ru"); pushHeaderLang("ru"); }}>RU</button>
              <button className={`btn btnSmall ${lang === "et" ? "btnActive" : ""}`} onClick={() => { setLang("et"); pushHeaderLang("et"); }}>ET</button>
              <button className={`btn btnSmall ${lang === "en" ? "btnActive" : ""}`} onClick={() => { setLang("en"); pushHeaderLang("en"); }}>EN</button>
            </div>
            <div className="drawerLangRow">
              <span className="drawerLangLabel">{lruet(lang, "Шрифт", "Font", "Font")}</span>
              <div className="fontToggle" role="group" aria-label="Cyrillic font switch">
                <button className={`btn btnSmall ${cyrillicFont === "ibm" ? "btnActive" : ""}`} onClick={() => setCyrillicFont("ibm")}>IBM</button>
                <button className={`btn btnSmall ${cyrillicFont === "manrope" ? "btnActive" : ""}`} onClick={() => setCyrillicFont("manrope")}>MAN</button>
              </div>
            </div>
          </>
        ) : null}
        <div className="filterGroup">
          <div className="filterGroupHead">
            <span className="filterGroupIcon" aria-hidden="true"><Icon name="globe" /></span>
            <span>{lruet(lang, "Где", "Kus", "Where")}</span>
          </div>
          <div className="field">
            <label htmlFor="segment-select">
              <span className="fieldIcon" aria-hidden="true"><Icon name="grid" /></span>
              {lruet(lang, "Тип точки", "Punkti tüüp", "Point type")}
            </label>
            <div className="selectWrap">
              <select id="segment-select" value={segment} onChange={(e) => setSegment(e.target.value)} aria-label="Filter by source category">
                <option value="all">{lruet(lang, "Все типы", "Kõik tüübid", "All types")}</option>
                {placeKinds.map((k) => (
                  <option key={`k-${k}`} value={k}>
                    {placeKindLabel(k)}
                  </option>
                ))}
              </select>
              <span className="selectChevron" aria-hidden="true"><Icon name="chevron-down" /></span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="county-select">
              <span className="fieldIcon" aria-hidden="true"><Icon name="globe" /></span>
              {t.county}
            </label>
            <div className="selectWrap">
              <select id="county-select" value={county} onChange={(e) => setCounty(e.target.value)} aria-label="Filter by county">
                <option value="all">{lruet(lang, "Все уезды", "Kõik maakonnad", "All counties")}</option>
                {counties.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
              <span className="selectChevron" aria-hidden="true"><Icon name="chevron-down" /></span>
            </div>
          </div>
        </div>

        <div className="filterGroup">
          <div className="filterGroupHead">
            <span className="filterGroupIcon" aria-hidden="true"><Icon name="alert" /></span>
            <span>{lruet(lang, "Статус и риск", "Staatus ja risk", "Status & risk")}</span>
          </div>
          <div className="field">
            <label htmlFor="risk-select">
              <span className="fieldIcon" aria-hidden="true"><Icon name="signal" /></span>
              {t.risk}
            </label>
            <div className="selectWrap">
              <select id="risk-select" value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Filter by risk level">
                {riskOrder.map((r) => (
                  <option key={r} value={r}>
                    {riskLabel(r)}
                  </option>
                ))}
              </select>
              <span className="selectChevron" aria-hidden="true"><Icon name="chevron-down" /></span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="official-select">
              <span className="fieldIcon" aria-hidden="true"><Icon name="check-circle" /></span>
              {t.official}
            </label>
            <div className="selectWrap">
              <select id="official-select" value={official} onChange={(e) => setOfficial(e.target.value as (typeof officialOrder)[number])}>
                {officialOrder.map((s) => (
                  <option key={s} value={s}>
                    {officialLabel(s)}
                  </option>
                ))}
              </select>
              <span className="selectChevron" aria-hidden="true"><Icon name="chevron-down" /></span>
            </div>
          </div>
          <div className="field rangeField">
            <label htmlFor="min-prob">
              <span className="fieldIcon" aria-hidden="true"><Icon name="alert" /></span>
              {t.minProb}
              <span className="rangeValue">{minProb.toFixed(2)}</span>
            </label>
            <input
              id="min-prob"
              className="rangeSlider"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={minProbInput}
              onInput={(e) => setMinProbInput(Number((e.target as HTMLInputElement).value))}
              style={{ "--range-fill": `${minProbInput * 100}%` } as React.CSSProperties}
            />
            <div className="rangeScale" aria-hidden="true">
              <span>0</span><span>0.5</span><span>1</span>
            </div>
          </div>
        </div>

        <div className="filterGroup">
          <div className="filterGroupHead">
            <span className="filterGroupIcon" aria-hidden="true"><Icon name="calendar" /></span>
            <span>{lruet(lang, "Дата пробы", "Proovi kuupäev", "Sample date")}</span>
          </div>
          <div className="field">
            <label>{t.latestSampleDate}</label>
          <div className="dateRangeRow">
            <div className="dateRangeField">
              <span className="dateRangeIcon" aria-hidden="true">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <rect x="1.5" y="2.5" width="13" height="12" rx="2"/>
                  <path d="M1.5 6.5h13M5 1v3M11 1v3"/>
                </svg>
              </span>
              <input
                type="date"
                value={sampleDateFrom}
                onChange={(e) => setSampleDateFrom(e.target.value)}
                aria-label={t.dateFrom}
                title={t.dateFrom}
              />
            </div>
            <span className="dateRangeSep" aria-hidden="true">—</span>
            <div className="dateRangeField">
              <span className="dateRangeIcon" aria-hidden="true">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <rect x="1.5" y="2.5" width="13" height="12" rx="2"/>
                  <path d="M1.5 6.5h13M5 1v3M11 1v3"/>
                </svg>
              </span>
              <input
                type="date"
                value={sampleDateTo}
                onChange={(e) => setSampleDateTo(e.target.value)}
                aria-label={t.dateTo}
                title={t.dateTo}
              />
            </div>
            {(sampleDateFrom || sampleDateTo) ? (
              <button
                className="btn dateRangeClearBtn"
                type="button"
                onClick={() => { setSampleDateFrom(""); setSampleDateTo(""); }}
                title={t.resetDate}
                aria-label={t.resetDate}
              >
                ×
              </button>
            ) : null}
          </div>
            <p className="hint">{t.latestSampleDateHint}</p>
          </div>
        </div>

        <div className="panel reportPanel">
          <h4>{lruet(lang, "Избранные точки", "Jälgimisnimekiri", "Your watchlist")}</h4>
          {watchlistPlaces.length === 0 ? (
            <p className="hint">
              {lruet(
                lang,
                "Сохраняйте ключевые пляжи, бассейны/SPA и питьевые точки для быстрого мониторинга.",
                "Salvesta olulised supluskohad, basseinid/SPA ja joogiveepunktid kiireks jälgimiseks.",
                "Save key beaches, pools/SPA and drinking-water points for quick monitoring."
              )}
            </p>
          ) : (
            <ul className="alertList">
              {watchlistPlaces.slice(0, 8).map((p) => (
                <li key={`watch-${p.id}`}>
                  <button className="linkBtn" onClick={() => selectPoint(p.id)}>
                    {p.location}
                  </button>
                  <span className={`badge ${p.risk_level === "high" ? "bad" : p.risk_level === "medium" ? "warn" : "good"}`}>
                    {p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : p.risk_level}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

      </aside>

      <div className="mainContent">
      <section
        ref={mapPanelRef}
        className={`panel mapTopPanel ${isMapFullscreen ? "mapPanelFullscreen" : ""} ${isMobile ? "mobileMapPanel" : ""}`}
      >
        <div className="mapHeaderRow">
          <h3 className="sectionTitle">{t.mapTitle}</h3>
        </div>
        {/* On-map filter chips — desktop overlay matching the mobile UX
            (domain segment, alerts-only, near-me). Sits on the map so
            users can toggle quick filters without opening the drawer.
            The first chip opens the full filter drawer. */}
        {!isMobile ? (
          <div className="mapChipBar desktopOnly" role="toolbar" aria-label={t.filters}>
            {!filtersPinned ? (
              <>
                <button
                  type="button"
                  className={`mapChip mapChipDrawer ${drawerOpen ? "mapChipActive" : ""}`}
                  onClick={() => setDrawerOpen((v) => !v)}
                  aria-label={drawerOpen ? t.close : t.openFilters}
                  aria-pressed={drawerOpen}
                  data-tooltip={drawerOpen ? t.close : t.openFilters}
                >
                  <Icon name={drawerOpen ? "filter-x" : "filters"} />
                </button>
                <div className="mapChipDivider" aria-hidden="true" />
              </>
            ) : null}
            {(() => {
              const allLabel = lruet(lang, "Все", "Kõik", "All");
              const countText = lruet(
                lang,
                `Все точки: ${filtered.length}`,
                `Kõik punktid: ${filtered.length}`,
                `All points: ${filtered.length}`
              );
              return (
                <button
                  type="button"
                  className={`mapChip ${segment === "all" ? "mapChipActive" : ""}`}
                  onClick={() => {
                    setSegment("all");
                    showCountBubble(countText);
                  }}
                  aria-label={allLabel}
                  data-tooltip={allLabel}
                >
                  <Icon name="grid" />
                </button>
              );
            })()}
            {(["swimming", "pool_spa", "drinking_water", "drinking_source"] as const).map((k) => {
              const iconName: IconName =
                k === "swimming" ? "swim" : k === "pool_spa" ? "pool" : k === "drinking_water" ? "tap" : "drop";
              const label =
                k === "swimming"
                  ? lruet(lang, "Купальные", "Suplusvesi", "Swimming")
                  : k === "pool_spa"
                  ? lruet(lang, "Бассейны", "Basseinid", "Pools")
                  : k === "drinking_water"
                  ? lruet(lang, "Питьевая", "Joogivesi", "Drinking")
                  : lruet(lang, "Источники", "Allikad", "Sources");
              const domainCount = snapshot.places.filter((p) => p.place_kind === k).length;
              return (
                <button
                  key={`mapchip-${k}`}
                  type="button"
                  className={`mapChip ${segment === k ? "mapChipActive" : ""}`}
                  onClick={() => {
                    const next = segment === k ? "all" : k;
                    setSegment(next);
                    showCountBubble(`${label}: ${domainCount}`);
                  }}
                  aria-label={label}
                  data-tooltip={label}
                >
                  <Icon name={iconName} />
                </button>
              );
            })}
            <div className="mapChipDivider" aria-hidden="true" />
            {(() => {
              const alertsLabel = alertsOnly
                ? lruet(lang, "Снять фильтр тревог", "Eemalda häirete filter", "Clear alerts filter")
                : lruet(lang, "Только тревоги", "Ainult häired", "Alerts only");
              return (
                <button
                  type="button"
                  className={`mapChip mapChipAlert ${alertsOnly ? "mapChipActive" : ""}`}
                  onClick={() => {
                    setAlertsOnly((v) => !v);
                    showCountBubble(
                      lruet(
                        lang,
                        `Тревог на карте: ${mapAlertsCount}`,
                        `Häireid kaardil: ${mapAlertsCount}`,
                        `Alerts on map: ${mapAlertsCount}`
                      )
                    );
                  }}
                  aria-label={alertsLabel}
                  aria-pressed={alertsOnly}
                  data-tooltip={alertsLabel}
                >
                  <Icon name="alert" />
                </button>
              );
            })()}
            {(() => {
              const nearLabel = nearbyOnly
                ? lruet(lang, "Снять фильтр «рядом»", "Eemalda läheduse filter", "Clear near-me filter")
                : lruet(lang, "Рядом со мной", "Minu lähedal", "Near me");
              return (
                <button
                  type="button"
                  className={`mapChip ${nearbyOnly ? "mapChipActive" : ""}`}
                  onClick={() => {
                    if (nearbyOnly) {
                      setNearbyOnly(false);
                      setGeoError(null);
                    } else if (userCoords) {
                      setNearbyOnly(true);
                      setGeoError(null);
                    } else {
                      activateNearMe();
                    }
                    const n = mapNearMeCount ?? 0;
                    showCountBubble(
                      lruet(
                        lang,
                        `Рядом на карте: ${n}`,
                        `Läheduses kaardil: ${n}`,
                        `Near me on map: ${n}`
                      )
                    );
                  }}
                  aria-label={nearLabel}
                  aria-pressed={nearbyOnly}
                  data-tooltip={nearLabel}
                >
                  <Icon name="locate" />
                </button>
              );
            })()}
            {risk !== "all" ? (
              <button
                type="button"
                className="mapChip mapChipActive"
                onClick={() => setRisk("all")}
                aria-label={lruet(lang, "Сбросить риск", "Lähtesta risk", "Clear risk filter")}
                data-tooltip={lruet(lang, "Сбросить риск", "Lähtesta risk", "Clear risk filter")}
              >
                <Icon name="signal" />
              </button>
            ) : null}
            <button
              type="button"
              className="mapChip mapChipClear"
              onClick={clearFilters}
              aria-label={t.clearFilters}
              data-tooltip={t.clearFilters}
            >
              <Icon name="filter-x" />
            </button>
          </div>
        ) : null}
        <MapClient
          places={mapPlaces}
          onSelectPoint={selectPoint}
          onSelectCluster={handleClusterSelect}
          onSelectCounty={handleCountySelect}
          selectedCounty={county !== "all" ? countyPretty(county) : undefined}
          locale={lang}
          selectedPoint={selectedPlace}
          userLocation={nearbyOnly ? userCoords : null}
          isFullscreen={isMapFullscreen}
          isMobile={isMobile}
          onToggleFullscreen={isMobile ? undefined : toggleMapFullscreen}
          fullscreenLabel={isMobile ? "" : isMapFullscreen ? lruet(lang, "Выйти из полноэкранного", "Välju täisekraanist", "Exit fullscreen") : lruet(lang, "Полный экран", "Täisekraan", "Fullscreen")}
          disableHoverPopups={isMobile}
          onRecenterUser={activateNearMe}
          recenterLabel={t.nearMe}
          resetViewLabel={lruet(lang, "Сбросить вид", "Lähtesta vaade", "Reset view")}
          showCountyOverlay={!isMobile}
          countyGeoJson={countyGeoJson}
          fitBoundsKey={fitBoundsKey}
          fitBoundsPlaces={fitBoundsPlaces}
          /* When the bottom sheet is half/full or the keyboard is open,
             tell MapClient how much screen real estate is obscured so
             flyTo() pans the marker into the still-visible area. */
          bottomOverlayPx={isMobile ? mobileBottomOverlayPx : 0}
          topOverlayPx={isMobile ? 105 : 20}
        />
        {/* Data/model freshness overlay — always visible on map */}
        <div className="mapFreshnessOverlay">
          <div className="mapFreshnessLine">
            <span className="mapFreshnessLabel">{lruet(lang, "Данные", "Andmed", "Data")}:</span>
            <span className="mapFreshnessValue">{dataFetchedLabel ?? "—"}</span>
          </div>
          {modelTrainedLabel ? (
            <div className="mapFreshnessLine">
              <span className="mapFreshnessLabel">{lruet(lang, "Модель", "Mudel", "Model")}:</span>
              <span className="mapFreshnessValue">{modelTrainedLabel}</span>
            </div>
          ) : null}
        </div>
      </section>

      {/* Stats row — always visible below map on desktop */}
      <div className="mapStatsRow desktopOnly">
        <div className="mapStat">
          <span className="mapStatK">{lruet(lang, "Видимых", "Nähtav", "Visible")}</span>
          <span className="mapStatV">{filtered.length}</span>
        </div>
        <div className="mapStat mapStatBad">
          <span className="mapStatK">{lruet(lang, "Высокий риск", "Kõrge risk", "High risk")}</span>
          <span className="mapStatV">{filtered.filter((p) => p.risk_level === "high").length}</span>
        </div>
        <div className="mapStat mapStatGood">
          <span className="mapStatK">{lruet(lang, "Низкий риск", "Madal risk", "Low risk")}</span>
          <span className="mapStatV">{filtered.filter((p) => p.risk_level === "low").length}</span>
        </div>
        <div className="mapStat">
          <span className="mapStatK">{lruet(lang, "Офиц. нарушения", "Ametlik rikkumine", "Violations")}</span>
          <span className="mapStatV mapStatBadText">{filtered.filter((p) => p.official_compliant === 0).length}</span>
        </div>
        <div className="mapStat">
          <span className="mapStatK">{lruet(lang, "С моделью", "Mudeli katvus", "With model")}</span>
          <span className="mapStatV">{filtered.filter((p) => p.model_violation_prob !== null).length}</span>
        </div>
        <div className={`mapStat ${healthIndex >= 75 ? "mapStatGood" : healthIndex >= 50 ? "mapStatWarn" : "mapStatBad"}`}>
          <span className="mapStatK">{lruet(lang, "Индекс здоровья", "Tervise indeks", "Health index")}</span>
          <span className="mapStatV">{healthIndex}/100</span>
        </div>
        <div className="mapStat">
          <span className="mapStatK">{lruet(lang, "Прогноз", "Prognoos", "Outlook")}</span>
          <span className="mapStatV">{prognosis}</span>
        </div>
        <div className="mapStat">
          <span className="mapStatK">{lruet(lang, "Ср. P(нарушения)", "Kesk. P(rikkumine)", "Avg P(viol.)")}</span>
          <span className="mapStatV">{avgProb === null ? "n/a" : avgProb.toFixed(2)}</span>
        </div>
      </div>

      <section className="panel selectedPointDesktop desktopOnly">
        <h3 className="sectionTitle">{t.selectedPoint}</h3>
        {!selectedPlace ? (
          <p className="hint">{t.noSelectedPoint}</p>
        ) : (
          <div className="pointGrid">
            <div className="panel reportPanel">
              <h4>{selectedPlace.location}</h4>
              <p className="hint">
                {selectedPlace.domain} / {selectedPlace.place_kind}
                <br />
                {t.county}: {countyPretty(selectedPlace.county || "Unknown")}
                <br />
                {lruet(lang, "Проба", "Proov", "Sample")}: {fmtDate(selectedPlace.sample_date)}
                <br />
                {lruet(lang, "Официальный статус", "Ametlik staatus", "Official status")}:{" "}
                {selectedPlace.official_compliant === 1 ? (
                  <span className="badge good">{officialStatusText(1)}</span>
                ) : selectedPlace.official_compliant === 0 ? (
                  <button
                    className="linkBtn badge bad clickableBadge"
                    onClick={() =>
                      openInfo(
                        lruet(lang, "Официальное нарушение", "Ametlik rikkumine", "Official violation"),
                        explainViolation(selectedPlace)
                      )
                    }
                  >
                    {officialStatusText(0)}
                  </button>
                ) : (
                  <span className="badge warn">n/a</span>
                )}
                <br />
                ID: {selectedPlace.id}
                <br />
                Coord source: {selectedPlace.coord_source || "n/a"}
                <br />
                {lruet(lang, "Прогноз выбранной модели", "Valitud mudeli prognoos", "Selected model prediction")}:{" "}
                {selectedPlace.model_violation_prob !== null ? selectedPlace.model_violation_prob.toFixed(2) : "n/a"}
                <br />
                <span className="modelAbbr" data-tooltip={lruet(lang, "Logistic Regression — линейная вероятностная модель", "Logistic Regression — lineaarne tõenäosusmudel", "Logistic Regression — linear probability model")}>LR</span>
                {"/"}
                <span className="modelAbbr" data-tooltip={lruet(lang, "Random Forest — ансамбль деревьев", "Random Forest — puuansambel", "Random Forest — ensemble of decision trees")}>RF</span>
                {"/"}
                <span className="modelAbbr" data-tooltip={lruet(lang, "Gradient Boosting — деревья последовательно исправляют ошибки", "Gradient Boosting — puud parandavad järjest vigu", "Gradient Boosting — trees sequentially correct errors")}>GB</span>
                {"/"}
                <span className="modelAbbr" data-tooltip={lruet(lang, "LightGBM — быстрый boosting на деревьях", "LightGBM — kiire puupõhine boosting", "LightGBM — fast histogram-based gradient boosting")}>LGBM</span>
                {": "}
                {[
                  selectedPlace.lr_violation_prob,
                  selectedPlace.rf_violation_prob,
                  selectedPlace.gb_violation_prob,
                  selectedPlace.lgbm_violation_prob
                ]
                  .map((v) => (typeof v === "number" ? v.toFixed(2) : "n/a"))
                  .join(" / ")}
              </p>
            </div>
            <div className="panel reportPanel">
              <h4>{t.measurements}</h4>
              {Object.keys(selectedPlace.measurements || {}).length === 0 ? (
                <p className="hint">n/a</p>
              ) : (
                <div className="tableWrap compact">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Показатель", "Näitaja", "Parameter")}</th>
                        <th>{lruet(lang, "Значение", "Väärtus", "Value")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(selectedPlace.measurements)
                        .slice(0, 25)
                        .map(([k, v]) => (
                          <tr key={`m-${k}`}>
                            <td>
                              <button
                                className="linkBtn"
                                onClick={() =>
                                  openInfo(
                                    labelForParam(k),
                                    descForParam(k)
                                  )
                                }
                              >
                                {labelForParam(k)}
                              </button>
                            </td>
                            <td>
                              <button
                                className="linkBtn"
                                onClick={() =>
                                  openInfo(
                                    `${labelForParam(k)}: ${lruet(lang, "норматив", "norm", "norm")}`,
                                    explainMeasurementNorm(k, v, selectedPlace)
                                  )
                                }
                              >
                                {String(v)}
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="panel reportPanel">
              <h4>{t.history}</h4>
              {selectedPlace.sample_history?.length ? (
                <div className="tableWrap compact">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Дата", "Kuupäev", "Date")}</th>
                        <th>{lruet(lang, "Статус", "Staatus", "Status")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPlace.sample_history.slice(0, 12).map((h, idx) => (
                        <tr
                          key={`hist-${idx}`}
                          onClick={() => {
                            openInfo(
                              lruet(lang, `История: ${fmtDate(h.sample_date)}`, `Ajalugu: ${fmtDate(h.sample_date)}`, `History: ${fmtDate(h.sample_date)}`),
                              explainHistoryMeasurements(selectedPlace, idx)
                            );
                          }}
                        >
                          <td>{fmtDate(h.sample_date)}</td>
                          <td>
                            {h.official_compliant === 1 ? (
                              <span className="badge good">{officialStatusText(1)}</span>
                            ) : h.official_compliant === 0 ? (
                              <button
                                className="linkBtn badge bad clickableBadge"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openInfo(
                                    lruet(lang, "Официальное нарушение (история)", "Ametlik rikkumine (ajalugu)", "Official violation (history)"),
                                    explainViolationFromMeasurements(selectedPlace.domain, historyMeasurements(selectedPlace, idx))
                                  );
                                }}
                              >
                                {officialStatusText(0)}
                              </button>
                            ) : (
                              <span className="badge warn">n/a</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="hint">{t.historyPlaceholder}</p>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Mobile bottom sheet — rendered unconditionally to avoid hydration
          flicker. CSS hides it on viewports wider than 900px. */}
      <section
          className={`mobileBottomSheet ${mobilePanelState} ${sheetDragging ? "dragging" : ""}`}
          style={{ "--sheet-drag-offset": `${sheetDragOffset}px` } as React.CSSProperties}
        >
          {/* Drag handle */}
          <button
            type="button"
            className="gmSheetHandle"
            onClick={cycleMobilePanelState}
            onPointerDown={onSheetPointerDown}
            onPointerMove={onSheetPointerMove}
            onPointerUp={onSheetPointerUp}
            onPointerCancel={() => {
              sheetDragStartY.current = null;
              sheetDragLastY.current = null;
              sheetDragLastTs.current = null;
              sheetDragVelocity.current = 0;
              setSheetDragging(false);
              setSheetDragOffset(0);
            }}
            aria-label={lruet(lang, "Изменить высоту панели", "Muuda paneeli kõrgust", "Toggle panel height")}
          >
            <span className="gmSheetHandlePill" />
          </button>

          {/* Collapsed peek row: just show count */}
          {mobilePanelState === "collapsed" ? (
            <div className="gmSheetPeek">
              <span className="gmSheetPeekCount">{filtered.length}</span>
              <span className="gmSheetPeekLabel">{lruet(lang, " мест на карте", " kohta kaardil", " places on map")}</span>
            </div>
          ) : sheetMode === "filter" ? (
            /* Filter mode header */
            <div className="gmSheetModeHeader">
              <span className="gmSheetModeTitle">{lruet(lang, "Фильтры", "Filtrid", "Filters")}</span>
              <button
                className="gmSheetClearBtn"
                type="button"
                onClick={clearFilters}
                aria-label={t.clearFilters}
                title={t.clearFilters}
              >
                <Icon name="filter-x" />
              </button>
              <button
                className="gmSheetCloseBtn"
                type="button"
                onClick={() => { setSheetMode("place"); setMobilePanelState("collapsed"); }}
                aria-label={t.close}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          ) : (
            /* Place mode header */
            <div className="gmSheetModeHeader">
              <span className="gmSheetModeTitle">
                {selectedPlace
                  ? selectedPlace.location
                  : clusterPlaces
                    ? lruet(lang, `${clusterPlaces.length} мест в этой точке`, `${clusterPlaces.length} kohta selles punktis`, `${clusterPlaces.length} places at this location`)
                    : lruet(lang, "Выберите точку", "Vali koht", "Select a place")}
              </span>
              <button
                className="gmSheetCloseBtn"
                type="button"
                onClick={() => { setMobilePanelState("collapsed"); setClusterPlaceIds(null); }}
                aria-label={t.close}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          )}

          {/* Sheet body — scrollable */}
          {mobilePanelState !== "collapsed" ? (
            <div className="gmSheetBody">
              {sheetMode === "filter" ? (
                /* ---- FILTER MODE / BURGER PANEL ---- */
                <div className="gmSheetFilterContent">
                  {/* Alerts-only + Near-me toggles removed from this sheet —
                      they were visually covered by the matching icons on the
                      top chip bar. Those chips now flash a small count bubble
                      instead of toggling a filter. */}
                  {nearbyOnly && userCoords ? (
                    <div className="nearbyPanel">
                      <label htmlFor="gm-nearby-radius">{t.nearRadius}: <b>{nearbyRadiusKm} km</b></label>
                      <input id="gm-nearby-radius" type="range" min={1} max={50} step={1} value={nearbyRadiusKm}
                        onChange={(e) => setNearbyRadiusKm(Number(e.target.value))} />
                      <button type="button" className="btn btnSmall" onClick={() => { setUserCoords(null); setNearbyOnly(false); setGeoError(null); }}>{t.clearNearMe}</button>
                    </div>
                  ) : null}
                  {geoError ? <p className="hint">{geoError}</p> : null}

                  <div className="field">
                    <label htmlFor="gm-county-select">{t.county}</label>
                    <select id="gm-county-select" value={county} onChange={(e) => setCounty(e.target.value)}>
                      <option value="all">{lruet(lang, "Все", "Kõik", "All")}</option>
                      {counties.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="gm-risk-select">{t.risk}</label>
                    <select id="gm-risk-select" value={risk} onChange={(e) => setRisk(e.target.value)}>
                      {riskOrder.map((r) => (
                        <option key={r} value={r}>
                          {(r as string) === "all" ? lruet(lang, "Все", "Kõik", "All")
                          : (r as string) === "low" ? lruet(lang, "Низкий", "Madal", "Low")
                          : (r as string) === "medium" ? lruet(lang, "Средний", "Keskmine", "Medium")
                          : (r as string) === "high" ? lruet(lang, "Высокий", "Kõrge", "High")
                          : lruet(lang, "Неизвестно", "Teadmata", "Unknown")}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="gm-official-select">{t.official}</label>
                    <select id="gm-official-select" value={official} onChange={(e) => setOfficial(e.target.value as (typeof officialOrder)[number])}>
                      {officialOrder.map((s) => (
                        <option key={s} value={s}>
                          {s === "all" ? lruet(lang, "Все", "Kõik", "All")
                          : s === "compliant" ? lruet(lang, "Соответствует", "Vastab", "Compliant")
                          : s === "violation" ? lruet(lang, "Нарушение", "Rikkumine", "Violation")
                          : lruet(lang, "Неизвестно", "Teadmata", "Unknown")}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="gm-min-prob">{t.minProb}: <b>{minProb.toFixed(2)}</b></label>
                    <input id="gm-min-prob" type="range" min={0} max={1} step={0.01} value={minProbInput}
                      onInput={(e) => setMinProbInput(Number((e.target as HTMLInputElement).value))} />
                  </div>
                  <div className="field">
                    <label>{t.latestSampleDate}</label>
                    {/* Compact From/To date pickers — calendar icons replace
                        the bulky native listboxes seen in the old UI. */}
                    <div className="gmDateRangeWrap">
                      <div className="gmDateRange">
                        <div>
                          <span className="gmDateLabel">{t.dateFrom}</span>
                          <div className="gmDateField">
                            <Icon name="calendar" />
                            <input
                              type="date"
                              value={sampleDateFrom}
                              onChange={(e) => setSampleDateFrom(e.target.value)}
                              aria-label={t.dateFrom}
                            />
                          </div>
                        </div>
                        <div>
                          <span className="gmDateLabel">{t.dateTo}</span>
                          <div className="gmDateField">
                            <Icon name="calendar" />
                            <input
                              type="date"
                              value={sampleDateTo}
                              onChange={(e) => setSampleDateTo(e.target.value)}
                              aria-label={t.dateTo}
                            />
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="gmDateClear"
                        onClick={() => { setSampleDateFrom(""); setSampleDateTo(""); }}
                        aria-label={t.resetDate}
                        title={t.resetDate}
                      >
                        <Icon name="reset" />
                      </button>
                    </div>
                    <p className="hint">{t.latestSampleDateHint}</p>
                  </div>
                  <div className="stats">
                    <div className="stat"><div className="k">{lruet(lang, "Видимых", "Nähtav", "Visible")}</div><div className="v">{filtered.length}</div></div>
                    <div className="stat"><div className="k">{lruet(lang, "Высокий риск", "Kõrge risk", "High risk")}</div><div className="v">{high}</div></div>
                    <div className="stat"><div className="k">{lruet(lang, "Низкий риск", "Madal risk", "Low risk")}</div><div className="v">{low}</div></div>
                    <div className="stat"><div className="k">{lruet(lang, "Офиц. нарушения", "Ametlik rikkumine", "Official violations")}</div><div className="v">{violations}</div></div>
                  </div>

                  {/* Burger settings panel: theme toggle, language, copyright —
                      moved to the bottom so the functional filters come first. */}
                  <div className="gmBurgerPanel">
                    <div className="gmBurgerRow">
                      <b>{lruet(lang, "Тема", "Teema", "Theme")}</b>
                      <div className="gmThemeToggle" role="group" aria-label="Theme">
                        <button
                          type="button"
                          className={`gmThemeBtn ${theme === "light" ? "active" : ""}`}
                          onClick={() => setTheme("light")}
                          aria-pressed={theme === "light"}
                        >
                          <span className="btnIcon" aria-hidden="true"><Icon name="sun" /></span>
                          {lruet(lang, "Светлая", "Hele", "Light")}
                        </button>
                        <button
                          type="button"
                          className={`gmThemeBtn ${theme === "dark" ? "active" : ""}`}
                          onClick={() => setTheme("dark")}
                          aria-pressed={theme === "dark"}
                        >
                          <span className="btnIcon" aria-hidden="true"><Icon name="moon" /></span>
                          {lruet(lang, "Тёмная", "Tume", "Dark")}
                        </button>
                      </div>
                    </div>
                    <div className="gmBurgerRow">
                      <b>{lruet(lang, "Язык", "Keel", "Language")}</b>
                      <div className="drawerLangRow" style={{ padding: 0 }}>
                        <button className={`btn btnSmall ${lang === "ru" ? "btnActive" : ""}`} onClick={() => { setLang("ru"); pushHeaderLang("ru"); }}>RU</button>
                        <button className={`btn btnSmall ${lang === "et" ? "btnActive" : ""}`} onClick={() => { setLang("et"); pushHeaderLang("et"); }}>ET</button>
                        <button className={`btn btnSmall ${lang === "en" ? "btnActive" : ""}`} onClick={() => { setLang("en"); pushHeaderLang("en"); }}>EN</button>
                      </div>
                    </div>
                    <p className="gmCopyright">
                      © {new Date().getFullYear()} H2O Atlas ·{" "}
                      {lruet(lang, "Открытые данные Terviseamet + ML", "Terviseameti avaandmed + ML", "Terviseamet open data + ML")}
                    </p>
                  </div>
                </div>
              ) : (
                /* ---- PLACE MODE ---- */
                <div className="gmSheetPlaceContent">
                  {!selectedPlace && clusterPlaces ? (
                    /* Cluster pick-list: tapping a co-located cluster on
                       mobile shows its children here instead of spiderfying. */
                    <div className="gmClusterList">
                      {clusterPlaces.map((cp) => (
                        <button
                          key={cp.id}
                          type="button"
                          className="gmClusterItem"
                          onClick={() => selectPoint(cp.id)}
                        >
                          <span className="gmClusterItemEmoji" aria-hidden="true">
                            {cp.place_kind === "swimming" ? "🏖" : cp.place_kind === "pool_spa" ? "🏊" : cp.place_kind === "drinking_water" ? "🚰" : "💧"}
                          </span>
                          <span className="gmClusterItemBody">
                            <span className="gmClusterItemName">{cp.location}</span>
                            <span className="gmClusterItemMeta">
                              {placeKindLabel(cp.place_kind)}
                              {cp.county ? ` · ${countyPretty(cp.county)}` : ""}
                            </span>
                          </span>
                          <span className="gmClusterItemBadges">
                            {cp.official_compliant === 0 ? (
                              <span className="badge bad" style={{ fontSize: "0.7rem" }}>✗</span>
                            ) : cp.official_compliant === 1 ? (
                              <span className="badge good" style={{ fontSize: "0.7rem" }}>✓</span>
                            ) : null}
                            {cp.risk_level === "high" ? (
                              <span className="badge bad" style={{ fontSize: "0.7rem" }}>▲</span>
                            ) : cp.risk_level === "medium" ? (
                              <span className="badge warn" style={{ fontSize: "0.7rem" }}>▲</span>
                            ) : null}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : !selectedPlace ? (
                    <p className="hint" style={{ textAlign: "center", paddingTop: "1.2rem" }}>
                      {lruet(lang, "Нажмите на метку на карте", "Vajuta kaardil märgile", "Tap a marker on the map")}
                    </p>
                  ) : (
                    <>
                      {/* Place kind + county */}
                      <div className="gmPlaceKindRow">
                        <span className="gmPlaceKindEmoji" aria-hidden="true">
                          {selectedPlace.place_kind === "swimming" ? "🏖" : selectedPlace.place_kind === "pool_spa" ? "🏊" : selectedPlace.place_kind === "drinking_water" ? "🚰" : "💧"}
                        </span>
                        <span className="gmPlaceKindLabel">{placeKindLabel(selectedPlace.place_kind)}</span>
                        {selectedPlace.county ? <span className="gmPlaceCounty">· {countyPretty(selectedPlace.county)}</span> : null}
                      </div>

                      {/* Sample date */}
                      <p className="hint gmPlaceMeta">
                        {lruet(lang, "Последняя проба", "Viimane proov", "Latest sample")}: <b>{fmtDate(selectedPlace.sample_date)}</b>
                      </p>

                      {/* Status row: official + risk */}
                      <div className="gmStatusRow">
                        {selectedPlace.official_compliant === 0 ? (
                          <button
                            className="badge bad linkBtn clickableBadge"
                            onClick={() => openInfo(lruet(lang, "Официальное нарушение", "Ametlik rikkumine", "Official violation"), explainViolation(selectedPlace))}
                          >
                            ✗ {officialStatusText(0)}
                          </button>
                        ) : (
                          <span className={`badge ${selectedPlace.official_compliant === 1 ? "good" : "warn"}`}>
                            {selectedPlace.official_compliant === 1 ? "✓ " : ""}{officialStatusText(selectedPlace.official_compliant)}
                          </span>
                        )}
                        <button
                          className={`badge ${selectedPlace.risk_level === "high" ? "bad" : selectedPlace.risk_level === "medium" ? "warn" : selectedPlace.risk_level === "low" ? "good" : ""} linkBtn clickableBadge`}
                          onClick={() => openInfo(
                            lruet(lang, "Оценка модели", "Mudeli hinnang", "Model assessment"),
                            [
                              `${lruet(lang, "Уровень риска", "Riskitase", "Risk level")}: ${selectedPlace.risk_level}`,
                              `P(violation): ${selectedPlace.model_violation_prob !== null ? selectedPlace.model_violation_prob.toFixed(2) : "n/a"}`,
                              `LR/RF/GB/LGBM: ${[selectedPlace.lr_violation_prob, selectedPlace.rf_violation_prob, selectedPlace.gb_violation_prob, selectedPlace.lgbm_violation_prob].map(v => (typeof v === "number" ? v.toFixed(2) : "n/a")).join(" / ")}`,
                            ].join("\n")
                          )}
                        >
                          ▲ {lruet(lang, "Риск", "Risk", "Risk")}: {selectedPlace.risk_level}
                          {selectedPlace.model_violation_prob !== null ? ` (${selectedPlace.model_violation_prob.toFixed(2)})` : ""}
                        </button>
                      </div>

                      {/* Measurements — all rows, with norm violation colouring */}
                      {Object.keys(selectedPlace.measurements || {}).length ? (
                        <>
                          <div className="gmSectionTitle">{t.measurements}</div>
                          <div className="tableWrap compact">
                            <table className="table">
                              <thead>
                                <tr>
                                  <th>{lruet(lang, "Показатель", "Näitaja", "Parameter")}</th>
                                  <th>{lruet(lang, "Значение", "Väärtus", "Value")}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {Object.entries(selectedPlace.measurements).map(([k, v]) => {
                                  const { violated } = assessNorm(k, Number(v), selectedPlace.domain);
                                  return (
                                    <tr key={`ms-${k}`} className={violated === true ? "rowViolated" : ""}>
                                      <td>
                                        <button className="linkBtn" onClick={() => openInfo(labelForParam(k), descForParam(k))}>
                                          {labelForParam(k)}
                                        </button>
                                      </td>
                                      <td>
                                        <button
                                          className={`linkBtn${violated === true ? " valueViolated" : ""}`}
                                          onClick={() => openInfo(`${labelForParam(k)}: ${lruet(lang, "норматив", "norm", "norm")}`, explainMeasurementNorm(k, v, selectedPlace))}
                                        >
                                          {String(v)}
                                        </button>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </>
                      ) : null}

                      {/* Sample history */}
                      {selectedPlace.sample_history?.length ? (
                        <>
                          <div className="gmSectionTitle">{t.history}</div>
                          <div className="tableWrap compact">
                            <table className="table">
                              <thead>
                                <tr>
                                  <th>{lruet(lang, "Дата", "Kuupäev", "Date")}</th>
                                  <th>{lruet(lang, "Статус", "Staatus", "Status")}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedPlace.sample_history.slice(0, 12).map((h, idx) => (
                                  <tr
                                    key={`mh-${idx}`}
                                    style={{ cursor: "pointer" }}
                                    onClick={() => openInfo(
                                      lruet(lang, `История: ${fmtDate(h.sample_date)}`, `Ajalugu: ${fmtDate(h.sample_date)}`, `History: ${fmtDate(h.sample_date)}`),
                                      explainHistoryMeasurements(selectedPlace, idx)
                                    )}
                                  >
                                    <td>{fmtDate(h.sample_date)}</td>
                                    <td>
                                      {h.official_compliant === 0 ? (
                                        <button
                                          className="linkBtn badge bad clickableBadge"
                                          onClick={(e) => { e.stopPropagation(); openInfo(lruet(lang, "Официальное нарушение (история)", "Ametlik rikkumine (ajalugu)", "Official violation (history)"), explainViolationFromMeasurements(selectedPlace.domain, historyMeasurements(selectedPlace, idx))); }}
                                        >
                                          {officialStatusText(0)}
                                        </button>
                                      ) : (
                                        <span className={`badge ${h.official_compliant === 1 ? "good" : "warn"}`}>
                                          {officialStatusText(h.official_compliant)}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      ) : (
                        <p className="hint" style={{ fontSize: "0.82rem", marginTop: "0.6rem" }}>{t.historyPlaceholder}</p>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </section>


      <section className="panel">
        {/* Tab row removed — Alerts button is gone (its info keeps rendering
            below), Domains button is gone (covered by Domain health report),
            and Diagnostics / About Model / About Service now open the
            info-page popup overlay via the header buttons (desktop) or the
            mobile search-bar info button. */}

        <div className="reportsGrid">
          <div className="panel reportPanel">
            <h4>{lruet(lang, "Центр алертов", "Häirekeskus", "Alert center")}</h4>
            <p className="hint">
              {lruet(
                lang,
                "Жёлтый статус означает недостаток модельных данных или промежуточный риск. Нажмите строку для деталей.",
                "Kollane tähendab kas puuduvaid mudeliandmeid või keskmist riski. Vajuta reale detailideks.",
                "Yellow status means either limited model data or medium risk. Tap a row for details."
              )}
            </p>
            {topAlerts.length === 0 ? (
              <p className="hint">{lruet(lang, "Нет активных алертов в текущем фильтре.", "Praeguse filtri vaates aktiivseid häireid pole.", "No active alerts in current filter scope.")}</p>
            ) : (
              <ul className="alertList">
                {topAlerts.map((p) => (
                  <li key={`alert-${p.id}`}>
                    <button className="linkBtn" onClick={() => selectPoint(p.id)}>
                      {p.location}
                    </button>
                    <span className={`badge ${p.risk_level === "high" ? "bad" : "warn"}`}>
                      {p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : p.risk_level}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="panel reportPanel">
            <h4>{lruet(lang, "Отчёт здоровья доменов", "Domeenide tervisearuanne", "Domain health report")}</h4>
            <div className={`tableWrap compact ${isMobile ? "mobileResponsiveTable" : ""}`}>
              <table className="table">
                <thead>
                  <tr>
                    <th>{lruet(lang, "Домен", "Domeen", "Domain")}</th>
                    <th>{lruet(lang, "Всего", "Kokku", "Total")}</th>
                    <th>{lruet(lang, "Наруш.", "Rikkum.", "Viol.")}</th>
                    <th>{lruet(lang, "Высок.", "Kõrge", "High")}</th>
                  </tr>
                </thead>
                <tbody>
                  {domainStats.map(([d, s]) => (
                    <tr key={`domain-${d}`}>
                      <td>{d}</td>
                      <td>{s.total}</td>
                      <td>{s.violations}</td>
                      <td>{s.highRisk}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>


        <div className={`tableWrap ${isMobile ? "mobileResponsiveTable" : ""}`}>
          <table className="table">
            <thead>
              <tr>
                <th>{lruet(lang, "Локация", "Asukoht", "Location")}</th>
                <th>{lruet(lang, "Уезд", "Maakond", "County")}</th>
                <th className="iconCol">
                  <span
                    className="iconTooltip"
                    data-tip={lruet(lang, "Домен / тип воды", "Domeen / vee tüüp", "Domain / water type")}
                  >
                    <span className="cellIcon" style={{ color: "var(--brand)" }}>
                      <Icon name="drop" />
                    </span>
                  </span>
                </th>
                <th className="iconCol">
                  <button
                    className="linkBtn iconTooltip"
                    style={{ padding: 0 }}
                    data-tip={lruet(lang, "Официальный статус", "Ametlik staatus", "Official status")}
                    onClick={() =>
                      openInfo(
                        lruet(lang, "Официальный статус", "Ametlik staatus", "Official status"),
                        lruet(
                          lang,
                          "Зелёный — соответствует нормам, красный — есть официальное нарушение.",
                          "Roheline — vastab normile, punane — ametlik rikkumine.",
                          "Green = compliant, red = official violation."
                        )
                      )
                    }
                  >
                    <span className="cellIcon"><Icon name="check-circle" /></span>
                  </button>
                </th>
                <th className="iconCol">
                  <button
                    className="linkBtn iconTooltip"
                    style={{ padding: 0 }}
                    data-tip={lruet(lang, "Риск модели (ML)", "Mudeli risk (ML)", "Model risk (ML)")}
                    onClick={() =>
                      openInfo(
                        lruet(lang, "Риск модели", "Mudeli risk", "Model risk"),
                        lruet(
                          lang,
                          "Low/Medium/High — интерпретация вероятности нарушения по ML-модели.",
                          "Low/Medium/High — rikkumise tõenäosuse ML-tõlgendus.",
                          "Low/Medium/High — interpretation of model-estimated violation probability."
                        )
                      )
                    }
                  >
                    <span className="cellIcon"><Icon name="signal" /></span>
                  </button>
                </th>
                <th className="iconCol">
                  <span
                    className="iconTooltip"
                    data-tip={lruet(lang, "P(нарушения) — вероятность по ML", "P(rikkumine) — ML tõenäosus", "P(violation) — ML probability")}
                  >
                    <small style={{ fontWeight: 700, fontSize: "0.7rem", letterSpacing: "0.01em" }}>P(v)</small>
                  </span>
                </th>
                <th className="dateCol">
                  <span
                    className="iconTooltip"
                    data-tip={lruet(lang, "Дата последней пробы", "Viimase proovi kuupäev", "Latest sample date")}
                  >
                    <span className="cellIcon" style={{ color: "var(--brand)" }}>
                      <Icon name="calendar" />
                    </span>
                  </span>
                </th>
                <th className="iconCol">
                  <span
                    className="iconTooltip"
                    data-tip={lruet(lang, "Отслеживание (избранное)", "Jälgimine (lemmikud)", "Watchlist (favorites)")}
                  >
                    <span className="cellIcon" style={{ color: "#f59e0b" }}>
                      <Icon name="star" />
                    </span>
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 250).map((p) => {
                const domIcon: IconName =
                  p.domain === "supluskoha" ? "swim"
                  : p.domain === "basseinid" ? "pool"
                  : p.domain === "veevark" ? "tap"
                  : "drop";
                const domTip =
                  p.domain === "supluskoha"
                    ? lruet(lang, "Купание (supluskoha)", "Supluskoht", "Swimming beach")
                    : p.domain === "basseinid"
                    ? lruet(lang, "Бассейн / СПА (basseinid)", "Bassein / SPA", "Pool / SPA")
                    : p.domain === "veevark"
                    ? lruet(lang, "Водопровод (veevärk)", "Ühisveevärk", "Water network")
                    : lruet(lang, "Питьевой источник (joogivesi)", "Joogivee allikas", "Drinking water source");
                const riskColor =
                  p.risk_level === "high" ? "var(--bad)"
                  : p.risk_level === "medium" ? "var(--warn)"
                  : p.risk_level === "low" ? "var(--good)"
                  : "var(--muted)";
                const riskTip = `${p.risk_level}${p.model_violation_prob !== null ? ` · P=${p.model_violation_prob.toFixed(2)}` : ""}`;
                const watching = watchlist.includes(p.id);
                return (
                  <tr key={p.id} onClick={() => selectPoint(p.id)} className={selectedId === p.id ? "rowSelected" : ""}>
                    <td>{p.location}</td>
                    <td>{countyPretty(p.county || "Unknown")}</td>
                    <td className="iconCol">
                      <span className="iconTooltip" data-tip={domTip} style={{ color: "var(--brand)" }}>
                        <span className="cellIcon"><Icon name={domIcon} /></span>
                      </span>
                    </td>
                    <td className="iconCol">
                      {p.official_compliant === 0 ? (
                        <button
                          className="starBtn iconTooltip"
                          data-tip={lruet(lang, "Нарушение — нажмите для подробностей", "Rikkumine — klõpsake üksikasjade jaoks", "Violation — click for details")}
                          style={{ color: "var(--bad)" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            openInfo(
                              lruet(lang, "Официальное нарушение", "Ametlik rikkumine", "Official violation"),
                              explainViolation(p)
                            );
                          }}
                        >
                          <span className="cellIcon"><Icon name="x-circle" /></span>
                        </button>
                      ) : p.official_compliant === 1 ? (
                        <span className="iconTooltip" data-tip={officialStatusText(1)} style={{ color: "var(--good)" }}>
                          <span className="cellIcon"><Icon name="check-circle" /></span>
                        </span>
                      ) : (
                        <span className="iconTooltip" data-tip={officialStatusText(null)} style={{ color: "var(--muted)" }}>
                          <span className="cellIcon"><Icon name="dash-circle" /></span>
                        </span>
                      )}
                    </td>
                    <td className="iconCol">
                      <span className="iconTooltip" data-tip={riskTip} style={{ color: riskColor }}>
                        <span className="cellIcon"><Icon name="signal" /></span>
                      </span>
                    </td>
                    <td className="iconCol" style={{ fontVariantNumeric: "tabular-nums" }}>
                      {p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : "—"}
                    </td>
                    <td className="dateCol">{fmtDate(p.sample_date)}</td>
                    <td className="iconCol">
                      <button
                        className="starBtn iconTooltip"
                        data-tip={
                          watching
                            ? lruet(lang, "Убрать из избранного", "Eemalda jälgimisest", "Unwatch")
                            : lruet(lang, "Добавить в избранное", "Lisa jälgimisse", "Watch")
                        }
                        style={{ color: watching ? "#f59e0b" : "var(--muted)" }}
                        onClick={(e) => { e.stopPropagation(); toggleWatch(p.id); }}
                      >
                        <span className="cellIcon"><Icon name={watching ? "star" : "star-outline"} /></span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      </div>

      {infoPageOpen ? (
        <div
          className="infoPageBackdrop"
          onClick={() => setInfoPageOpen(false)}
          role="presentation"
        >
        <div
          className="infoPageOverlay"
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="infoPageHeader">
            <h3 className="infoPageTitle">H2O Atlas</h3>
            <button
              className="btn btnSmall infoPageCloseBtn"
              type="button"
              onClick={() => setInfoPageOpen(false)}
              aria-label={t.close}
              title={t.close}
            >
              <span className="btnIcon" aria-hidden="true"><Icon name="close" /></span>
            </button>
          </div>
          <div className="infoPageTabRow">
            {/* Alerts tab removed (its data stays on the main page and keeps
                updating there). Domains tab removed entirely — its info is
                covered by the Domain health report on the main page. */}
            {(["analytics", "aboutModel", "aboutService"] as TabKey[]).map((tab) => (
              <button
                key={`ipt-${tab}`}
                className={`infoPageTab ${infoPageTab === tab ? "active" : ""}`}
                onClick={() => setInfoPageTab(tab)}
              >
                {t.tabs[tab]}
              </button>
            ))}
          </div>
          <div className="infoPageBody">
            {infoPageTab === "alerts" ? (
              <div>
                <h4>{lruet(lang, "Центр алертов", "Häirekeskus", "Alert center")}</h4>
                <p className="hint">
                  {lruet(
                    lang,
                    "Точки с высоким модельным риском или официальными нарушениями.",
                    "Punktid kõrge mudeliriski või ametliku rikkumisega.",
                    "Points with high model risk or official violations."
                  )}
                </p>
                {topAlerts.length === 0 ? (
                  <p className="hint">{lruet(lang, "Нет активных алертов.", "Aktiivseid häireid pole.", "No active alerts.")}</p>
                ) : (
                  <ul className="alertList">
                    {topAlerts.map((p) => (
                      <li key={`ip-alert-${p.id}`}>
                        <button className="linkBtn" onClick={() => { selectPoint(p.id); setInfoPageOpen(false); }}>
                          {p.location}
                        </button>
                        <span className={`badge ${p.risk_level === "high" ? "bad" : "warn"}`}>
                          {p.model_violation_prob !== null ? p.model_violation_prob.toFixed(2) : p.risk_level}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}

            {infoPageTab === "domain" ? (
              <div>
                <h4>{lruet(lang, "Отчёт по доменам", "Domeenide aruanne", "Domain report")}</h4>
                <div className="tableWrap mobileResponsiveTable">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Домен", "Domeen", "Domain")}</th>
                        <th>{lruet(lang, "Всего", "Kokku", "Total")}</th>
                        <th>{lruet(lang, "Наруш.", "Rikkum.", "Viol.")}</th>
                        <th>{lruet(lang, "Высок.", "Kõrge", "High")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {domainStats.map(([d, s]) => (
                        <tr key={`ip-domain-${d}`}>
                          <td>{d}</td>
                          <td>{s.total}</td>
                          <td>{s.violations}</td>
                          <td>{s.highRisk}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {infoPageTab === "analytics" ? (
              <div>
                <h4>{t.tabs.analytics}</h4>
                <div className="stats">
                  {quickInsights.map((i) => (
                    <div className="stat" key={`ip-qi-${i.key}`}>
                      <div className="k">{i.label}</div>
                      <div className="v">
                        {i.value} <span className={`badge ${i.level}`}>{severityLabel(i.level)}</span>
                      </div>
                      <div className="hint">{i.hint}</div>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: "0.75rem" }}>
                  <p className="hint">
                    {lruet(
                      lang,
                      "Модели (LR, RF, GB, LightGBM) оценивают P(нарушение) по лабораторным данным. Это не прогноз будущего.",
                      "Mudelid (LR, RF, GB, LightGBM) hindavad P(rikkumine) laborinäitajate põhjal.",
                      "Models (LR, RF, GB, LightGBM) estimate P(violation) from lab data."
                    )}
                  </p>
                  <div className="tableWrap compact mobileResponsiveTable" style={{ marginTop: "0.5rem" }}>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Model</th>
                          <th>{lruet(lang, "Средняя P", "Keskmine P", "Average P")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(snapshot.diagnostics.mean_model_probabilities || {}).map(([key, val]) => (
                          <tr key={`ip-diag-${key}`}>
                            <td>{snapshot.model_labels?.[key] || key}</td>
                            <td>{typeof val === "number" ? val.toFixed(2) : "n/a"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}

            {infoPageTab === "aboutModel" ? (
              <div>
                <h4>{t.tabs.aboutModel}</h4>
                <p className="hint">{t.aboutModel}</p>

                {/* ── Model comparison: visual bar chart ────────────────── */}
                <div style={{ margin: "1rem 0 0.5rem" }}>
                  <h5 style={{ marginBottom: "0.5rem" }}>
                    {lruet(lang, "Сравнение 4 моделей", "4 mudeli võrdlus", "4-model comparison")}
                    <span className="hint" style={{ fontWeight: 400, marginLeft: "0.5rem" }}>
                      {lruet(lang, "(темпоральный split, тест 2025+)", "(temporal split, test 2025+)", "(temporal split, test 2025+)")}
                    </span>
                  </h5>
                  {[
                    { name: "LR", auc: 0.947, recall: 0.890, precision: 0.560 },
                    { name: "RF", auc: 0.981, recall: 0.929, precision: 0.791 },
                    { name: "GB", auc: 0.982, recall: 0.887, precision: 0.887 },
                    { name: "LGBM", auc: 0.984, recall: 0.949, precision: 0.800 },
                  ].map((m) => (
                    <div key={`mc-${m.name}`} style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
                      <span style={{ width: "3.2rem", fontWeight: 600, fontSize: "0.82rem", fontFamily: "var(--font-latin-ui)" }}>{m.name}</span>
                      <div style={{ flex: 1, display: "flex", gap: "3px", height: "18px" }}>
                        <div title={`AUC ${m.auc}`} style={{ width: `${m.auc * 100}%`, background: "var(--brand, #2563eb)", borderRadius: "3px 0 0 3px", minWidth: "2px", opacity: 0.85 }} />
                        <div title={`Recall ${m.recall}`} style={{ width: `${m.recall * 100}%`, background: "var(--good, #139b55)", minWidth: "2px", opacity: 0.8 }} />
                        <div title={`Precision ${m.precision}`} style={{ width: `${m.precision * 100}%`, background: "var(--warn, #e38f00)", borderRadius: "0 3px 3px 0", minWidth: "2px", opacity: 0.75 }} />
                      </div>
                      <span className="hint" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>AUC {m.auc.toFixed(3)}</span>
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: "1rem", marginTop: "0.3rem", fontSize: "0.72rem" }}>
                    <span><span style={{ display: "inline-block", width: 10, height: 10, background: "var(--brand, #2563eb)", borderRadius: 2, marginRight: 3, verticalAlign: "middle", opacity: 0.85 }} />AUC</span>
                    <span><span style={{ display: "inline-block", width: 10, height: 10, background: "var(--good, #139b55)", borderRadius: 2, marginRight: 3, verticalAlign: "middle", opacity: 0.8 }} />Recall</span>
                    <span><span style={{ display: "inline-block", width: 10, height: 10, background: "var(--warn, #e38f00)", borderRadius: 2, marginRight: 3, verticalAlign: "middle", opacity: 0.75 }} />Precision</span>
                  </div>
                </div>

                {/* ── Key numbers strip ────────────────────────────────── */}
                <div className="stats" style={{ marginTop: "0.75rem" }}>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Проб в корпусе", "Proove korpuses", "Corpus probes")}</div>
                    <div className="v" style={{ fontFamily: "var(--font-latin-ui)" }}>69 536</div>
                  </div>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Фичей модели", "Tunnuseid", "Features")}</div>
                    <div className="v" style={{ fontFamily: "var(--font-latin-ui)" }}>72</div>
                  </div>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Лучшая модель", "Parim mudel", "Best model")}</div>
                    <div className="v">LightGBM <span className="badge good">AUC 0.984</span></div>
                  </div>
                </div>

                <div className="stats" style={{ marginTop: "0.5rem" }}>
                  {quickInsights.map((i) => (
                    <div className="stat" key={`ip-qim-${i.key}`}>
                      <div className="k">{i.label}</div>
                      <div className="v">{i.value} <span className={`badge ${i.level}`}>{severityLabel(i.level)}</span></div>
                    </div>
                  ))}
                </div>

                {/* ── Top SHAP features ────────────────────────────────── */}
                <div style={{ margin: "0.75rem 0 0.5rem" }}>
                  <h5 style={{ marginBottom: "0.4rem" }}>
                    {lruet(lang, "Топ-5 предикторов (SHAP)", "Top-5 ennustajat (SHAP)", "Top-5 predictors (SHAP)")}
                  </h5>
                  {[
                    { param: "iron", label: lruet(lang, "Железо", "Raud", "Iron"), shap: 1.217 },
                    { param: "color", label: lruet(lang, "Цветность", "Värvus", "Color"), shap: 0.751 },
                    { param: "coliforms", label: lruet(lang, "Колиформы", "Kolibakterid", "Coliforms"), shap: 0.591 },
                    { param: "manganese", label: lruet(lang, "Марганец", "Mangaan", "Manganese"), shap: 0.478 },
                    { param: "e_coli", label: "E. coli", shap: 0.312 },
                  ].map((f) => (
                    <div key={`shap-${f.param}`} style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                      <span style={{ width: "5.5rem", fontSize: "0.78rem", color: "var(--muted)" }}>{f.label}</span>
                      <div style={{ flex: 1, height: "12px", background: "var(--panel-soft, #eef1f5)", borderRadius: 6, overflow: "hidden" }}>
                        <div style={{ width: `${Math.min(f.shap / 1.3 * 100, 100)}%`, height: "100%", background: "linear-gradient(90deg, var(--bad, #dc3545), #ff6b6b)", borderRadius: 6, transition: "width 0.6s ease" }} />
                      </div>
                      <span style={{ width: "2.8rem", textAlign: "right", fontSize: "0.72rem", fontFamily: "var(--font-latin-ui)", fontWeight: 600 }}>{f.shap.toFixed(3)}</span>
                    </div>
                  ))}
                  <p className="hint" style={{ fontSize: "0.7rem", marginTop: "0.2rem" }}>
                    {lruet(lang,
                      "SHAP: средний абсолютный вклад в предсказание. Чем длиннее полоска, тем сильнее параметр влияет на риск.",
                      "SHAP: keskmine absoluutne panus ennustusse. Pikem riba = suurem mõju riskile.",
                      "SHAP: mean absolute contribution to prediction. Longer bar = stronger impact on risk.")}
                  </p>
                </div>

                <p className="hint" style={{ marginTop: "0.75rem" }}>
                  {lang === "ru"
                    ? "4 уровня оценки качества: ROC-AUC (разделение классов), Precision/Recall (баланс ошибок), калибровка (доверие к вероятности) и SHAP (пояснение причин прогноза)."
                    : lang === "et"
                      ? "4 hindamistaset: ROC-AUC, Precision/Recall, kalibreeritus ja SHAP selgitused."
                      : "Four levels of model assessment: ROC-AUC (class separation), Precision/Recall (error trade-off), Calibration (probability trust) and SHAP (per-prediction explanation)."}
                </p>
                <div className="tableWrap compact mobileResponsiveTable" style={{ marginTop: "0.75rem" }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Уровень", "Tase", "Level")}</th>
                        <th>{lruet(lang, "Вопрос", "Küsimus", "Question")}</th>
                        <th>{lruet(lang, "Метрика", "Mõõdik", "Metric")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>1</td>
                        <td>{lruet(lang, "Разделяет ли модель классы?", "Kas mudel eristab klasse?", "Does the model separate classes?")}</td>
                        <td>ROC-AUC</td>
                      </tr>
                      <tr>
                        <td>2</td>
                        <td>{lruet(lang, "Какие ошибки?", "Milliseid vigu?", "What errors?")}</td>
                        <td>Precision / Recall</td>
                      </tr>
                      <tr>
                        <td>3</td>
                        <td>{lruet(lang, "Калиброваны ли вероятности?", "Kui hästi kalibreeritud?", "Calibrated?")}</td>
                        <td>Calibration</td>
                      </tr>
                      <tr>
                        <td>4</td>
                        <td>{lruet(lang, "Почему этот риск?", "Miks just see risk?", "Why this risk?")}</td>
                        <td>SHAP</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <h4 style={{ marginTop: "1rem" }}>{t.metricGuideTitle}</h4>
                <div className="infoCardGrid">
                  {(["roc", "pr", "calibration", "shap"] as const).map((key) => (
                    <article key={`ipg-${key}`} className="infoCard">
                      <div className="infoCardHead">
                        <span className="infoCardIcon" aria-hidden>
                          {key === "roc" ? "📈" : key === "pr" ? "🎯" : key === "calibration" ? "⚖️" : "🧠"}
                        </span>
                        <div>
                          <h5>{t.metricGuide[key].title}</h5>
                        </div>
                      </div>
                      <p className="hint"><b>{lruet(lang, "Точно:", "Täpselt:", "Precise:")}</b> {t.metricGuide[key].precise}</p>
                      <p className="hint"><b>{lruet(lang, "Интуиция:", "Intuitsioon:", "Intuition:")}</b> {t.metricGuide[key].intuitive}</p>
                      <p className="hint"><b>{lruet(lang, "Как читать:", "Kuidas lugeda:", "How to read:")}</b> {t.metricGuide[key].reading}</p>
                    </article>
                  ))}
                </div>
                <button
                  className="btn btnSmall"
                  style={{ marginTop: "0.6rem" }}
                  onClick={() => openInfo(lruet(lang, "Режим эксперта", "Eksperdireziim", "Expert mode"), expertModeText)}
                >
                  {lruet(lang, "Подробнее (режим эксперта)", "Rohkem (eksperdireziim)", "More (expert mode)")}
                </button>
              </div>
            ) : null}

            {infoPageTab === "aboutService" ? (
              <div>
                <h4>{t.tabs.aboutService}</h4>
                <p className="hint">{t.aboutService}</p>

                {/* ── Data corpus at a glance ──────────────────────────── */}
                <div className="stats" style={{ marginTop: "0.75rem" }}>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Проб", "Proove", "Probes")}</div>
                    <div className="v" style={{ fontFamily: "var(--font-latin-ui)", fontSize: "1.1rem" }}>69 536</div>
                  </div>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Доменов", "Domeene", "Domains")}</div>
                    <div className="v" style={{ fontFamily: "var(--font-latin-ui)", fontSize: "1.1rem" }}>4</div>
                  </div>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Лет данных", "Aastat andmeid", "Years of data")}</div>
                    <div className="v" style={{ fontFamily: "var(--font-latin-ui)", fontSize: "1.1rem" }}>2021–2026</div>
                  </div>
                  <div className="stat">
                    <div className="k">{lruet(lang, "Точек на карте", "Punkte kaardil", "Map locations")}</div>
                    <div className="v" style={{ fontFamily: "var(--font-latin-ui)", fontSize: "1.1rem" }}>{snapshot.places?.length || "2 196"}</div>
                  </div>
                </div>

                <p className="hint" style={{ marginTop: "0.6rem" }}>
                  {lang === "ru"
                    ? "Этот сервис — публичный инструмент экологической прозрачности для жителей, муниципалитетов и госструктур. Он объединяет официальные открытые данные Terviseamet и аналитический ML-слой, чтобы вода оценивалась не только постфактум, но и через ранние риск-сигналы."
                    : lang === "et"
                      ? "See teenus on avalik keskkonnaläbipaistvuse tööriist elanikele, omavalitsustele ja riigiasutustele. See ühendab Terviseameti ametlikud avaandmed ning ML-analüüsi kihi."
                      : "A public environmental-transparency tool for residents, municipalities and authorities. It combines official Terviseamet open data with an ML analytics layer for early risk signals on top of post-fact compliance reporting."}
                </p>
                <p className="hint">
                  {lang === "ru"
                    ? "По каждой точке доступны: дата и контекст последней пробы, официальный статус соответствия, вероятности нарушения от нескольких моделей, история наблюдений и пояснения ключевых параметров."
                    : lang === "et"
                      ? "Iga punkti kohta: viimase proovi kuupäev, ametlik vastavus, mitme mudeli rikkumistõenäosused, vaatlusajalugu ja võtmenäitajate selgitused."
                      : "For every point: latest sample date and context, official compliance status, model violation probabilities, observation history and explanations of the main water parameters."}
                </p>
                <p className="hint">
                  {lang === "ru"
                    ? "Важно: модельные оценки не заменяют официальный санитарный вердикт. Они предназначены для приоритезации проверок и более раннего обнаружения потенциально проблемных зон."
                    : lang === "et"
                      ? "Oluline: mudelihinnangud ei asenda ametlikku sanitaarset otsust — need on mõeldud kontrollide prioritiseerimiseks."
                      : "Important: model assessments do not replace the official sanitary verdict. They support inspection prioritization and earlier detection of potential problem areas."}
                </p>
                {/* ── Key research findings ─────────────────────────── */}
                <div style={{ margin: "0.75rem 0", padding: "0.6rem 0.8rem", background: "var(--panel-soft, #eef1f5)", borderRadius: 8, borderLeft: "3px solid var(--brand, #2563eb)" }}>
                  <h5 style={{ marginBottom: "0.35rem", fontSize: "0.82rem" }}>
                    {lruet(lang, "Ключевые находки проекта", "Projekti peamised avastused", "Key research findings")}
                  </h5>
                  <ul className="hint" style={{ margin: 0, paddingLeft: "1.1rem", lineHeight: 1.6 }}>
                    <li>{lruet(lang,
                      "Обнаружена и исправлена ошибка в нормах хлора бассейнов: free_chlorine [0.2, 0.6] → [0.5, 1.5] мг/л — устранены 288 ложных срабатываний.",
                      "Avastatud ja parandatud basseini kloori normide viga: free_chlorine [0.2, 0.6] → [0.5, 1.5] mg/l — 288 valepositiivset kõrvaldatud.",
                      "Pool chlorine norms bug found and fixed: free_chlorine [0.2, 0.6] → [0.5, 1.5] mg/l — 288 false positives eliminated."
                    )}</li>
                    <li>{lruet(lang,
                      "3.1% проб (2 164 из 69 536) не воспроизводимы из опубликованных параметров — запрос в Terviseamet подготовлен.",
                      "3.1% proovidest (2 164 / 69 536) pole avalikustatud parameetritest reprodutseeritavad — päring Terviseametile koostatud.",
                      "3.1% of probes (2,164 / 69,536) cannot be reproduced from published parameters — inquiry to Terviseamet prepared."
                    )}</li>
                    <li>{lruet(lang,
                      "XML-парсер проверен на 160 МБ данных: ноль потерянных параметров.",
                      "XML parser kontrollitud 160 MB andmetel: null kaotatud parameetrit.",
                      "XML parser verified on 160 MB of data: zero measurement parameters lost."
                    )}</li>
                  </ul>
                </div>

                {snapshot.data_catalog_url ? (
                  <p className="hint">
                    {lruet(lang, "Источник:", "Allikas:", "Source:")}{" "}
                    <a href={snapshot.data_catalog_url} target="_blank" rel="noreferrer" className="linkBtn">
                      {snapshot.data_catalog_url}
                    </a>
                  </p>
                ) : null}
                <h4 style={{ marginTop: "1rem" }}>{lruet(lang, "Слои и интерпретация карты", "Kaardikihid ja tõlgendus", "Map layers")}</h4>
                <div className="tableWrap compact mobileResponsiveTable" style={{ marginTop: "0.4rem" }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{lruet(lang, "Элемент", "Element", "Element")}</th>
                        <th>{lruet(lang, "Описание", "Kirjeldus", "Description")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>{lruet(lang, "Цвет маркера", "Markeri värv", "Marker color")}</td>
                        <td>{lruet(lang, "Зелёный/жёлтый/красный = низкий/средний/высокий риск", "Roheline/kollane/punane = madal/keskmine/kõrge risk", "Green/yellow/red = low/medium/high risk")}</td>
                      </tr>
                      <tr>
                        <td>{lruet(lang, "Иконка", "Ikoon", "Icon")}</td>
                        <td>{lruet(lang, "Тип: пляж, бассейн, сеть, источник", "Tüüp: rand, bassein, võrk, allikas", "Type: beach, pool, network, source")}</td>
                      </tr>
                      <tr>
                        <td>{lruet(lang, "Кластер", "Klaster", "Cluster")}</td>
                        <td>{lruet(lang, "Количество точек в группе", "Punktide arv grupis", "Number of points in group")}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <h4 style={{ marginTop: "1rem" }}>{lruet(lang, "Карточки параметров", "Parameetrikaardid", "Parameter cards")}</h4>
                <div className="infoCardGrid">
                  {parameterCards.map((card) => (
                    <article key={`ipc-${card.key}`} className="infoCard">
                      <div className="infoCardHead">
                        <span className="infoCardIcon" aria-hidden>{card.icon}</span>
                        <div>
                          <h5>{lruet(lang, card.ruTitle, card.etTitle, card.ruTitle)}</h5>
                          <span className="badge warn">{lruet(lang, card.ruImpact, card.etImpact, card.enImpact || card.ruImpact)}</span>
                        </div>
                      </div>
                      <p className="hint">{lruet(lang, card.ruWhy, card.etWhy, card.enWhy || card.ruWhy)}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Copyright footer — present on every info tab so the user
                always sees attribution and disclaimer. */}
            <p className="gmCopyright" style={{ marginTop: "1.2rem" }}>
              © {new Date().getFullYear()} H2O Atlas ·{" "}
              {lruet(
                lang,
                "Открытые данные Terviseamet · ML — поддержка решений, не медицинская рекомендация.",
                "Terviseameti avaandmed · ML — otsusetugi, mitte meditsiiniline soovitus.",
                "Terviseamet open data · ML — decision support, not medical advice."
              )}
            </p>
          </div>
        </div>
        </div>
      ) : null}

      {infoOpen ? (
        <div className="modalBackdrop" onClick={() => setInfoOpen(false)}>
          <div
            className="modalCard panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="info-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modalHeader">
              <h3 className="sectionTitle" id="info-modal-title">{infoTitle}</h3>
              <button
                ref={infoCloseBtnRef}
                type="button"
                className="modalCloseBtn"
                onClick={() => setInfoOpen(false)}
                aria-label={t.close}
                title={t.close}
              >
                <Icon name="close" />
              </button>
            </div>
            <div className="modalBody">{renderInfoContent(infoText)}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
