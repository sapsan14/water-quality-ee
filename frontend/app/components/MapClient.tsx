"use client";

import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import type { FrontendPlace } from "../lib/types";
import { pointInFeature, countyNameNorm as geoCountyNameNorm, countyFeatureName as geoCountyFeatureName } from "../lib/geo";

type DomainKey = "supluskoha" | "veevark" | "joogivesi" | "basseinid";
type NormRule = { min?: number; max?: number; exact?: number; unit: string };

const NORM_RULES: Record<string, Partial<Record<DomainKey, NormRule>> & { default?: NormRule }> = {
  e_coli: {
    supluskoha: { max: 500, unit: "KOE/100 ml" },
    basseinid: { exact: 0, unit: "KOE/100 ml" },
    default: { max: 500, unit: "KOE/100 ml" }
  },
  enterococci: { supluskoha: { max: 200, unit: "KOE/100 ml" }, default: { max: 200, unit: "KOE/100 ml" } },
  coliforms: { basseinid: { exact: 0, unit: "KOE/100 ml" } },
  pseudomonas: { basseinid: { exact: 0, unit: "KOE/100 ml" } },
  staphylococci: { basseinid: { max: 20, unit: "KOE/100 ml" } },
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
  turbidity: { basseinid: { max: 0.5, unit: "NTU" }, default: { max: 4.0, unit: "NTU" } },
  color: { default: { max: 20, unit: "mg Pt/L" } },
  chlorides: { default: { max: 250, unit: "mg/L" } },
  sulfates: { default: { max: 250, unit: "mg/L" } },
  free_chlorine: { basseinid: { min: 0.2, max: 0.6, unit: "mg/L" } },
  combined_chlorine: { basseinid: { max: 0.4, unit: "mg/L" } }
};

const getNormRule = (param: string, domain: string): NormRule | null => {
  const def = NORM_RULES[param];
  if (!def) return null;
  return (def[domain as DomainKey] ?? def.default ?? null) as NormRule | null;
};

const formatNorm = (rule: NormRule) => {
  if (typeof rule.exact === "number") return `= ${rule.exact} ${rule.unit}`;
  if (typeof rule.min === "number" && typeof rule.max === "number") return `${rule.min}-${rule.max} ${rule.unit}`;
  if (typeof rule.min === "number") return `>= ${rule.min} ${rule.unit}`;
  if (typeof rule.max === "number") return `<= ${rule.max} ${rule.unit}`;
  return rule.unit;
};

const isViolated = (value: number, rule: NormRule) => {
  if (typeof rule.exact === "number" && value !== rule.exact) return true;
  if (typeof rule.min === "number" && value < rule.min) return true;
  if (typeof rule.max === "number" && value > rule.max) return true;
  return false;
};

const markerHtml = (riskLevel: FrontendPlace["risk_level"]) => {
  const base =
    riskLevel === "high"
      ? "#ef4444"
      : riskLevel === "medium"
        ? "#f59e0b"
        : riskLevel === "low"
          ? "#22c55e"
          : "#64748b";
  return base;
};

function placeKindGlyph(kind: string) {
  if (kind === "swimming") return "🏖";
  if (kind === "pool_spa") return "🏊";
  if (kind === "drinking_water") return "🚰";
  if (kind === "drinking_source") return "💧";
  return "📍";
}

const markerBadgeHtml = (color: string, glyph: string, pulse = false) => `
  <div style="
    position:relative;
    width:44px;
    height:56px;
    filter:drop-shadow(0 4px 10px rgba(0,0,0,0.45));
  ">
    <div style="
      width:44px;height:44px;border-radius:50%;background:${color};
      border:3px solid rgba(255,255,255,0.95);display:flex;align-items:center;
      justify-content:center;font-size:22px;line-height:1;
      ${pulse ? "animation:pinPulse 1.8s ease-in-out infinite;" : ""}
    ">${glyph}</div>
    <div style="
      position:absolute;bottom:0;left:50%;transform:translateX(-50%);
      width:0;height:0;
      border-left:9px solid transparent;border-right:9px solid transparent;
      border-top:14px solid ${color};
    "></div>
  </div>
`;

