"""
Вывод уезда (maakond) из текста location, если в XML поле maakond пустое.

Каскад:
1. Уже заполненный county из XML — без изменений (county_source=xml).
2. Справочник data/reference/location_county_overrides.csv (нормализованный ключ).
3. Кэш геокодирования data/processed/county_geocode_cache.json.
4. Google Geocoding (если задан google_api_key или env GOOGLE_MAPS_GEOCODING_API_KEY) — из address_components.
5. OpenCage Geocoding (fallback, если задан opencage_api_key или env OPENCAGE_API_KEY) — из components.

Публичный Nominatim и In-ADS не используются. Нужен requests; без сети: geocode=False — только XML, overrides и кэш.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests

_county_log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
OVERRIDES_CSV = DATA_ROOT / "reference" / "location_county_overrides.csv"
GEOCODE_CACHE_PATH = DATA_ROOT / "processed" / "county_geocode_cache.json"

# Локальные источники для затравки (seed) кэша уездов без HTTP.
SNAPSHOT_JSON = REPO_ROOT / "citizen-service" / "artifacts" / "snapshot.json"
COORD_OVERRIDES_JSON = REPO_ROOT / "citizen-service" / "data" / "coordinate_overrides.json"
COORD_RESOLVE_CACHE_JSON = REPO_ROOT / "citizen-service" / "data" / "coordinate_resolve_cache.json"
GEOCODE_CACHE_SIMPLE_JSON = REPO_ROOT / "citizen-service" / "data" / "geocode_cache.json"
COUNTIES_GEOJSON = REPO_ROOT / "frontend" / "public" / "data" / "estonia_counties_simplified.geojson"

_POLYGONS_CACHE: Optional[list] = None

OPENCAGE_GEOCODE_URL = "https://api.opencagedata.com/geocode/v1/json"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Англ. названия OSM → официальная форма как в Eesti haldusjaotus
_COUNTY_EN_TO_ET = {
    "harju county": "Harju maakond",
    "hiiu county": "Hiiu maakond",
    "ida-viru county": "Ida-Viru maakond",
    "järva county": "Järva maakond",
    "jõgeva county": "Jõgeva maakond",
    "lääne county": "Lääne maakond",
    "lääne-viru county": "Lääne-Viru maakond",
    "pärnu county": "Pärnu maakond",
    "põlva county": "Põlva maakond",
    "rapla county": "Rapla maakond",
    "saare county": "Saare maakond",
    "tartu county": "Tartu maakond",
    "valga county": "Valga maakond",
    "viljandi county": "Viljandi maakond",
    "võru county": "Võru maakond",
}


def normalize_location(text: Optional[str]) -> str:
    """Ключ для словаря и кэша: NFC, lower, без лишних пробелов."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text).strip()
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_county_name(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "maakond" in s.lower():
        return s
    key = s.lower()
    return _COUNTY_EN_TO_ET.get(key, s)


def load_overrides() -> Dict[str, str]:
    if not OVERRIDES_CSV.is_file():
        return {}
    df = pd.read_csv(OVERRIDES_CSV, comment="#")
    if df.empty or "location_norm" not in df.columns or "county" not in df.columns:
        return {}
    out: Dict[str, str] = {}
    for _, row in df.iterrows():
        k = normalize_location(row["location_norm"])
        v = row["county"]
        if pd.isna(v) or not k:
            continue
        out[k] = str(v).strip()
    return out


def load_geocode_cache() -> Dict[str, Any]:
    if not GEOCODE_CACHE_PATH.is_file():
        return {}
    try:
        with open(GEOCODE_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_geocode_cache(cache: Dict[str, Any]) -> None:
    GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GEOCODE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def _county_from_opencage_components(components: Any) -> Optional[str]:
    """Вытащить maakond из OpenCage results[].components."""
    if not isinstance(components, dict):
        return None
    for key in ("state", "county", "region", "state_district"):
        val = components.get(key)
        if not val:
            continue
        s = str(val).strip()
        if not s:
            continue
        if "maakond" in s.lower() or "county" in s.lower():
            return _normalize_county_name(s)
    return None


def _geocode_one_opencage(location_display: str, api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Вернуть (county, query_used) через OpenCage Geocoding API."""
    query = f"{location_display}, Estonia"
    try:
        r = requests.get(
            OPENCAGE_GEOCODE_URL,
            params={
                "q": query,
                "key": api_key,
                "limit": 1,
                "countrycode": "ee",
                "language": "et,en",
                "no_annotations": 1,
            },
            timeout=25,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError, KeyError) as e:
        _county_log.warning("OpenCage county: HTTP/JSON error: %s", e)
        return None, query
    st = data.get("status") or {}
    if st.get("code") != 200:
        msg = (st.get("message") or "").strip()
        _county_log.warning(
            "OpenCage county: status code=%s%s",
            st.get("code"),
            f" — {msg[:400]}" if msg else "",
        )
        return None, query
    results = data.get("results") or []
    if not results:
        return None, query
    comps = results[0].get("components") or {}
    county = _county_from_opencage_components(comps)
    return _normalize_county_name(county), query


def _county_from_google_components(components: Any) -> Optional[str]:
    """Вытащить maakond из Google results[].address_components."""
    if not isinstance(components, list):
        return None
    for comp in components:
        if not isinstance(comp, dict):
            continue
        types = comp.get("types")
        if not isinstance(types, list):
            continue
        tset = set(str(t) for t in types)
        if not (
            "administrative_area_level_1" in tset
            or "administrative_area_level_2" in tset
            or "administrative_area_level_3" in tset
        ):
            continue
        for key in ("long_name", "short_name"):
            v = comp.get(key)
            if not v:
                continue
            s = str(v).strip()
            if not s:
                continue
            if "maakond" in s.lower() or "county" in s.lower():
                return _normalize_county_name(s)
    return None


def _geocode_one_google(location_display: str, api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Вернуть (county, query_used) через Google Geocoding API."""
    query = f"{location_display}, Estonia"
    try:
        r = requests.get(
            GOOGLE_GEOCODE_URL,
            params={
                "address": query,
                "key": api_key,
                "region": "ee",
                "language": "et",
            },
            timeout=25,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError, KeyError) as e:
        _county_log.warning("Google county: HTTP/JSON error: %s", e)
        return None, query
    status = str(data.get("status") or "").strip()
    if status != "OK":
        if status not in ("ZERO_RESULTS", ""):
            err = (str(data.get("error_message") or "") or "").strip()
            _county_log.warning("Google county: status=%s%s", status, f" — {err[:400]}" if err else "")
        return None, query
    results = data.get("results") or []
    if not results:
        return None, query
    county = _county_from_google_components(results[0].get("address_components") or [])
    return _normalize_county_name(county), query


_CANONICAL_COUNTIES = (
    "Harju maakond",
    "Hiiu maakond",
    "Ida-Viru maakond",
    "Järva maakond",
    "Jõgeva maakond",
    "Lääne maakond",
    "Lääne-Viru maakond",
    "Pärnu maakond",
    "Põlva maakond",
    "Rapla maakond",
    "Saare maakond",
    "Tartu maakond",
    "Valga maakond",
    "Viljandi maakond",
    "Võru maakond",
)
_CANONICAL_COUNTY_BY_LOWER = {c.lower(): c for c in _CANONICAL_COUNTIES}


def _canonicalize_county(raw: Optional[str]) -> Optional[str]:
    """Привести название уезда к каноничной форме MNIMI ('Tartu maakond').

    Принимает 'Tartu Maakond', 'IDA-VIRU MAAKOND', 'lääne-viru maakond',
    английские 'Tartu county' и т.п.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFC", s)
    key = re.sub(r"\s+", " ", s.lower())
    canon = _CANONICAL_COUNTY_BY_LOWER.get(key)
    if canon:
        return canon
    return _normalize_county_name(s)


def _load_counties_polygons() -> list:
    """[(county_name, [ring_of_(lon,lat), ...]), ...] — lazy-loaded from geojson."""
    global _POLYGONS_CACHE
    if _POLYGONS_CACHE is not None:
        return _POLYGONS_CACHE
    if not COUNTIES_GEOJSON.is_file():
        _POLYGONS_CACHE = []
        return _POLYGONS_CACHE
    try:
        with open(COUNTIES_GEOJSON, "r", encoding="utf-8") as f:
            gj = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _county_log.warning("counties geojson не читается: %s", e)
        _POLYGONS_CACHE = []
        return _POLYGONS_CACHE

    polys: list = []
    for feat in gj.get("features", []) or []:
        props = feat.get("properties") or {}
        name = _canonicalize_county(props.get("MNIMI"))
        if not name:
            continue
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon":
            # coordinates: [ [ [lon, lat], ... ], ... ]  (первый ring — внешний)
            for ring in coords:
                polys.append((name, [(float(pt[0]), float(pt[1])) for pt in ring]))
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    polys.append((name, [(float(pt[0]), float(pt[1])) for pt in ring]))
    _POLYGONS_CACHE = polys
    return _POLYGONS_CACHE


def _point_in_ring(lon: float, lat: float, ring: list) -> bool:
    """Ray-casting: точка (lon, lat) внутри замкнутого ring'а [(lon, lat), ...]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_county(lon: float, lat: float, polygons: list) -> Optional[str]:
    """Вернуть каноничное имя уезда для точки (lon, lat) или None."""
    for name, ring in polygons:
        if _point_in_ring(lon, lat, ring):
            return name
    return None


def _seed_put(
    cache: Dict[str, Any],
    nk: str,
    county: Optional[str],
    display: str,
    provider: str,
) -> bool:
    """Записать seed-значение в cache, если ключа ещё нет или он не имеет county.

    Первый источник выигрывает: запись с truthy 'county' никогда не перезаписывается.
    Seed-источники вызываются в порядке убывания доверия (snapshot → overrides → PIP).
    """
    if not nk or not county:
        return False
    existing = cache.get(nk)
    if isinstance(existing, dict) and existing.get("county"):
        return False
    cache[nk] = {"county": county, "query": display, "provider": provider}
    return True


def _seed_from_snapshot(cache: Dict[str, Any]) -> int:
    """Затравить cache из citizen-service/artifacts/snapshot.json."""
    if not SNAPSHOT_JSON.is_file():
        return 0
    try:
        with open(SNAPSHOT_JSON, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _county_log.debug("snapshot.json не читается: %s", e)
        return 0
    places = snap.get("places") if isinstance(snap, dict) else None
    if not isinstance(places, list):
        return 0
    added = 0
    for place in places:
        if not isinstance(place, dict):
            continue
        loc = place.get("location")
        cty = _canonicalize_county(place.get("county"))
        if not loc or not cty:
            continue
        nk = normalize_location(loc)
        if _seed_put(cache, nk, cty, str(loc), "seed_snapshot"):
            added += 1
    return added


def _strip_estonia_suffix(query: str) -> str:
    """'Ulge talu veevärk, Estonia' -> 'Ulge talu veevärk'."""
    s = str(query).strip()
    return re.sub(r",\s*Estonia\s*$", "", s, flags=re.IGNORECASE).strip()


def _seed_from_coords(cache: Dict[str, Any]) -> int:
    """Затравить cache через координатные кэши + point-in-polygon."""
    polygons = _load_counties_polygons()
    if not polygons:
        return 0
    added = 0

    # 1) coordinate_overrides.json — {'version': ..., 'items': [ {location, lat, lon, ...}, ... ]}
    if COORD_OVERRIDES_JSON.is_file():
        try:
            with open(COORD_OVERRIDES_JSON, "r", encoding="utf-8") as f:
                ovr = json.load(f)
            items = ovr.get("items") if isinstance(ovr, dict) else None
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    loc = item.get("location")
                    lat = item.get("lat")
                    lon = item.get("lon")
                    if not loc or lat is None or lon is None:
                        continue
                    try:
                        cty = _point_in_county(float(lon), float(lat), polygons)
                    except (TypeError, ValueError):
                        continue
                    nk = normalize_location(loc)
                    if _seed_put(cache, nk, cty, str(loc), "seed_overrides"):
                        added += 1
        except (json.JSONDecodeError, OSError) as e:
            _county_log.debug("coordinate_overrides.json не читается: %s", e)

    # 2) coordinate_resolve_cache.json — {'provider|address': {lat, lon, ...}}
    if COORD_RESOLVE_CACHE_JSON.is_file():
        try:
            with open(COORD_RESOLVE_CACHE_JSON, "r", encoding="utf-8") as f:
                res = json.load(f)
            if isinstance(res, dict):
                for key, val in res.items():
                    if not isinstance(val, dict):
                        continue
                    lat = val.get("lat")
                    lon = val.get("lon")
                    if lat is None or lon is None:
                        continue
                    addr = str(key).split("|", 1)[-1] if "|" in str(key) else str(key)
                    # удалить вероятный ", <region>, eesti" хвост для display — берём первую часть
                    display = addr.split(",", 1)[0].strip() or addr
                    try:
                        cty = _point_in_county(float(lon), float(lat), polygons)
                    except (TypeError, ValueError):
                        continue
                    nk = normalize_location(display)
                    if _seed_put(cache, nk, cty, display, "seed_coord_cache"):
                        added += 1
        except (json.JSONDecodeError, OSError) as e:
            _county_log.debug("coordinate_resolve_cache.json не читается: %s", e)

    # 3) geocode_cache.json — {'<address>, Estonia': {lat, lon, miss?}}
    if GEOCODE_CACHE_SIMPLE_JSON.is_file():
        try:
            with open(GEOCODE_CACHE_SIMPLE_JSON, "r", encoding="utf-8") as f:
                gc = json.load(f)
            if isinstance(gc, dict):
                for key, val in gc.items():
                    if not isinstance(val, dict):
                        continue
                    if val.get("miss"):
                        continue
                    lat = val.get("lat")
                    lon = val.get("lon")
                    if lat is None or lon is None:
                        continue
                    display = _strip_estonia_suffix(str(key))
                    try:
                        cty = _point_in_county(float(lon), float(lat), polygons)
                    except (TypeError, ValueError):
                        continue
                    nk = normalize_location(display)
                    if _seed_put(cache, nk, cty, display, "seed_geocode_cache"):
                        added += 1
        except (json.JSONDecodeError, OSError) as e:
            _county_log.debug("geocode_cache.json не читается: %s", e)

    return added


def _seed_cache_from_local_sources(cache: Dict[str, Any], *, verbose: bool) -> bool:
    """Затравить cache из snapshot.json + координатных кэшей + county polygons.

    Порядок: snapshot (авторитетно) → координатные файлы через PIP.
    Не перезаписывает реальные HTTP-хиты (provider без префикса 'seed_').
    """
    n_snap = _seed_from_snapshot(cache)
    n_coord = _seed_from_coords(cache)
    total = n_snap + n_coord
    if verbose and total:
        _county_log.info(
            "Seeded county cache from local sources: %s entries (snapshot=%s, coord_pip=%s)",
            total,
            n_snap,
            n_coord,
        )
    return total > 0


def enrich_county_column(
    df: pd.DataFrame,
    *,
    geocode: bool = False,
    geocode_limit: Optional[int] = None,
    google_api_key: Optional[str] = None,
    google_delay_sec: float = 0.2,
    opencage_api_key: Optional[str] = None,
    opencage_delay_sec: float = 0.55,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Заполнить пропуски в колонке county; добавить county_source.

    county_source: xml | override | geocache | geocache_miss | geocode_google | geocode_opencage | unknown

    По умолчанию геокодирование выключено: XML, overrides и файл кэша.
    При geocode=True: HTTP к Google (и fallback к OpenCage) для каждой уникальной локации без county в кэше/overrides,
    пока не исчерпан geocode_limit. **geocode_limit=None** (по умолчанию) — без ограничения числа
    запросов за вызов. Уже успешные и уже проверенные промахи (**miss** в county_geocode_cache.json)
    повторно в OpenCage не отправляются.
    Укажите целое число в geocode_limit, чтобы ограничить расход квоты (например в CI).
    Пауза между запросами — opencage_delay_sec (по умолчанию ~0.55 с; env OPENCAGE_MIN_DELAY_SEC,
    не ниже ~0.15; при 429 увеличьте до 1.0).
    """
    if df.empty or "location" not in df.columns:
        return df

    env_oc = os.environ.get("OPENCAGE_MIN_DELAY_SEC", "").strip()
    if env_oc:
        try:
            opencage_delay_sec = max(0.15, float(env_oc))
        except ValueError:
            pass

    out = df.copy()
    if "county" not in out.columns:
        out["county"] = None

    if verbose:
        _county_log.info("Обогащение county для %s строк", len(out))

    overrides = load_overrides()
    cache = load_geocode_cache()
    modified_cache = False
    if _seed_cache_from_local_sources(cache, verbose=verbose):
        modified_cache = True

    # Источник для уже заполненного из XML
    src = []
    for i, row in out.iterrows():
        c = row.get("county")
        if c is not None and not (isinstance(c, float) and pd.isna(c)) and str(c).strip():
            src.append("xml")
        else:
            src.append(None)
    out["_county_src"] = src

    # Apply overrides even to rows with XML county — fixes data-entry errors
    # in the source XML (e.g. wrong maakond for a location).
    if overrides:
        override_corrections = 0
        for i, row in out.iterrows():
            nk = normalize_location(row.get("location"))
            if nk and nk in overrides:
                old_county = out.at[i, "county"]
                new_county = overrides[nk]
                if out.at[i, "_county_src"] == "xml" and str(old_county).strip().lower() != new_county.strip().lower():
                    override_corrections += 1
                out.at[i, "county"] = new_county
                out.at[i, "_county_src"] = "override"
        if verbose and override_corrections:
            _county_log.info(
                "Overrides скорректировали %s строк с XML-county",
                override_corrections,
            )

    # Уникальные нормализованные локации с пропуском county
    need_keys: Dict[str, str] = {}  # norm -> первый оригинальный текст для запроса
    for i, row in out.iterrows():
        if out.at[i, "_county_src"] in ("xml", "override"):
            continue
        loc = row.get("location")
        nk = normalize_location(loc)
        if not nk:
            continue
        if nk not in need_keys and loc is not None and str(loc).strip():
            need_keys[nk] = str(loc).strip()

    if verbose:
        _county_log.info("Уникальных локаций без maakond из XML: %s", len(need_keys))

    resolved: Dict[str, Tuple[str, str]] = {}  # norm -> (county, source)

    geocode_calls = 0
    lim = geocode_limit if geocode else 0

    gk = (google_api_key or os.environ.get("GOOGLE_MAPS_GEOCODING_API_KEY", "") or "").strip() or None
    ok = (opencage_api_key or os.environ.get("OPENCAGE_API_KEY", "") or "").strip() or None
    pending_http = 0
    if geocode and (gk or ok):
        for _nk in need_keys:
            if _nk in overrides:
                continue
            _ent = cache.get(_nk)
            if isinstance(_ent, dict) and _ent.get("county"):
                continue
            if isinstance(_ent, dict) and _ent.get("miss"):
                # legacy miss (обычно старый OpenCage) можно пере-проверить через Google
                if gk and _ent.get("provider") not in ("google", "google+opencage"):
                    pass
                else:
                    continue
            pending_http += 1

    if verbose and geocode and (gk or ok):
        cap = pending_http if lim is None else min(pending_http, lim)
        est_min = max(1, int(cap * (max(google_delay_sec, opencage_delay_sec) + 0.25) / 60))
        lim_msg = "без лимита (все отсутствующие в кэше)" if lim is None else str(lim)
        provider_msg = "Google" if gk else "OpenCage"
        _county_log.info(
            "Уезд (%s): уникальных без кэша/overrides ≈ %s; за этот вызов HTTP ≤ %s; пауза ~%.2f/%.2fs; оценка ~%s мин",
            provider_msg,
            pending_http,
            lim_msg,
            google_delay_sec,
            opencage_delay_sec,
            est_min,
        )
    elif verbose and geocode and not (gk or ok):
        _county_log.warning("geocode=True, но нет GOOGLE_MAPS_GEOCODING_API_KEY/OPENCAGE_API_KEY — новых HTTP-запросов не будет")

    for nk, display in need_keys.items():
        if nk in overrides:
            resolved[nk] = (overrides[nk], "override")
            continue
        ent = cache.get(nk)
        if isinstance(ent, dict) and ent.get("county"):
            resolved[nk] = (str(ent["county"]), "geocache")
            continue
        if isinstance(ent, dict) and ent.get("miss"):
            # Для старых miss без Google-провайдера даем еще один шанс через Google.
            if not (geocode and gk and ent.get("provider") not in ("google", "google+opencage")):
                resolved[nk] = (None, "geocache_miss")
                continue
        if not geocode:
            continue
        if lim is not None and geocode_calls >= lim:
            break

        county: Optional[str] = None
        src_geo: Optional[str] = None
        provider_used: Optional[str] = None

        if gk and (lim is None or geocode_calls < lim):
            county, _gq = _geocode_one_google(display, gk)
            geocode_calls += 1
            provider_used = "google"
            if county:
                src_geo = "geocode_google"
            time.sleep(google_delay_sec)
            if verbose and geocode_calls % 25 == 0:
                cap = f"/{lim}" if lim is not None else " (∞)"
                _county_log.info("County HTTP: запрос %s%s (Google/OpenCage)", geocode_calls, cap)

        # Если доступен Google, OpenCage fallback для county не используем:
        # это исключает 402 и лишние запросы в старый провайдер.
        if not county and ok and not gk and (lim is None or geocode_calls < lim):
            county, _oq = _geocode_one_opencage(display, ok)
            geocode_calls += 1
            provider_used = "google+opencage" if provider_used == "google" else "opencage"
            if county:
                src_geo = "geocode_opencage"
            time.sleep(opencage_delay_sec)
            if verbose and geocode_calls % 25 == 0:
                cap = f"/{lim}" if lim is not None else " (∞)"
                _county_log.info("County HTTP: запрос %s%s (Google/OpenCage)", geocode_calls, cap)

        if county:
            resolved[nk] = (county, src_geo or "geocode_opencage")
            cache[nk] = {"county": county, "query": display, "provider": provider_used or src_geo}
            modified_cache = True
        else:
            cache[nk] = {"county": None, "query": display, "miss": True, "provider": provider_used}
            modified_cache = True

    if modified_cache:
        save_geocode_cache(cache)

    for i, row in out.iterrows():
        if out.at[i, "_county_src"] in ("xml", "override"):
            continue
        nk = normalize_location(row.get("location"))
        if nk in resolved:
            co, source = resolved[nk]
            out.at[i, "county"] = co
            out.at[i, "_county_src"] = source
        else:
            out.at[i, "_county_src"] = "unknown"

    out["county_source"] = out["_county_src"].astype(str)
    out.drop(columns=["_county_src"], inplace=True)

    if verbose:
        n_new = (out["county"].notna() & (out["county_source"] != "xml")).sum()
        _county_log.info(
            "Заполнено county не из XML: %s строк; распределение county_source:\n%s",
            int(n_new),
            out["county_source"].value_counts().to_string(),
        )

    return out


__all__ = [
    "normalize_location",
    "load_overrides",
    "load_geocode_cache",
    "save_geocode_cache",
    "enrich_county_column",
    "OVERRIDES_CSV",
    "GEOCODE_CACHE_PATH",
]
