"use client";

import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import type { FrontendPlace } from "../lib/types";

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

const markerBadgeHtml = (color: string, glyph: string) => `
  <span style="
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:30px;
    height:30px;
    border-radius:10px;
    background:${color};
    border:2px solid rgba(255,255,255,0.9);
    box-shadow:0 2px 10px rgba(0,0,0,0.35);
    font-size:16px;
    line-height:1;
  ">${glyph}</span>
`;

function markerIcon(place: FrontendPlace) {
  const colorByRisk = markerHtml(place.risk_level);
  const fallbackByOfficial =
    place.official_compliant === 1 ? "#22c55e" : place.official_compliant === 0 ? "#ef4444" : "#94a3b8";
  const color = place.model_violation_prob !== null ? colorByRisk : fallbackByOfficial;
  const glyph = placeKindGlyph(place.place_kind);
  return L.divIcon({
    className: "",
    html: markerBadgeHtml(color, glyph),
    iconSize: [30, 30],
    iconAnchor: [15, 15]
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

const countyNameNorm = (s: string) => s.trim().toLowerCase();
const countyDisplay = (s: string) =>
  s
    .trim()
    .split(/\s+/)
    .map((x) => x.charAt(0).toUpperCase() + x.slice(1).toLowerCase())
    .join(" ");

const countyFeatureName = (feature?: GeoJSON.Feature) => countyDisplay(String(feature?.properties?.MNIMI || "").trim());

const isFiniteNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function pointInRing(lon: number, lat: number, ring: number[][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i]?.[0];
    const yi = ring[i]?.[1];
    const xj = ring[j]?.[0];
    const yj = ring[j]?.[1];
    if (!isFiniteNumber(xi) || !isFiniteNumber(yi) || !isFiniteNumber(xj) || !isFiniteNumber(yj)) continue;
    const intersects = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi + Number.EPSILON) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointInPolygon(lon: number, lat: number, polygonCoords: number[][][]) {
  if (!polygonCoords.length) return false;
  const [outerRing, ...holes] = polygonCoords;
  if (!outerRing || !pointInRing(lon, lat, outerRing)) return false;
  for (const hole of holes) {
    if (pointInRing(lon, lat, hole)) return false;
  }
  return true;
}

function pointInFeature(lon: number, lat: number, feature: GeoJSON.Feature) {
  const geom = feature.geometry;
  if (!geom) return false;
  if (geom.type === "Polygon") {
    return pointInPolygon(lon, lat, geom.coordinates as number[][][]);
  }
  if (geom.type === "MultiPolygon") {
    const polys = geom.coordinates as number[][][][];
    return polys.some((poly) => pointInPolygon(lon, lat, poly));
  }
  return false;
}

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
};

function MarkerClusterLayer({
  places,
  locale,
  onSelectPoint,
  disableHoverPopups = false
}: {
  places: FrontendPlace[];
  locale: "ru" | "et" | "en";
  onSelectPoint?: (id: string) => void;
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
      showCoverageOnHover: false,
      iconCreateFunction: (cluster: unknown) => {
        const c = cluster as ClusterLike;
        const children = c.getAllChildMarkers();
        const probs = children
          .map((m) => m.options?.place?.model_violation_prob)
          .filter((v: unknown) => typeof v === "number") as number[];
        const avg = probs.length ? probs.reduce((a, b) => a + b, 0) / probs.length : 0.5;
        const color = clusterColor(avg);
        const count = c.getChildCount();
        return L.divIcon({
          html: `<div style="background:${color};color:#fff;border-radius:999px;width:42px;height:42px;display:flex;align-items:center;justify-content:center;border:3px solid #fff;font-weight:700;box-shadow:0 2px 10px rgba(0,0,0,0.25)">${count}</div>`,
          className: "",
          iconSize: [42, 42]
        });
      }
    });

    places.forEach((place) => {
      const marker = L.marker([place.lat, place.lon], {
        icon: markerIcon(place),
        place
      } as L.MarkerOptions & { place: FrontendPlace });
      marker.bindPopup(popupHtml(place, locale), { maxWidth: 360 });
      marker.on("click", () => onSelectPoint?.(place.id));
      if (!disableHoverPopups) {
        marker.on("mouseover", () => marker.openPopup());
        marker.on("mouseout", () => marker.closePopup());
      }
      (group as L.LayerGroup).addLayer(marker);
    });

    map.addLayer(group as L.Layer);
    return () => {
      map.removeLayer(group as L.Layer);
    };
  }, [map, places, locale, onSelectPoint, clusterReady, disableHoverPopups]);
  return null;
}

type Props = {
  places: FrontendPlace[];
  onSelectPoint?: (id: string) => void;
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
};

function FocusOnSelectedPoint({ selectedPoint }: { selectedPoint?: FrontendPlace | null }) {
  const map = useMap();
  useEffect(() => {
    if (!selectedPoint) return;
    map.flyTo([selectedPoint.lat, selectedPoint.lon], Math.max(map.getZoom(), 10), {
      duration: 0.7
    });
  }, [map, selectedPoint]);
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

export default function MapClient({
  places,
  onSelectPoint,
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
  canRecenter = true
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
  // Estonia viewport bounds (southWest, northEast)
  const estoniaBounds: [[number, number], [number, number]] = [
    [57.1, 20.7],
    [60.15, 29.4]
  ];
  const mapRef = useRef<L.Map | null>(null);
  const [countyGeoJson, setCountyGeoJson] = useState<GeoJSON.GeoJsonObject | null>(null);

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
    let alive = true;
    fetch("/data/estonia_counties_simplified.geojson")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!alive) return;
        setCountyGeoJson(d);
      })
      .catch(() => {
        if (!alive) return;
        setCountyGeoJson(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    const t = window.setTimeout(() => {
      mapRef.current?.invalidateSize();
    }, 220);
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
      <button type="button" className="mapFloatingBtn mapFullscreenBtn" onClick={onToggleFullscreen} aria-label={fullscreenLabel} title={fullscreenLabel}>
        ⛶
      </button>
      <MapContainer
        ref={(instance) => {
          mapRef.current = instance;
        }}
        center={center}
        zoom={7}
        minZoom={6}
        maxZoom={15}
        maxBounds={estoniaBounds}
        maxBoundsViscosity={0.35}
        style={{ height: "100%", width: "100%", borderRadius: isFullscreen ? "0" : "12px" }}
        scrollWheelZoom
        preferCanvas
      >
        <TileLayer
          attribution='Tiles &copy; Esri, OpenStreetMap contributors'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        />
        <FocusOnUserLocation userLocation={userLocation} />
        <FocusOnSelectedPoint selectedPoint={selectedPoint} />
        {countyGeoJson ? <GeoJSON data={countyGeoJson} style={countyStyle} onEachFeature={onEachCounty} /> : null}
      <MarkerClusterLayer places={visiblePlaces} locale={locale} onSelectPoint={onSelectPoint} disableHoverPopups={disableHoverPopups} />
      </MapContainer>
    </div>
  );
}
