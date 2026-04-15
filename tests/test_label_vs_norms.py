"""Unit tests for src/audit/label_vs_norms.py — deterministic label checker."""

import numpy as np
import pandas as pd
import pytest

from audit.label_vs_norms import (
    audit_dataframe,
    bucket_name,
    check_probe,
)
from features import NORMS, NORMS_POOL


# ── check_probe: clear compliant cases ──────────────────────────────────────


def test_clean_drinking_water_probe_is_compliant():
    row = pd.Series(
        {
            "domain": "veevark",
            "e_coli": 0.0,
            "coliforms": 0.0,
            "ph": 7.2,
            "iron": 0.05,
            "manganese": 0.01,
            "turbidity": 0.4,
            "color": 5.0,
            "nitrates": 10.0,
        }
    )
    verdict = check_probe(row)
    assert verdict["any_violation"] is False
    assert verdict["violated_params"] == []
    assert "e_coli" in verdict["measured_params"]
    assert "ph" in verdict["measured_params"]
    # Unmeasured drinking-water params (e.g. fluoride, chlorides) should be listed.
    assert "fluoride" in verdict["unmeasured_norm_params"]


def test_clean_bathing_water_probe_is_compliant():
    row = pd.Series(
        {
            "domain": "supluskoha",
            "e_coli": 150.0,  # below 500
            "enterococci": 50.0,  # below 200
            "ph": 7.8,
        }
    )
    verdict = check_probe(row)
    assert verdict["any_violation"] is False
    assert "e_coli" in verdict["measured_params"]
    assert "enterococci" in verdict["measured_params"]


# ── check_probe: clear violation cases ──────────────────────────────────────


def test_drinking_water_probe_with_high_ecoli_violates():
    row = pd.Series({"domain": "veevark", "e_coli": 10_000.0})
    verdict = check_probe(row)
    assert verdict["any_violation"] is True
    assert "e_coli" in verdict["violated_params"]


def test_iron_over_threshold_violates():
    row = pd.Series({"domain": "veevark", "iron": 0.5})  # norm 0.2
    verdict = check_probe(row)
    assert "iron" in verdict["violated_params"]


def test_ph_below_range_violates_via_range_check():
    row = pd.Series({"domain": "veevark", "ph": 5.5})
    verdict = check_probe(row)
    assert "ph" in verdict["violated_params"]
    assert verdict["any_violation"] is True


def test_ph_above_range_violates():
    row = pd.Series({"domain": "veevark", "ph": 9.5})
    verdict = check_probe(row)
    assert "ph" in verdict["violated_params"]


# ── check_probe: domain-conditional thresholds (pool vs drinking) ───────────


def test_pool_turbidity_uses_stricter_norm_than_drinking():
    """0.8 NTU passes drinking-water norm (4.0) but fails pool norm (0.5)."""
    drinking = pd.Series({"domain": "veevark", "turbidity": 0.8})
    pool = pd.Series({"domain": "basseinid", "turbidity": 0.8})

    assert check_probe(drinking)["any_violation"] is False
    pool_verdict = check_probe(pool)
    assert pool_verdict["any_violation"] is True
    assert "turbidity" in pool_verdict["violated_params"]


def test_pool_ph_range_is_tighter_than_drinking():
    """pH 9.2 passes drinking (6.0–9.0 — no wait, 9.2 > 9.0). Use 8.8 instead."""
    # 8.8 — passes drinking (6–9) but fails pool (6.5–8.5)
    drinking = pd.Series({"domain": "veevark", "ph": 8.8})
    pool = pd.Series({"domain": "basseinid", "ph": 8.8})
    assert check_probe(drinking)["any_violation"] is False
    assert "ph" in check_probe(pool)["violated_params"]


def test_pool_free_chlorine_range_violation_low():
    row = pd.Series({"domain": "basseinid", "free_chlorine": 0.1})  # below 0.2
    assert "free_chlorine" in check_probe(row)["violated_params"]


def test_pool_free_chlorine_range_violation_high():
    row = pd.Series({"domain": "basseinid", "free_chlorine": 0.8})  # above 0.6
    assert "free_chlorine" in check_probe(row)["violated_params"]


def test_pool_free_chlorine_in_range_is_compliant():
    row = pd.Series({"domain": "basseinid", "free_chlorine": 0.4})
    assert "free_chlorine" not in check_probe(row)["violated_params"]


def test_pool_pseudomonas_any_count_violates():
    row = pd.Series({"domain": "basseinid", "pseudomonas": 5.0})
    verdict = check_probe(row)
    assert "pseudomonas" in verdict["violated_params"]


