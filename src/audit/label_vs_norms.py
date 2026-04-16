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
- `coliforms`: phase 10 added a `coliforms > 0 → violation` rule to the audit
  checker. This rule is **NOT** mirrored in `features.add_ratio_features`,
  which is the first known divergence between audit and model features.
  Rationale: `coliforms` is published in 1439/2194 snapshot probes (the
  most-measured chemistry parameter); 13 veevark probes labelled non-compliant
  carry `coliforms > 0` and zero other violations under the published params.
  Without this rule those would be hidden_violation forever. Adding the same
  rule to `add_ratio_features` requires a `coliforms_detected` feature and a
  model retrain — that is Phase 11 work. See `docs/phase_10_findings.md` § R2.
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

# Parameters that have a "any positive count → violation" rule across all
# non-bathing domains. EU 2006/7/EC bathing-water directive does NOT regulate
# coliform bacteria — only e_coli and enterococci — so supluskoha probes are
# excluded from this rule. Drinking water (veevark, joogivesi) and pool
# (basseinid) regulations both require coliforms = 0.
_DETECTION_PARAMS_NON_BATHING: List[str] = ["coliforms"]


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
    is_bathing = (domain == "supluskoha")

    # Build the set of parameters we will check for this domain.
    norm_params: List[str] = list(_THRESHOLD_PARAMS)
    if is_pool:
        norm_params = norm_params + _POOL_ONLY_PARAMS
    # Phase 10 R2: coliforms = 0 rule applies to non-bathing domains.
    if not is_bathing:
        norm_params = norm_params + _DETECTION_PARAMS_NON_BATHING
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

        if param == "coliforms":
            # Phase 10 R2: detection rule for non-bathing domains.
            # Audit-only (not yet mirrored in features.add_ratio_features).
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


# ── Phase 10 R3: EU 2006/7/EC bathing-water 95-percentile aggregation ─────────

# Bathing-water class thresholds for inland waters, per EU 2006/7/EC Annex I
# Table 1. For binary compliance the project labels everything below "Poor"
# as compliant, so we apply the 95th-percentile rule against the "Sufficient"
# threshold (E. coli ≤ 900 / enterococci ≤ 330, the boundary where a site
# stops being officially acceptable).
_BATHING_E_COLI_P95_MAX_INLAND = 900.0       # CFU/100 mL
_BATHING_ENTEROCOCCI_P95_MAX_INLAND = 330.0  # CFU/100 mL


def _bathing_season_year(date) -> Optional[int]:
    """Calendar-year bucket. EU directive evaluates over multi-year windows;
    for an interim audit we use single calendar-year buckets per location.

    Returns None for NaT.
    """
    if date is None or (hasattr(date, "year") is False) or pd.isna(date):
        return None
    return int(date.year)


def audit_dataframe_with_bathing_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Same as `audit_dataframe`, but for `domain == 'supluskoha'` rows the
    `e_coli` and `enterococci` per-probe checks are replaced with a
    per-(location_key × calendar year) 95-percentile check per EU 2006/7/EC.

    The per-probe verdict for non-bathing rows is unchanged.

    Why
    ---
    EU 2006/7/EC classifies bathing waters by percentile evaluation over a
    multi-season window, not by single-probe pass/fail. Our default checker
    flags any single sample with `e_coli > 500` (the "Excellent" threshold),
    which over-counts violations on bathing waters: a site with one spike
    inside an otherwise clean season is officially compliant under the
    directive but `hidden_pass` under the per-probe rule.

    This aggregator implements the per-(location × season) 95-percentile rule
    so that the per-probe "spike" no longer turns into a hidden_pass.

    Requirements
    ------------
    The input DataFrame must include `location_key` (use `data_loader.normalize_location`)
    and `sample_date`. Rows missing either are kept under per-probe verdicts
    (no aggregation possible).

    Practical scope
    ---------------
    On the citizen-service snapshot (one latest probe per location) the
    aggregator is a no-op: 95-percentile of a single value equals the value
    itself. The function is wired up so that running the audit notebook
    against the *full* multi-year corpus from `load_all()` produces the
    correct `supluskoha` numbers without further code changes. See
    `docs/phase_10_findings.md` § R3.
    """
    audited = audit_dataframe(df)

    if "location_key" not in audited.columns or "sample_date" not in audited.columns:
        return audited

    bathing_mask = audited["domain"] == "supluskoha"
    bathing = audited.loc[bathing_mask].copy()
    if bathing.empty:
        return audited

    bathing["bathing_season"] = bathing["sample_date"].apply(_bathing_season_year)
    can_aggregate = bathing["location_key"].notna() & bathing["bathing_season"].notna()
    aggregable = bathing.loc[can_aggregate]
    if aggregable.empty:
        return audited

    # For each (location_key, season) bucket compute 95p of the indicators.
    by_group = aggregable.groupby(["location_key", "bathing_season"])
    e_coli_p95 = by_group["e_coli"].quantile(0.95) if "e_coli" in aggregable.columns else None
    entero_p95 = (
        by_group["enterococci"].quantile(0.95) if "enterococci" in aggregable.columns else None
    )

    def _aggregated_violation(row: pd.Series) -> Optional[bool]:
        key = (row["location_key"], row["bathing_season"])
        ec = e_coli_p95.get(key) if e_coli_p95 is not None else None
        en = entero_p95.get(key) if entero_p95 is not None else None
        ec_violates = (ec is not None) and (not pd.isna(ec)) and (ec > _BATHING_E_COLI_P95_MAX_INLAND)
        en_violates = (en is not None) and (not pd.isna(en)) and (en > _BATHING_ENTEROCOCCI_P95_MAX_INLAND)
        return bool(ec_violates or en_violates)

    aggregable_index = aggregable.index
    aggregated_verdict = aggregable.apply(_aggregated_violation, axis=1)

    # Override the supluskoha rows: replace per-probe verdict with aggregated
    # one and recompute the bucket. Other domains are untouched.
    audited.loc[aggregable_index, "norms_violation"] = aggregated_verdict
    if "compliant" in audited.columns:
        audited.loc[aggregable_index, "bucket"] = [
            bucket_name(c, v)
            for c, v in zip(
                audited.loc[aggregable_index, "compliant"],
                aggregated_verdict,
            )
        ]

    return audited