function markerIcon(place: FrontendPlace) {
  const colorByRisk = markerHtml(place.risk_level);
  const fallbackByOfficial =
    place.official_compliant === 1 ? "#22c55e" : place.official_compliant === 0 ? "#ef4444" : "#94a3b8";
  const color = place.model_violation_prob !== null ? colorByRisk : fallbackByOfficial;
  const glyph = placeKindGlyph(place.place_kind);
  const pulse = place.risk_level === "high" && place.model_violation_prob !== null;
  return L.divIcon({
    className: "",
    html: markerBadgeHtml(color, glyph, pulse),
    iconSize: [44, 56],
    iconAnchor: [22, 56],
    popupAnchor: [0, -58]
  });
}

const riskLabel = (riskLevel: FrontendPlace["risk_level"], locale: "ru" | "et" | "en") => {
  const ru = { low: "низкий", medium: "средний", high: "высокий", unknown: "неизвестно" };
  const et = { low: "madal", medium: "keskmine", high: "kõrge", unknown: "teadmata" };
  const en = { low: "low", medium: "medium", high: "high", unknown: "unknown" };
  return locale === "ru" ? ru[riskLevel] : locale === "et" ? et[riskLevel] : en[riskLevel];
};

const placeKindLabel = (kind: string, locale: "ru" | "et" | "en") => {
  const ru: Record<string, string> = {
    swimming: "Открытая вода",
    pool_spa: "Бассейн/СПА",
    drinking_water: "Питьевая вода (сеть)",
    drinking_source: "Источник питьевой воды"
  };
  const et: Record<string, string> = {
    swimming: "Avavesi",
    pool_spa: "Bassein/SPA",
    drinking_water: "Joogivesi (võrk)",
    drinking_source: "Joogiveeallikas"
  };
  const en: Record<string, string> = {
    swimming: "Open water",
    pool_spa: "Pool/SPA",
    drinking_water: "Drinking water (network)",
    drinking_source: "Drinking water source"
  };
  return (locale === "ru" ? ru : locale === "et" ? et : en)[kind] || kind;
};

const countyNameNorm = geoCountyNameNorm;
const countyDisplay = (s: string) =>
  s
    .trim()
    .split(/\s+/)
    .map((x) => x.charAt(0).toUpperCase() + x.slice(1).toLowerCase())
    .join(" ");

const countyFeatureName = geoCountyFeatureName;

