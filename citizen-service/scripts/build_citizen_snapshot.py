#!/usr/bin/env python3
"""
Собрать snapshot для гражданского приложения: последняя проба по (domain, location),
официальный compliant, вероятности нарушения по 4 моделям (LR, RF, GradBoost, LightGBM), координаты.

Координаты в XML Terviseamet нет. Режим --resolve-coordinates: каскад In-ADS (Maa-amet) →
Google (переменная GOOGLE_MAPS_GEOCODING_API_KEY) → Nominatim; кэш coordinate_resolve_cache.json.
--geocode-limit — лимит HTTP-запросов на всю сборку (разделён между сервисами).

Запуск из корня репозитория:
  python citizen-service/scripts/build_citizen_snapshot.py
  python citizen-service/scripts/build_citizen_snapshot.py --resolve-coordinates --geocode-limit 8000 --infer-county
  python citizen-service/scripts/build_citizen_snapshot.py --geocode-limit 300   # только старый Nominatim
  python citizen-service/scripts/build_citizen_snapshot.py --map-only
  python citizen-service/scripts/build_citizen_snapshot.py --infer-county

Требует: скачанные XML (python src/data_loader.py) и зависимости из requirements.txt.
Для полного снимка также нужен joblib (модели пишутся в artifacts/citizen_model.joblib).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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
from sklearn.preprocessing import StandardScaler

# корень репозитория: .../water-quality-ee
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_loader import load_all  # noqa: E402
from features import (  # noqa: E402
    META_EXTRA_NUMERIC,
    build_citizen_meta_frame,
    build_dataset_with_meta,
)

_cc = importlib.util.spec_from_file_location(
    "county_centroids", ROOT / "citizen-service" / "county_centroids.py"
)
_county_mod = importlib.util.module_from_spec(_cc)
assert _cc.loader is not None
_cc.loader.exec_module(_county_mod)
county_to_latlon = _county_mod.county_to_latlon

_gr = importlib.util.spec_from_file_location(
    "geocode_resolve", ROOT / "citizen-service" / "geocode_resolve.py"
)
_geocode_resolve = importlib.util.module_from_spec(_gr)
assert _gr.loader is not None
_gr.loader.exec_module(_geocode_resolve)

ARTIFACTS = ROOT / "citizen-service" / "artifacts"
GEOCODE_PATH = ROOT / "citizen-service" / "data" / "geocode_cache.json"
COORD_RESOLVE_PATH = ROOT / "citizen-service" / "data" / "coordinate_resolve_cache.json"
# Точки на карте: купание, бассейны/СПА, водопровод (питьевая вода по точкам сети)
MAP_DOMAINS = {"supluskoha", "basseinid", "veevark", "joogivesi"}
OPENDATA_CATALOG_URL = "https://vtiav.sm.ee/index.php/opendata/"

PLACE_KIND = {
    "supluskoha": "swimming",
    "basseinid": "pool_spa",
    "veevark": "drinking_water",
    "joogivesi": "drinking_source",
}
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


def geocode_nominatim(query: str, cache: dict) -> tuple[float, float] | None:
    if query in cache:
        c = cache[query]
        return float(c["lat"]), float(c["lon"])
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter

        nom = Nominatim(user_agent="water-quality-ee-citizen-snapshot")
        geocode = RateLimiter(nom.geocode, min_delay_seconds=1.1)
        loc = geocode(query)
        if loc is None:
            cache[query] = {"lat": None, "lon": None}
            return None
        cache[query] = {"lat": loc.latitude, "lon": loc.longitude}
        return loc.latitude, loc.longitude
    except Exception as e:
        print(f"[geocode] пропуск '{query[:50]}...': {e}")
        return None


def _nominatim_pair(query: str, nom_cache: dict) -> tuple[float, float] | None:
    geocode_nominatim(query, nom_cache)
    c = nom_cache.get(query, {})
    if c.get("lat") is None:
        return None
    return float(c["lat"]), float(c["lon"])


def _timer_print(label: str, t_run_start: float, last: list[float]) -> None:
    now = time.perf_counter()
    step = now - last[0]
    total = now - t_run_start
    print(
        f"[citizen/timer] {label}: {step:.2f}s (шаг), {total:.2f}s (с начала)",
        flush=True,
    )
    last[0] = now


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geocode-limit", type=int, default=0, help="сколько новых точек геокодировать через Nominatim")
    ap.add_argument("--no-cache-xml", action="store_true", help="перекачать XML (load_all use_cache=False)")
    ap.add_argument(
        "--map-only",
        action="store_true",
        help="только официальные данные и карта: без Random Forest и без citizen_model.joblib",
    )
    ap.add_argument(
        "--infer-county",
        action="store_true",
        help="дозаполнить county через county_infer (кэш + при необходимости Nominatim; медленнее, точнее карта)",
    )
    ap.add_argument(
        "--resolve-coordinates",
        action="store_true",
        help="In-ADS → Google → Nominatim по вариантам адреса; --geocode-limit = лимит HTTP на всю сборку",
    )
    args = ap.parse_args()

    t_run = time.perf_counter()
    last = [t_run]

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    df = load_all(
        use_cache=not args.no_cache_xml,
        geocode_county=args.infer_county,
    )
    if args.infer_county:
        print("[citizen] load_all с --infer-county: попытка восстановить maakond для карты")
    _timer_print("1) load_all — загрузка и парсинг XML → DataFrame", t_run, last)

    if args.map_only:
        print("[citizen] режим --map-only: без матрицы X и без моделей (только meta для карты)")
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
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_imp)
        _timer_print("3) SimpleImputer(median) + StandardScaler fit_transform", t_run, last)

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
    latest_idx = full.groupby(["domain", "location"], sort=False).tail(1).index
    latest = full.loc[latest_idx].copy()
    latest = latest[latest["domain"].isin(MAP_DOMAINS)]
    _timer_print(
        "6) dedupe: последняя проба на (domain, location) + фильтр map_domains",
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
    google_key = os.environ.get("GOOGLE_MAPS_GEOCODING_API_KEY")
    budget_remain = [max(0, int(args.geocode_limit))]
    api_calls = 0
    rows_out = []

    for _, row in latest.iterrows():
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

        if args.resolve_coordinates:
            queries = _geocode_resolve.build_geocode_queries(
                str(domain), loc_name, site, fac, str(county) if county else None
            )
            got = _geocode_resolve.resolve_coordinates_cascade(
                queries,
                resolve_cache=resolve_cache,
                nominatim_cache=cache,
                session=session,
                google_api_key=google_key,
                nominatim_fn=_nominatim_pair,
                budget_remaining=budget_remain,
            )
            if got:
                coord_source, lat, lon, geocode_matched = got
        else:
            query = f"{loc_name}, Estonia"
            needs_geo = query not in cache or cache[query].get("lat") is None
            if needs_geo and api_calls < args.geocode_limit:
                geocode_nominatim(query, cache)
                api_calls += 1
                time.sleep(0.05)

            c = cache.get(query, {})
            if c.get("lat") is not None:
                lat, lon = float(c["lat"]), float(c["lon"])
                coord_source = "nominatim"

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

    _timer_print(
        f"7) цикл координат по {len(latest)} точкам "
        f"({'resolve: In-ADS/Google/Nominatim' if args.resolve_coordinates else 'Nominatim'}; "
        f"HTTP остаток лимита: {budget_remain[0] if args.resolve_coordinates else '—'})",
        t_run,
        last,
    )

    if args.resolve_coordinates:
        _geocode_resolve.save_resolve_cache(COORD_RESOLVE_PATH, resolve_cache)
        save_geocode_cache(cache)
        print(
            f"[citizen] resolve-кэш: {COORD_RESOLVE_PATH}; Nominatim-кэш обновлён: {GEOCODE_PATH} "
            f"(HTTP по каскаду использовано: {max(0, args.geocode_limit - budget_remain[0])} из {args.geocode_limit})"
        )
    elif api_calls > 0:
        save_geocode_cache(cache)
        print(f"[citizen] Nominatim вызовов: {api_calls}, кэш: {GEOCODE_PATH}")

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
        print(f"[citizen] модели ({bundle['models']}): {ARTIFACTS / 'citizen_model.joblib'}")
        _timer_print("8) joblib.dump(imputer + scaler + 4 clf) → citizen_model.joblib", t_run, last)
    else:
        print("[citizen] режим --map-only: citizen_model.joblib не перезаписывался (старый файл может остаться с прошлого полного прогона)")

    base_disclaimer = (
        "Официальный статус — по полю vastavus в данных Terviseamet. "
        "Координаты в XML нет; при --resolve-coordinates используются In-ADS (Maa-amet) и при наличии ключа Google Geocoding, "
        "затем Nominatim. coord_source=inads|google|nominatim — привязка к найденному адресу (см. geocode_matched_address в точке); "
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
    print(f"[citizen] snapshot: {len(rows_out)} мест, с координатами: {n_pts}")
    print(f"[citizen] записано: {ARTIFACTS / 'snapshot.json'}")
    print(
        f"[citizen/timer] ИТОГО wall time: {time.perf_counter() - t_run:.2f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
