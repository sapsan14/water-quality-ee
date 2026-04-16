#!/usr/bin/env python
"""
full_corpus_audit.py — Run the deterministic label-vs-norms audit on the full
69k+ corpus from load_all() and produce structured output.

Usage:
    python scripts/full_corpus_audit.py
    python scripts/full_corpus_audit.py --out data/audit/full_corpus_divergences.csv

Requires data/raw/*.xml to be populated (run `python src/data_loader.py` first).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from audit.label_vs_norms import (
    BUCKETS,
    audit_dataframe,
    audit_dataframe_with_bathing_aggregation,
)
from data_loader import load_all


def run_full_audit(
    bathing_aggregation: bool = True,
    out_csv: Path | None = None,
    out_summary: Path | None = None,
) -> tuple[pd.DataFrame, dict]:

    print("Loading full corpus via load_all()...")
    df = load_all()
    print(f"Loaded {len(df)} probes across {df['domain'].nunique()} domains")

    labelled = df[df["compliant"].notna()]
    print(f"Labelled probes: {len(labelled)}")

    print("Running audit...")
    if bathing_aggregation:
        audited = audit_dataframe_with_bathing_aggregation(df)
    else:
        audited = audit_dataframe(df)

    n_labelled = int(audited["compliant"].notna().sum())
    bucket_counts = (
        audited["bucket"].value_counts().reindex(BUCKETS, fill_value=0).to_dict()
    )
    agree = bucket_counts["agree_pass"] + bucket_counts["agree_violate"]
    agree_rate = agree / n_labelled if n_labelled else float("nan")

    by_domain = (
        audited.groupby(["domain", "bucket"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=BUCKETS, fill_value=0)
    )

    hv = audited[audited["bucket"] == "hidden_violation"].copy()

    unmeasured_freq: dict[str, int] = {}
    for params_list in hv["unmeasured_norm_params"]:
        if isinstance(params_list, list):
            for p in params_list:
                unmeasured_freq[p] = unmeasured_freq.get(p, 0) + 1
    unmeasured_sorted = sorted(unmeasured_freq.items(), key=lambda x: -x[1])

    hv_n_measured = hv["n_measured_norm_params"].describe() if len(hv) > 0 else {}

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_total": len(audited),
        "n_labelled": n_labelled,
        "bucket_counts": bucket_counts,
        "agree_rate": round(agree_rate, 4),
        "self_check_pass": agree_rate >= 0.85,
        "by_domain": by_domain.to_dict(),
        "hidden_violation": {
            "total": int(bucket_counts.get("hidden_violation", 0)),
            "by_domain": hv["domain"].value_counts().to_dict() if len(hv) > 0 else {},
            "n_measured_stats": (
                {k: round(v, 2) for k, v in hv_n_measured.to_dict().items()}
                if hasattr(hv_n_measured, "to_dict")
                else {}
            ),
            "top_unmeasured_params": unmeasured_sorted[:15],
            "zero_measured_count": int((hv["n_measured_norm_params"] == 0).sum())
            if len(hv) > 0
            else 0,
        },
        "hidden_pass": {
            "total": int(bucket_counts.get("hidden_pass", 0)),
            "by_domain": audited[audited["bucket"] == "hidden_pass"]["domain"]
            .value_counts()
            .to_dict(),
        },
    }

    print("\n" + "=" * 60)
    print("FULL CORPUS AUDIT RESULTS")
    print("=" * 60)
    print(f"Total probes:    {summary['n_total']:,}")
    print(f"Labelled probes: {summary['n_labelled']:,}")
    print(f"Agree rate:      {summary['agree_rate']:.4f}")
    print(f"Self-check (≥85%): {'PASS' if summary['self_check_pass'] else 'FAIL'}")
    print()
    print("Buckets (overall):")
    for b in BUCKETS:
        c = bucket_counts[b]
        pct = c / n_labelled * 100 if n_labelled else 0
        print(f"  {b:<20s}: {c:>7,}  ({pct:5.1f}%)")
    print()
    print("Buckets by domain:")
    print(by_domain.to_string())
    print()
    print(f"Hidden violation: {summary['hidden_violation']['total']:,}")
    print(f"  zero-measured probes: {summary['hidden_violation']['zero_measured_count']}")
    print(f"  by domain: {summary['hidden_violation']['by_domain']}")
    print(f"  top unmeasured params:")
    for param, count in unmeasured_sorted[:10]:
        pct = count / max(len(hv), 1) * 100
        print(f"    {param:<25s}: {count:>5}  ({pct:5.1f}%)")

    if out_csv:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        divergences = audited[
            audited["bucket"].isin(["hidden_violation", "hidden_pass"])
        ].copy()
        for col in ("violated_params", "unmeasured_norm_params"):
            if col in divergences.columns:
                divergences[col] = divergences[col].apply(
                    lambda xs: "|".join(xs) if isinstance(xs, list) else ""
                )
        cols_to_keep = [
            c
            for c in [
                "sample_id",
                "domain",
                "location",
                "location_key",
                "county",
                "sample_date",
                "compliant",
                "bucket",
                "norms_violation",
                "violated_params",
                "unmeasured_norm_params",
                "n_measured_norm_params",
            ]
            if c in divergences.columns
        ]
        divergences[cols_to_keep].to_csv(out_csv, index=False)
        print(f"\nDivergences CSV: {out_csv} ({len(divergences):,} rows)")

    if out_summary:
        out_summary.parent.mkdir(parents=True, exist_ok=True)
        serializable = json.loads(
            json.dumps(summary, default=str)
        )
        with open(out_summary, "w") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        print(f"Summary JSON:    {out_summary}")

    # Also output the top 20 hidden_violation probes for inquiry reference
    if len(hv) > 0:
        print(f"\n{'='*60}")
        print("TOP 20 HIDDEN VIOLATION PROBES (by n_measured desc)")
        print("=" * 60)
        top = hv.nlargest(20, "n_measured_norm_params")
        for _, row in top.iterrows():
            loc = str(row.get("location", ""))[:50]
            sid = row.get("sample_id", "?")
            dom = row.get("domain", "?")
            nm = row.get("n_measured_norm_params", 0)
            dt = str(row.get("sample_date", ""))[:10]
            um = row.get("unmeasured_norm_params", [])
            um_str = ", ".join(um[:5]) if isinstance(um, list) else ""
            print(f"  sid {sid:<10} {dom:12} {dt}  n_meas={nm:>2}  {loc}")
            if um_str:
                print(f"    unmeasured: {um_str}")

    return audited, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "audit" / "full_corpus_divergences.csv",
    )
    ap.add_argument(
        "--summary",
        type=Path,
        default=REPO_ROOT / "data" / "audit" / "full_corpus_summary.json",
    )
    ap.add_argument("--no-bathing-aggregation", action="store_true")
    args = ap.parse_args()

    run_full_audit(
        bathing_aggregation=not args.no_bathing_aggregation,
        out_csv=args.out,
        out_summary=args.summary,
    )


if __name__ == "__main__":
    main()
