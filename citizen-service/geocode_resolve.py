"""
Каскадное получение координат (WGS84) для точек Terviseamet без lat/lon в XML.

Порядок (для каждого варианта запроса из build_geocode_queries):
  1) **Google Geocoding** — основной внешний провайдер при GOOGLE_MAPS_GEOCODING_API_KEY.
  2) **Geoapify Geocoding** — fallback при GEOAPIFY_API_KEY (https://www.geoapify.com/).
  3) **OpenCage Geocoding** — fallback при OPENCAGE_API_KEY (https://opencagedata.com/).

In-ADS и публичный Nominatim не используются.

Кэш JSON: citizen-service/data/coordinate_resolve_cache.json
Ключ: "opencage|…" (нормализованная строка запроса). В старых кэшах могут остаться ключи `google|…` — они не читаются и не обновляются.
Ответы OpenCage без привязки к месту (только «Eesti», maakond, низкий confidence) отбрасываются и не попадают в кэш.
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

GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
OPENCAGE_GEOCODE_URL = "https://api.opencagedata.com/geocode/v1/json"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
USER_AGENT = "water-quality-ee-citizen/1.0 (research; contact: repo water-quality-ee)"

EE_LAT = (55.5, 60.5)
EE_LON = (20.0, 30.0)

# OpenCage: низкий confidence = большой bbox (часто вся страна / maakond).
# См. https://opencagedata.com/api — не кэшируем «Eesti» и аналогичные ответы без конкретного места.
OPENCAGE_MIN_CONFIDENCE = 5
_COARSE_OC_TYPES = frozenset(
    {"country", "continent", "political_union", "state", "region", "county", "macroregion", "archipelago"}
)
_FINE_COMPONENT_KEYS = frozenset(
    {
        "road",
        "house_number",
        "house",
        "building",
        "city",
        "town",
        "village",
        "hamlet",
        "municipality",
        "city_district",
        "suburb",
        "neighbourhood",
        "residential",
        "amenity",
        "shop",
        "tourism",
        "leisure",
        "office",
        "industrial",
    }
)
# При confidence 3–4 точка может быть всё ещё полезной, если тип объекта узкий.
_FINE_OC_TYPES_LOW_CONF = frozenset(
    {
        "house",
        "building",
        "road",
        "pedestrian",
        "amenity",
        "attraction",
        "village",
        "hamlet",
        "city",
        "town",
        "suburb",
        "neighbourhood",
        "residential",
        "locality",
        "postcode",
    }
)


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


def _opencage_components_type(components: Any) -> Optional[str]:
    if not isinstance(components, dict):
        return None
    t = components.get("_type")
    return str(t).strip().lower() if t is not None else None


def _opencage_has_fine_place_component(components: dict) -> bool:
    return bool(_FINE_COMPONENT_KEYS.intersection(components.keys()))


def opencage_result_is_precise_enough(first: dict) -> bool:
    """
    True — можно ставить точку на карте (не страна / не maakond без населённого пункта и т.п.).
    """
    components = first.get("components") if isinstance(first.get("components"), dict) else {}
    oc_type = _opencage_components_type(components)
    formatted = (first.get("formatted") or "").strip().lower()
    if formatted in ("eesti", "estonia"):
        return False
    if oc_type in _COARSE_OC_TYPES:
        return False
    conf = first.get("confidence")
    c: Optional[int]
    try:
        c = int(conf) if conf is not None and str(conf).strip() != "" else None
    except (TypeError, ValueError):
        c = None
    if c is not None and c < OPENCAGE_MIN_CONFIDENCE:
        if oc_type in _FINE_OC_TYPES_LOW_CONF and c >= 3:
            return True
        return False
    if not _opencage_has_fine_place_component(components):
        if oc_type in _FINE_OC_TYPES_LOW_CONF:
            return True
        return False
    return True


def geocode_cache_entry_is_precise_enough(ent: dict[str, Any]) -> bool:
    """Проверка записи кэша (новой или старой без confidence/oc_type)."""
    if ent.get("miss") or ent.get("lat") is None or ent.get("lon") is None:
        return False
    mlow = (str(ent.get("matched_address") or "").strip().lower())
    if mlow in ("eesti", "estonia"):
        return False
    ot_raw = ent.get("oc_type")
    ot = str(ot_raw).strip().lower() if ot_raw is not None else None
    if ot in _COARSE_OC_TYPES:
        return False
    try:
        c = (
            int(ent["confidence"])
            if ent.get("confidence") is not None and str(ent.get("confidence")).strip() != ""
            else None
        )
    except (TypeError, ValueError):
        c = None
    if c is not None and c < OPENCAGE_MIN_CONFIDENCE:
        if ot in _FINE_OC_TYPES_LOW_CONF and c >= 3:
            return True
        return False
    if c is None and ot is None:
        try:
            lat = float(ent["lat"])
            lon = float(ent["lon"])
        except (TypeError, ValueError):
            return False
        if abs(lat - 59.0) < 0.02 and abs(lon - 26.0) < 0.02:
            return False
    return True


def geocode_opencage(address: str, api_key: str, session: requests.Session) -> Optional[dict]:
    r = session.get(
        OPENCAGE_GEOCODE_URL,
        params={
            "q": address,
            "key": api_key,
            "limit": 1,
            "countrycode": "ee",
            "language": "et,en",
            "no_annotations": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    st = data.get("status") or {}
    code = st.get("code")
    if code != 200:
        msg = (st.get("message") or "").strip()
        _log.warning(
            "OpenCage geocode coordinates: status code=%s%s",
            code,
            f" — {msg[:400]}" if msg else "",
        )
        return None
    results = data.get("results") or []
    if not results:
        return None
    geom = results[0].get("geometry") or {}
    try:
        lat = float(geom["lat"])
        lon = float(geom["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_estonia_bbox(lat, lon):
        return None
    first = results[0]
    if not opencage_result_is_precise_enough(first):
        return None
    comps = first.get("components") if isinstance(first.get("components"), dict) else {}
    oc_type = _opencage_components_type(comps)
    conf = first.get("confidence")
    try:
        conf_i = int(conf) if conf is not None and str(conf).strip() != "" else None
    except (TypeError, ValueError):
        conf_i = None
    return {
        "lat": lat,
        "lon": lon,
        "matched_address": first.get("formatted"),
        "confidence": conf_i,
        "oc_type": oc_type,
    }


def geocode_geoapify(address: str, api_key: str, session: requests.Session) -> Optional[dict]:
    r = session.get(
        GEOAPIFY_GEOCODE_URL,
        params={
            "text": address,
            "filter": "countrycode:ee",
            "limit": 1,
            "lang": "et",
            "format": "json",
            "apiKey": api_key,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    feats = data.get("results") or []
    if not feats:
        return None
    first = feats[0]
    try:
        lat = float(first["lat"])
        lon = float(first["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_estonia_bbox(lat, lon):
        return None
    matched = str(first.get("formatted") or "").strip()
    if matched.lower() in ("eesti", "estonia"):
        return None
    # Geoapify rank.confidence обычно [0..1].
    rank = first.get("rank") if isinstance(first.get("rank"), dict) else {}
    conf = rank.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    if conf_f is not None and conf_f < 0.35:
        return None
    return {
        "lat": lat,
        "lon": lon,
        "matched_address": matched,
        "confidence": conf_f,
        "provider_rank": rank,
    }


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
    geoapify_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    opencage_api_key: Optional[str] = None,
    delay_geoapify: float = 0.25,
    delay_google: float = 0.15,
    delay_opencage: float = 0.55,
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

        # 1) Google Geocoding — основной внешний провайдер.
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

        # 2) Geoapify — fallback.
        gk = f"geoapify|{nq}"
        if geoapify_api_key:
            if gk in resolve_cache:
                ent = resolve_cache[gk]
                if ent.get("miss"):
                    lg.debug("coords cache-hit miss geoapify query=%s", _clip_q(raw_q))
                elif ent.get("lat") is not None and ent.get("lon") is not None:
                    return ("geoapify", float(ent["lat"]), float(ent["lon"]), ent.get("matched_address"))
            elif budget_remaining[0] > 0:
                budget_remaining[0] -= 1
                lg.info(
                    "coords HTTP geoapify budget_left=%s query=%s",
                    budget_remaining[0],
                    _clip_q(raw_q),
                )
                time.sleep(delay_geoapify)
                try:
                    res_g = geocode_geoapify(raw_q, geoapify_api_key, session)
                except (requests.RequestException, ValueError, json.JSONDecodeError, KeyError):
                    res_g = None
                if res_g:
                    resolve_cache[gk] = {
                        "lat": res_g["lat"],
                        "lon": res_g["lon"],
                        "matched_address": res_g.get("matched_address"),
                        "confidence": res_g.get("confidence"),
                    }
                    lg.info(
                        "coords update-cache geoapify lat=%.5f lon=%.5f match=%s",
                        float(res_g["lat"]),
                        float(res_g["lon"]),
                        _clip_q(str(res_g.get("matched_address") or "")),
                    )
                    return ("geoapify", res_g["lat"], res_g["lon"], res_g.get("matched_address"))
                resolve_cache[gk] = {"lat": None, "lon": None, "miss": True}
                lg.info("coords miss geoapify (cached) query=%s", _clip_q(raw_q))

        # 3) OpenCage — fallback.
        ok = f"opencage|{nq}"
        if opencage_api_key:
            if ok in resolve_cache:
                ent = resolve_cache[ok]
                if ent.get("miss"):
                    lg.debug("coords cache-hit miss opencage query=%s", _clip_q(raw_q))
                    continue
                if ent.get("lat") is not None and ent.get("lon") is not None:
                    if geocode_cache_entry_is_precise_enough(ent):
                        lg.debug(
                            "coords cache-hit verify opencage lat=%.5f lon=%.5f query=%s",
                            float(ent["lat"]),
                            float(ent["lon"]),
                            _clip_q(raw_q),
                        )
                        return (
                            "opencage",
                            float(ent["lat"]),
                            float(ent["lon"]),
                            ent.get("matched_address"),
                        )
                    lg.info(
                        "coords cache-ignore imprecise opencage query=%s match=%s",
                        _clip_q(raw_q),
                        _clip_q(str(ent.get("matched_address") or "")),
                    )
                    del resolve_cache[ok]

            if budget_remaining[0] > 0:
                budget_remaining[0] -= 1
                lg.info(
                    "coords HTTP opencage budget_left=%s query=%s",
                    budget_remaining[0],
                    _clip_q(raw_q),
                )
                time.sleep(delay_opencage)
                try:
                    res = geocode_opencage(raw_q, opencage_api_key, session)
                except (requests.RequestException, ValueError, json.JSONDecodeError, KeyError):
                    res = None
                if res:
                    resolve_cache[ok] = {
                        "lat": res["lat"],
                        "lon": res["lon"],
                        "matched_address": res.get("matched_address"),
                        "confidence": res.get("confidence"),
                        "oc_type": res.get("oc_type"),
                    }
                    lg.info(
                        "coords update-cache opencage lat=%.5f lon=%.5f match=%s",
                        float(res["lat"]),
                        float(res["lon"]),
                        _clip_q(str(res.get("matched_address") or "")),
                    )
                    return ("opencage", res["lat"], res["lon"], res.get("matched_address"))
                resolve_cache[ok] = {"lat": None, "lon": None, "miss": True}
                lg.info("coords miss opencage (cached) query=%s", _clip_q(raw_q))

    return None
