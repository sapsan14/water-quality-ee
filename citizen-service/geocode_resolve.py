"""
Каскадное получение координат (WGS84) для точек Terviseamet без lat/lon в XML.

Порядок (для каждого варианта запроса из build_geocode_queries):
  1) **Google Geocoding** — единственный внешний провайдер при GOOGLE_MAPS_GEOCODING_API_KEY.

In-ADS и публичный Nominatim не используются.

Кэш JSON: citizen-service/data/coordinate_resolve_cache.json
Ключ: "google|…" (нормализованная строка запроса).
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional

import requests

_log = logging.getLogger(__name__)


def _clip_q(q: str, n: int = 88) -> str:
    s = " ".join(str(q).split())
    return s if len(s) <= n else s[: n - 3] + "..."

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
USER_AGENT = "water-quality-ee-citizen/1.0 (research; contact: repo water-quality-ee)"

EE_LAT = (55.5, 60.5)
EE_LON = (20.0, 30.0)


def normalize_query_key(q: str) -> str:
    s = unicodedata.normalize("NFC", q.strip().lower())
    s = re.sub(r"\s+", " ", s)
    return s


def build_geocode_queries(
    domain: str,
    location_display: str,
    geocode_site: str,
    geocode_facility: str,
    county: Optional[str],
) -> list[str]:
    """Варианты строк поиска: сначала конкретнее (площадка отбора + уезд), затем объект."""
    county = (county or "").strip()
    if county.lower() in ("", "unknown", "none", "nan"):
        county = ""
    county_bit = f", {county}" if county else ""
    ee = ", Eesti"
    seen: set[str] = set()
    out: list[str] = []

    def add(q: str) -> None:
        q = q.strip()
        if len(q) < 3:
            return
        if q in seen:
            return
        seen.add(q)
        out.append(q)

    site = (geocode_site or "").strip()
    fac = (geocode_facility or "").strip()
    loc = (location_display or "").strip()

    if site and county_bit:
        add(f"{site}{county_bit}{ee}")
    if site:
        add(f"{site}{ee}")
    if fac and county_bit and fac != site:
        add(f"{fac}{county_bit}{ee}")
    if fac and fac != site:
        add(f"{fac}{ee}")
    if loc and loc not in (site, fac):
        add(f"{loc}{ee}")
    if loc:
        add(f"{loc}, Estonia")
    return out


def _in_estonia_bbox(lat: float, lon: float) -> bool:
    return EE_LAT[0] < lat < EE_LAT[1] and EE_LON[0] < lon < EE_LON[1]


def geocode_google(address: str, api_key: str, session: requests.Session) -> Optional[dict]:
    r = session.get(
        GOOGLE_GEOCODE_URL,
        params={
            "address": address,
            "key": api_key,
            "region": "ee",
            "language": "et",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if str(data.get("status") or "") != "OK":
        return None
    results = data.get("results") or []
    if not results:
        return None
    first = results[0]
    geom = first.get("geometry") if isinstance(first.get("geometry"), dict) else {}
    loc = geom.get("location") if isinstance(geom.get("location"), dict) else {}
    try:
        lat = float(loc["lat"])
        lon = float(loc["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_estonia_bbox(lat, lon):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "matched_address": str(first.get("formatted_address") or "").strip() or None,
    }


def load_resolve_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_resolve_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def resolve_coordinates_cascade(
    queries: list[str],
    *,
    resolve_cache: dict[str, Any],
    session: requests.Session,
    google_api_key: Optional[str] = None,
    delay_google: float = 0.15,
    budget_remaining: list[int],
    log: Optional[logging.Logger] = None,
) -> Optional[tuple[str, float, float, Optional[str]]]:
    """
    Возвращает (source, lat, lon, matched_label) или None.
    budget_remaining — [N]: списывается только при реальном HTTP-запросе.
    """
    lg = log or _log
    for raw_q in queries:
        nq = normalize_query_key(raw_q)

        gg = f"google|{nq}"
        if google_api_key:
            if gg in resolve_cache:
                ent = resolve_cache[gg]
                if ent.get("miss"):
                    lg.debug("coords cache-hit miss google query=%s", _clip_q(raw_q))
                elif ent.get("lat") is not None and ent.get("lon") is not None:
                    return ("google", float(ent["lat"]), float(ent["lon"]), ent.get("matched_address"))
            elif budget_remaining[0] > 0:
                budget_remaining[0] -= 1
                lg.info(
                    "coords HTTP google budget_left=%s query=%s",
                    budget_remaining[0],
                    _clip_q(raw_q),
                )
                time.sleep(delay_google)
                try:
                    res_gg = geocode_google(raw_q, google_api_key, session)
                except (requests.RequestException, ValueError, json.JSONDecodeError, KeyError):
                    res_gg = None
                if res_gg:
                    resolve_cache[gg] = {
                        "lat": res_gg["lat"],
                        "lon": res_gg["lon"],
                        "matched_address": res_gg.get("matched_address"),
                    }
                    lg.info(
                        "coords update-cache google lat=%.5f lon=%.5f match=%s",
                        float(res_gg["lat"]),
                        float(res_gg["lon"]),
                        _clip_q(str(res_gg.get("matched_address") or "")),
                    )
                    return ("google", res_gg["lat"], res_gg["lon"], res_gg.get("matched_address"))
                resolve_cache[gg] = {"lat": None, "lon": None, "miss": True}
                lg.info("coords miss google (cached) query=%s", _clip_q(raw_q))

    return None