function popupHtml(place: FrontendPlace, locale: "ru" | "et" | "en") {
  const status =
    place.official_compliant === 1
      ? locale === "ru"
        ? "соответствует"
        : "vastab"
      : place.official_compliant === 0
        ? locale === "ru"
          ? "нарушение"
          : "rikkumine"
        : "n/a";

  const probPct = place.model_violation_prob !== null ? `${(place.model_violation_prob * 100).toFixed(0)}%` : "n/a";
  const measurementRows = Object.entries(place.measurements || {})
    .slice(0, 8)
    .map(([k, v]) => {
      const numericValue = typeof v === "number" ? v : Number(v);
      const rule = getNormRule(k, place.domain);
      const normText = rule ? formatNorm(rule) : (locale === "ru" ? "нет нормы" : locale === "et" ? "norm puudub" : "no norm");
      const violated = Number.isFinite(numericValue) && rule ? isViolated(numericValue, rule) : false;
      return `<tr><td style="padding-right:8px">${k}</td><td><b>${String(v)}</b></td><td style="padding-left:8px;color:${violated ? "#ef4444" : "#64748b"}">${normText}</td></tr>`;
    })
    .join("");
  const violatedRows = Object.entries(place.measurements || {})
    .map(([k, v]) => {
      const numericValue = typeof v === "number" ? v : Number(v);
      if (!Number.isFinite(numericValue)) return "";
      const rule = getNormRule(k, place.domain);
      if (!rule || !isViolated(numericValue, rule)) return "";
      return `<li>${k}: <b>${numericValue}</b> (${locale === "ru" ? "норма" : locale === "et" ? "norm" : "norm"} ${formatNorm(rule)})</li>`;
    })
    .filter(Boolean)
    .join("");

  return `
    <div style="font-size:13px;line-height:1.35;min-width:250px">
      <div style="font-weight:700;margin-bottom:4px">${place.location}</div>
      <div style="color:#475569">${placeKindLabel(place.place_kind, locale)} · ${place.domain}</div>
      <div style="margin-top:6px">${locale === "ru" ? "Официально" : locale === "et" ? "Ametlik" : "Official"}: <b>${status}</b></div>
      <div>${locale === "ru" ? "Риск" : locale === "et" ? "Risk" : "Risk"}: <b>${riskLabel(place.risk_level, locale)}</b></div>
      <div>${locale === "ru" ? "Вероятность нарушения" : locale === "et" ? "Rikkumise tõenäosus" : "Violation probability"}: <b>${probPct}</b></div>
      <div style="margin-top:4px;color:#475569">${locale === "ru" ? `Это значит: примерно ${probPct} риск нарушения для этой пробы по модели (это не прогноз будущего).` : locale === "et" ? `See tähendab: umbes ${probPct} rikkumisrisk selle proovi jaoks mudeli järgi (see ei ole tuleviku prognoos).` : `This means: about ${probPct} violation risk for this sample according to the model (not a future forecast).`}</div>
      <div style="margin-top:6px;color:#475569">${locale === "ru" ? "Последняя проба" : locale === "et" ? "Viimane proov" : "Latest sample"}: ${place.sample_date || "n/a"}</div>
      ${
        measurementRows
          ? `<div style="margin-top:6px"><div style="font-weight:600;margin-bottom:2px">${locale === "ru" ? "Показатели (со справкой по нормам)" : locale === "et" ? "Näitajad (normi viitega)" : "Measurements (with norm reference)"}</div><table>${measurementRows}</table></div>`
          : ""
      }
      ${
        place.official_compliant === 0
          ? `<div style="margin-top:6px"><div style="font-weight:600;margin-bottom:2px;color:#ef4444">${locale === "ru" ? "Причина нарушения" : locale === "et" ? "Rikkumise põhjus" : "Violation reason"}</div>${
              violatedRows
                ? `<ul style="margin:0;padding-left:16px">${violatedRows}</ul>`
                : `<div style="color:#64748b">${locale === "ru" ? "По текущим экспортированным показателям явное превышение не найдено." : locale === "et" ? "Praeguste eksporditud näitajate põhjal selget ületust ei leitud." : "No explicit exceedance found in currently exported measurements."}</div>`
            }</div>`
          : ""
      }
    </div>
  `;
}

function clusterColor(avg: number) {
  if (avg >= 0.7) return "#ef4444";
  if (avg >= 0.4) return "#f59e0b";
  return "#22c55e";
}

type ClusterLike = {
  getAllChildMarkers: () => Array<L.Marker & { options: L.MarkerOptions & { place?: FrontendPlace } }>;
  getChildCount: () => number;
  spiderfy: () => void;
  getBounds: () => L.LatLngBounds;
  zoomToBounds: (opts?: { padding: [number, number] }) => void;
};

