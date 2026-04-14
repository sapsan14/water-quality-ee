"""
features.py — Инженерия признаков для модели качества воды

Входные данные: сырой DataFrame из data_loader.py
Выходные данные: X (признаки), y (целевая переменная)
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, RobustScaler
from sklearn.impute import SimpleImputer
from typing import Tuple, List, Optional, Dict

COUNTY_UNKNOWN = "unknown"


# ── Временные признаки ────────────────────────────────────────────────────────

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Добавить признаки из даты: месяц, сезон, год."""
    df = df.copy()

    if "sample_date" not in df.columns:
        return df

    df["month"] = df["sample_date"].dt.month
    df["year"]  = df["sample_date"].dt.year

    # Сезон (важен для открытых водоёмов)
    season_map = {
        12: "winter", 1: "winter",  2: "winter",
        3:  "spring", 4: "spring",  5: "spring",
        6:  "summer", 7: "summer",  8: "summer",
        9:  "autumn", 10: "autumn", 11: "autumn",
    }
    df["season"] = df["month"].map(season_map)
    df["is_summer"] = (df["season"] == "summer").astype(int)

    return df


# ── Признаки нарушения нормативов ────────────────────────────────────────────

NORMS = {
    # Supluskohad (EU Bathing Water Directive 2006/7/EC, внутренние воды)
    "e_coli":       500.0,   # КОЕ/100 мл
    "enterococci":  200.0,   # КОЕ/100 мл
    "ph_min":       6.0,
    "ph_max":       9.0,

    # Veevärk / joogivesi (питьевая вода, EU DWD 2020/2184)
    "nitrates":     50.0,    # мг/л
    "nitrites":     0.5,     # мг/л
    "ammonium":     0.5,     # мг/л
    "fluoride":     1.5,     # мг/л
    "manganese":    0.05,    # мг/л
    "iron":         0.2,     # мг/л
    "turbidity":    4.0,     # NTU (veevark/joogivesi; для бассейнов — 0.5 NTU, см. NORMS_POOL)
    "color":        20.0,    # мг Pt/л
    "chlorides":    250.0,   # мг/л
    "sulfates":     250.0,   # мг/л
}

# Нормы специфичные для бассейнов/ujula/СПА (Estonian pool regulations / Terviseamet)
# Отличаются от питьевой воды и от открытых водоёмов.
# Используются в add_ratio_features при domain == 'basseinid'.
NORMS_POOL = {
    "e_coli":              0.0,   # КОЕ/100 мл — норма строже: должно быть 0
    "coliforms":           0.0,   # КОЕ/100 мл
    "pseudomonas":         0.0,   # КОЕ/100 мл (P. aeruginosa)
    "staphylococci":      20.0,   # КОЕ/100 мл
    "ph_min":              6.5,
    "ph_max":              8.5,   # уже, чем veevark (6.5–9.5)
    "free_chlorine_min":   0.2,   # мг/л — нижняя граница (мало хлора → риск)
    "free_chlorine_max":   0.6,   # мг/л — верхняя граница (много хлора → раздражение)
    "combined_chlorine":   0.4,   # мг/л — верхний предел
    "turbidity":           0.5,   # NTU — в 8× строже, чем для питьевой воды
}


