#!/usr/bin/env python3
"""
Собрать snapshot для гражданского приложения: последняя проба по (domain, location),
официальный compliant, вероятности нарушения по 4 моделям (LR, RF, GradBoost, LightGBM), координаты.

Координаты в файлах *_veeproovid_YYYY.xml нет; при load_all/load_domain подтягиваются
официальные L-EST97→WGS84 из справочников opendata (supluskohad.xml и др.) → official_lat/lon.
Если их нет — простой режим или --resolve-coordinates: Google → Geoapify → OpenCage;
кэш coordinate_resolve_cache.json. Google / In-ADS / Nominatim не используются.
--geocode-limit — лимит HTTP-запросов на всю сборку.

Запуск из корня репозитория:
  python citizen-service/scripts/build_citizen_snapshot.py
  python citizen-service/scripts/build_citizen_snapshot.py --resolve-coordinates --geocode-limit 8000 --infer-county
  python citizen-service/scripts/build_citizen_snapshot.py --geocode-limit 300   # простой режим: Google→Geoapify→OpenCage
  python citizen-service/scripts/build_citizen_snapshot.py --map-only
  python citizen-service/scripts/build_citizen_snapshot.py --infer-county
  python citizen-service/scripts/build_citizen_snapshot.py --log-level DEBUG  # подробный лог геокода/кэша

Требует: скачанные XML (python src/data_loader.py) и зависимости из requirements.txt.
Для полного снимка также нужен joblib (модели пишутся в artifacts/citizen_model.joblib).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from lxml import html as lxml_html

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler

# корень репозитория: .../water-quality-ee
ROOT = Path(__file__).resolve().parents[2]

# src/ — модули доступны после `pip install -e .` (см. CLAUDE.md).
# Fallback для запуска без editable install.
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from data_loader import load_all  # noqa: E402
from features import (  # noqa: E402
    META_EXTRA_NUMERIC,
    build_citizen_meta_frame,
    build_dataset_with_meta,
)

# citizen-service/ содержит вспомогательные модули (не часть пакета src/).
_CS_DIR = ROOT / "citizen-service"
if str(_CS_DIR) not in sys.path:
    sys.path.insert(0, str(_CS_DIR))

from county_centroids import COUNTY_CENTROIDS, county_to_latlon  # noqa: E402
import geocode_resolve as _geocode_resolve  # noqa: E402

ARTIFACTS = ROOT / "citizen-service" / "artifacts"
GEOCODE_PATH = ROOT / "citizen-service" / "data" / "geocode_cache.json"
COORD_RESOLVE_PATH = ROOT / "citizen-service" / "data" / "coordinate_resolve_cache.json"
COORD_OVERRIDES_PATH = ROOT / "citizen-service" / "data" / "coordinate_overrides.json"
PAGED_ADDR_CACHE_PATH = ROOT / "citizen-service" / "data" / "paged_address_cache.json"

LOG = logging.getLogger("citizen.snapshot")


def _opencage_inter_request_delay_sec() -> float:
    """Пауза между запросами OpenCage (см. county_infer / OPENCAGE_MIN_DELAY_SEC)."""
    raw = (os.environ.get("OPENCAGE_MIN_DELAY_SEC") or "").strip()
    if raw:
        try:
            return max(0.15, float(raw))
        except ValueError:
            pass
    return 0.55


def _load_repo_dotenv() -> None:
    """Подхватить корневой .env (не в git). Явные переменные окружения не перезаписываем."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path, override=False)