function MarkerClusterLayer({
  places,
  locale,
  onSelectPoint,
  onSelectCluster,
  disableHoverPopups = false
}: {
  places: FrontendPlace[];
  locale: "ru" | "et" | "en";
  onSelectPoint?: (id: string) => void;
  onSelectCluster?: (ids: string[]) => void;
  disableHoverPopups?: boolean;
}) {
  const map = useMap();
  const [clusterReady, setClusterReady] = useState(false);

  useEffect(() => {
    let alive = true;
    import("leaflet.markercluster")
      .then(() => {
        if (alive) setClusterReady(true);
      })
      .catch(() => {
        if (alive) setClusterReady(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!clusterReady) return;
    const markerClusterFactory = (L as unknown as { markerClusterGroup: (opts: unknown) => L.LayerGroup }).markerClusterGroup;
    const group = markerClusterFactory({
      chunkedLoading: true,
      spiderfyOnMaxZoom: true,
      spiderfyDistanceMultiplier: 1.35,
      showCoverageOnHover: false,
      zoomToBoundsOnClick: false,
      iconCreateFunction: (cluster: unknown) => {
        const c = cluster as ClusterLike;
        const children = c.getAllChildMarkers();
        const probs = children
          .map((m) => m.options?.place?.model_violation_prob)
          .filter((v: unknown) => typeof v === "number") as number[];
        const avg = probs.length ? probs.reduce((a, b) => a + b, 0) / probs.length : 0.5;
        const color = clusterColor(avg);
        const count = c.getChildCount();
        const size = count > 99 ? 52 : count > 9 ? 48 : 44;
        return L.divIcon({
          html: `<div style="background:${color};color:#fff;border-radius:999px;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;border:3px solid rgba(255,255,255,0.95);font-weight:700;font-size:${count > 99 ? 13 : 15}px;box-shadow:0 3px 12px rgba(0,0,0,0.35)">${count}</div>`,
          className: "",
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2]
        });
      }
    });

    // Custom cluster click: if all children share (nearly) the same
    // coordinates, show them as a list in the bottom sheet (via
    // onSelectCluster) instead of zooming — which would just
    // re-cluster them at a higher zoom level. For spread clusters,
    // zoom to bounds as usual.
    (group as L.LayerGroup & { on: (event: string, fn: (e: unknown) => void) => void }).on(
      "clusterclick",
      (e: unknown) => {
        const evt = e as { layer: ClusterLike };
        const cluster = evt.layer;
        const bounds = cluster.getBounds();

        // ~50 meters in lat/lon degrees — any cluster fitting in this
        // box has all children at effectively the same physical location.
        const THRESHOLD = 0.0005;
        const latSpan = bounds.getNorth() - bounds.getSouth();
        const lngSpan = bounds.getEast() - bounds.getWest();

        if (latSpan < THRESHOLD && lngSpan < THRESHOLD) {
          // Co-located: show list in bottom sheet, cluster stays on map
          if (onSelectCluster) {
            const ids = cluster.getAllChildMarkers()
              .map((m) => m.options?.place?.id)
              .filter((id): id is string => Boolean(id));
            onSelectCluster(ids);
          } else {
            cluster.spiderfy();
          }
        } else {
          cluster.zoomToBounds({ padding: [20, 20] });
        }
      }
    );

    places.forEach((place) => {
      const marker = L.marker([place.lat, place.lon], {
        icon: markerIcon(place),
        place
      } as L.MarkerOptions & { place: FrontendPlace });
      // On mobile (disableHoverPopups=true): skip popup entirely — bottom sheet shows details
      if (!disableHoverPopups) {
        // Desktop: let Leaflet auto-pan the map when a popup would be
        // clipped by map borders or covered by the floating UI buttons.
        // Padding clears:
        //  - top-right:   mapFullscreenBtn (~46–56px tall, ~140px wide incl. label)
        //  - bottom-right: mapFloatingControls stack — recenter + reset
        //                  (~100px tall, ~66px wide)
        // Extra top padding also keeps the popup tip (popupAnchor -58)
        // from being cropped at the top edge.
        marker.bindPopup(popupHtml(place, locale), {
          maxWidth: 360,
          autoPan: true,
          autoPanPaddingTopLeft: L.point(20, 90),
          autoPanPaddingBottomRight: L.point(90, 110)
        });

        // Use a short close-delay so moving from the pin into the popup doesn't
        // cause flicker (mouseover → popup opens over pin → mouseout fires → popup
        // closes → back to marker → repeat). The popup's own mouseenter/mouseleave
        // cancel / reschedule the timer so the popup stays open while hovered.
        let closeTimer: ReturnType<typeof setTimeout> | null = null;
        const cancelClose = () => {
          if (closeTimer !== null) { clearTimeout(closeTimer); closeTimer = null; }
        };
        const scheduleClose = () => {
          cancelClose();
          closeTimer = setTimeout(() => { marker.closePopup(); }, 150);
        };

        marker.on("mouseover", () => { cancelClose(); marker.openPopup(); });
        marker.on("mouseout", scheduleClose);

        marker.on("popupopen", () => {
          const el = marker.getPopup()?.getElement();
          if (!el) return;
          el.removeEventListener("mouseenter", cancelClose);
          el.removeEventListener("mouseleave", scheduleClose);
          el.addEventListener("mouseenter", cancelClose);
          el.addEventListener("mouseleave", scheduleClose);
        });
      }
      marker.on("click", () => {
        onSelectPoint?.(place.id);
        if (!disableHoverPopups) marker.openPopup();
      });
      (group as L.LayerGroup).addLayer(marker);
    });

    map.addLayer(group as L.Layer);
    return () => {
      map.removeLayer(group as L.Layer);
    };
  }, [map, places, locale, onSelectPoint, onSelectCluster, clusterReady, disableHoverPopups]);
  return null;
}

// Module-level constant so it's stable across renders
const ESTONIA_BOUNDS: [[number, number], [number, number]] = [
  [57.1, 20.7],
  [60.15, 29.4]
];

type Props = {
  places: FrontendPlace[];
  onSelectPoint?: (id: string) => void;
  onSelectCluster?: (ids: string[]) => void;
  locale?: "ru" | "et" | "en";
  onSelectCounty?: (county: string) => void;
  selectedCounty?: string;
  selectedPoint?: FrontendPlace | null;
  userLocation?: { lat: number; lon: number } | null;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
  fullscreenLabel?: string;
  disableHoverPopups?: boolean;
  onResetView?: () => void;
  onRecenterUser?: () => void;
  resetViewLabel?: string;
  recenterLabel?: string;
  canRecenter?: boolean;
  isMobile?: boolean;
  showCountyOverlay?: boolean;
  /** Pre-loaded county GeoJSON from Dashboard. When provided, MapClient
   *  skips its own fetch and uses this for the overlay + polygon filter. */
  countyGeoJson?: GeoJSON.GeoJsonObject | null;
  fitBoundsKey?: string;
  fitBoundsPlaces?: [number, number][];
  /** Pixels obscured by the bottom sheet (peek/half) + on-screen keyboard. */
  bottomOverlayPx?: number;
  /** Pixels obscured by the top search bar + chip bar. */
  topOverlayPx?: number;
};

/**
 * Compute the map-container y coordinate where the selected marker should
 * appear: the centre of the visible strip between the top chrome and the
 * bottom sheet, clamped with a ~72px margin on each side so the pin never
 * hugs either edge. In the degenerate "sheet covers almost everything"
 * case (e.g. full drawer on a short phone) the clamp still guarantees the
 * pin sits above the sheet top rather than vanishing underneath it.
 *
 * Coordinates are in *map container* pixels — i.e. the same frame Leaflet
 * uses for `project` / `unproject`. `topOverlayPx` / `bottomOverlayPx` are
 * measured from the respective edges of the **visible viewport** (window.
 * innerHeight), which normally matches the map container height but may
 * differ on mobile browsers where `100vh` / large-viewport units leak
 * extra pixels below the URL bar. We correct for that below.
 */
function computeVisibleTargetY(
  mapHeight: number,
  viewportHeight: number,
  topOverlayPx: number,
  bottomOverlayPx: number
): number {
  // Sheet top / chrome bottom in map-container coords. The container's y=0
  // aligns with the visible viewport's top (fullscreen map is
  // `position: fixed; inset: 0`), so overlay measurements carry over
  // directly; we only need to clamp to the container's own bottom.
  const sheetTopY = Math.max(0, viewportHeight - bottomOverlayPx);
  const chromeBottomY = Math.min(mapHeight, Math.max(0, topOverlayPx));
  const MARGIN = 72;
  const safeTop = chromeBottomY + MARGIN;
  const safeBottom = Math.min(mapHeight, sheetTopY) - MARGIN;
  if (safeBottom <= safeTop) {
    // Visible strip is narrower than 2×MARGIN; prefer keeping the pin above
    // the sheet so the user can still see it, even if we crowd the top
    // chrome a bit.
    return Math.max(MARGIN, Math.min(mapHeight - MARGIN, sheetTopY - MARGIN));
  }
  const centre = (chromeBottomY + Math.min(mapHeight, sheetTopY)) / 2;
  return Math.max(safeTop, Math.min(safeBottom, centre));
}

/**
 * Keep the selected point centred in the *visible* strip of the map, i.e.
 * the area not covered by the top search/chip bar nor the bottom sheet or
 * on-screen keyboard. Re-runs whenever the selected point identity changes
 * OR an overlay height changes (sheet snap state, keyboard open/close),
 * so the pin stays in view as the UI expands/collapses around it.
 *
 * `bottomOverlayPx` = pixels obscured at the bottom (sheet peek/half/full + IME).
 * `topOverlayPx`    = pixels obscured at the top (search bar + chip bar).
 *
 * During a sheet drag the overlay value does NOT change (it's derived from
 * the discrete snap state, not the live drag offset), so this effect does
 * not cause jitter while the user is dragging.
 */
function FocusOnSelectedPoint({
  selectedPoint,
  bottomOverlayPx = 0,
  topOverlayPx = 0
}: {
  selectedPoint?: FrontendPlace | null;
  bottomOverlayPx?: number;
  topOverlayPx?: number;
}) {
  const map = useMap();
  const prevIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedPoint) { prevIdRef.current = null; return; }
    const idChanged = selectedPoint.id !== prevIdRef.current;
    prevIdRef.current = selectedPoint.id;

    const target: [number, number] = [selectedPoint.lat, selectedPoint.lon];
    const targetZoom = Math.max(map.getZoom(), 11);

    // Use actual map container dimensions (not window.innerHeight) so the
    // math is correct even when `100vh` ≠ visible viewport height on
    // mobile browsers. Leaflet's `getSize()` returns the map container in
    // CSS pixels — the same frame `project` / `unproject` operate in.
    const mapSize = map.getSize();
    const mapHeight = mapSize.y;
    const viewportHeight =
      typeof window !== "undefined" ? window.innerHeight : mapHeight;

    const desiredY = computeVisibleTargetY(
      mapHeight,
      viewportHeight,
      topOverlayPx,
      bottomOverlayPx
    );

    // We want the marker to land at container y = desiredY. At zoom Z,
    // marker_container_y = mapHeight/2 + project(marker).y - project(centre).y
    // Solving: project(centre).y = project(marker).y + mapHeight/2 - desiredY
    const offsetY = mapHeight / 2 - desiredY;
    const point = map.project(target, targetZoom);
    point.y += offsetY;
    const adjusted = map.unproject(point, targetZoom);

    // On a fresh selection, fly with the usual cinematic duration. When only
    // an overlay changed (e.g. sheet dragged to a new snap state for the
    // same pin), pan more briskly so the pin tracks the visible strip
    // without a slow re-zoom animation.
    if (idChanged) {
      map.flyTo(adjusted, targetZoom, { duration: 0.6 });
    } else {
      map.panTo(adjusted, { animate: true, duration: 0.35 });
    }
  }, [map, selectedPoint, bottomOverlayPx, topOverlayPx]);
  return null;
}