def add_ratio_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Добавить отношение измеренного значения к нормативу.
    ratio > 1.0 = нарушение нормы (или выход за допустимый диапазон).

    Для домена basseinid применяются NORMS_POOL вместо NORMS там,
    где нормы отличаются:
    - turbidity: 0.5 NTU (бассейн) вместо 4.0 NTU (veevark)
    - staphylococci, pseudomonas: только в бассейнах
    - free_chlorine, combined_chlorine: диапазонные нормы бассейна
    - pH: диапазон 6.5–8.5 для бассейна вместо 6.0–9.0
    """
    df = df.copy()

    is_pool = (df.get("domain") == "basseinid") if "domain" in df.columns else pd.Series(False, index=df.index)

    for param, norm in NORMS.items():
        if param in ("ph_min", "ph_max"):
            continue
        if param not in df.columns:
            continue
        if param == "turbidity":
            # Бассейн: 0.5 NTU; остальные: 4.0 NTU
            pool_norm = NORMS_POOL["turbidity"]
            ratio = np.where(is_pool, df[param] / pool_norm, df[param] / norm)
            df["turbidity_ratio"] = np.where(df[param].isna(), np.nan, ratio)
        else:
            df[f"{param}_ratio"] = df[param] / norm

    # Бассейновые параметры: staphylococci, pseudomonas
    if "staphylococci" in df.columns:
        pool_norm = NORMS_POOL["staphylococci"]
        df["staphylococci_ratio"] = np.where(
            is_pool & df["staphylococci"].notna(),
            df["staphylococci"] / pool_norm,
            np.nan,
        )
    if "pseudomonas" in df.columns:
        # норма = 0: ratio не применима напрямую; используем бинарный признак
        df["pseudomonas_detected"] = np.where(
            is_pool & df["pseudomonas"].notna(),
            (df["pseudomonas"] > 0).astype(float),
            np.nan,
        )

    # Свободный хлор: нарушение если < min (мало) или > max (много)
    if "free_chlorine" in df.columns:
        fc = df["free_chlorine"]
        fc_min = NORMS_POOL["free_chlorine_min"]
        fc_max = NORMS_POOL["free_chlorine_max"]
        # deviation: 0 = в норме, >0 = выход за диапазон [fc_min, fc_max]
        # np.maximum принимает ровно 2 массива; вычисляем как max(low_viol, high_viol, 0)
        deviation = np.maximum(np.maximum(fc_min - fc, fc - fc_max), 0)
        df["free_chlorine_deviation"] = np.where(
            is_pool & fc.notna(), deviation, np.nan
        )

    # Связанный хлор: верхний предел
    if "combined_chlorine" in df.columns:
        pool_norm = NORMS_POOL["combined_chlorine"]
        df["combined_chlorine_ratio"] = np.where(
            is_pool & df["combined_chlorine"].notna(),
            df["combined_chlorine"] / pool_norm,
            np.nan,
        )

    # pH: расстояние от нормального диапазона (домен-зависимые границы)
    if "ph" in df.columns:
        ph_min_pool = NORMS_POOL["ph_min"]
        ph_max_pool = NORMS_POOL["ph_max"]
        ph_min_def  = NORMS["ph_min"]
        ph_max_def  = NORMS["ph_max"]

        def _ph_deviation(row_ph, is_pool_row):
            if pd.isna(row_ph):
                return np.nan
            if is_pool_row:
                return max(0, ph_min_pool - row_ph, row_ph - ph_max_pool)
            return max(0, ph_min_def - row_ph, row_ph - ph_max_def)

        df["ph_deviation"] = [
            _ph_deviation(ph, pool)
            for ph, pool in zip(df["ph"], is_pool)
        ]

    return df


def add_missing_indicators(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    Добавить бинарные индикаторы пропуска для важных признаков.
    Пропуск может нести информацию (параметр не измерялся / не требовался).
    """
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[f"{col}_missing"] = df[col].isna().astype(int)
    return df


# ── Кодирование категорий ─────────────────────────────────────────────────────

def fit_county_mapping(train_county: pd.Series) -> Dict[str, int]:
    """
    Словарь уезд → int по обучающей выборке (без утечки из test).
    Редкие / новые уезды в test кодируются как unknown при применении.
    """
    s = train_county.fillna(COUNTY_UNKNOWN).astype(str)
    vals = sorted(s.unique())
    return {v: i for i, v in enumerate(vals)}


