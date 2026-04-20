#!/usr/bin/env python3
"""
drift_monitor.py — AI Act Art 15 drift detection for water-quality features.

Compares a *reference* slice of features (the training window) to a *current*
slice (the most recent probes) and reports:

- Population Stability Index (PSI) per numeric feature
- KL divergence on the compliance label
- A single overall status: OK / WARN / ALERT

Intended to run inside the citizen-snapshot CI workflow
(`.github/workflows/citizen-snapshot.yml`) after `build_citizen_snapshot.py`
produces the trained model but before the snapshot is signed. A WARN or ALERT
triggers a GitHub Actions annotation so the maintainers can review whether the
published model still matches the data it was trained on.

Usage (local):

    python scripts/drift_monitor.py --reference-years 2021,2022,2023,2024 --current-year 2025
    python scripts/drift_monitor.py --json-out data/audit/drift_2026-04.json

This is a deliberately small-surface tool: no scikit-learn dependency beyond
what features.py already requires, no external ML services, pure pandas/numpy.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_loader import load_all  # noqa: E402
from features import NUMERIC_PARAMS, engineer_features  # noqa: E402


PSI_WARN = 0.1
PSI_ALERT = 0.25
KL_WARN = 0.05
KL_ALERT = 0.15
DEFAULT_BINS = 10


@dataclass
class FeatureDrift:
    feature: str
    psi: float
    reference_n: int
    current_n: int
    reference_missing_share: float
    current_missing_share: float
    status: str  # "ok" | "warn" | "alert" | "skipped"
    note: str = ""


def _bin_edges(series: pd.Series, bins: int) -> np.ndarray:
    """Equal-frequency bin edges on the reference series (deciles by default)."""
    s = series.dropna()
    if len(s) < bins:
        return np.array([])
    quantiles = np.linspace(0.0, 1.0, bins + 1)
    edges = np.quantile(s.values, quantiles)
    # Collapse duplicate edges to a minimal unique set.
    edges = np.unique(edges)
    if len(edges) < 3:
        return np.array([])
    edges[0] = -np.inf
    edges[-1] = np.inf
    return edges


def _psi(ref: pd.Series, cur: pd.Series, edges: np.ndarray) -> float:
    """Population Stability Index on a pre-computed set of bin edges."""
    if len(edges) == 0:
        return float("nan")
    ref_counts, _ = np.histogram(ref.dropna().values, bins=edges)
    cur_counts, _ = np.histogram(cur.dropna().values, bins=edges)
    eps = 1e-6
    ref_pct = ref_counts / max(ref_counts.sum(), 1) + eps
    cur_pct = cur_counts / max(cur_counts.sum(), 1) + eps
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def _label_kl(ref_y: pd.Series, cur_y: pd.Series) -> float:
    """KL divergence between two binary label distributions."""
    eps = 1e-6
    r_pos = (ref_y == 0).mean() + eps
    r_neg = 1.0 - r_pos
    c_pos = (cur_y == 0).mean() + eps
    c_neg = 1.0 - c_pos
    return float(c_pos * np.log(c_pos / r_pos) + c_neg * np.log(c_neg / r_neg))


def _status_from_psi(value: float) -> str:
    if np.isnan(value):
        return "skipped"
    if value >= PSI_ALERT:
        return "alert"
    if value >= PSI_WARN:
        return "warn"
    return "ok"


def _status_from_kl(value: float) -> str:
    if np.isnan(value):
        return "skipped"
    if value >= KL_ALERT:
        return "alert"
    if value >= KL_WARN:
        return "warn"
    return "ok"


def compute_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    bins: int = DEFAULT_BINS,
) -> dict:
    """Core compute: returns a dict ready for JSON + human printing."""
    results: list[FeatureDrift] = []
    worst_psi: tuple[str, float] = ("", 0.0)
    for feat in NUMERIC_PARAMS:
        if feat not in reference.columns or feat not in current.columns:
            results.append(FeatureDrift(feat, float("nan"), 0, 0, 0.0, 0.0, "skipped", "feature missing"))
            continue
        ref_col = reference[feat]
        cur_col = current[feat]
        ref_n, cur_n = len(ref_col), len(cur_col)
        ref_miss = float(ref_col.isna().mean()) if ref_n else 0.0
        cur_miss = float(cur_col.isna().mean()) if cur_n else 0.0
        edges = _bin_edges(ref_col, bins)
        psi = _psi(ref_col, cur_col, edges)
        status = _status_from_psi(psi)
        if not np.isnan(psi) and psi > worst_psi[1]:
            worst_psi = (feat, psi)
        results.append(
            FeatureDrift(
                feature=feat,
                psi=round(psi, 4) if not np.isnan(psi) else float("nan"),
                reference_n=ref_n,
                current_n=cur_n,
                reference_missing_share=round(ref_miss, 4),
                current_missing_share=round(cur_miss, 4),
                status=status,
            )
        )

    if "compliant" in reference.columns and "compliant" in current.columns:
        label_kl = _label_kl(reference["compliant"].dropna(), current["compliant"].dropna())
        label_status = _status_from_kl(label_kl)
    else:
        label_kl = float("nan")
        label_status = "skipped"

    per_feature_statuses = [r.status for r in results if r.status != "skipped"]
    if "alert" in per_feature_statuses or label_status == "alert":
        overall = "alert"
    elif "warn" in per_feature_statuses or label_status == "warn":
        overall = "warn"
    else:
        overall = "ok"

    return {
        "overall_status": overall,
        "label_kl": round(label_kl, 4) if not np.isnan(label_kl) else None,
        "label_status": label_status,
        "worst_feature": {"name": worst_psi[0], "psi": round(worst_psi[1], 4)} if worst_psi[0] else None,
        "thresholds": {"psi_warn": PSI_WARN, "psi_alert": PSI_ALERT, "kl_warn": KL_WARN, "kl_alert": KL_ALERT},
        "per_feature": [asdict(r) for r in results],
    }


def _filter_years(df: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    if "sample_date" not in df.columns:
        raise RuntimeError("sample_date column missing; drift_monitor requires engineered features")
    yr = pd.to_datetime(df["sample_date"], errors="coerce").dt.year
    return df[yr.isin(years)].copy()


def main() -> int:
    p = argparse.ArgumentParser(description="Drift monitor for water-quality features.")
    p.add_argument(
        "--reference-years",
        default="2021,2022,2023,2024",
        help="Comma-separated years used as the reference slice (training window).",
    )
    p.add_argument(
        "--current-year",
        default=None,
        help="Year used as the current slice; defaults to max(year) in the corpus.",
    )
    p.add_argument("--bins", type=int, default=DEFAULT_BINS)
    p.add_argument("--json-out", type=str, default=None, help="Write the full report to a JSON file.")
    p.add_argument(
        "--fail-on",
        choices=("never", "warn", "alert"),
        default="never",
        help="Exit with a non-zero status when the overall status reaches this level.",
    )
    args = p.parse_args()

    ref_years = [int(y.strip()) for y in args.reference_years.split(",") if y.strip()]
    raw = load_all()
    engineered = engineer_features(raw)

    if args.current_year is None:
        year_series = pd.to_datetime(engineered["sample_date"], errors="coerce").dt.year
        current_year = int(year_series.max())
    else:
        current_year = int(args.current_year)

    reference = _filter_years(engineered, ref_years)
    current = _filter_years(engineered, [current_year])

    if reference.empty or current.empty:
        print(
            f"[drift_monitor] Empty slice: reference={len(reference)} current={len(current)}",
            file=sys.stderr,
        )
        return 2

    report = compute_drift(reference, current, bins=args.bins)
    report["reference_years"] = ref_years
    report["current_year"] = current_year
    report["reference_n"] = len(reference)
    report["current_n"] = len(current)

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"[drift_monitor] report written: {args.json_out}")

    print(
        f"[drift_monitor] status={report['overall_status']} "
        f"label_kl={report['label_kl']} worst={report['worst_feature']}"
    )
    for r in report["per_feature"]:
        if r["status"] in ("warn", "alert"):
            print(
                f"  {r['status'].upper():5s} {r['feature']:20s} psi={r['psi']} "
                f"ref_miss={r['reference_missing_share']} cur_miss={r['current_missing_share']}"
            )

    exit_levels = {"never": None, "warn": {"warn", "alert"}, "alert": {"alert"}}
    fail_set = exit_levels[args.fail_on]
    if fail_set and report["overall_status"] in fail_set:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
