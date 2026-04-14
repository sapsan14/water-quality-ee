"""
Вывод уезда (maakond) из текста location, если в XML поле maakond пустое.

Каскад:
1. Уже заполненный county из XML — без изменений (county_source=xml).
2. Справочник data/reference/location_county_overrides.csv (нормализованный ключ).
3. Кэш геокодирования data/processed/county_geocode_cache.json.
4. OpenCage Geocoding (если задан opencage_api_key или env OPENCAGE_API_KEY) — из components.

Google Geocoding, публичный Nominatim и In-ADS не используются. Нужен requests; без сети: geocode=False — только XML, overrides и кэш.
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

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
OVERRIDES_CSV = DATA_ROOT / "reference" / "location_county_overrides.csv"
GEOCODE_CACHE_PATH = DATA_ROOT / "processed" / "county_geocode_cache.json"

OPENCAGE_GEOCODE_URL = "https://api.opencagedata.com/geocode/v1/json"

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


def enrich_county_column(
    df: pd.DataFrame,
    *,
    geocode: bool = False,
    geocode_limit: Optional[int] = None,
    opencage_api_key: Optional[str] = None,
    opencage_delay_sec: float = 0.55,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Заполнить пропуски в колонке county; добавить county_source.

    county_source: xml | override | geocache | geocache_miss | geocode_opencage | geocode_google (устар.) | unknown

    По умолчанию геокодирование выключено: XML, overrides и файл кэша.
    При geocode=True: HTTP к OpenCage для каждой уникальной локации без county в кэше/overrides,
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

    # Источник для уже заполненного из XML
    src = []
    for i, row in out.iterrows():
        c = row.get("county")
        if c is not None and not (isinstance(c, float) and pd.isna(c)) and str(c).strip():
            src.append("xml")
        else:
            src.append(None)
    out["_county_src"] = src

    # Уникальные нормализованные локации с пропуском county
    need_keys: Dict[str, str] = {}  # norm -> первый оригинальный текст для запроса
    for i, row in out.iterrows():
        if out.at[i, "_county_src"] == "xml":
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

    ok = (opencage_api_key or os.environ.get("OPENCAGE_API_KEY", "") or "").strip() or None
    pending_http = 0
    if geocode and ok:
        for _nk in need_keys:
            if _nk in overrides:
                continue
            _ent = cache.get(_nk)
            if isinstance(_ent, dict) and _ent.get("county"):
                continue
            if isinstance(_ent, dict) and _ent.get("miss"):
                continue
            pending_http += 1

    if verbose and geocode and ok:
        cap = pending_http if lim is None else min(pending_http, lim)
        est_min = max(1, int(cap * (opencage_delay_sec + 0.25) / 60))
        lim_msg = "без лимита (все отсутствующие в кэше)" if lim is None else str(lim)
        _county_log.info(
            "Уезд (OpenCage): уникальных без кэша/overrides ≈ %s; за этот вызов HTTP ≤ %s; пауза ~%.2fs; оценка ~%s мин",
            pending_http,
            lim_msg,
            opencage_delay_sec,
            est_min,
        )
    elif verbose and geocode and not ok:
        _county_log.warning("geocode=True, но нет OPENCAGE_API_KEY — новых HTTP-запросов не будет")

    for nk, display in need_keys.items():
        if nk in overrides:
            resolved[nk] = (overrides[nk], "override")
            continue
        ent = cache.get(nk)
        if isinstance(ent, dict) and ent.get("county"):
            resolved[nk] = (str(ent["county"]), "geocache")
            continue
        if isinstance(ent, dict) and ent.get("miss"):
            resolved[nk] = (None, "geocache_miss")
            continue
        if not geocode:
            continue
        if lim is not None and geocode_calls >= lim:
            break

        county: Optional[str] = None
        src_geo: Optional[str] = None

        if ok and (lim is None or geocode_calls < lim):
            county, _oq = _geocode_one_opencage(display, ok)
            geocode_calls += 1
            if county:
                src_geo = "geocode_opencage"
            time.sleep(opencage_delay_sec)
            if verbose and geocode_calls % 25 == 0:
                cap = f"/{lim}" if lim is not None else " (∞)"
                _county_log.info("County HTTP: запрос %s%s (OpenCage)", geocode_calls, cap)

        if county:
            resolved[nk] = (county, src_geo or "geocode_opencage")
            cache[nk] = {"county": county, "query": display}
            modified_cache = True
        else:
            cache[nk] = {"county": None, "query": display, "miss": True}
            modified_cache = True

    if modified_cache:
        save_geocode_cache(cache)

    for i, row in out.iterrows():
        if out.at[i, "_county_src"] == "xml":
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