/**
 * When filters/search shrink the result set, fit the visible bounds — but
 * if it collapses to a single (or near-single) match, fly to the first hit
 * with offsets that account for the search bar, chips and bottom sheet.
 */
function FitBoundsOnVersion({
  fitBoundsKey,
  places,
  topOverlayPx = 95,
  bottomOverlayPx = 62
}: {
  fitBoundsKey?: string;
  places?: [number, number][];
  topOverlayPx?: number;
  bottomOverlayPx?: number;
}) {
  const map = useMap();
  const prevKeyRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!fitBoundsKey || fitBoundsKey === prevKeyRef.current || !places || places.length === 0) return;
    prevKeyRef.current = fitBoundsKey;
    if (places.length === 1) {
      const targetZoom = Math.max(map.getZoom(), 12);
      // Reuse FocusOnSelectedPoint's clamped visible-strip centre so a
      // single match lands in the same safe area as a tapped pin, even
      // when the bottom sheet is already open.
      const mapSize = map.getSize();
      const mapHeight = mapSize.y;
      const viewportHeight =
        typeof window !== "undefined" ? window.innerHeight : mapHeight;
      const desiredY = computeVisibleTargetY(
        mapHeight,
        viewportHeight,
        topOverlayPx,
        bottomOverlayPx
      );
      const point = map.project(places[0], targetZoom);
      point.y += mapHeight / 2 - desiredY;
      const adjusted = map.unproject(point, targetZoom);
      map.flyTo(adjusted, targetZoom, { duration: 0.6 });
      return;
    }
    const bounds = L.latLngBounds(places.map(([lat, lon]) => [lat, lon]));
    map.fitBounds(bounds, {
      animate: true,
      paddingTopLeft: [10, topOverlayPx],
      paddingBottomRight: [10, bottomOverlayPx],
      maxZoom: 13
    });
  }, [fitBoundsKey, places, map, topOverlayPx, bottomOverlayPx]);
  return null;
}

