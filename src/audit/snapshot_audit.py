"""
snapshot_audit.py — Run `audit_dataframe` against `citizen-service/artifacts/snapshot.json`.

Why this exists
---------------
The canonical audit input is `load_all()` from `data_loader.py`, which pulls
fresh year files from `vtiav.sm.ee` and produces ~tens of thousands of probes
across multiple years per domain. That is what `notebooks/07_data_gaps_audit.ipynb`
is wired against.

In environments where the live opendata feed is unreachable (sandboxed CI,
offline review, agent runs), the only persisted real-world dataset shipped
with the repository is the citizen-service snapshot at
`citizen-service/artifacts/snapshot.json`. This is one *latest* probe per
location across the four mapped domains — significantly smaller than the
full corpus (≈2 200 probes vs ≈40 k+) but still real Terviseamet data with
real `official_compliant` labels and real measurement values.

This module loads that snapshot into a DataFrame whose columns match what
`audit.label_vs_norms.audit_dataframe` expects, runs the deterministic
checker, and returns the audited DataFrame plus a small summary dict.

It is the same code path that the notebook uses, just with a different
data source. Anything we learn from this subset is qualitatively informative
about the full corpus but quantitatively must be reported as
"latest-per-location subset (n=2194)" — see `docs/phase_10_findings.md`
for the framing.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from audit.label_vs_norms import (
    BUCKETS,
    audit_dataframe,
    audit_dataframe_with_bathing_aggregation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SNAPSHOT = REPO_ROOT / "citizen-service" / "artifacts" / "snapshot.json"


def load_snapshot_as_dataframe(
    snapshot_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Load the citizen-service snapshot JSON into a DataFrame compatible with
    `audit.label_vs_norms.audit_dataframe`.

    The output frame has one row per `places[i]` entry, with columns:
        sample_id, location, domain, county, sample_date, compliant,
        plus one column per measurement key present anywhere in the snapshot
        (e_coli, enterococci, ph, turbidity, coliforms, ...). Missing
        measurements are NaN.

    Locations missing from the snapshot's `measurements` block (e.g.
    coordinate-only review queue entries) are still emitted; their measurement
    columns are simply NaN. The audit checker will bucket them under
    `unknown` if the label is also missing, otherwise as `agree_pass`
    (no measurement → no detected violation).
    """
    path = snapshot_path or DEFAULT_SNAPSHOT
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    places = data.get("places") or []
    rows = []
    for p in places:
        m = p.get("measurements") or {}
        row: Dict[str, object] = {
            "sample_id": p.get("sample_id"),
            "location": p.get("location"),
            "domain": p.get("domain"),
            "county": p.get("county"),
            "sample_date": p.get("sample_date"),
            "compliant": p.get("official_compliant"),
        }
        # Flatten all measurement keys observed anywhere in the snapshot.
        for k, v in m.items():
            row[k] = v
        rows.append(row)

    df = pd.DataFrame(rows)

    # Coerce every measurement column to numeric (some come as strings or None).
    measurement_cols = [
        c
        for c in df.columns
        if c
        not in {
            "sample_id",
            "location",
            "domain",
            "county",
            "sample_date",
            "compliant",
        }
    ]
    for col in measurement_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "sample_date" in df.columns:
        df["sample_date"] = pd.to_datetime(df["sample_date"], errors="coerce")

    return df


def summarise_audit(audited: pd.DataFrame) -> Dict[str, object]:
    """
    Compact summary of an audited DataFrame for logs and report tables.
    """
    n_total = len(audited)
    n_labelled = int(audited["compliant"].notna().sum())
    bucket_counts = audited["bucket"].value_counts().reindex(BUCKETS, fill_value=0).to_dict()

    # agree rate over labelled probes (self-check threshold for the audit
    # is 85 % — see docs/data_gaps.md "Double-verification stance").
    if n_labelled > 0:
        agree = bucket_counts["agree_pass"] + bucket_counts["agree_violate"]
        agree_rate = agree / n_labelled
    else:
        agree_rate = float("nan")

    by_domain = (
        audited.groupby(["domain", "bucket"]).size().unstack(fill_value=0).reindex(columns=BUCKETS, fill_value=0)
    )

    return {
        "n_total": n_total,
        "n_labelled": n_labelled,
        "bucket_counts": bucket_counts,
        "agree_rate": agree_rate,
        "by_domain": by_domain,
    }


def run_snapshot_audit(
    snapshot_path: Optional[Path] = None,
    out_parquet: Optional[Path] = None,
    bathing_aggregation: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """
    Convenience entry point: load → audit → optional persist → summary.

    Parameters
    ----------
    snapshot_path
        Citizen-service snapshot JSON; defaults to the bundled artifact.
    out_parquet
        Optional parquet output path.
    bathing_aggregation
        If True, run `audit_dataframe_with_bathing_aggregation` instead of
        `audit_dataframe`. On the snapshot (one probe per location) this is
        a no-op for `domain == 'supluskoha'`, but keeps the entry point
        ready for full-corpus audits via `data_loader.load_all()`.

    Returns
    -------
    audited
        DataFrame from `audit_dataframe(...)` plus the original snapshot rows.
    summary
        Output of `summarise_audit(...)`.
    """
    df = load_snapshot_as_dataframe(snapshot_path)
    if bathing_aggregation:
        audited = audit_dataframe_with_bathing_aggregation(df)
    else:
        audited = audit_dataframe(df)
    summary = summarise_audit(audited)

    if out_parquet is not None:
        out_parquet.parent.mkdir(parents=True, exist_ok=True)
        # Lists in audit columns must be turned into JSON-friendly form
        # because the default arrow writer rejects mixed object types.
        persisted = audited.copy()
        for col in ("violated_params", "unmeasured_norm_params"):
            if col in persisted.columns:
                persisted[col] = persisted[col].apply(
                    lambda xs: ",".join(xs) if isinstance(xs, list) else ""
                )
        persisted.to_parquet(out_parquet, index=False)

    return audited, summary


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT,
        help="Path to citizen-service snapshot JSON (default: %(default)s)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT
        / "data"
        / "audit"
        / f"divergences_snapshot_{datetime.utcnow().strftime('%Y-%m-%d')}.parquet",
        help="Parquet output path",
    )
    ap.add_argument(
        "--bathing-aggregation",
        action="store_true",
        help="Apply EU 2006/7/EC 95-percentile aggregation per (location_key × season) for supluskoha rows",
    )
    args = ap.parse_args()

    audited, summary = run_snapshot_audit(
        args.snapshot,
        out_parquet=args.out,
        bathing_aggregation=args.bathing_aggregation,
    )

    print("=== snapshot label-vs-norms audit ===")
    print(f"snapshot   : {args.snapshot}")
    print(f"n_total    : {summary['n_total']}")
    print(f"n_labelled : {summary['n_labelled']}")
    print(f"agree_rate : {summary['agree_rate']:.4f}")
    print()
    print("buckets (overall):")
    for b in BUCKETS:
        print(f"  {b:<18s}: {summary['bucket_counts'][b]}")
    print()
    print("buckets by domain:")
    print(summary["by_domain"].to_string())
    print()
    print(f"wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
