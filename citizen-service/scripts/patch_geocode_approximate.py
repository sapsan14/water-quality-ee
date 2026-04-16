#!/usr/bin/env python3
"""
Targeted geocoding for approximate_ee places in snapshot.json.

Loads snapshot.json, finds all places with coord_source=approximate_ee,
geocodes them via Google → Geoapify → OpenCage cascade, and patches
the snapshot back. Falls back to county_centroid if geocoding fails.
"""
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
_CS_DIR = ROOT / "citizen-service"
if str(_CS_DIR) not in sys.path:
    sys.path.insert(0, str(_CS_DIR))

import geocode_resolve as _geocode_resolve  # noqa: E402
from county_centroids import county_to_latlon  # noqa: E402

SNAPSHOT_PATH = ROOT / "citizen-service" / "artifacts" / "snapshot.json"
RESOLVE_CACHE_PATH = ROOT / "citizen-service" / "data" / "coordinate_resolve_cache.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOG = logging.getLogger("patch_geocode")

STRIP_SUFFIXES = [
    r"\s+mineraalvee\s+veevärk$",
    r"\s+ühisveevärk$",
    r"\s+veevärk$",
    r"\s+veevõrk$",
    r"\s+mullivanniga$",
    r"\s+mullivann$",
    r"\s+massaaživann$",
    r"\s+soolabassein$",
    r"\s+lastebassein$",
    r"\s+bassein$",
    r"\s+puurkaev\s+nr\s*\d+.*$",
]


def _load_dotenv():
    path = ROOT / ".env"
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
    except ImportError:
        pass


def _prefer_certifi():
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE"):
        return
    try:
        import certifi
        bundle = certifi.where()
    except ImportError:
        return
    os.environ.setdefault("SSL_CERT_FILE", bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)


def clean_location(name: str) -> str:
    """Strip water-infrastructure suffixes to get a geocodable place name."""
    cleaned = name.strip()
    for pat in STRIP_SUFFIXES:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def build_queries(location: str, domain: str) -> list[str]:
    """Build multiple geocoding queries from most to least specific."""
    queries = []
    loc = location.strip()
    cleaned = clean_location(loc)

    if loc != cleaned and cleaned:
        queries.append(f"{cleaned}, Eesti")
    queries.append(f"{loc}, Eesti")
    queries.append(f"{loc}, Estonia")
    if loc != cleaned and cleaned:
        queries.append(f"{cleaned}, Estonia")

    parts = re.split(r"[,\(\)]", cleaned)
    if len(parts) > 1:
        main = parts[0].strip()
        if main and main != cleaned:
            queries.append(f"{main}, Estonia")

    seen = set()
    deduped = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


def main():
    _load_dotenv()
    _prefer_certifi()

    geoapify_key = (os.environ.get("GEOAPIFY_API_KEY") or "").strip() or None
    google_key = (os.environ.get("GOOGLE_MAPS_GEOCODING_API_KEY") or "").strip() or None
    opencage_key = (os.environ.get("OPENCAGE_API_KEY") or "").strip() or None

    LOG.info("API keys: Google=%s Geoapify=%s OpenCage=%s",
             "yes" if google_key else "NO",
             "yes" if geoapify_key else "NO",
             "yes" if opencage_key else "NO")

    if not (google_key or geoapify_key or opencage_key):
        LOG.error("No geocoding API keys found in environment. Aborting.")
        sys.exit(1)

    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        snapshot = json.load(f)

    resolve_cache = {}
    if RESOLVE_CACHE_PATH.is_file():
        with open(RESOLVE_CACHE_PATH, encoding="utf-8") as f:
            resolve_cache = json.load(f)

    places = snapshot["places"]
    approx = [(i, p) for i, p in enumerate(places) if p.get("coord_source") == "approximate_ee"]
    LOG.info("Found %d approximate_ee places to geocode", len(approx))

    if not approx:
        LOG.info("Nothing to do.")
        return

    session = requests.Session()
    session.headers.update({
        "User-Agent": "water-quality-ee-patch-geocode/1.0",
        "Accept": "application/json",
    })

    budget = [len(approx) * 5]
    geocoded = 0
    centroid_fallback = 0
    still_approx = 0

    for seq, (idx, place) in enumerate(approx, 1):
        loc = place.get("location", "")
        domain = place.get("domain", "")
        LOG.info("[%d/%d] %s (domain=%s)", seq, len(approx), loc[:70], domain)

        queries = build_queries(loc, domain)
        LOG.info("  queries: %s", queries[:4])

        got = _geocode_resolve.resolve_coordinates_cascade(
            queries,
            resolve_cache=resolve_cache,
            session=session,
            geoapify_api_key=geoapify_key,
            google_api_key=google_key,
            opencage_api_key=opencage_key,
            budget_remaining=budget,
            log=LOG,
        )

        if got:
            source, lat, lon, matched = got
            LOG.info("  -> GEOCODED via %s: lat=%.5f lon=%.5f matched=%s",
                     source, lat, lon, (matched or "")[:60])
            places[idx]["lat"] = lat
            places[idx]["lon"] = lon
            places[idx]["coord_source"] = source
            if matched:
                places[idx]["geocode_matched"] = matched
            geocoded += 1
        else:
            county_str = place.get("county")
            # county from data is unreliable for approximate_ee — skip centroid
            # since the county was likely wrong too. Keep approximate_ee.
            LOG.warning("  -> MISS: no geocoding result for %s", loc[:70])
            still_approx += 1

    LOG.info("Results: geocoded=%d, still_approx=%d, total=%d",
             geocoded, still_approx, len(approx))

    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)
    LOG.info("Patched snapshot saved to %s", SNAPSHOT_PATH)

    _geocode_resolve.save_resolve_cache(RESOLVE_CACHE_PATH, resolve_cache)
    LOG.info("Resolve cache saved (%d entries)", len(resolve_cache))


if __name__ == "__main__":
    main()
