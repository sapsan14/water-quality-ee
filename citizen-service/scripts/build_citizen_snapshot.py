#!/usr/bin/env python3
"""
Собрать snapshot для гражданского приложения: последняя проба по (domain, location),
официальный compliant, вероятность нарушения по RF, координаты (кэш Nominatim + центроид уезда).

Запуск из корня репозитория:
  python citizen-service/scripts/build_citizen_snapshot.py
  python citizen-service/scripts/build_citizen_snapshot.py --geocode-limit 300

Требует: скачанные XML (python src/data_loader.py) и зависимости из requirements.txt + joblib.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer

# корень репозитория: .../water-quality-ee
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_loader import load_all  # noqa: E402
from features import META_EXTRA_NUMERIC, build_dataset_with_meta  # noqa: E402

import importlib.util

_cc = importlib.util.spec_from_file_location(
    "county_centroids", ROOT / "citizen-service" / "county_centroids.py"
)
_county_mod = importlib.util.module_from_spec(_cc)
assert _cc.loader is not None
_cc.loader.exec_module(_county_mod)
county_to_latlon = _county_mod.county_to_latlon

ARTIFACTS = ROOT / "citizen-service" / "artifacts"
GEOCODE_PATH = ROOT / "citizen-service" / "data" / "geocode_cache.json"
# Точки на карте: купание, бассейны/СПА, водопровод (питьевая вода по точкам сети)
MAP_DOMAINS = {"supluskoha", "basseinid", "veevark", "joogivesi"}

PLACE_KIND = {
    "supluskoha": "swimming",
    "basseinid": "pool_spa",
    "veevark": "drinking_water",
    "joogivesi": "drinking_source",
}
# Если нет ни Nominatim, ни maakond — показать точку в Эстонии с разбросом (только для обзора на карте).
EE_CENTER = (58.65, 25.5)


def hash_jitter(seed: tuple, scale: float = 0.35) -> tuple[float, float]:
    h = hash(seed) % (2**32)
    dx = ((h & 0xFFFF) / 0xFFFF - 0.5) * scale
    dy = (((h >> 16) & 0xFFFF) / 0xFFFF - 0.5) * scale
    return dx, dy


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geocode-limit", type=int, default=0, help="сколько новых точек геокодировать через Nominatim")
    ap.add_argument("--no-cache-xml", action="store_true", help="перекачать XML (load_all use_cache=False)")
    args = ap.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    df = load_all(use_cache=not args.no_cache_xml, geocode_county=False)
    X, y, meta = build_dataset_with_meta(df)
    meta = meta.reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = y.reset_index(drop=True)

    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X)
    clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=14,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_imp, y)
    proba_violation = clf.predict_proba(X_imp)[:, 0]

    full = meta.copy()
    full["model_violation_prob"] = proba_violation
    full["sample_date"] = pd.to_datetime(full["sample_date"], errors="coerce")
    full = full.sort_values("sample_date")
    latest_idx = full.groupby(["domain", "location"], sort=False).tail(1).index
    latest = full.loc[latest_idx].copy()
    latest = latest[latest["domain"].isin(MAP_DOMAINS)]

    cache = load_geocode_cache()
    api_calls = 0
    rows_out = []

    for _, row in latest.iterrows():
        loc_name = row["location"] or ""
        domain = row["domain"]
        county = row["county"] if "county" in row.index else None
        lat = lon = None
        coord_source = "none"

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

        # небольшой jitter по уезду, чтобы маркеры не слипались в одной точке
        if coord_source == "county_centroid" and lat is not None:
            h = hash((domain, loc_name)) % 1000
            lat += (h % 17 - 8) * 0.02
            lon += (h // 17 % 17 - 8) * 0.02

        if lat is None:
            jx, jy = hash_jitter((domain, loc_name))
            lat = EE_CENTER[0] + jx
            lon = EE_CENTER[1] + jy
            coord_source = "approximate_ee"

        kind = PLACE_KIND.get(domain, "other")
        rows_out.append(
            {
                "location": loc_name,
                "domain": domain,
                "place_kind": kind,
                "county": county,
                "sample_date": row["sample_date"].isoformat()
                if pd.notna(row["sample_date"])
                else None,
                "official_compliant": int(row["compliant"]),
                "model_violation_prob": float(row["model_violation_prob"]),
                "measurements": row_measurements(row),
                "lat": lat,
                "lon": lon,
                "coord_source": coord_source,
            }
        )

    if api_calls > 0:
        save_geocode_cache(cache)
        print(f"[citizen] Nominatim вызовов: {api_calls}, кэш: {GEOCODE_PATH}")

    bundle = {"imputer": imputer, "clf": clf, "feature_columns": list(X.columns)}
    joblib.dump(bundle, ARTIFACTS / "citizen_model.joblib")

    snapshot = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "map_domains": sorted(MAP_DOMAINS),
        "place_kinds": {
            "swimming": "Открытая вода (купальные места)",
            "pool_spa": "Бассейн / СПА / ujula",
            "drinking_water": "Питьевая вода (водопровод, точка сети)",
            "drinking_source": "Питьевая вода (источник / родник, joogiveeallikas)",
            "other": "Прочее",
        },
        "disclaimer": (
            "Официальный статус — по полю vastavus в данных Terviseamet. "
            "model_violation_prob — оценка отдельной модели (Random Forest), не замена официальной оценки. "
            "Координаты водопроводных точек часто приблизительные (геокод названия или центроид уезда)."
        ),
        "places": rows_out,
    }
    with open(ARTIFACTS / "snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    n_pts = len(rows_out)
    print(f"[citizen] snapshot: {len(rows_out)} мест, с координатами: {n_pts}")
    print(f"[citizen] записано: {ARTIFACTS / 'snapshot.json'}")


if __name__ == "__main__":
    main()
