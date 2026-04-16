/**
 * Point-in-polygon utilities for geographic filtering.
 * Used by both MapClient (overlay filtering) and Dashboard (county filter).
 */

const isFiniteNumber = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

export function pointInRing(lon: number, lat: number, ring: number[][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i]?.[0];
    const yi = ring[i]?.[1];
    const xj = ring[j]?.[0];
    const yj = ring[j]?.[1];
    if (
      !isFiniteNumber(xi) ||
      !isFiniteNumber(yi) ||
      !isFiniteNumber(xj) ||
      !isFiniteNumber(yj)
    )
      continue;
    const intersects =
      yi > lat !== yj > lat &&
      lon < ((xj - xi) * (lat - yi)) / (yj - yi + Number.EPSILON) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

export function pointInPolygon(
  lon: number,
  lat: number,
  polygonCoords: number[][][]
) {
  if (!polygonCoords.length) return false;
  const [outerRing, ...holes] = polygonCoords;
  if (!outerRing || !pointInRing(lon, lat, outerRing)) return false;
  for (const hole of holes) {
    if (pointInRing(lon, lat, hole)) return false;
  }
  return true;
}

export function pointInFeature(
  lon: number,
  lat: number,
  feature: GeoJSON.Feature
) {
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

/** Normalize a county name for comparison (lowercase, trimmed). */
export const countyNameNorm = (s: string) => s.trim().toLowerCase();

/** Extract the display name from a GeoJSON county feature. */
export const countyFeatureName = (feature?: GeoJSON.Feature) =>
  (String(feature?.properties?.MNIMI || "").trim())
    .split(/\s+/)
    .map((x) => x.charAt(0).toUpperCase() + x.slice(1).toLowerCase())
    .join(" ");

/**
 * Find the GeoJSON Feature for a county by normalized name.
 * Returns null if the GeoJSON data is missing or the county isn't found.
 */
export function findCountyFeature(
  countyNorm: string,
  geoJson: GeoJSON.GeoJsonObject | null
): GeoJSON.Feature | null {
  if (!geoJson || geoJson.type !== "FeatureCollection") return null;
  const fc = geoJson as GeoJSON.FeatureCollection;
  return (
    fc.features.find(
      (f) => countyNameNorm(countyFeatureName(f)) === countyNorm
    ) || null
  );
}