def encode_categoricals(
    df: pd.DataFrame,
    county_mapping: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """
    Кодировать категориальные признаки: county, domain, season.

    county_mapping:
        None — обучить LabelEncoder на всех строках df (как раньше; возможна утечка).
        dict — из fit_county_mapping(train_county); неизвестные уезды → код unknown.
    """
    df = df.copy()

    if "county" in df.columns:
        s = df["county"].fillna(COUNTY_UNKNOWN).astype(str)
        if county_mapping is None:
            le = LabelEncoder()
            df["county_encoded"] = le.fit_transform(s)
        else:
            unk_code = county_mapping.get(COUNTY_UNKNOWN, 0)
            df["county_encoded"] = s.map(lambda x: county_mapping.get(x, unk_code))

    if "domain" in df.columns:
        dummies = pd.get_dummies(df["domain"], prefix="domain")
        df = pd.concat([df, dummies], axis=1)

    if "season" in df.columns:
        dummies = pd.get_dummies(df["season"], prefix="season")
        df = pd.concat([df, dummies], axis=1)

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    До кодирования категорий: фильтр compliant, время, ratio, индикаторы пропусков.
    Дальше — train_test_split по индексу и encode_categoricals(..., county_mapping=...).
    """
    df_clean = df.dropna(subset=["compliant"]).copy()
    print(f"[features] После удаления без compliant: {len(df_clean)} строк")
    df_clean = add_time_features(df_clean)
    df_clean = add_ratio_features(df_clean)
    df_clean = add_missing_indicators(df_clean, NUMERIC_PARAMS)
    return df_clean


# ── Сборка финального датасета ────────────────────────────────────────────────

NUMERIC_PARAMS = [
    "e_coli", "enterococci", "ph", "transparency",
    "nitrates", "nitrites", "ammonium", "fluoride",
    "manganese", "iron", "turbidity", "color",
    "coliforms", "chlorides", "sulfates",
    # Параметры бассейнов/ujula/СПА (domain=basseinid)
    "staphylococci", "pseudomonas", "free_chlorine", "combined_chlorine",
    "oxidizability", "colonies_37c",
]

# Параметры с ratio-признаками в NORMS (универсальные, не pH и не pool-специфичные)
_NORMS_RATIO_PARAMS = [
    "e_coli", "enterococci",                              # supluskoha + veevark
    "nitrates", "nitrites", "ammonium", "fluoride",       # veevark/joogivesi
    "manganese", "iron", "turbidity", "color",            # veevark/joogivesi
    "chlorides", "sulfates",                              # veevark
]
# Параметры без ratio в NORMS: transparency (нет нормы), coliforms (норма 0 для веды,
# нет смысла делить), oxidizability, colonies_37c (бассейновые, без стандартной нормы)
RATIO_COLS = [f"{p}_ratio" for p in _NORMS_RATIO_PARAMS]
RATIO_COLS += [
    "ph_deviation",
    # Бассейновые ratio/deviation (только для domain=basseinid, иначе NaN)
    "staphylococci_ratio",
    "pseudomonas_detected",
    "free_chlorine_deviation",
    "combined_chlorine_ratio",
]

FEATURE_COLS = (
    NUMERIC_PARAMS +
    RATIO_COLS +
    [f"{p}_missing" for p in NUMERIC_PARAMS] +
    ["month", "year", "is_summer", "county_encoded"] +
    [
        "domain_supluskoha",
        "domain_veevark",
        "domain_basseinid",
        "domain_joogivesi",
        "season_summer",
        "season_winter",
        "season_spring",
        "season_autumn",
    ]
)


def build_dataset(
    df: pd.DataFrame,
    county_mapping: Optional[Dict[str, int]] = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Полный пайплайн: сырой DataFrame → (X, y).

    county_mapping:
        None — кодирование уезда на всём df (совместимость со старыми ноутбуками).
        Иначе — передать fit_county_mapping(train_county) после split на train.
    """
    df_clean = engineer_features(df)
    df_clean = encode_categoricals(df_clean, county_mapping=county_mapping)

    y = df_clean["compliant"].astype(int)
    available_features = [c for c in FEATURE_COLS if c in df_clean.columns]
    X = df_clean[available_features].copy()

    print(f"[features] Итого признаков: {X.shape[1]}")
    print(f"[features] Распределение классов:\n{y.value_counts()}")

    return X, y


# Дополнительные столбцы в meta для citizen-service / отчётов по пробам.
# Pool-параметры (free_chlorine, pseudomonas и др.) уже включены в NUMERIC_PARAMS.
META_EXTRA_NUMERIC = list(NUMERIC_PARAMS)


def _encode_for_citizen_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Инженерия + кодирование категорий для citizen-снимка (уезд на всём df)."""
    df_clean = engineer_features(df)
    return encode_categoricals(df_clean, county_mapping=None)


def _citizen_meta_columns(df_clean: pd.DataFrame) -> List[str]:
    base_meta = ["location", "domain", "sample_date", "compliant"]
    meta_cols = [c for c in base_meta if c in df_clean.columns]
    if "sample_id" in df_clean.columns:
        meta_cols.append("sample_id")
    if "county" in df_clean.columns:
        meta_cols.append("county")
    for _geo in ("geocode_site", "geocode_facility"):
        if _geo in df_clean.columns and _geo not in meta_cols:
            meta_cols.append(_geo)
    for _off in ("official_lat", "official_lon", "official_coord_source"):
        if _off in df_clean.columns and _off not in meta_cols:
            meta_cols.append(_off)
    for c in META_EXTRA_NUMERIC:
        if c in df_clean.columns and c not in meta_cols:
            meta_cols.append(c)
    return meta_cols


def build_citizen_meta_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Только строки meta для карты (--map-only): без матрицы признаков X и без обучения модели.
    Совпадает по строкам и столбцам meta-части с build_dataset_with_meta.
    """
    df_clean = _encode_for_citizen_snapshot(df)
    meta = df_clean[_citizen_meta_columns(df_clean)].copy()
    y = df_clean["compliant"].astype(int)
    print(f"[features] citizen meta (без X): {len(meta)} строк")
    print(f"[features] Распределение классов:\n{y.value_counts()}")
    return meta


def build_dataset_with_meta(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Как build_dataset, но дополнительно возвращает meta со столбцами места, даты и измерений
    (для снимков карты и трассировки строк).

    Уезд кодируется по всей выборке (офлайн-снимок / полное обучение citizen-модели).
    """
    df_clean = _encode_for_citizen_snapshot(df)

    y = df_clean["compliant"].astype(int)
    available_features = [c for c in FEATURE_COLS if c in df_clean.columns]
    X = df_clean[available_features].copy()

    meta = df_clean[_citizen_meta_columns(df_clean)].copy()

    print(f"[features] Итого признаков: {X.shape[1]}")
    print(f"[features] Распределение классов:\n{y.value_counts()}")

    return X, y, meta


def impute_and_scale(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Заполнить пропуски и масштабировать. Только fit на train!

    Возвращает:
        (X_train_scaled, X_test_scaled)
    """
    X_train = X_train.copy()
    X_test = X_test.copy()
    # Столбцы без ни одного значения в train ломают SimpleImputer (срезают признаки).
    for col in X_train.columns:
        if X_train[col].notna().sum() == 0:
            X_train[col] = 0.0
            X_test[col] = X_test[col].fillna(0.0)

    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    # RobustScaler вместо StandardScaler: устойчив к выбросам (E. coli max=100 000 при норме 500).
    # Масштабирует по медиане и IQR — выбросы не искажают признаки для всей выборки.
    scaler = RobustScaler()

    X_train_imp = imputer.fit_transform(X_train)
    X_test_imp = imputer.transform(X_test)

    X_train_scaled = scaler.fit_transform(X_train_imp)
    X_test_scaled  = scaler.transform(X_test_imp)

    return (
        pd.DataFrame(X_train_scaled, columns=X_train.columns),
        pd.DataFrame(X_test_scaled,  columns=X_test.columns)
    )