def test_pool_staphylococci_over_threshold_violates():
    row = pd.Series({"domain": "basseinid", "staphylococci": 50.0})  # norm 20
    assert "staphylococci" in check_probe(row)["violated_params"]


def test_drinking_domain_ignores_pool_only_params():
    """Pool-only params must not be evaluated when domain != basseinid."""
    row = pd.Series(
        {
            "domain": "veevark",
            "pseudomonas": 100.0,  # would violate pool rule, should be ignored
            "staphylococci": 500.0,
            "e_coli": 0.0,
        }
    )
    verdict = check_probe(row)
    assert verdict["any_violation"] is False
    assert "pseudomonas" not in verdict["measured_params"]


# ── check_probe: missing values and unmeasured norm params ─────────────────


def test_nan_values_are_unmeasured_not_violations():
    row = pd.Series(
        {
            "domain": "veevark",
            "e_coli": np.nan,
            "iron": np.nan,
            "ph": 7.0,
        }
    )
    verdict = check_probe(row)
    assert verdict["any_violation"] is False
    assert "e_coli" in verdict["unmeasured_norm_params"]
    assert "iron" in verdict["unmeasured_norm_params"]
    assert verdict["n_measured"] == 1  # only pH was measured


def test_n_measured_counts_only_norm_params_with_values():
    row = pd.Series(
        {
            "domain": "veevark",
            "e_coli": 10.0,
            "iron": 0.05,
            "ph": 7.0,
        }
    )
    verdict = check_probe(row)
    assert verdict["n_measured"] == 3


# ── bucket_name: 4-way classification logic ─────────────────────────────────


def test_bucket_agree_pass():
    assert bucket_name(1, False) == "agree_pass"


def test_bucket_agree_violate():
    assert bucket_name(0, True) == "agree_violate"


def test_bucket_hidden_violation():
    """Label = non-compliant, but checker found no published violation.
    This is the 'reflection note' case — the whole point of the audit."""
    assert bucket_name(0, False) == "hidden_violation"


def test_bucket_hidden_pass():
    assert bucket_name(1, True) == "hidden_pass"


def test_bucket_unknown_when_label_missing():
    assert bucket_name(None, False) == "unknown"
    assert bucket_name(np.nan, True) == "unknown"


# ── audit_dataframe: end-to-end on a small frame ────────────────────────────


def test_audit_dataframe_end_to_end():
    df = pd.DataFrame(
        {
            "domain": ["veevark", "veevark", "veevark", "basseinid"],
            "compliant": [1, 0, 0, 1],
            "e_coli": [0.0, 10_000.0, 0.0, 0.0],
            "iron": [0.05, 0.05, 0.05, np.nan],
            "ph": [7.2, 7.2, 7.2, 8.8],  # last one fails pool range
            "turbidity": [0.4, 0.4, 0.4, 0.3],
        }
    )
    out = audit_dataframe(df)

    assert list(out["bucket"]) == [
        "agree_pass",  # compliant=1, no violation
        "agree_violate",  # compliant=0, e_coli violation
        "hidden_violation",  # compliant=0, nothing violates — the signal we care about
        "hidden_pass",  # compliant=1, ph out of pool range
    ]
    assert out["norms_violation"].tolist() == [False, True, False, True]
    assert "e_coli" in out["violated_params"].iloc[1]
    assert "ph" in out["violated_params"].iloc[3]


def test_audit_dataframe_requires_domain_column():
    df = pd.DataFrame({"e_coli": [1.0]})
    with pytest.raises(ValueError, match="domain"):
        audit_dataframe(df)


def test_audit_dataframe_handles_missing_compliant_column():
    df = pd.DataFrame({"domain": ["veevark"], "e_coli": [0.0]})
    out = audit_dataframe(df)
    assert out["bucket"].iloc[0] == "unknown"


# ── Consistency with features.NORMS ─────────────────────────────────────────


def test_thresholds_come_from_features_norms_no_duplication():
    """
    Regression guard: if someone edits features.NORMS, the checker must follow.
    This test pins one known threshold and asserts the checker respects the
    live value, not a hard-coded copy.
    """
    row_ok = pd.Series({"domain": "veevark", "iron": NORMS["iron"] - 0.01})
    row_bad = pd.Series({"domain": "veevark", "iron": NORMS["iron"] + 0.01})
    assert check_probe(row_ok)["any_violation"] is False
    assert "iron" in check_probe(row_bad)["violated_params"]


def test_pool_turbidity_threshold_from_norms_pool():
    row = pd.Series(
        {"domain": "basseinid", "turbidity": NORMS_POOL["turbidity"] + 0.01}
    )
    assert "turbidity" in check_probe(row)["violated_params"]
