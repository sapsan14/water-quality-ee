#!/usr/bin/env python
"""
temporal_hidden_violation_analysis.py — Evaluate hypothesis #3 (measurement
frequency variance) by cross-referencing hidden_violation probes against
all other probes at the same (location_key, domain).

For each hidden_violation probe's unmeasured parameter, checks whether the
same parameter has a non-null value in ANY other probe at the same site.

    never_measured_at_site     → supports hypothesis #1 (partial publication)
    measured_elsewhere_at_site → supports hypothesis #3 (frequency variance)

Usage:
    python scripts/temporal_hidden_violation_analysis.py
    python scripts/temporal_hidden_violation_analysis.py --out data/audit/temporal_analysis_summary.json

Requires cached XML in data/raw/ (run `python src/data_loader.py` first).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from data_loader import load_all
from audit.label_vs_norms import audit_dataframe
from features import NORMS

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "audit" / "temporal_analysis_summary.json"

# Parameters with norms that the checker evaluates.
_NORM_PARAMS = [p for p in NORMS.keys() if p not in ("ph_min", "ph_max")] + ["ph", "coliforms"]
_POOL_EXTRA = ["staphylococci", "pseudomonas", "free_chlorine", "combined_chlorine"]


def run_temporal_analysis(df: pd.DataFrame = None):
    if df is None:
        df = load_all()
    print(f"Loaded: {len(df)} probes")

    audited = audit_dataframe(df)
    hv = audited[audited["bucket"] == "hidden_violation"].copy()
    print(f"hidden_violation: {len(hv)}")

    # Build "ever measured" lookup per (location_key, domain)
    site_measured = {}
    for (lk, dom), grp in audited.groupby(["location_key", "domain"]):
        params = list(_NORM_PARAMS) + (_POOL_EXTRA if dom == "basseinid" else [])
        ever = {p for p in params if p in grp.columns and grp[p].notna().any()}
        site_measured[(lk, dom)] = ever

    # Classify each unmeasured param
    results = []
    for _, row in hv.iterrows():
        lk, dom = row.get("location_key"), row["domain"]
        unmeasured = row.get("unmeasured_norm_params", "")
        if isinstance(unmeasured, list):
            params = unmeasured
        else:
            params = [p.strip() for p in str(unmeasured).split(",") if p.strip()]

        ever = site_measured.get((lk, dom), set())
        for param in params:
            results.append({
                "sample_id": row["sample_id"],
                "domain": dom,
                "location_key": lk,
                "month": row["sample_date"].month if pd.notna(row.get("sample_date")) else None,
                "param": param,
                "classification": "measured_elsewhere_at_site" if param in ever else "never_measured_at_site",
            })

    rdf = pd.DataFrame(results)

    # Summary
    total = len(rdf)
    h1 = (rdf["classification"] == "never_measured_at_site").sum()
    h3 = (rdf["classification"] == "measured_elsewhere_at_site").sum()
    h1_pct = round(h1 / total * 100, 1) if total else 0
    h3_pct = round(h3 / total * 100, 1) if total else 0

    print(f"\nOverall: H1={h1} ({h1_pct}%), H3={h3} ({h3_pct}%)")

    by_domain = {}
    for dom in ["basseinid", "veevark", "supluskoha", "joogivesi"]:
        sub = rdf[rdf["domain"] == dom]
        if sub.empty:
            continue
        n1 = int((sub["classification"] == "never_measured_at_site").sum())
        n3 = int((sub["classification"] == "measured_elsewhere_at_site").sum())
        by_domain[dom] = {
            "n_probes": int(sub["sample_id"].nunique()),
            "never_measured": n1,
            "measured_elsewhere": n3,
            "h3_pct": round(n3 / len(sub) * 100, 1) if len(sub) else 0,
        }
        print(f"  [{dom}] H1={n1}, H3={n3} ({by_domain[dom]['h3_pct']}%)")

    monthly = hv["sample_date"].dt.month.value_counts().sort_index().to_dict()
    verdict = "H3_strongly_supported" if h3_pct > 30 else ("H3_moderate" if h3_pct > 10 else "H1_dominates")

    summary = {
        "n_hidden_violation_probes": int(len(hv)),
        "n_param_instances": total,
        "h1_pct": h1_pct,
        "h3_pct": h3_pct,
        "verdict": verdict,
        "by_domain": by_domain,
        "monthly_distribution": {str(k): v for k, v in monthly.items()},
    }
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    summary = run_temporal_analysis()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nVerdict: {summary['verdict']}")
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