def _prefer_certifi_ca_bundle() -> None:
    """На части WSL/корпоративных Linux системный CA-пакет пустой — requests/geopy падают по SSL."""
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE"):
        return
    try:
        import certifi

        bundle = certifi.where()
    except ImportError:
        return
    os.environ.setdefault("SSL_CERT_FILE", bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
# Точки на карте по умолчанию: купание, бассейны/СПА, водопровод, источники питьевой воды.
# Mineraalvesi можно включить флагом --include-mineraalvesi без изменения дефолта.
BASE_MAP_DOMAINS = {"supluskoha", "basseinid", "veevark", "joogivesi"}
OPENDATA_CATALOG_URL = "https://vtiav.sm.ee/index.php/opendata/"

PLACE_KIND = {
    "supluskoha": "swimming",
    "basseinid": "pool_spa",
    "veevark": "drinking_water",
    "joogivesi": "drinking_source",
    "mineraalvesi": "drinking_water",
}

# Для этих доменов не шлём name-only геокодинг:
# только адрес из paged-таблиц vtiav (U/JV), иначе без HTTP-запроса.
STRICT_PAGED_ADDRESS_ONLY_DOMAINS = {"veevark", "basseinid"}
_COUNTY_ADDR_RE = re.compile(r"\b([A-ZÕÄÖÜa-zõäöü\-]+(?:\s+[A-ZÕÄÖÜa-zõäöü\-]+)*)\s+maakond\b", re.IGNORECASE)


def _normalize_location_key(name: str, domain: str) -> str:
    """
    Нормализованный ключ названия места для дедупликации.

    Terviseamet переименовывал объекты между годами в opendata XML, например:
      'Harku järve supluskoht' → 'Harku järve rand'
      'Abja-Paluoja  veevärk'  → 'Abja-Paluoja veevärk'  (лишний пробел)
      'Haaslava küla veevärk'  → 'Haaslava küla ühisveevärk'
      'Tootsi Ujumisbassein'   → 'Tootsi ujumisbassein'   (регистр)

    Алгоритм: нижний регистр → убрать суффиксы домена → нормализовать пунктуацию/пробелы.
    Два названия с одинаковым ключом в одном домене считаются одним местом;
    берётся запись с более свежей датой пробы.
    """
    import re as _re
    n = name.lower().strip()
    # Суффиксы купальных мест (менялись между годами)
    n = _re.sub(r"\bsupluskoht\b", "", n)
    n = _re.sub(r"\bsupluskoha\b", "", n)
    n = _re.sub(r"\brand\b", "", n)
    n = _re.sub(r"\bsuplusala\b", "", n)
    # Суффиксы водопровода
    n = _re.sub(r"\bühistveevärk\b", "", n)
    n = _re.sub(r"\bühisveevärk\b", "", n)
    n = _re.sub(r"\bveevärk\b", "", n)
    n = _re.sub(r"\bveevõrk\b", "", n)
    n = _re.sub(r"\bveevork\b", "", n)
    # Нормализация пунктуации и пробелов
    n = _re.sub(r"[-–—]+", " ", n)
    n = _re.sub(r"[,;]+", " ", n)
    n = _re.sub(r"\s+", " ", n).strip()
    return f"{domain}|{n}"


def _extract_county_from_address(addr: str | None) -> str | None:
    if not addr:
        return None
    m = _COUNTY_ADDR_RE.search(str(addr))
    if not m:
        return None
    base = " ".join((m.group(1) or "").split()).strip()
    if not base:
        return None
    return f"{base} maakond"


def _nearest_county_from_coords(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    try:
        lt = float(lat)
        ln = float(lon)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(lt) or not np.isfinite(ln):
        return None
    best_name: str | None = None
    best_d2: float | None = None
    for nm, (clat, clon) in COUNTY_CENTROIDS.items():
        d2 = (lt - float(clat)) ** 2 + (ln - float(clon)) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            best_name = nm
    if not best_name:
        return None
    return " ".join(str(best_name).split()).strip().title()

# Kui pole Nominatimi ega maakonda: stabiilne punkt EE bbox-is (pole GPS, ainult ülevaade).
EE_BBOX_LAT = (57.48, 59.68)
EE_BBOX_LON = (21.65, 28.22)


def approximate_point_estonia(domain: str, location: str) -> tuple[float, float]:
    """
    Deterministic pseudo-coordinates inside Estonia bounding box.
    Avoids a single mega-cluster at one centroid; still NOT real object coordinates.
    """
    payload = f"{domain}\n{location}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    u = int.from_bytes(digest[0:8], "big") / (2**64)
    v = int.from_bytes(digest[8:16], "big") / (2**64)
    lat0 = EE_BBOX_LAT[0] + u * (EE_BBOX_LAT[1] - EE_BBOX_LAT[0])
    lon0 = EE_BBOX_LON[0] + v * (EE_BBOX_LON[1] - EE_BBOX_LON[0])
    du = (digest[16] / 255.0 - 0.5) * 0.08
    dv = (digest[17] / 255.0 - 0.5) * 0.12
    return lat0 + du, lon0 + dv


def load_geocode_cache() -> dict:
    if GEOCODE_PATH.is_file():
        with open(GEOCODE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_geocode_cache(cache: dict) -> None:
    GEOCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GEOCODE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def _text_norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _last_page_from_html(page_html: str, tab_id: str) -> int:
    # На сайте встречаются оба варианта: active_tab_id и active%5Ftab%5Fid.
    # Берём максимум page=N среди ссылок текущего tab, это надёжнее, чем парсить "Viimane" текст.
    pat = re.compile(
        rf"page=(\d+)&active(?:%5[fF]|_)tab(?:%5[fF]|_)id={re.escape(tab_id)}",
        re.I,
    )
    nums = [int(m.group(1)) for m in pat.finditer(page_html)]
    return max(nums) if nums else 1


def _fetch_tab_rows(session: requests.Session, tab_id: str) -> list[dict]:
    base = "https://vtiav.sm.ee"
    first_url = f"{base}/index.php/?active_tab_id={tab_id}"
    first_html = session.get(first_url, timeout=45).text
    last_page = _last_page_from_html(first_html, tab_id)
    rows: list[dict] = []

    for p in range(1, last_page + 1):
        u = f"{base}/index.php/?page={p}&active_tab_id={tab_id}"
        t = session.get(u, timeout=45).text
        doc = lxml_html.fromstring(t)
        tr_nodes = doc.xpath('//tr[.//a[contains(@href,"/frontpage/show?id=")]]')
        for tr in tr_nodes:
            a_nodes = tr.xpath('.//a[contains(@href,"/frontpage/show?id=")]')
            if not a_nodes:
                continue
            href = a_nodes[0].get("href") or ""
            m = re.search(r"id=(\d+)", href)
            if not m:
                continue
            cells = [_text_norm(c.text_content()) for c in tr.xpath("./td")]
            rows.append({"id": m.group(1), "cells": cells})
    return rows


def build_paged_address_index(session: requests.Session, use_cache: bool = True) -> dict[str, str]:
    """
    Собрать индекс адресов из публичных paged-страниц:
    - U: bassein (название бассейна) -> Asukoht
    - JV: veevark (название сети) -> Tegutsemise piirkond
    """
    if use_cache and PAGED_ADDR_CACHE_PATH.is_file():
        try:
            with open(PAGED_ADDR_CACHE_PATH, encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and isinstance(payload.get("index"), dict):
                return payload["index"]
        except (OSError, json.JSONDecodeError):
            pass

    idx: dict[str, str] = {}

    # U: col[4] = Basseini nimi, col[1] = Asukoht
    try:
        for r in _fetch_tab_rows(session, "U"):
            cells = r["cells"]
            if len(cells) < 5:
                continue
            bassein_name = cells[4]
            asukoht = cells[1]
            if bassein_name and asukoht:
                idx[_normalize_location_key(bassein_name, "basseinid")] = asukoht
    except requests.RequestException as e:
        LOG.warning("Не удалось собрать адреса с active_tab_id=U: %s", e)

    # JV: col[1] = Veevärk, col[2] = Tegutsemise piirkond
    try:
        for r in _fetch_tab_rows(session, "JV"):
            cells = r["cells"]
            if len(cells) < 3:
                continue
            veevark_name = cells[1]
            area_addr = cells[2]
            if veevark_name and area_addr:
                idx[_normalize_location_key(veevark_name, "veevark")] = area_addr
    except requests.RequestException as e:
        LOG.warning("Не удалось собрать адреса с active_tab_id=JV: %s", e)

    PAGED_ADDR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "index_size": len(idx),
        "index": idx,
    }
    with open(PAGED_ADDR_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return idx


def load_coordinate_overrides() -> dict[str, dict]:
    """
    Загрузить ручные оверрайды координат.

    Формат файла citizen-service/data/coordinate_overrides.json:
    {
      "version": 1,
      "items": [
        {"domain": "veevark", "location": "X", "action": "set_manual", "lat": 58.1, "lon": 25.2},
        {"domain": "veevark", "location": "Y", "action": "hide", "note": "..."}
      ]
    }
    """
    if not COORD_OVERRIDES_PATH.is_file():
        return {}
    try:
        with open(COORD_OVERRIDES_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        LOG.warning("Не удалось прочитать coordinate_overrides.json: %s", e)
        return {}

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}

    out: dict[str, dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        dom = str(it.get("domain") or "").strip()
        loc = str(it.get("location") or "").strip()
        if not dom or not loc:
            continue
        key = _normalize_location_key(loc, dom)
        out[key] = it
    return out


def _serialize_measurement_value(val) -> float | int | str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return str(val)
    if abs(f) < 1e12 and f == int(f):
        return int(f)
    return round(f, 5)


def row_measurements(row: pd.Series) -> dict[str, float | int | str]:
    """Ненулевые измерения из последней пробы для всплывающей карточки."""
    out: dict[str, float | int | str] = {}
    for k in META_EXTRA_NUMERIC:
        if k not in row.index:
            continue
        v = _serialize_measurement_value(row[k])
        if v is not None:
            out[k] = v
    return out


def geocode_address_simple(
    query: str,
    cache: dict,
    session: requests.Session,
    *,
    geoapify_key: str | None,
    opencage_key: str | None,
    google_key: str | None,
    http_budget: int,
) -> tuple[float | None, float | None, str | None, int]:
    """
    Простой режим (без --resolve-coordinates): кэш geocode_cache.json, иначе Google→Geoapify→OpenCage.
    Возвращает (lat, lon, coord_source, число_HTTP); lat/lon None при промахе.
    """
    clip = query[:88] + ("…" if len(query) > 88 else "")
    if query in cache:
        c = cache[query]
        if c.get("lat") is not None and c.get("lon") is not None:
            if not _geocode_resolve.geocode_cache_entry_is_precise_enough(c):
                LOG.info(
                    "coords simple-cache-ignore imprecise query=%s match=%s",
                    clip,
                    (str(c.get("matched_address") or ""))[:88],
                )
                del cache[query]
            else:
                src = str(c.get("coord_source") or "geocode_cache")
                LOG.debug(
                    "coords verified simple-cache lat=%.5f lon=%.5f source=%s query=%s",
                    float(c["lat"]),
                    float(c["lon"]),
                    src,
                    clip,
                )
                return float(c["lat"]), float(c["lon"]), src, 0
        elif c.get("miss"):
            return None, None, None, 0
    used = 0
    if http_budget <= 0:
        return None, None, None, 0
    if not geoapify_key and not opencage_key and not google_key:
        LOG.warning("coords simple: нет GEOAPIFY/OPENCAGE/GOOGLE key — пропуск query=%s", clip)
        cache[query] = {"lat": None, "lon": None, "miss": True}
        return None, None, None, 0

    if google_key and used < http_budget:
        LOG.info("coords HTTP google(simple) query=%s", clip)
        time.sleep(max(0.12, _opencage_inter_request_delay_sec() * 0.35))
        used += 1
        try:
            res = _geocode_resolve.geocode_google(query, google_key, session)
        except (requests.RequestException, ValueError, KeyError) as e:
            LOG.warning("coords google(simple) error: %s", e)
            res = None
        if res:
            cache[query] = {
                "lat": res["lat"],
                "lon": res["lon"],
                "coord_source": "google",
                "matched_address": res.get("matched_address"),
            }
            LOG.info(
                "coords update-cache google(simple) lat=%.5f lon=%.5f query=%s",
                float(res["lat"]),
                float(res["lon"]),
                clip,
            )
            return float(res["lat"]), float(res["lon"]), "google", used

    if geoapify_key and used < http_budget:
        LOG.info("coords HTTP geoapify(simple) query=%s", clip)
        time.sleep(max(0.15, _opencage_inter_request_delay_sec() * 0.5))
        used += 1
        try:
            res = _geocode_resolve.geocode_geoapify(query, geoapify_key, session)
        except (requests.RequestException, ValueError, KeyError) as e:
            LOG.warning("coords geoapify(simple) error: %s", e)
            res = None
        if res:
            cache[query] = {
                "lat": res["lat"],
                "lon": res["lon"],
                "coord_source": "geoapify",
                "matched_address": res.get("matched_address"),
                "confidence": res.get("confidence"),
            }
            LOG.info(
                "coords update-cache geoapify(simple) lat=%.5f lon=%.5f query=%s",
                float(res["lat"]),
                float(res["lon"]),
                clip,
            )
            return float(res["lat"]), float(res["lon"]), "geoapify", used

    if opencage_key and used < http_budget:
        LOG.info("coords HTTP opencage(simple) query=%s", clip)
        time.sleep(_opencage_inter_request_delay_sec())
        used += 1
        try:
            res = _geocode_resolve.geocode_opencage(query, opencage_key, session)
        except (requests.RequestException, ValueError, KeyError) as e:
            LOG.warning("coords opencage(simple) error: %s", e)
            res = None
        if res:
            cache[query] = {
                "lat": res["lat"],
                "lon": res["lon"],
                "coord_source": "opencage",
                "matched_address": res.get("matched_address"),
                "confidence": res.get("confidence"),
                "oc_type": res.get("oc_type"),
            }
            LOG.info(
                "coords update-cache opencage(simple) lat=%.5f lon=%.5f query=%s",
                float(res["lat"]),
                float(res["lon"]),
                clip,
            )
            return float(res["lat"]), float(res["lon"]), "opencage", used

    cache[query] = {"lat": None, "lon": None, "miss": True}
    LOG.info("coords miss simple (google/geoapify/opencage) query=%s", clip)
    return None, None, None, used


def _timer_print(label: str, t_run_start: float, last: list[float]) -> None:
    now = time.perf_counter()
    step = now - last[0]
    total = now - t_run_start
    msg = f"[citizen/timer] {label}: {step:.2f}s (шаг), {total:.2f}s (с начала)"
    print(msg, flush=True)
    LOG.info("%s", msg)
    last[0] = now


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--geocode-limit",
        type=int,
        default=0,
        help="лимит новых HTTP к внешним геокодерам на сборку (простой режим и --resolve-coordinates)",
    )
    ap.add_argument("--no-cache-xml", action="store_true", help="перекачать XML (load_all use_cache=False)")
    ap.add_argument(
        "--map-only",
        action="store_true",
        help="только официальные данные и карта: без Random Forest и без citizen_model.joblib",
    )
    ap.add_argument(
        "--infer-county",
        action="store_true",
        help="дозаполнить county через county_infer (кэш + Google→OpenCage; медленнее, точнее карта)",
    )
    ap.add_argument(
        "--resolve-coordinates",
        action="store_true",
        help="Google→Geoapify→OpenCage по вариантам адреса; --geocode-limit = лимит HTTP",
    )
    ap.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="уровень логирования (DEBUG — кэш координат в citizen/geocode_resolve; URL с ключами в лог не выводятся)",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=50,
        metavar="N",
        help="каждые N мест на карте писать строку прогресса в лог (и 1-е и последнее всегда)",
    )
    ap.add_argument(
        "--include-mineraalvesi",
        action="store_true",
        help="добавить в сборку домен mineraalvesi (если доступен у источника данных)",
    )
    args = ap.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    # DEBUG включает urllib3 — в лог попадают полные URL с ?key=… (утечка ключа).
    for _lg_name in ("urllib3", "urllib3.connectionpool", "urllib3.util.retry", "charset_normalizer"):
        logging.getLogger(_lg_name).setLevel(logging.WARNING)
    if args.log_level.upper() == "DEBUG":
        LOG.warning(
            "Уровень DEBUG: логи urllib3 отключены (WARNING), чтобы ключи API не попадали в вывод. "
            "См. geocode_resolve / county_infer для своих DEBUG-сообщений."
        )
    _load_repo_dotenv()
    _prefer_certifi_ca_bundle()

    t_run = time.perf_counter()
    last = [t_run]

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    map_domains = set(BASE_MAP_DOMAINS)
    if args.include_mineraalvesi:
        map_domains.add("mineraalvesi")
    selected_domains = sorted(map_domains)

    LOG.info(
        "Старт: map_only=%s resolve_coordinates=%s infer_county=%s include_mineraalvesi=%s geocode_limit=%s log_level=%s",
        args.map_only,
        args.resolve_coordinates,
        args.infer_county,
        args.include_mineraalvesi,
        args.geocode_limit,
        args.log_level,
    )

    df = load_all(
        domains=selected_domains,
        use_cache=not args.no_cache_xml,
        geocode_county=args.infer_county,
    )
    loaded_domains = set()
    if "domain" in df.columns:
        loaded_domains = set(str(x) for x in df["domain"].dropna().astype(str).unique().tolist())
    domain_source_status = {
        d: {
            "requested": True,
            "loaded": d in loaded_domains,
            "reason": "ok" if d in loaded_domains else "no_rows_or_source_unavailable",
        }
        for d in selected_domains
    }
    if args.include_mineraalvesi and "mineraalvesi" not in loaded_domains:
        LOG.warning(
            "mineraalvesi был запрошен (--include-mineraalvesi), но не загружен: источник не отдаёт данные или вернул 0 строк"
        )
    if args.infer_county:
        LOG.info("load_all: --infer-county — Google→OpenCage для локаций без county в кэше (лимит HTTP снят)")
    _timer_print("1) load_all — загрузка и парсинг XML → DataFrame", t_run, last)
    data_fetched_at = pd.Timestamp.now("UTC").isoformat()

    if args.map_only:
        LOG.info("Режим --map-only: без матрицы X и без обучения моделей (только meta для карты)")
        full = build_citizen_meta_frame(df).reset_index(drop=True)
        _timer_print("2) build_citizen_meta_frame — признаки только для meta (без X)", t_run, last)
    else:
        X, y, meta = build_dataset_with_meta(df)
        _timer_print(
            "2) build_dataset_with_meta — инженерия признаков + X, y, meta (~все строки)",
            t_run,
            last,
        )
        meta = meta.reset_index(drop=True)
        X = X.reset_index(drop=True)
        y = y.reset_index(drop=True)
        full = meta.copy()

        # Импутация + скейлинг (LR и GB требуют, RF и LGBM — нет, но используют одни данные для честного сравнения)
        imputer = SimpleImputer(strategy="median")
        X_imp = imputer.fit_transform(X)
        scaler = RobustScaler()
        X_scaled = scaler.fit_transform(X_imp)
        _timer_print("3) SimpleImputer(median) + RobustScaler fit_transform", t_run, last)

        # Логистическая регрессия
        lr = LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            random_state=42,
        )
        lr.fit(X_scaled, y)
        full["lr_violation_prob"] = lr.predict_proba(X_scaled)[:, 0]
        _timer_print("4a) LogisticRegression.fit", t_run, last)

        # Random Forest (основная, как было раньше — model_violation_prob для совместимости)
        clf = RandomForestClassifier(
            n_estimators=120,
            max_depth=14,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_imp, y)
        full["rf_violation_prob"] = clf.predict_proba(X_imp)[:, 0]
        full["model_violation_prob"] = full["rf_violation_prob"]  # обратная совместимость
        _timer_print("4b) RandomForestClassifier.fit (120 деревьев)", t_run, last)

        # Gradient Boosting
        w_map = {0: len(y) / (2 * (y == 0).sum()), 1: len(y) / (2 * (y == 1).sum())}
        sw = np.array([w_map[c] for c in y])
        gb = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
        )
        gb.fit(X_scaled, y, sample_weight=sw)
        full["gb_violation_prob"] = gb.predict_proba(X_scaled)[:, 0]
        _timer_print("4c) GradientBoostingClassifier.fit (200 деревьев)", t_run, last)

        # LightGBM (опционально — если не установлен, пропускаем без ошибки)
        lgbm_clf = None
        try:
            import lightgbm as lgb  # noqa: PLC0415
            lgbm_clf = lgb.LGBMClassifier(
                n_estimators=300,
                learning_rate=0.05,
                max_depth=6,
                num_leaves=63,
                min_child_samples=20,
                subsample=0.8,
                colsample_bytree=0.8,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )
            lgbm_clf.fit(X_imp, y)  # LGBM нативно обрабатывает NaN до импутации, но для единообразия используем X_imp
            full["lgbm_violation_prob"] = lgbm_clf.predict_proba(X_imp)[:, 0]
            _timer_print("4d) LGBMClassifier.fit (300 деревьев)", t_run, last)
        except ImportError:
            print("[citizen] lightgbm не установлен — lgbm_violation_prob не будет в снимке")

        _timer_print("5) predict_proba всех моделей → violation_prob в full DataFrame", t_run, last)
    model_trained_at = pd.Timestamp.now("UTC").isoformat() if not args.map_only else None
    full["sample_date"] = pd.to_datetime(full["sample_date"], errors="coerce")
    full = full.sort_values("sample_date")

    # Нормализованный ключ места: убираем суффиксы, которые Terviseamet менял между годами
    # (supluskoht → rand, veevärk → ühisveevärk, пробелы, регистр).
    # Дедупликация идёт по нормализованному ключу, но в снимок записывается
    # актуальное (последнее) название.
    full["_loc_key"] = full.apply(
        lambda r: _normalize_location_key(str(r.get("location", "") or ""), str(r.get("domain", "") or "")),
        axis=1,
    )
    latest_idx = full.groupby(["domain", "_loc_key"], sort=False).tail(1).index
    latest = full.loc[latest_idx].copy()
    latest = latest[latest["domain"].isin(map_domains)]
    n_dedup = len(full[full["domain"].isin(map_domains)].groupby(["domain", "location"])) - len(latest)
    if n_dedup > 0:
        LOG.info("Дедупликация по нормализованному имени: объединено %s дублей (переименования в XML)", n_dedup)
    _timer_print(
        "6) dedupe: последняя проба на (domain, norm_location_key) + фильтр map_domains",
        t_run,
        last,
    )

    cache = load_geocode_cache()
    coord_overrides = load_coordinate_overrides()
    resolve_cache = (
        _geocode_resolve.load_resolve_cache(COORD_RESOLVE_PATH) if args.resolve_coordinates else {}
    )
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "water-quality-ee-citizen-snapshot/1.0 (TalTech water-quality course)",
            "Accept": "application/json",
        }
    )
    paged_addr_index = build_paged_address_index(session, use_cache=not args.no_cache_xml)
    LOG.info("Индекс адресов paged U/JV: %s записей", len(paged_addr_index))
    geoapify_key = ((os.environ.get("GEOAPIFY_API_KEY") or "").strip() or None)
    google_key = ((os.environ.get("GOOGLE_MAPS_GEOCODING_API_KEY") or "").strip() or None)
    opencage_key = ((os.environ.get("OPENCAGE_API_KEY") or "").strip() or None)
    budget_remain = [max(0, int(args.geocode_limit))]
    api_calls = 0
    rows_out = []
    hidden_rows = 0
    overridden_rows = 0
    n_map = len(latest)
    LOG.info(
        "Координаты: мест на карте после дедупа=%s; resolve=%s; HTTP-бюджет=%s; Geoapify=%s; OpenCage=%s; Google=%s",
        n_map,
        args.resolve_coordinates,
        args.geocode_limit,
        "да" if geoapify_key else "нет",
        "да" if opencage_key else "нет",
        "да" if google_key else "нет",
    )
    progress_every = max(1, int(args.progress_every))

    for idx, (_, row) in enumerate(latest.iterrows(), start=1):
        loc_name = row["location"] or ""
        if isinstance(loc_name, float) and pd.isna(loc_name):
            loc_name = ""
        loc_name = str(loc_name).strip()
        domain = row["domain"]
        county = row["county"] if "county" in row.index else None
        if county is not None and isinstance(county, float) and pd.isna(county):
            county = None
        site = row["geocode_site"] if "geocode_site" in row.index else ""
        fac = row["geocode_facility"] if "geocode_facility" in row.index else ""
        if isinstance(site, float) and pd.isna(site):
            site = ""
        if isinstance(fac, float) and pd.isna(fac):
            fac = ""
        site, fac = str(site).strip(), str(fac).strip()

        lat = lon = None
        coord_source = "none"
        geocode_matched: str | None = None

        ola = row.get("official_lat") if "official_lat" in row.index else None
        olo = row.get("official_lon") if "official_lon" in row.index else None
        if ola is not None and olo is not None:
            try:
                f_lat, f_lon = float(ola), float(olo)
                if np.isfinite(f_lat) and np.isfinite(f_lon):
                    lat, lon = f_lat, f_lon
                    cs = row.get("official_coord_source") if "official_coord_source" in row.index else None
                    if cs is not None and pd.notna(cs):
                        coord_source = str(cs)
                    else:
                        coord_source = "terviseamet_official"
            except (TypeError, ValueError):
                pass

        if lat is None and args.resolve_coordinates:
            strict_paged_only = domain in STRICT_PAGED_ADDRESS_ONLY_DOMAINS
            paged_addr = paged_addr_index.get(_normalize_location_key(loc_name, domain))
            if paged_addr:
                got = _geocode_resolve.resolve_coordinates_cascade(
                    [f"{paged_addr}, Eesti", f"{loc_name}, {paged_addr}, Eesti"],
                    resolve_cache=resolve_cache,
                    session=session,
                    geoapify_api_key=geoapify_key,
                    google_api_key=google_key,
                    opencage_api_key=opencage_key,
                    budget_remaining=budget_remain,
                    log=LOG,
                )
                if got:
                    coord_source, lat, lon, geocode_matched = got
                    coord_source = f"{coord_source}_paged_address"

            if lat is None and not strict_paged_only:
                queries = _geocode_resolve.build_geocode_queries(
                    str(domain), loc_name, site, fac, str(county) if county else None
                )
                got = _geocode_resolve.resolve_coordinates_cascade(
                    queries,
                    resolve_cache=resolve_cache,
                    session=session,
                    geoapify_api_key=geoapify_key,
                    google_api_key=google_key,
                    opencage_api_key=opencage_key,
                    budget_remaining=budget_remain,
                    log=LOG,
                )
                if got:
                    coord_source, lat, lon, geocode_matched = got
        elif lat is None:
            strict_paged_only = domain in STRICT_PAGED_ADDRESS_ONLY_DOMAINS
            paged_addr = paged_addr_index.get(_normalize_location_key(loc_name, domain))
            if paged_addr:
                q_addr = f"{paged_addr}, Eesti"
                rem_addr = max(0, int(args.geocode_limit) - api_calls)
                _, _, src_addr, nu_addr = geocode_address_simple(
                    q_addr,
                    cache,
                    session,
                    geoapify_key=geoapify_key,
                    opencage_key=opencage_key,
                    google_key=google_key,
                    http_budget=rem_addr,
                )
                api_calls += nu_addr
                c_addr = cache.get(q_addr, {})
                if c_addr.get("lat") is not None:
                    lat, lon = float(c_addr["lat"]), float(c_addr["lon"])
                    coord_source = (
                        f"{src_addr}_paged_address"
                        if src_addr
                        else "geocode_cache_paged_address"
                    )

            if lat is None and not strict_paged_only:
                query = f"{loc_name}, Estonia"
                needs_geo = query not in cache or cache[query].get("lat") is None
                rem = max(0, int(args.geocode_limit) - api_calls)
                if needs_geo and rem > 0:
                    LOG.info(
                        "coords simple-mode Geocoding %s/%s для места %s/%s",
                        api_calls + 1,
                        args.geocode_limit,
                        idx,
                        n_map,
                    )
                    _, _, _, nu = geocode_address_simple(
                        query,
                        cache,
                        session,
                        geoapify_key=geoapify_key,
                        opencage_key=opencage_key,
                        google_key=google_key,
                        http_budget=rem,
                    )
                    api_calls += nu

                c = cache.get(query, {})
                if c.get("lat") is not None:
                    lat, lon = float(c["lat"]), float(c["lon"])
                    coord_source = str(c.get("coord_source") or "geocode_cache")

        if lat is None and county:
            cll = county_to_latlon(str(county))
            if cll:
                lat, lon = cll
                coord_source = "county_centroid"

        if lat is None:
            lat, lon = approximate_point_estonia(domain, loc_name)
            coord_source = "approximate_ee"

        # Ручные оверрайды (приоритетнее автологики): set_manual | hide
        ov_key = _normalize_location_key(loc_name, domain)
        ov = coord_overrides.get(ov_key)
        if isinstance(ov, dict):
            action = str(ov.get("action") or "").strip().lower()
            if action == "hide":
                hidden_rows += 1
                continue
            if action == "set_manual":
                try:
                    ov_lat = float(ov.get("lat"))
                    ov_lon = float(ov.get("lon"))
                    if np.isfinite(ov_lat) and np.isfinite(ov_lon):
                        lat, lon = ov_lat, ov_lon
                        coord_source = "manual_override"
                        overridden_rows += 1
                except (TypeError, ValueError):
                    LOG.warning(
                        "Некорректный manual override для %s/%s: %s",
                        domain,
                        loc_name,
                        ov,
                    )

        county_out = str(county).strip() if county else None
        if not county_out:
            county_from_match = _extract_county_from_address(geocode_matched)
            if county_from_match:
                county_out = county_from_match
        if not county_out:
            county_from_coords = _nearest_county_from_coords(lat, lon)
            if county_from_coords:
                county_out = county_from_coords

        kind = PLACE_KIND.get(domain, "other")
        sid = None
        if "sample_id" in row.index and pd.notna(row.get("sample_id")):
            sid = str(row["sample_id"]).strip() or None
        row_out = {
            "location": loc_name,
            "domain": domain,
            "place_kind": kind,
            "county": county_out,
            "sample_date": row["sample_date"].isoformat()
            if pd.notna(row["sample_date"])
            else None,
            "official_compliant": int(row["compliant"]),
            "measurements": row_measurements(row),
            "lat": lat,
            "lon": lon,
            "coord_source": coord_source,
        }
        if geocode_matched:
            row_out["geocode_matched_address"] = geocode_matched
        # Основная прогноз (RF, обратная совместимость)
        if "model_violation_prob" in row.index and pd.notna(row.get("model_violation_prob")):
            row_out["model_violation_prob"] = float(row["model_violation_prob"])
        # Прогнозы по всем 4 моделям
        for prob_col in ("lr_violation_prob", "rf_violation_prob", "gb_violation_prob", "lgbm_violation_prob"):
            if prob_col in row.index and pd.notna(row.get(prob_col)):
                row_out[prob_col] = float(row[prob_col])
        if sid:
            row_out["sample_id"] = sid
        rows_out.append(row_out)
        if idx == 1 or idx % progress_every == 0 or idx == n_map:
            LOG.info(
                "Прогресс карты: место %s/%s; HTTP-бюджет осталось=%s; последний coord_source=%s domain=%s",
                idx,
                n_map,
                budget_remain[0] if args.resolve_coordinates else "—",
                coord_source,
                domain,
            )

    _timer_print(
        f"7) цикл координат по {len(latest)} точкам "
        f"({'resolve: Google→Geoapify→OpenCage' if args.resolve_coordinates else 'Google→Geoapify→OpenCage (simple)'}; "
        f"HTTP остаток лимита: {budget_remain[0] if args.resolve_coordinates else '—'})",
        t_run,
        last,
    )

    if args.resolve_coordinates:
        _geocode_resolve.save_resolve_cache(COORD_RESOLVE_PATH, resolve_cache)
        save_geocode_cache(cache)
        used = max(0, args.geocode_limit - budget_remain[0])
        LOG.info(
            "Сохранены кэши координат: resolve=%s geocode=%s (HTTP каскада: %s из %s)",
            COORD_RESOLVE_PATH,
            GEOCODE_PATH,
            used,
            args.geocode_limit,
        )
    elif api_calls > 0:
        save_geocode_cache(cache)
        LOG.info("Сохранён geocode_cache: %s (HTTP: %s)", GEOCODE_PATH, api_calls)

    if not args.map_only:
        bundle = {
            "imputer": imputer,
            "scaler": scaler,
            "clf_lr": lr,
            "clf_rf": clf,
            "clf_gb": gb,
            "clf_lgbm": lgbm_clf,  # None если lightgbm не установлен
            # обратная совместимость: clf = RF
            "clf": clf,
            "feature_columns": list(X.columns),
            "models": ["lr", "rf", "gb"] + (["lgbm"] if lgbm_clf is not None else []),
        }
        joblib.dump(bundle, ARTIFACTS / "citizen_model.joblib")
        LOG.info("Модели записаны: %s (%s)", ARTIFACTS / "citizen_model.joblib", bundle["models"])
        _timer_print("8) joblib.dump(imputer + scaler + 4 clf) → citizen_model.joblib", t_run, last)
    else:
        LOG.info(
            "Режим --map-only: citizen_model.joblib не перезаписан (при необходимости полной модели запустите без --map-only)"
        )

    base_disclaimer = (
        "Официальный статус — по полю vastavus в данных Terviseamet. "
        "Координаты: при наличии — из справочников opendata Terviseamet (EPSG:3301→WGS84), см. coord_source terviseamet_*; "
        "иначе при --resolve-coordinates или простом режиме с лимитом — Google→Geoapify→OpenCage. "
        "coord_source=opencage|geocode_cache (в старых снимках возможны google) — привязка к найденному адресу (см. geocode_matched_address в точке); "
        "county_centroid — центроид уезда; approximate_ee — только визуальный разброс по bbox Эстонии, не место объекта."
    )
    model_note = (
        " Прогнозы моделей (lr/rf/gb/lgbm_violation_prob) — оценки отдельных ML-моделей"
        " (Logistic Regression, Random Forest, Gradient Boosting, LightGBM),"
        " не замена официальной оценке Terviseamet."
        if not args.map_only
        else " Прогноз моделей в этом снимке не включён; пересоберите без --map-only для слоя модели на карте."
    )

    available_models: list[str] = []
    if not args.map_only:
        available_models = ["lr", "rf", "gb"]
        if lgbm_clf is not None:
            available_models.append("lgbm")

    snapshot = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "data_fetched_at": data_fetched_at,
        "model_trained_at": model_trained_at,
        "has_model_predictions": not args.map_only,
        "available_models": available_models,
        "model_labels": {
            "lr": "Logistic Regression",
            "rf": "Random Forest",
            "gb": "Gradient Boosting",
            "lgbm": "LightGBM",
        },
        "data_catalog_url": OPENDATA_CATALOG_URL,
        "map_domains": selected_domains,
        "source_domain_status": domain_source_status,
        "mineraalvesi_status": {
            "requested": bool(args.include_mineraalvesi),
            "loaded": "mineraalvesi" in loaded_domains,
            "reason": (
                "ok"
                if "mineraalvesi" in loaded_domains
                else ("not_requested" if not args.include_mineraalvesi else "no_rows_or_source_unavailable")
            ),
        },
        "place_kinds": {
            "swimming": "Открытая вода (купальные места)",
            "pool_spa": "Бассейн / СПА / ujula",
            "drinking_water": "Питьевая вода (водопровод, точка сети)",
            "drinking_source": "Питьевая вода (источник / родник, joogiveeallikas)",
            "other": "Прочее",
        },
        "disclaimer": base_disclaimer + model_note,
        "coordinate_override_stats": {
            "overrides_loaded": len(coord_overrides),
            "manual_applied": overridden_rows,
            "hidden_applied": hidden_rows,
        },
        "places": rows_out,
    }
    with open(ARTIFACTS / "snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    _timer_print("9) запись snapshot.json", t_run, last)

    n_pts = len(rows_out)
    by_src: dict[str, int] = {}
    for r in rows_out:
        s = str(r.get("coord_source") or "none")
        by_src[s] = by_src.get(s, 0) + 1
    LOG.info("Итог snapshot: мест=%s; coord_source=%s", n_pts, by_src)
    print(f"[citizen] snapshot: {len(rows_out)} мест, с координатами: {n_pts}")
    print(f"[citizen] записано: {ARTIFACTS / 'snapshot.json'}")
    total_wall = time.perf_counter() - t_run
    print(f"[citizen/timer] ИТОГО wall time: {total_wall:.2f}s", flush=True)
    LOG.info("ИТОГО wall time: %.2fs", total_wall)


if __name__ == "__main__":
    main()
