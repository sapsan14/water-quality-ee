#!/usr/bin/env python3
"""
Метрики LightGBM на темпоральном split (как в 06): для сверки с docs/report.md.
Запуск из корня: python scripts/compute_report_metrics.py
Требует: данные в data/raw/, pip install lightgbm

Почему долго: load_all() парсит/мержит XML; затем один полный fit LightGBM; затем
CalibratedClassifierCV(cv=N) по умолчанию снова обучает базовую модель на каждом
фолде (ещё N полноценных fit на подвыборках train). Скрипт конечный — это не зависание.

Быстрая калибровка без дополнительных fit: --prefit-calibration (изотоника на prob
с уже обученного LGBM; цифры чуть отличаются от cv-калибровки из ноутбука).

Ускорение целиком: --fast (100 деревьев + prefit). Меньше деревьев: --n-estimators N.
Во время fit LGBM по умолчанию печатается прогресс каждые 25 итераций (--log-every 0 — выкл.).
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

warnings.filterwarnings("ignore")

import lightgbm as lgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, precision_score, recall_score, roc_auc_score

from data_loader import load_all
from features import FEATURE_COLS, engineer_features, encode_categoricals, fit_county_mapping

TOTAL_STEPS = 6


def _banner(line: str, char: str = "=") -> None:
    print(char * 72, flush=True)
    print(line, flush=True)
    print(char * 72, flush=True)


def _elapsed(t0: float) -> str:
    return f"{time.perf_counter() - t0:.1f}s"


def _step_start(step: int, title: str, *, next_hint: str | None = None) -> None:
    print(flush=True)
    print(f"--- Шаг {step}/{TOTAL_STEPS}: {title} ---", flush=True)
    if next_hint:
        print(f"    Дальше: {next_hint}", flush=True)


def _step_done(t0: float, detail: str) -> None:
    print(f"    Готово ({detail}). От старта скрипта: {_elapsed(t0)}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="LightGBM temporal metrics for report.md")
    ap.add_argument(
        "--prefit-calibration",
        action="store_true",
        help="Калибровка cv='prefit' (секунды вместо повторных fit LightGBM по фолдам)",
    )
    ap.add_argument(
        "--calibration-cv",
        type=int,
        default=3,
        metavar="N",
        help="Фолды CalibratedClassifierCV (игнорируется с --prefit-calibration). По умолчанию: 3",
    )
    ap.add_argument(
        "--fast",
        action="store_true",
        help="Быстрый прогон: 100 деревьев + prefit-калибровка (без cv×LGBM)",
    )
    ap.add_argument(
        "--n-estimators",
        type=int,
        default=None,
        metavar="N",
        help="Число деревьев LGBM (по умолчанию 300; с --fast без этого флага — 100)",
    )
    ap.add_argument(
        "--log-every",
        type=int,
        default=25,
        metavar="K",
        help="Печатать eval LGBM каждые K итераций (0 = не печатать)",
    )
    args = ap.parse_args()

    n_estimators = (
        args.n_estimators
        if args.n_estimators is not None
        else (100 if args.fast else 300)
    )
    use_prefit = args.prefit_calibration or args.fast

    t0 = time.perf_counter()
    cal_mode = (
        "prefit (быстро)"
        if use_prefit
        else f"cv={args.calibration_cv} (долго, +{args.calibration_cv} fit LGBM)"
    )

    _banner("compute_report_metrics.py — метрики LightGBM для сверки с docs/report.md")
    print(
        "Что делает скрипт:\n"
        "  1) Загружает 4 домена воды (XML из кэша data/raw/ при use_cache).\n"
        "  2) Строит признаки, сортирует по дате, делит 80% train / 20% test по времени.\n"
        "  3) Обучает LightGBM на train, считает ROC-AUC / recall / precision по нарушениям на test.\n"
        "  4) Калибрует вероятности (isotonic), снова считает метрики на test.\n"
        f"Режим калибровки сейчас: {cal_mode}.\n"
        f"Деревьев LGBM: {n_estimators}.\n"
        "Конец работы: после строки «ИТОГ» внизу (и сводки по времени).\n"
        "На шаге 3 во время бустинга идут строки [n] valid's binary_logloss: … (если не задали --log-every 0).\n",
        flush=True,
    )
    _banner("", "-")

    _step_start(
        1,
        "Загрузка данных load_all()",
        next_hint="инженерия признаков и разбиение train/test (шаг 2)",
    )
    df = load_all(use_cache=True, geocode_county=False)
    _step_done(t0, f"строк: {len(df):,}")

    _step_start(
        2,
        "Признаки, кодирование county (только train), матрица X и split 80/20",
        next_hint="обучение LightGBM — самый тяжёлый шаг после загрузки (шаг 3)",
    )
    df_eng = engineer_features(df)
    df_time = df_eng.sort_values("sample_date").reset_index(drop=True)
    cut = int(len(df_time) * 0.8)
    train_ix = df_time.index[:cut]
    cmap = fit_county_mapping(df_time.loc[train_ix, "county"])
    df_enc = encode_categoricals(df_time, county_mapping=cmap)
    y = df_enc["compliant"].astype(int)
    available = [c for c in FEATURE_COLS if c in df_enc.columns]
    X = df_enc[available]
    X_train, X_test = X.iloc[:cut], X.iloc[cut:]
    y_train, y_test = y.iloc[:cut], y.iloc[cut:]
    _step_done(
        t0,
        f"признаков в X: {len(available)}, train={len(X_train):,}, test={len(X_test):,}",
    )

    _step_start(
        3,
        f"Обучение LightGBM ({n_estimators} деревьев, class_weight=balanced)",
        next_hint="сырые метрики на test и затем калибровка (шаги 4–5)",
    )
    params = dict(
        n_estimators=n_estimators,
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
    lgbm = lgb.LGBMClassifier(**params)
    # Лог по итерациям: хвост train как hold-out только для вывода (не для early stopping).
    fit_kw: dict = {}
    if args.log_every and args.log_every > 0:
        log_n = min(10_000, len(X_train))
        X_va = X_train.iloc[-log_n:]
        y_va = y_train.iloc[-log_n:]
        print(
            f"    (лог LGBM: eval на последних {log_n:,} строках train, каждые {args.log_every} итераций)",
            flush=True,
        )
        fit_kw["eval_set"] = [(X_va, y_va)]
        fit_kw["eval_metric"] = "binary_logloss"
        fit_kw["callbacks"] = [lgb.log_evaluation(period=args.log_every)]
    else:
        print("    (лог итераций LGBM выключен: --log-every 0)", flush=True)
    lgbm.fit(X_train, y_train, **fit_kw)
    _step_done(t0, "один полный fit на train")

    _step_start(
        4,
        "Прогноз на test без калибровки (вероятности и метрики)",
        next_hint="калибровка вероятностей (шаг 5)",
    )
    y_proba = lgbm.predict_proba(X_test)[:, 1]
    y_pred = lgbm.predict(X_test)
    auc = roc_auc_score(y_test, y_proba)
    r0 = recall_score(y_test, y_pred, pos_label=0, zero_division=0)
    p0 = precision_score(y_test, y_pred, pos_label=0, zero_division=0)
    _step_done(t0, f"ROC-AUC={auc:.4f}")

    if use_prefit:
        cal = CalibratedClassifierCV(lgbm, method="isotonic", cv="prefit")
        _step_start(
            5,
            "Калибровка isotonic, cv=prefit (поверх уже обученного LGBM)",
            next_hint="метрики после калибровки и печать отчёта (шаг 6)",
        )
    else:
        cal = CalibratedClassifierCV(lgbm, method="isotonic", cv=args.calibration_cv)
        _step_start(
            5,
            f"Калибровка isotonic, cv={args.calibration_cv} "
            f"(на каждом фолде снова обучается LGBM — долго, без промежуточного вывода)",
            next_hint="метрики после калибровки и печать отчёта (шаг 6)",
        )
    cal.fit(X_train, y_train)
    _step_done(t0, "калибратор обучен")

    _step_start(
        6,
        "Прогноз с калибровкой и вывод результатов",
        next_hint="это последний шаг — сразу после блока метрик будет ИТОГ",
    )
    y_pred_c = cal.predict(X_test)
    r0c = recall_score(y_test, y_pred_c, pos_label=0, zero_division=0)
    p0c = precision_score(y_test, y_pred_c, pos_label=0, zero_division=0)

    rep = classification_report(y_test, y_pred, target_names=["viol", "ok"], output_dict=True)

    _step_done(t0, "метрики посчитаны, печатаю таблицу ниже")
    print(flush=True)
    _banner("Результаты")

    print("=== Объём (4 домена load_all, county только train по времени) ===")
    print(f"n={len(X)}, train={len(X_train)}, test={len(X_test)}")
    print(f"Домены в df: {df['domain'].value_counts().to_dict()}")
    print(f"test violations: {(y_test == 0).sum()} / {len(y_test)}")
    print()
    print(f"=== LightGBM temporal (test), n_estimators={n_estimators} ===")
    print(f"ROC-AUC: {auc:.4f}")
    print(f"Recall(нарушение): {r0:.4f}, Precision(нарушение): {p0:.4f}, F1(0): {rep['viol']['f1-score']:.4f}")
    print()
    cal_label = "prefit" if use_prefit else f"cv={args.calibration_cv}"
    print(f"=== + CalibratedClassifierCV isotonic {cal_label} ===")
    print(f"Recall(нарушение): {r0c:.4f}, Precision(нарушение): {p0c:.4f}")

    print(flush=True)
    _banner("ИТОГ")
    print(
        f"Скрипт завершён успешно. Все {TOTAL_STEPS} шагов выполнены.\n"
        f"Общее время: {_elapsed(t0)}.\n"
        "Можно сверять числа с docs/report.md (учитывая отличия split/seed/cv от ноутбука 06).",
        flush=True,
    )
    _banner("", "-")


if __name__ == "__main__":
    main()
