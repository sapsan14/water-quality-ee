"""
Вывод уезда (maakond) из текста location, если в XML поле maakond пустое.

Каскад:
1. Уже заполненный county из XML — без изменений (county_source=xml).
2. Справочник data/reference/location_county_overrides.csv (нормализованный ключ).
3. Кэш геокодирования data/processed/county_geocode_cache.json.
4. Nominatim (geopy), не чаще min_delay_sec запросов; новые ответы пишутся в кэш.

Требует пакет geopy. Без сети: передайте geocode=False — сработают только XML, overrides и существующий кэш.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
OVERRIDES_CSV = DATA_ROOT / "reference" / "location_county_overrides.csv"
GEOCODE_CACHE_PATH = DATA_ROOT / "processed" / "county_geocode_cache.json"

NOMINATIM_USER_AGENT = "water-quality-ee/1.0 (TalTech water-quality course project)"

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


def _extract_county_from_nominatim_address(addr: Dict[str, str]) -> Optional[str]:
    if not addr:
        return None
    for key in ("county", "state", "region"):
        val = addr.get(key)
        if not val:
            continue
        v = str(val).strip()
        if "maakond" in v.lower():
            return _normalize_county_name(v)
        if "county" in v.lower():
            return _normalize_county_name(v)
    return None


def _geocode_one(location_display: str) -> Tuple[Optional[str], Optional[str]]:
    """Вернуть (county, query_used)."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    except ImportError:
        return None, None

    geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT)
    query = f"{location_display}, Estonia"
    try:
        loc = geolocator.geocode(
            query,
            addressdetails=True,
            language="et,en",
            timeout=15,
        )
    except (GeocoderTimedOut, GeocoderServiceError, OSError):
        return None, query
    if loc is None or not getattr(loc, "raw", None):
        return None, query
    addr = loc.raw.get("address") or {}
    county = _extract_county_from_nominatim_address(addr)
    return _normalize_county_name(county), query


def enrich_county_column(
    df: pd.DataFrame,
    *,
    geocode: bool = False,
    geocode_limit: Optional[int] = 200,
    min_delay_sec: float = 1.1,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Заполнить пропуски в колонке county; добавить county_source.

    county_source: xml | override | geocache | geocode | unknown

    По умолчанию геокодирование выключено: XML, overrides и файл кэша.
    При geocode=True не более geocode_limit новых HTTP-запросов за вызов
    (None = без лимита). Между запросами — min_delay_sec.
    """
    if df.empty or "location" not in df.columns:
        return df

    out = df.copy()
    if "county" not in out.columns:
        out["county"] = None

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

    resolved: Dict[str, Tuple[str, str]] = {}  # norm -> (county, source)

    geocode_calls = 0
    lim = geocode_limit if geocode else 0

    for nk, display in need_keys.items():
        if nk in overrides:
            resolved[nk] = (overrides[nk], "override")
            continue
        ent = cache.get(nk)
        if isinstance(ent, dict) and ent.get("county"):
            resolved[nk] = (str(ent["county"]), "geocache")
            continue
        if not geocode:
            continue
        if lim is not None and geocode_calls >= lim:
            break
        county, _q = _geocode_one(display)
        geocode_calls += 1
        time.sleep(min_delay_sec)
        if county:
            resolved[nk] = (county, "geocode")
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
        print(
            f"[county_infer] Заполнено county не из XML: {int(n_new)} строк; "
            f"распределение county_source:\n{out['county_source'].value_counts().to_string()}"
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
