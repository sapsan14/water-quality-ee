"""
evaluate.py — Метрики и визуализация для моделей качества воды
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
    precision_recall_curve,
    recall_score,
    precision_score,
)
from sklearn.model_selection import TimeSeriesSplit
from typing import Dict, Any, Callable, Optional, Tuple


# ── Основная оценка модели ────────────────────────────────────────────────────

def evaluate_model(
    model,
    X_test,
    y_test,
    model_name: str = "Model"
) -> Dict[str, Any]:
    """
    Полная оценка модели: метрики + confusion matrix + ROC.

    Возвращает словарь с результатами.
    """
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    roc_auc = roc_auc_score(y_test, y_prob)
    report  = classification_report(
        y_test, y_pred,
        target_names=["Нарушение (0)", "Норма (1)"],
        output_dict=True
    )

    print(f"\n{'='*50}")
    print(f"Модель: {model_name}")
    print(f"{'='*50}")
    print(classification_report(
        y_test, y_pred,
        target_names=["Нарушение (0)", "Норма (1)"]
    ))
    print(f"ROC-AUC: {roc_auc:.4f}")

    return {
        "model_name":  model_name,
        "roc_auc":     roc_auc,
        "report":      report,
        "y_pred":      y_pred,
        "y_prob":      y_prob,
        "y_test":      y_test,
    }


# ── Визуализация ──────────────────────────────────────────────────────────────

def plot_confusion_matrix(y_test, y_pred, model_name: str = "Model"):
    """Нарисовать confusion matrix с читаемыми подписями."""
    cm = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=["Pred: Нарушение", "Pred: Норма"],
        yticklabels=["True: Нарушение", "True: Норма"],
        ax=ax
    )

    # Выделить FN (опасная вода, которую пропустили)
    ax.add_patch(plt.Rectangle((1, 0), 1, 1, fill=False,
                                edgecolor='red', linewidth=3))
    ax.set_title(f"Confusion Matrix — {model_name}\n"
                 f"(красная рамка = пропущенные нарушения!)")
    plt.tight_layout()
    plt.show()


def plot_roc_curve(results_list: list):
    """
    Нарисовать ROC-кривые для нескольких моделей на одном графике.

    Параметры:
        results_list: список результатов из evaluate_model()
    """
    fig, ax = plt.subplots(figsize=(7, 5))

    for result in results_list:
        fpr, tpr, _ = roc_curve(
            # нужны y_test — передавать снаружи
            result["y_test"], result["y_prob"]
        )
        ax.plot(fpr, tpr, label=f"{result['model_name']} (AUC={result['roc_auc']:.3f})")

    ax.plot([0, 1], [0, 1], "k--", label="Random baseline")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC-кривые моделей")
    ax.legend()
    plt.tight_layout()
    plt.show()


def plot_pr_curve(results_list: list):
    """
    PR-кривые (Precision-Recall) для нескольких моделей.

    При несбалансированных классах (12 % нарушений) PR-кривая информативнее ROC:
    она показывает, сколько реальных нарушений находит модель (recall) при заданной
    доле ложных тревог (precision), без влияния большого числа TN.

    Параметры:
        results_list: список результатов из evaluate_model()
    """
    fig, ax = plt.subplots(figsize=(7, 5))

    for result in results_list:
        # score нарушения = 1 - P(норма)
        scores_viol = 1.0 - result["y_prob"]
        y_viol = (result["y_test"] == 0).astype(int)
        prec, rec, _ = precision_recall_curve(y_viol, scores_viol)
        # AP — площадь под PR-кривой (average precision)
        ap = float(np.trapz(prec, rec) * -1)  # trapz по убывающему rec → нужно abs
        ap = abs(ap)
        ax.plot(rec, prec, label=f"{result['model_name']} (AP={ap:.3f})")

    # Baseline: доля нарушений в y_test
    if results_list:
        baseline = float((results_list[0]["y_test"] == 0).mean())
        ax.axhline(baseline, color="k", linestyle="--",
                   label=f"Random baseline (precision={baseline:.3f})")

    ax.set_xlabel("Recall (нарушения)")
    ax.set_ylabel("Precision (нарушения)")
    ax.set_title("PR-кривые моделей\n(class 0 = нарушение; лучше ROC при дисбалансе)")
    ax.legend()
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    plt.tight_layout()
    plt.show()


def plot_feature_importance(model, feature_names: list, top_n: int = 15):
    """Feature importance для Random Forest."""
    if not hasattr(model, "feature_importances_"):
        # Попробовать достать из Pipeline
        if hasattr(model, "named_steps"):
            clf = model.named_steps.get("model") or model.named_steps.get("classifier")
            if clf and hasattr(clf, "feature_importances_"):
                importances = clf.feature_importances_
            else:
                print("Модель не поддерживает feature_importances_")
                return
        else:
            print("Модель не поддерживает feature_importances_")
            return
    else:
        importances = model.feature_importances_

    importance_df = pd.Series(importances, index=feature_names).sort_values(ascending=True)
    top = importance_df.tail(top_n)

    fig, ax = plt.subplots(figsize=(8, 6))
    top.plot(kind="barh", ax=ax, color="steelblue")
    ax.set_title(f"Топ-{top_n} признаков по важности")
    ax.set_xlabel("Importance")
    plt.tight_layout()
    plt.show()


def plot_class_distribution(y: pd.Series, title: str = "Распределение классов"):
    """Гистограмма распределения целевой переменной."""
    counts = y.value_counts()
    labels = ["Норма (1)", "Нарушение (0)"]
    colors = ["steelblue", "salmon"]

    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(
        [str(k) for k in counts.index],
        counts.values,
        color=[colors[k] for k in counts.index],
        edgecolor="white"
    )
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                f"{val}\n({val/len(y)*100:.1f}%)",
                ha="center", va="bottom", fontsize=10)

    ax.set_title(title)
    ax.set_xlabel("Класс")
    ax.set_ylabel("Количество проб")
    plt.tight_layout()
    plt.show()


# ── Сравнение моделей ─────────────────────────────────────────────────────────

def compare_models(results: list) -> pd.DataFrame:
    """
    Таблица сравнения моделей по основным метрикам.

    Параметры:
        results: список результатов из evaluate_model()

    Возвращает:
        pd.DataFrame с метриками
    """
    rows = []
    for r in results:
        rep = r["report"]
        rows.append({
            "Модель":    r["model_name"],
            "Accuracy":  rep["accuracy"],
            "Precision (нарушение)": rep["Нарушение (0)"]["precision"],
            "Recall (нарушение)":    rep["Нарушение (0)"]["recall"],
            "F1 (нарушение)":        rep["Нарушение (0)"]["f1-score"],
            "ROC-AUC":   r["roc_auc"],
        })

    df = pd.DataFrame(rows).set_index("Модель")
    return df.round(4)


# ── Порог по вероятности нарушения ─────────────────────────────────────────────

def best_threshold_max_recall_at_precision(
    y_true,
    proba_compliant: np.ndarray,
    min_precision: float = 0.7,
) -> Dict[str, Any]:
    """
    Подобрать порог по score = P(нарушение) = 1 - P(норма).
    Максимизируем recall класса 0 при условии precision(0) >= min_precision.

    Если ограничение недостижимо, возвращается порог с лучшим F1 на кривой P–R
    (constraint_met=False).
    """
    y_true = np.asarray(y_true)
    scores = 1.0 - np.asarray(proba_compliant)
    y_viol = (y_true == 0).astype(int)
    prec, rec, thr = precision_recall_curve(y_viol, scores)

    if len(thr) == 0:
        return {
            "threshold": 0.5,
            "recall_violation": float("nan"),
            "precision_violation": float("nan"),
            "min_precision": min_precision,
            "constraint_met": False,
        }

    best_i: Optional[int] = None
    best_r = -1.0
    for i in range(len(thr)):
        p, r = prec[i + 1], rec[i + 1]
        if p >= min_precision and r > best_r:
            best_r, best_i = r, i

    if best_i is not None:
        return {
            "threshold": float(thr[best_i]),
            "recall_violation": float(rec[best_i + 1]),
            "precision_violation": float(prec[best_i + 1]),
            "min_precision": min_precision,
            "constraint_met": True,
        }

    f1 = 2.0 * prec[1:] * rec[1:] / (prec[1:] + rec[1:] + 1e-12)
    j = int(np.nanargmax(f1))
    return {
        "threshold": float(thr[j]),
        "recall_violation": float(rec[j + 1]),
        "precision_violation": float(prec[j + 1]),
        "min_precision": min_precision,
        "constraint_met": False,
    }


def predict_compliant_from_violation_threshold(
    proba_compliant: np.ndarray,
    threshold_violation: float,
) -> np.ndarray:
    """1 = норма, 0 = нарушение; нарушение если P(нарушение) >= threshold_violation."""
    viol = 1.0 - np.asarray(proba_compliant)
    return np.where(viol >= threshold_violation, 0, 1)


# ── Кросс-валидация по времени ────────────────────────────────────────────────

def temporal_cv_metrics(
    model_factory: Callable,
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    TimeSeriesSplit на уже отсортированных по времени X, y (одинаковый индекс).

    model_factory: вызывается без аргументов, возвращает новый не обученный estimator
    с методами fit, predict, predict_proba.
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    rows = []
    for fold, (tr_idx, te_idx) in enumerate(tscv.split(X)):
        model = model_factory()
        model.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        proba = model.predict_proba(X.iloc[te_idx])[:, 1]
        y_te = y.iloc[te_idx].to_numpy()
        pred = model.predict(X.iloc[te_idx])
        auc = roc_auc_score(y_te, proba)
        r0 = recall_score(y_te, pred, pos_label=0, zero_division=0)
        p0 = precision_score(y_te, pred, pos_label=0, zero_division=0)
        rows.append(
            {
                "fold": fold + 1,
                "n_train": len(tr_idx),
                "n_test": len(te_idx),
                "roc_auc": auc,
                "recall_violation": r0,
                "precision_violation": p0,
            }
        )
    df_fold = pd.DataFrame(rows)
    summary = df_fold[["roc_auc", "recall_violation", "precision_violation"]].agg(["mean", "std"])
    return df_fold, summary