function FocusOnUserLocation({ userLocation }: { userLocation?: { lat: number; lon: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (!userLocation) return;
    map.flyTo([userLocation.lat, userLocation.lon], Math.max(map.getZoom(), 11), {
      duration: 0.7
    });
  }, [map, userLocation]);
  return null;
}

function MapClient({
  places,
  onSelectPoint,
  onSelectCluster,
  locale = "ru",
  onSelectCounty,
  selectedCounty,
  selectedPoint,
  userLocation,
  isFullscreen = false,
  onToggleFullscreen,
  fullscreenLabel = "Fullscreen",
  disableHoverPopups = false,
  onResetView,
  onRecenterUser,
  resetViewLabel = "Reset view",
  recenterLabel = "Near me",
  canRecenter = true,
  isMobile = false,
  showCountyOverlay = true,
  countyGeoJson: countyGeoJsonProp,
  fitBoundsKey,
  fitBoundsPlaces,
  bottomOverlayPx = 0,
  topOverlayPx = 95
}: Props) {
  const selectedCountyNorm = selectedCounty ? countyNameNorm(selectedCounty) : null;
  const countyRisk = useMemo(() => {
    const acc = new Map<string, { sum: number; n: number }>();
    for (const p of places) {
      const county = countyDisplay((p.county || "").trim());
      if (!county || p.model_violation_prob === null) continue;
      const prev = acc.get(county) || { sum: 0, n: 0 };
      prev.sum += p.model_violation_prob;
      prev.n += 1;
      acc.set(county, prev);
    }
    const out = new Map<string, number>();
    for (const [k, v] of acc.entries()) out.set(k, v.sum / Math.max(1, v.n));
    return out;
  }, [places]);

  const center: [number, number] = [58.75, 25.0];
  const mapRef = useRef<L.Map | null>(null);
  // Use the prop if Dashboard provides it; otherwise fall back to local state.
  const [countyGeoJsonLocal, setCountyGeoJsonLocal] = useState<GeoJSON.GeoJsonObject | null>(null);
  const countyGeoJson = countyGeoJsonProp ?? countyGeoJsonLocal;
  const setCountyGeoJson = setCountyGeoJsonLocal;

  const visiblePlaces = useMemo(() => {
    if (!selectedCountyNorm || !countyGeoJson || countyGeoJson.type !== "FeatureCollection") return places;
    const featureCollection = countyGeoJson as GeoJSON.FeatureCollection;
    const features = featureCollection.features as GeoJSON.Feature[];
    const selectedFeature = features.find((f) => countyNameNorm(countyFeatureName(f)) === selectedCountyNorm);
    if (!selectedFeature) return places;
    return places.filter((p) => pointInFeature(p.lon, p.lat, selectedFeature));
  }, [places, selectedCountyNorm, countyGeoJson]);


  useEffect(() => {
    return () => {
      // В dev (Fast Refresh) Leaflet иногда оставляет map instance на контейнере.
      // Явно удаляем карту, чтобы избежать "Map container is already initialized".
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const labels = [
      { name: "Lahemaa", lat: 59.58, lon: 25.9 },
      { name: "Soomaa", lat: 58.44, lon: 25.11 },
      { name: "Saaremaa", lat: 58.42, lon: 22.55 },
      { name: "Peipsi", lat: 58.6, lon: 27.3 }
    ];
    const g = L.layerGroup();
    labels.forEach((z) => {
      L.marker([z.lat, z.lon], {
        interactive: false,
        icon: L.divIcon({
          className: "",
          html: `<div class="zoneTag">${z.name}</div>`
        })
      }).addTo(g);
    });
    g.addTo(map);
    return () => {
      g.remove();
    };
  }, []);

  useEffect(() => {
    if (!showCountyOverlay) return;
    // Skip refetch if we already have the data (from prop or prior fetch).
    if (countyGeoJson) return;
    if (countyGeoJsonProp !== undefined) return;
    let alive = true;
    // Defer the 12 MB GeoJSON fetch until the browser is idle so it does not
    // compete with Leaflet tile downloads on the critical path. Mobile users
    // see the map first; overlay paints in ~1s later on 4G.
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
      // force-cache lets the Cloudflare _headers immutable directive dedupe
      // repeat visits. Once we ship a pre-simplified + hashed file the
      // service-worker-free caching story becomes fully correct.
      fetch("/data/estonia_counties_simplified.geojson", { cache: "force-cache" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!alive) return;
          setCountyGeoJson(d);
        })
        .catch(() => {
          if (!alive) return;
          setCountyGeoJson(null);
        });
    });
    return () => {
      alive = false;
      cancelIdle(handle);
    };
  }, [showCountyOverlay, countyGeoJson, countyGeoJsonProp, setCountyGeoJson]);

  useEffect(() => {
    if (!mapRef.current) return;
    const t = window.setTimeout(() => {
      mapRef.current?.invalidateSize();
      // After entering fullscreen, re-fit Estonia keeping it clear of
      // the search+chips overlay (≈95px top) and sheet peek (≈62px bottom).
      if (isFullscreen) {
        mapRef.current?.fitBounds(ESTONIA_BOUNDS, {
          animate: false,
          paddingTopLeft: [10, 95],
          paddingBottomRight: [10, 62]
        });
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [isFullscreen]);

  const resetView = () => {
    if (onResetView) {
      onResetView();
      return;
    }
    mapRef.current?.flyTo(center, 7, { duration: 0.6 });
  };

  const recenter = () => {
    onRecenterUser?.();
  };

  const countyStyle = (feature?: GeoJSON.Feature) => {
    const countyName = countyFeatureName(feature);
    const avg = countyRisk.get(countyName);
    let fill = "#243249";
    if (typeof avg === "number") {
      if (avg >= 0.7) fill = "#ef4444";
      else if (avg >= 0.4) fill = "#f59e0b";
      else fill = "#22c55e";
    }
    const selected = selectedCountyNorm && countyNameNorm(countyName) === selectedCountyNorm;
    return {
      color: "#64748b",
      weight: selected ? 2.5 : 1,
      fillColor: fill,
      fillOpacity: selected ? 0.3 : 0.16
    };
  };

  const onEachCounty = (feature: GeoJSON.Feature, layer: L.Layer) => {
    const countyName = countyFeatureName(feature);
    layer.on("click", () => {
      if (!countyName) return;
      onSelectCounty?.(countyName);
    });
  };

  return (
    <div className={`mapShell ${isFullscreen ? "isFullscreen" : ""}`}>
      {!(isMobile && isFullscreen) ? (
        <div className="mapFloatingControls">
          <button type="button" className="mapFloatingBtn mapResetBtn" onClick={resetView} aria-label={resetViewLabel} title={resetViewLabel}>
            🧭
          </button>
          <button
            type="button"
            className="mapFloatingBtn mapRecenterBtn"
            onClick={recenter}
            disabled={!canRecenter}
            aria-label={recenterLabel}
            title={recenterLabel}
          >
            ◎
          </button>
        </div>
      ) : null}
      <button type="button" className="mapFloatingBtn mapFullscreenBtn" onClick={onToggleFullscreen} aria-label={fullscreenLabel} title={fullscreenLabel}>
        <span aria-hidden="true">⛶</span>
        <span className="mapFullscreenLabel">{fullscreenLabel}</span>
      </button>
      <MapContainer
        ref={(instance) => {
          mapRef.current = instance;
        }}
        center={center}
        zoom={7}
        minZoom={6}
        maxZoom={15}
        maxBounds={ESTONIA_BOUNDS}
        maxBoundsViscosity={0.35}
        zoomAnimation={!isMobile}
        fadeAnimation={!isMobile}
        markerZoomAnimation={!isMobile}
        style={{ height: "100%", width: "100%", borderRadius: (isFullscreen || isMobile) ? "0" : "12px" }}
        scrollWheelZoom
        preferCanvas
      >
        <TileLayer
          attribution='Tiles &copy; Esri, OpenStreetMap contributors'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
          keepBuffer={isMobile ? 2 : 5}
        />
        <FocusOnUserLocation userLocation={userLocation} />
        <FocusOnSelectedPoint
          selectedPoint={selectedPoint}
          bottomOverlayPx={bottomOverlayPx}
          topOverlayPx={topOverlayPx}
        />
        <FitBoundsOnVersion
          fitBoundsKey={fitBoundsKey}
          places={fitBoundsPlaces}
          topOverlayPx={topOverlayPx}
          bottomOverlayPx={bottomOverlayPx}
        />
        {showCountyOverlay && countyGeoJson ? <GeoJSON data={countyGeoJson} style={countyStyle} onEachFeature={onEachCounty} /> : null}
      <MarkerClusterLayer places={visiblePlaces} locale={locale} onSelectPoint={onSelectPoint} onSelectCluster={onSelectCluster} disableHoverPopups={disableHoverPopups} />
      </MapContainer>
    </div>
  );
}

export default memo(MapClient);
