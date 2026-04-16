"""Тесты вспомогательных функций evaluate.py (без данных проекта)."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from evaluate import (
    best_threshold_max_recall_at_precision,
    temporal_cv_metrics,
)


def test_best_threshold_returns_keys():
    np.random.seed(0)
    n = 400
    y = pd.Series(np.array([0] * 50 + [1] * (n - 50)))
    # вероятность «норма»: выше для класса 1
    proba_ok = np.where(y == 1, 0.85, 0.35) + np.random.uniform(-0.05, 0.05, n)
    proba_ok = np.clip(proba_ok, 0.01, 0.99)
    out = best_threshold_max_recall_at_precision(y, proba_ok, min_precision=0.1)
    assert "threshold" in out
    assert "recall_violation" in out
    assert "precision_violation" in out
    assert "constraint_met" in out


def test_temporal_cv_metrics_runs():
    np.random.seed(1)
    X = pd.DataFrame(np.random.randn(80, 4), columns=list("abcd"))
    y = pd.Series((np.random.rand(80) > 0.85).astype(int))
    # избегаем один класс
    y.iloc[0] = 0
    y.iloc[1] = 1

    def factory():
        return LogisticRegression(max_iter=500, random_state=0)

    fold_df, summary = temporal_cv_metrics(factory, X, y, n_splits=3)
    assert len(fold_df) == 3
    assert "roc_auc" in fold_df.columns
    assert summary.shape[0] == 2  # mean, std
