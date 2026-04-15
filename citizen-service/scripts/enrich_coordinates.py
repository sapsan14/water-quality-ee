#!/usr/bin/env python3
"""
Обогащение координат для карты Citizen Service — без пересборки ML-моделей.

Читает существующий snapshot.json и заменяет approximate_ee / county_centroid
реальными координатами через три источника (по убыванию приоритета):

  1. EEA Bathing Water FeatureServer (supluskoha — официальные GPS купальных мест ЕС)
  2. veevargid.xml  (vtiav.sm.ee — список объектов водопровода с L-EST97 координатами)
  3. OpenCage Geocoding (все домены; ключ OPENCAGE_API_KEY)

Результат:
  - обновлённый  citizen-service/artifacts/snapshot.json
  - кэш          citizen-service/data/coordinate_resolve_cache.json

Запуск (из корня репозитория):
  python citizen-service/scripts/enrich_coordinates.py --limit 200
  python citizen-service/scripts/enrich_coordinates.py --domain supluskoha --limit 0
  python citizen-service/scripts/enrich_coordinates.py --dry-run   # только статистика

Переменные окружения:
  OPENCAGE_API_KEY — ключ OpenCage (https://opencagedata.com). Без ключа — только EEA + veevargid.

Этот скрипт НЕЗАВИСИМ от обучения моделей. snapshot.json содержит предсказания
с прошлой полной сборки; обогащение меняет только поля lat/lon/coord_source.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import requests

# ── Пути ──────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "citizen-service" / "artifacts"
DATA_DIR = ROOT / "citizen-service" / "data"
COORD_CACHE = DATA_DIR / "coordinate_resolve_cache.json"
SNAPSHOT_PATH = ARTIFACTS / "snapshot.json"

_CS_DIR = ROOT / "citizen-service"
if str(_CS_DIR) not in sys.path:
    sys.path.insert(0, str(_CS_DIR))

import geocode_resolve as _geo  # noqa: E402

# ── Константы ──────────────────────────────────────────────────────────────────

# L-EST97 (EPSG:3301) параметры
_LEST97_A = 6_378_137.0
_LEST97_B = 6_356_752.314_140_347
_LEST97_E2 = 1.0 - (_LEST97_B / _LEST97_A) ** 2
_LEST97_K0 = 0.9996
_LEST97_LON0 = math.radians(24.0)
_LEST97_LAT0 = math.radians(57.517_5)
_LEST97_FE = 500_000.0
_LEST97_FN = 6_375_000.0

# EEA Bathing Water FeatureServer
_EEA_FS_URLS = [
    (
        "https://discomap.eea.europa.eu/arcgis/rest/services"
        "/Bathing_Water_Directive/BWD_BathingWaterProfiles/FeatureServer/0/query"
    ),
    (
        "https://discomap.eea.europa.eu/arcgis/rest/services"
        "/Bathing_Water_Directive/BWD_BathingWaterStatus/FeatureServer/0/query"
    ),
]
_EEA_COMMON_PARAMS = {
    "where": "countryCode='EE'",
    "outFields": "bwId,bwName,lat,lon",
    "f": "json",
    "resultRecordCount": 2000,
}

_VEEVARGID_URL = "https://vtiav.sm.ee/index.php/opendata/veevargid.xml"

_EE_LAT = (57.48, 59.72)
_EE_LON = (21.65, 28.22)


# ── L-EST97 → WGS84 ───────────────────────────────────────────────────────────

def _lest97_to_wgs84(northing: float, easting: float) -> Optional[tuple[float, float]]:
    """Конвертировать L-EST97 (EPSG:3301) → WGS84 (lat, lon). Без pyproj."""
    x = easting - _LEST97_FE
    y = northing - _LEST97_FN

    e2 = _LEST97_E2
    n = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    a = _LEST97_A

    m0 = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * _LEST97_LAT0
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * _LEST97_LAT0)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * _LEST97_LAT0)
        - (35 * e2**3 / 3072) * math.sin(6 * _LEST97_LAT0)
    )
    m = m0 + y / _LEST97_K0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))

    fp = (
        mu
        + (3 * n / 2 - 27 * n**3 / 32) * math.sin(2 * mu)
        + (21 * n**2 / 16 - 55 * n**4 / 32) * math.sin(4 * mu)
        + (151 * n**3 / 96) * math.sin(6 * mu)
        + (1097 * n**4 / 512) * math.sin(8 * mu)
    )

    sinFp = math.sin(fp)
    cosFp = math.cos(fp)
    tanFp = math.tan(fp)

    n1 = a / math.sqrt(1 - e2 * sinFp**2)
    t1 = tanFp**2
    c1 = (e2 / (1 - e2)) * cosFp**2
    r1 = a * (1 - e2) / (1 - e2 * sinFp**2) ** 1.5
    d = x / (n1 * _LEST97_K0)

    lat = fp - (n1 * tanFp / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e2 / (1 - e2)) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e2 / (1 - e2) - 3 * c1**2) * d**6 / 720
    )
    lon = _LEST97_LON0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e2 / (1 - e2) + 24 * t1**2) * d**5 / 120
    ) / cosFp

    lat_deg = math.degrees(lat)
    lon_deg = math.degrees(lon)

    if not (_EE_LAT[0] <= lat_deg <= _EE_LAT[1] and _EE_LON[0] <= lon_deg <= _EE_LON[1]):
        return None
    return round(lat_deg, 6), round(lon_deg, 6)


# ── Нормализация имён ─────────────────────────────────────────────────────────

def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFC", s.strip().lower())
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _name_similarity(a: str, b: str) -> float:
    ta = set(_norm_name(a).split())
    tb = set(_norm_name(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── EEA Bathing Water ─────────────────────────────────────────────────────────

def _fetch_eea_estonia(session: requests.Session, verbose: bool = True) -> dict[str, tuple[float, float]]:
    """Загрузить координаты купальных мест Эстонии из EEA WISE FeatureServer."""
    for url in _EEA_FS_URLS:
        try:
            r = session.get(url, params=_EEA_COMMON_PARAMS, timeout=30)
            if r.status_code != 200:
                if verbose:
                    print(f"[EEA] {url[:60]}… → HTTP {r.status_code}")
                continue
            data = r.json()
        except Exception as exc:
            if verbose:
                print(f"[EEA] ошибка {url[:60]}…: {exc}")
            continue

        features = data.get("features") or []
        if not features:
            if verbose:
                print(f"[EEA] пустой ответ от {url[:60]}…")
            continue

        out: dict[str, tuple[float, float]] = {}
        for feat in features:
            attrs = feat.get("attributes", {}) or {}
            geom = feat.get("geometry", {}) or {}
            name = str(attrs.get("bwName") or "").strip()
            if not name:
                continue
            try:
                lat = float(attrs.get("lat") or geom.get("y") or 0)
                lon = float(attrs.get("lon") or geom.get("x") or 0)
            except (TypeError, ValueError):
                continue
            if not (_EE_LAT[0] <= lat <= _EE_LAT[1] and _EE_LON[0] <= lon <= _EE_LON[1]):
                continue
            out[_norm_name(name)] = (lat, lon)

        if out:
            if verbose:
                print(f"[EEA] загружено {len(out)} купальных мест Эстонии")
            return out

    if verbose:
        print("[EEA] данные не получены")
    return {}


def _match_eea(location: str, eea_data: dict[str, tuple[float, float]], threshold: float = 0.5) -> Optional[tuple[float, float]]:
    nk = _norm_name(location)
    if nk in eea_data:
        return eea_data[nk]
    for eea_name, coords in eea_data.items():
        if _name_similarity(nk, eea_name) >= threshold:
            return coords
    return None


# ── veevargid.xml ─────────────────────────────────────────────────────────────

def _fetch_veevargid(session: requests.Session, verbose: bool = True) -> dict[str, tuple[float, float]]:
    """Попытаться загрузить список объектов водопровода с L-EST97 координатами."""
    try:
        r = session.get(_VEEVARGID_URL, timeout=30)
        if r.status_code != 200:
            if verbose:
                print(f"[veevargid] HTTP {r.status_code}: файл недоступен")
            return {}
    except Exception as exc:
        if verbose:
            print(f"[veevargid] ошибка загрузки: {exc}")
        return {}

    content = r.content
    if b"<html" in content[:200].lower() or b"<!doctype" in content[:200].lower():
        if verbose:
            print("[veevargid] получен HTML — файл не существует в opendata")
        return {}

    try:
        from lxml import etree
        tree = etree.fromstring(content)
    except Exception as exc:
        if verbose:
            print(f"[veevargid] ошибка парсинга XML: {exc}")
        return {}

    out: dict[str, tuple[float, float]] = {}
    n_ok = n_fail = 0

    for obj in tree.findall(".//*"):
        name_el = obj.find("nimi") or obj.find("nimetus") or obj.find("veevark")
        name = (name_el.text or "").strip() if name_el is not None else ""
        if not name:
            continue

        north_el = (
            obj.find("koordinaat_n") or obj.find("n_koordinaat") or
            obj.find("koordinaat_y") or obj.find("y") or obj.find("lest_n")
        )
        east_el = (
            obj.find("koordinaat_e") or obj.find("e_koordinaat") or
            obj.find("koordinaat_x") or obj.find("x") or obj.find("lest_e")
        )

        if north_el is None or east_el is None:
            lat_el = obj.find("lat") or obj.find("latitude") or obj.find("wgs84_n")
            lon_el = obj.find("lon") or obj.find("longitude") or obj.find("wgs84_e")
            if lat_el is not None and lon_el is not None:
                try:
                    lat = float((lat_el.text or "").replace(",", "."))
                    lon = float((lon_el.text or "").replace(",", "."))
                    if _EE_LAT[0] <= lat <= _EE_LAT[1] and _EE_LON[0] <= lon <= _EE_LON[1]:
                        out[_norm_name(name)] = (lat, lon)
                        n_ok += 1
                except ValueError:
                    n_fail += 1
            continue

        try:
            north = float((north_el.text or "").replace(",", ".").replace(" ", ""))
            east = float((east_el.text or "").replace(",", ".").replace(" ", ""))
        except ValueError:
            n_fail += 1
            continue

        if 6_200_000 <= north <= 6_800_000 and 200_000 <= east <= 900_000:
            coords = _lest97_to_wgs84(north, east)
            if coords:
                out[_norm_name(name)] = coords
                n_ok += 1
            else:
                n_fail += 1
        else:
            n_fail += 1

    if verbose:
        print(f"[veevargid] объектов с координатами: {n_ok} (неудача конвертации: {n_fail})")
    return out


# ── Основная функция обогащения ────────────────────────────────────────────────

def enrich(
    *,
    limit: int = 200,
    domain_filter: Optional[str] = None,
    skip_eea: bool = False,
    skip_veevargid: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
    opencage_api_key: Optional[str] = None,
) -> dict:
    """
    Обогатить координаты в snapshot.json.

    Args:
        limit:           максимум HTTP-запросов OpenCage на этот запуск.
        domain_filter:   только этот домен (None = все).
        skip_eea:        не запрашивать EEA (не нужен интернет для supluskoha).
        skip_veevargid:  не пробовать veevargid.xml.
        dry_run:         только статистика, не сохранять файлы.
        opencage_api_key: ключ OpenCage (по умолчанию из OPENCAGE_API_KEY env).

    Returns:
        Словарь со статистикой (source → count).
    """
    if opencage_api_key is None:
        opencage_api_key = os.environ.get("OPENCAGE_API_KEY") or None

    if not SNAPSHOT_PATH.exists():
        print(f"[enrich] snapshot.json не найден: {SNAPSHOT_PATH}")
        return {}

    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        snapshot = json.load(f)

    places = snapshot.get("places", [])
    resolve_cache = _geo.load_resolve_cache(COORD_CACHE)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "water-quality-ee-enrich/1.0 (TalTech water-quality research)",
        "Accept": "application/json",
    })

    # ── 1. EEA Bathing Water для supluskoha ───────────────────────────────────
    eea_data: dict[str, tuple[float, float]] = {}
    if not skip_eea and (domain_filter is None or domain_filter == "supluskoha"):
        eea_data = _fetch_eea_estonia(session, verbose=verbose)

    # ── 2. veevargid.xml для veevark ─────────────────────────────────────────
    vvg_data: dict[str, tuple[float, float]] = {}
    if not skip_veevargid and (domain_filter is None or domain_filter == "veevark"):
        vvg_data = _fetch_veevargid(session, verbose=verbose)

    budget = [max(0, limit)]
    stats: dict[str, int] = {
        "already_ok": 0, "eea_bathing": 0, "veevargid": 0,
        "opencage": 0, "unchanged": 0,
    }

    for place in places:
        if domain_filter and place.get("domain") != domain_filter:
            continue

        src = place.get("coord_source", "")
        loc = str(place.get("location") or "").strip()
        domain = str(place.get("domain") or "").strip()
        county = place.get("county")
        county = str(county).strip() if county else None

        lat = lon = None
        new_src = None

        # ── EEA для supluskoha (приоритет над OpenCage — официальные EU coords) ─
        if domain == "supluskoha" and eea_data and src != "eea_bathing":
            m = _match_eea(loc, eea_data)
            if m:
                lat, lon = m
                new_src = "eea_bathing"

        # ── veevargid для veevark (L-EST97 точнее OpenCage для водопровода) ────
        if lat is None and domain == "veevark" and vvg_data and src != "veevargid":
            m = vvg_data.get(_norm_name(loc))
            if m:
                lat, lon = m
                new_src = "veevargid"

        # Уже есть нормальные координаты и EEA/veevargid не дали лучших — пропустить
        if lat is None and src not in ("approximate_ee", "county_centroid", "none", "", None):
            stats["already_ok"] += 1
            continue

        # ── OpenCage каскад ───────────────────────────────────────────────────
        if lat is None and (opencage_api_key or budget[0] > 0):
            fac = str(place.get("geocode_facility") or loc).strip()
            site = str(place.get("geocode_site") or "").strip()
            queries = _geo.build_geocode_queries(domain, loc, site, fac, county)
            got = _geo.resolve_coordinates_cascade(
                queries,
                resolve_cache=resolve_cache,
                session=session,
                opencage_api_key=opencage_api_key,
                budget_remaining=budget,
            )
            if got:
                new_src, lat, lon, _ = got

        if lat is not None and new_src:
            stats[new_src] = stats.get(new_src, 0) + 1
            if verbose:
                print(f"[{new_src:12s}] {domain:10s} | {loc[:55]}: ({lat:.4f}, {lon:.4f})")
            if not dry_run:
                place["lat"] = lat
                place["lon"] = lon
                place["coord_source"] = new_src
        else:
            stats["unchanged"] += 1

    if not dry_run:
        _geo.save_resolve_cache(COORD_CACHE, resolve_cache)
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    total = sum(stats.values())
    resolved = sum(v for k, v in stats.items() if k not in ("already_ok", "unchanged"))
    print()
    print("=" * 60)
    print(f"[enrich] ИТОГО: {total} точек обработано")
    print(f"  уже с координатами: {stats['already_ok']}")
    print(f"  обогащено:          {resolved}")
    for src in ("eea_bathing", "veevargid", "opencage"):
        if stats.get(src, 0):
            print(f"    └─ {src}: {stats[src]}")
    print(f"  без координат:      {stats['unchanged']}")
    print(f"  OpenCage бюджет остаток: {budget[0]} из {limit}")
    if not dry_run:
        print(f"  кэш:      {COORD_CACHE}")
        print(f"  snapshot: {SNAPSHOT_PATH}")
    print("=" * 60)

    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Обогатить координаты в snapshot.json без пересборки модели.",
    )
    ap.add_argument(
        "--limit", type=int, default=200,
        help="максимум HTTP-запросов OpenCage (по умолчанию 200)",
    )
    ap.add_argument(
        "--domain",
        choices=["supluskoha", "veevark", "basseinid", "joogivesi"],
        default=None,
        help="только один домен (по умолчанию — все)",
    )
    ap.add_argument("--skip-eea", action="store_true", help="не запрашивать EEA API")
    ap.add_argument("--skip-veevargid", action="store_true", help="не пробовать veevargid.xml")
    ap.add_argument("--dry-run", action="store_true", help="только статистика, не сохранять")
    ap.add_argument("--quiet", action="store_true", help="минимальный вывод")
    args = ap.parse_args()

    enrich(
        limit=args.limit,
        domain_filter=args.domain,
        skip_eea=args.skip_eea,
        skip_veevargid=args.skip_veevargid,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
