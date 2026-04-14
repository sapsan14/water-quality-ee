#!/usr/bin/env python3
"""
Собрать snapshot для гражданского приложения: последняя проба по (domain, location),
официальный compliant, вероятности нарушения по 4 моделям (LR, RF, GradBoost, LightGBM), координаты.

Координаты в файлах *_veeproovid_YYYY.xml нет; при load_all/load_domain подтягиваются
официальные L-EST97→WGS84 из справочников opendata (supluskohad.xml и др.) → official_lat/lon.
Если их нет — простой режим или --resolve-coordinates: OpenCage (OPENCAGE_API_KEY);
кэш coordinate_resolve_cache.json. Google / In-ADS / Nominatim не используются.
--geocode-limit — лимит HTTP-запросов на всю сборку.

Запуск из корня репозитория:
  python citizen-service/scripts/build_citizen_snapshot.py
  python citizen-service/scripts/build_citizen_snapshot.py --resolve-coordinates --geocode-limit 8000 --infer-county
  python citizen-service/scripts/build_citizen_snapshot.py --geocode-limit 300   # простой режим: OpenCage
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
import sys
import time
from pathlib import Path

import requests

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

from county_centroids import county_to_latlon  # noqa: E402
import geocode_resolve as _geocode_resolve  # noqa: E402

ARTIFACTS = ROOT / "citizen-service" / "artifacts"
GEOCODE_PATH = ROOT / "citizen-service" / "data" / "geocode_cache.json"
COORD_RESOLVE_PATH = ROOT / "citizen-service" / "data" / "coordinate_resolve_cache.json"

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
# Точки на карте: купание, бассейны/СПА, водопровод (питьевая вода по точкам сети)
MAP_DOMAINS = {"supluskoha", "basseinid", "veevark", "joogivesi"}
OPENDATA_CATALOG_URL = "https://vtiav.sm.ee/index.php/opendata/"

PLACE_KIND = {
    "supluskoha": "swimming",
    "basseinid": "pool_spa",
    "veevark": "drinking_water",
    "joogivesi": "drinking_source",
}


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
    opencage_key: str | None,
    http_budget: int,
) -> tuple[float | None, float | None, str | None, int]:
    """
    Простой режим (без --resolve-coordinates): кэш geocode_cache.json, иначе OpenCage.
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
    if not opencage_key:
        LOG.warning("coords simple: нет OPENCAGE_API_KEY — пропуск query=%s", clip)
        cache[query] = {"lat": None, "lon": None, "miss": True}
        return None, None, None, 0

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
    LOG.info("coords miss simple (opencage) query=%s", clip)
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
        help="лимит новых HTTP к OpenCage на сборку (простой режим и --resolve-coordinates)",
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
        help="дозаполнить county через county_infer (кэш + OpenCage; медленнее, точнее карта)",
    )
    ap.add_argument(
        "--resolve-coordinates",
        action="store_true",
        help="OpenCage по вариантам адреса (нужен OPENCAGE_API_KEY); --geocode-limit = лимит HTTP",
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

    LOG.info(
        "Старт: map_only=%s resolve_coordinates=%s infer_county=%s geocode_limit=%s log_level=%s",
        args.map_only,
        args.resolve_coordinates,
        args.infer_county,
        args.geocode_limit,
        args.log_level,
    )

    df = load_all(
        use_cache=not args.no_cache_xml,
        geocode_county=args.infer_county,
    )
    if args.infer_county:
        LOG.info("load_all: --infer-county — OpenCage для всех локаций без county в кэше (лимит HTTP снят)")
    _timer_print("1) load_all — загрузка и парсинг XML → DataFrame", t_run, last)

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
    latest = latest[latest["domain"].isin(MAP_DOMAINS)]
    n_dedup = len(full[full["domain"].isin(MAP_DOMAINS)].groupby(["domain", "location"])) - len(latest)
    if n_dedup > 0:
        LOG.info("Дедупликация по нормализованному имени: объединено %s дублей (переименования в XML)", n_dedup)
    _timer_print(
        "6) dedupe: последняя проба на (domain, norm_location_key) + фильтр map_domains",
        t_run,
        last,
    )

    cache = load_geocode_cache()
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
    opencage_key = ((os.environ.get("OPENCAGE_API_KEY") or "").strip() or None)
    budget_remain = [max(0, int(args.geocode_limit))]
    api_calls = 0
    rows_out = []
    n_map = len(latest)
    LOG.info(
        "Координаты: мест на карте после дедупа=%s; resolve=%s; HTTP-бюджет=%s; OpenCage=%s",
        n_map,
        args.resolve_coordinates,
        args.geocode_limit,
        "да" if opencage_key else "нет",
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
            queries = _geocode_resolve.build_geocode_queries(
                str(domain), loc_name, site, fac, str(county) if county else None
            )
            got = _geocode_resolve.resolve_coordinates_cascade(
                queries,
                resolve_cache=resolve_cache,
                session=session,
                opencage_api_key=opencage_key,
                budget_remaining=budget_remain,
                log=LOG,
            )
            if got:
                coord_source, lat, lon, geocode_matched = got
        elif lat is None:
            query = f"{loc_name}, Estonia"
            needs_geo = query not in cache or cache[query].get("lat") is None
            rem = max(0, int(args.geocode_limit) - api_calls)
            if needs_geo and rem > 0:
                LOG.info(
                    "coords simple-mode OpenCage %s/%s для места %s/%s",
                    api_calls + 1,
                    args.geocode_limit,
                    idx,
                    n_map,
                )
                _, _, _, nu = geocode_address_simple(
                    query,
                    cache,
                    session,
                    opencage_key=opencage_key,
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

        kind = PLACE_KIND.get(domain, "other")
        sid = None
        if "sample_id" in row.index and pd.notna(row.get("sample_id")):
            sid = str(row["sample_id"]).strip() or None
        row_out = {
            "location": loc_name,
            "domain": domain,
            "place_kind": kind,
            "county": county,
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
        f"({'resolve: OpenCage' if args.resolve_coordinates else 'OpenCage (simple)'}; "
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
        "иначе при --resolve-coordinates или простом режиме с лимитом — OpenCage (OPENCAGE_API_KEY). "
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
        "has_model_predictions": not args.map_only,
        "available_models": available_models,
        "model_labels": {
            "lr": "Logistic Regression",
            "rf": "Random Forest",
            "gb": "Gradient Boosting",
            "lgbm": "LightGBM",
        },
        "data_catalog_url": OPENDATA_CATALOG_URL,
        "map_domains": sorted(MAP_DOMAINS),
        "place_kinds": {
            "swimming": "Открытая вода (купальные места)",
            "pool_spa": "Бассейн / СПА / ujula",
            "drinking_water": "Питьевая вода (водопровод, точка сети)",
            "drinking_source": "Питьевая вода (источник / родник, joogiveeallikas)",
            "other": "Прочее",
        },
        "disclaimer": base_disclaimer + model_note,
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
