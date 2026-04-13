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
)
from typing import Dict, Any


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
