"""
Каскадное получение координат (WGS84) для точек Terviseamet без lat/lon в XML.

Порядок (для каждого варианта запроса из build_geocode_queries):
  1. In-ADS / gazetteer (Maa-amet) — официальный адресный справочник Эстонии.
     GET https://inaadress.maaamet.ee/inaadress/gazetteer?address=…&results=8
     Поля ответа: viitepunkt_b (широта), viitepunkt_l (долгота) в градусах.
  2. Google Geocoding API — если задана переменная окружения GOOGLE_MAPS_GEOCODING_API_KEY.
  3. Nominatim (OpenStreetMap) — общий fallback, уважать usage policy и задержки.

Кэш JSON: citizen-service/data/coordinate_resolve_cache.json
Ключи: "inads|…", "google|…", "nominatim|…" (нормализованная строка запроса).

Документация In-ADS: https://geoportaal.maaamet.ee (интегрируемый поиск адресов).
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

import requests

INADS_GAZETTEER = "https://inaadress.maaamet.ee/inaadress/gazetteer"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
USER_AGENT = "water-quality-ee-citizen/1.0 (research; contact: repo water-quality-ee)"


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


def _pick_inads_address(addresses: list[dict]) -> Optional[dict]:
    if not addresses:
        return None
    prim = [a for a in addresses if str(a.get("primary", "")).lower() == "true"]
    pool = prim if prim else addresses
    for a in pool:
        try:
            lat = float(a["viitepunkt_b"])
            lon = float(a["viitepunkt_l"])
        except (KeyError, TypeError, ValueError):
            continue
        if 55.5 < lat < 60.5 and 20.0 < lon < 30.0:
            return {**a, "_lat": lat, "_lon": lon}
    return None


def geocode_inads(address: str, session: requests.Session) -> Optional[dict]:
    r = session.get(
        INADS_GAZETTEER,
        params={"address": address, "results": 8},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    addrs = data.get("addresses")
    if not isinstance(addrs, list):
        return None
    hit = _pick_inads_address(addrs)
    if not hit:
        return None
    return {
        "lat": hit["_lat"],
        "lon": hit["_lon"],
        "matched_address": hit.get("ipikkaadress") or hit.get("pikkaadress"),
        "kvaliteet": hit.get("kvaliteet"),
    }


def geocode_google(address: str, api_key: str, session: requests.Session) -> Optional[dict]:
    r = session.get(
        GOOGLE_GEOCODE_URL,
        params={"address": address, "key": api_key, "region": "ee"},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return None
    results = data.get("results") or []
    if not results:
        return None
    loc = results[0].get("geometry", {}).get("location") or {}
    try:
        lat = float(loc["lat"])
        lon = float(loc["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "matched_address": results[0].get("formatted_address"),
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
    nominatim_cache: dict[str, Any],
    session: requests.Session,
    google_api_key: Optional[str],
    nominatim_fn: Callable[[str, dict], Optional[tuple[float, float]]],
    delay_inads: float = 0.12,
    delay_google: float = 0.05,
    delay_nominatim: float = 1.05,
    budget_remaining: list[int],
) -> Optional[tuple[str, float, float, Optional[str]]]:
    """
    Возвращает (source, lat, lon, matched_label) или None.
    budget_remaining — [N]: списывается только при реальном HTTP-запросе.
    """
    for raw_q in queries:
        nq = normalize_query_key(raw_q)

        ck = f"inads|{nq}"
        if ck in resolve_cache:
            ent = resolve_cache[ck]
            if ent.get("lat") is not None and ent.get("lon") is not None:
                return (
                    "inads",
                    float(ent["lat"]),
                    float(ent["lon"]),
                    ent.get("matched_address"),
                )
            if ent.get("miss"):
                pass
        elif budget_remaining[0] > 0:
            budget_remaining[0] -= 1
            time.sleep(delay_inads)
            try:
                res = geocode_inads(raw_q, session)
            except (requests.RequestException, ValueError, json.JSONDecodeError):
                res = None
            if res:
                resolve_cache[ck] = {
                    "lat": res["lat"],
                    "lon": res["lon"],
                    "matched_address": res.get("matched_address"),
                    "kvaliteet": res.get("kvaliteet"),
                }
                return ("inads", res["lat"], res["lon"], res.get("matched_address"))
            resolve_cache[ck] = {"lat": None, "lon": None, "miss": True}

        gk = f"google|{nq}"
        if google_api_key:
            if gk in resolve_cache:
                ent = resolve_cache[gk]
                if ent.get("lat") is not None and ent.get("lon") is not None:
                    return (
                        "google",
                        float(ent["lat"]),
                        float(ent["lon"]),
                        ent.get("matched_address"),
                    )
            elif budget_remaining[0] > 0:
                budget_remaining[0] -= 1
                time.sleep(delay_google)
                try:
                    res = geocode_google(raw_q, google_api_key, session)
                except (requests.RequestException, ValueError, json.JSONDecodeError, KeyError):
                    res = None
                if res:
                    resolve_cache[gk] = {
                        "lat": res["lat"],
                        "lon": res["lon"],
                        "matched_address": res.get("matched_address"),
                    }
                    return ("google", res["lat"], res["lon"], res.get("matched_address"))
                resolve_cache[gk] = {"lat": None, "lon": None, "miss": True}

        nk = f"nominatim|{nq}"
        if nk in resolve_cache:
            ent = resolve_cache[nk]
            if ent.get("lat") is not None and ent.get("lon") is not None:
                return (
                    "nominatim",
                    float(ent["lat"]),
                    float(ent["lon"]),
                    ent.get("matched_address"),
                )
            if ent.get("miss"):
                continue
        elif raw_q in nominatim_cache and nominatim_cache[raw_q].get("lat") is not None:
            c = nominatim_cache[raw_q]
            return ("nominatim", float(c["lat"]), float(c["lon"]), raw_q)
        elif budget_remaining[0] > 0:
            budget_remaining[0] -= 1
            time.sleep(delay_nominatim)
            got = nominatim_fn(raw_q, nominatim_cache)
            if got:
                lat, lon = got
                resolve_cache[nk] = {"lat": lat, "lon": lon, "matched_address": raw_q}
                return ("nominatim", lat, lon, raw_q)
            resolve_cache[nk] = {"lat": None, "lon": None, "miss": True}

    return None
