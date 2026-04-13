"""
features.py — Инженерия признаков для модели качества воды

Входные данные: сырой DataFrame из data_loader.py
Выходные данные: X (признаки), y (целевая переменная)
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from typing import Tuple, List


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
    # Supluskohad (внутренние воды)
    "e_coli":       500.0,   # КОЕ/100 мл
    "enterococci":  200.0,   # КОЕ/100 мл
    "ph_min":       6.0,
    "ph_max":       9.0,

    # Veevärk (питьевая вода)
    "nitrates":     50.0,    # мг/л
    "nitrites":     0.5,
    "ammonium":     0.5,
    "fluoride":     1.5,
    "manganese":    0.05,
    "iron":         0.2,
    "turbidity":    4.0,     # NTU
}


def add_ratio_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Добавить отношение измеренного значения к нормативу.
    ratio > 1.0 = нарушение.
    """
    df = df.copy()

    for param, norm in NORMS.items():
        if param in ("ph_min", "ph_max"):
            continue
        if param in df.columns:
            df[f"{param}_ratio"] = df[param] / norm

    # pH: расстояние от нормального диапазона
    if "ph" in df.columns:
        df["ph_deviation"] = df["ph"].apply(
            lambda x: max(0, NORMS["ph_min"] - x, x - NORMS["ph_max"])
            if pd.notna(x) else np.nan
        )

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

def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Кодировать категориальные признаки: county, domain, season."""
    df = df.copy()

    # Уезд (maakond) — Label Encoding
    if "county" in df.columns:
        le = LabelEncoder()
        df["county_encoded"] = le.fit_transform(df["county"].fillna("unknown"))

    # Домен (supluskoha / veevark / ...) — One-Hot Encoding
    if "domain" in df.columns:
        dummies = pd.get_dummies(df["domain"], prefix="domain")
        df = pd.concat([df, dummies], axis=1)

    # Сезон — One-Hot
    if "season" in df.columns:
        dummies = pd.get_dummies(df["season"], prefix="season")
        df = pd.concat([df, dummies], axis=1)

    return df


# ── Сборка финального датасета ────────────────────────────────────────────────

NUMERIC_PARAMS = [
    "e_coli", "enterococci", "ph", "transparency",
    "nitrates", "nitrites", "ammonium", "fluoride",
    "manganese", "iron", "turbidity", "color",
    "coliforms", "chlorides", "sulfates",
]

RATIO_COLS = [f"{p}_ratio" for p in NUMERIC_PARAMS if p not in ("ph",)]
RATIO_COLS += ["ph_deviation"]

FEATURE_COLS = (
    NUMERIC_PARAMS +
    RATIO_COLS +
    [f"{p}_missing" for p in NUMERIC_PARAMS] +
    ["month", "year", "is_summer", "county_encoded"] +
    ["domain_supluskoha", "domain_veevark", "domain_basseinid",
     "season_summer", "season_winter", "season_spring", "season_autumn"]
)


def build_dataset(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Полный пайплайн: сырой DataFrame → (X, y).

    Параметры:
        df: результат load_domain() или load_all()

    Возвращает:
        X: DataFrame с признаками
        y: Series с целевой переменной (1/0)
    """
    # Убрать строки без целевой переменной
    df_clean = df.dropna(subset=["compliant"]).copy()
    print(f"[features] После удаления без compliant: {len(df_clean)} строк")

    # Добавить производные признаки
    df_clean = add_time_features(df_clean)
    df_clean = add_ratio_features(df_clean)
    df_clean = add_missing_indicators(df_clean, NUMERIC_PARAMS)
    df_clean = encode_categoricals(df_clean)

    # Целевая переменная
    y = df_clean["compliant"].astype(int)

    # Признаки — берём только то, что есть в датасете
    available_features = [c for c in FEATURE_COLS if c in df_clean.columns]
    X = df_clean[available_features].copy()

    print(f"[features] Итого признаков: {X.shape[1]}")
    print(f"[features] Распределение классов:\n{y.value_counts()}")

    return X, y


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
    scaler = StandardScaler()

    X_train_imp = imputer.fit_transform(X_train)
    X_test_imp = imputer.transform(X_test)

    X_train_scaled = scaler.fit_transform(X_train_imp)
    X_test_scaled  = scaler.transform(X_test_imp)

    return (
        pd.DataFrame(X_train_scaled, columns=X_train.columns),
        pd.DataFrame(X_test_scaled,  columns=X_test.columns)
    )
