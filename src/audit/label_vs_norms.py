"""
label_vs_norms.py — Deterministic per-probe norm checker.

PURPOSE
-------
Re-derive the expected `compliant` label for every probe from the *published*
parameter values alone, using the exact norm tables that `features.add_ratio_features`
consumes. Any probe where the deterministic verdict disagrees with the official
`hinnang`-derived `compliant` label is direct evidence that the open-data slice
published by Terviseamet cannot by itself reproduce the compliance decision.

This is the evidence base for `docs/data_gaps.md` and for the draft engineering
inquiry in `docs/terviseamet_inquiry.md`.

DESIGN NOTES
------------
1. **Single source of truth.** We import `NORMS` and `NORMS_POOL` from
   `features.py` directly. If the feature thresholds ever change, the audit
   follows automatically — there is no second copy of the numbers to drift.

2. **Logic mirrors `features.add_ratio_features`.** The ratio features the
   model consumes apply norms per-parameter with a domain override only for
   `turbidity`, plus pool-only `staphylococci`/`pseudomonas`/`free_chlorine`/
   `combined_chlorine`. We replicate exactly that decision surface so that
   "the model sees X as a violation" and "the checker marks X as violating"
   cannot diverge from pipeline bugs. Known consequence: the pool-stricter
   `e_coli = 0` / `coliforms = 0` rules from `NORMS_POOL` are **not** applied
   here, matching the fact that `add_ratio_features` does not apply them
   either. See the "Caveats" section below.

3. **Single-probe approximation for bathing waters.** EU 2006/7/EC classifies
   bathing waters on a 90/95-percentile over multi-season samples — not
   per-probe. Our check is per-probe. That means for `domain == 'supluskoha'`
   a "hidden_pass" result (one spike, still officially compliant) is expected
   behaviour of the directive, not evidence of a data gap. Down-stream
   analysis in `notebooks/07_data_gaps_audit.ipynb` reports `supluskoha`
   separately for this reason.

4. **What a "hidden_violation" means.** `compliant == 0` (Terviseamet says
   non-compliant) but no published parameter exceeds its norm. This is the
   signal the reflection note at
   `sapsan14/life:reflect/2026-04-15_health-data-gaps.md` is about.

Caveats
-------
- `e_coli` norm is 500 CFU/100 mL from `NORMS`. That is the bathing-water
  threshold; drinking-water directive 2020/2184 is stricter (0 CFU/100 mL).
  The model's features do not distinguish, and neither does this checker.
  Drinking-water probes with `e_coli` in (0, 500] will register as compliant
  by the checker even if they are technically non-compliant under 2020/2184.
- `transparency` has no norm and is not checked.
- `coliforms` has no norm in `NORMS` and is not checked (only the pool
  `NORMS_POOL["coliforms"] = 0` entry exists, and — per note 2 above — is
  intentionally not applied to stay in sync with `add_ratio_features`).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from features import NORMS, NORMS_POOL


# Parameters in NORMS that are actually used as scalar max-thresholds in
# add_ratio_features (i.e. everything except the pH range keys).
_THRESHOLD_PARAMS: List[str] = [
    p for p in NORMS.keys() if p not in ("ph_min", "ph_max")
]

# Pool-only parameters checked when domain == 'basseinid'.
_POOL_ONLY_PARAMS: List[str] = [
    "staphylococci",
    "pseudomonas",
    "free_chlorine",
    "combined_chlorine",
]


def _is_pool(domain: Optional[str]) -> bool:
    return domain == "basseinid"


def _threshold_for(param: str, is_pool: bool) -> float:
    """Return the threshold used by add_ratio_features for this (param, domain)."""
    if param == "turbidity" and is_pool:
        return NORMS_POOL["turbidity"]
    return NORMS[param]


def _ph_range(is_pool: bool) -> tuple[float, float]:
    if is_pool:
        return NORMS_POOL["ph_min"], NORMS_POOL["ph_max"]
    return NORMS["ph_min"], NORMS["ph_max"]


def check_probe(row: pd.Series) -> Dict[str, object]:
    """
    Check one probe against the norm tables used by the model's ratio features.

    Parameters
    ----------
    row
        A pandas Series with at least a `domain` field plus whichever measured
        parameter columns exist (e_coli, iron, ph, ...). Missing columns are
        treated as "not measured".

    Returns
    -------
    dict with keys:
        domain                    : str or None
        is_pool                   : bool
        measured_params           : list[str]  — params with a numeric value
        violated_params           : list[str]  — measured params exceeding norm
        unmeasured_norm_params    : list[str]  — params that HAVE a norm but were not measured
        any_violation             : bool       — any measured param violated its norm
        n_params_with_norm        : int        — size of the domain's norm set
        n_measured                : int        — |measured_params ∩ norm set|
    """
    domain = row.get("domain")
    is_pool = _is_pool(domain)

    # Build the set of parameters we will check for this domain.
    norm_params: List[str] = list(_THRESHOLD_PARAMS)
    if is_pool:
        norm_params = norm_params + _POOL_ONLY_PARAMS
    # pH is checked separately (range, not scalar). Include in the "norm set"
    # bookkeeping under the name "ph".
    norm_params.append("ph")

    measured: List[str] = []
    violated: List[str] = []
    unmeasured: List[str] = []

    for param in norm_params:
        val = row.get(param)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            unmeasured.append(param)
            continue

        measured.append(param)

        if param == "ph":
            lo, hi = _ph_range(is_pool)
            if val < lo or val > hi:
                violated.append(param)
            continue

        if param == "free_chlorine":
            # Range rule: below min or above max is a violation.
            if val < NORMS_POOL["free_chlorine_min"] or val > NORMS_POOL["free_chlorine_max"]:
                violated.append(param)
            continue

        if param == "combined_chlorine":
            if val > NORMS_POOL["combined_chlorine"]:
                violated.append(param)
            continue

        if param == "pseudomonas":
            # norm = 0 CFU; any positive count is a violation.
            if val > 0:
                violated.append(param)
            continue

        if param == "staphylococci":
            if val > NORMS_POOL["staphylococci"]:
                violated.append(param)
            continue

        # Default: scalar max threshold (same rule the ratio feature uses).
        threshold = _threshold_for(param, is_pool)
        if val > threshold:
            violated.append(param)

    return {
        "domain": domain,
        "is_pool": is_pool,
        "measured_params": measured,
        "violated_params": violated,
        "unmeasured_norm_params": unmeasured,
        "any_violation": len(violated) > 0,
        "n_params_with_norm": len(norm_params),
        "n_measured": len(measured),
    }


# ── DataFrame-level audit ────────────────────────────────────────────────────

BUCKETS = ("agree_pass", "agree_violate", "hidden_violation", "hidden_pass", "unknown")


def bucket_name(compliant: Optional[float], any_violation: bool) -> str:
    """
    Four-way bucketing of (official label, deterministic verdict).

    agree_pass       : label = compliant (1), checker = no violation
    agree_violate    : label = violation (0), checker = violation
    hidden_violation : label = violation (0), checker = no violation
                       → evidence that open-data alone cannot reproduce label
    hidden_pass      : label = compliant (1), checker = violation
                       → threshold interpretation / aggregation rule gap
    unknown          : label is NaN (hinnang absent in source XML)
    """
    if compliant is None or (isinstance(compliant, float) and np.isnan(compliant)):
        return "unknown"
    if int(compliant) == 1:
        return "hidden_pass" if any_violation else "agree_pass"
    return "agree_violate" if any_violation else "hidden_violation"


def audit_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply `check_probe` row-wise and attach audit columns.

    Adds columns:
        norms_violation           : bool
        violated_params           : list[str]
        unmeasured_norm_params    : list[str]
        n_measured_norm_params    : int
        bucket                    : str  (see `bucket_name`)

    The input DataFrame must include a `domain` column and ideally a
    `compliant` column; if `compliant` is missing, the bucket is "unknown".
    """
    if "domain" not in df.columns:
        raise ValueError("audit_dataframe requires a 'domain' column")

    verdicts = df.apply(check_probe, axis=1)

    out = df.copy()
    out["norms_violation"] = verdicts.apply(lambda d: d["any_violation"]).astype(bool)
    out["violated_params"] = verdicts.apply(lambda d: d["violated_params"])
    out["unmeasured_norm_params"] = verdicts.apply(lambda d: d["unmeasured_norm_params"])
    out["n_measured_norm_params"] = verdicts.apply(lambda d: d["n_measured"]).astype(int)

    if "compliant" in out.columns:
        out["bucket"] = [
            bucket_name(c, v) for c, v in zip(out["compliant"], out["norms_violation"])
        ]
    else:
        out["bucket"] = "unknown"

    return out
