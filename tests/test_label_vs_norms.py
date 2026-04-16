"""Unit tests for src/audit/label_vs_norms.py — deterministic label checker."""

import numpy as np
import pandas as pd
import pytest

from audit.label_vs_norms import (
    audit_dataframe,
    audit_dataframe_with_bathing_aggregation,
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
    # Phase 10: range corrected to [0.5, 1.5] per Sotsiaalministri 49/2019
    row = pd.Series({"domain": "basseinid", "free_chlorine": 0.3})  # below 0.5
    assert "free_chlorine" in check_probe(row)["violated_params"]


def test_pool_free_chlorine_range_violation_high():
    row = pd.Series({"domain": "basseinid", "free_chlorine": 1.8})  # above 1.5
    assert "free_chlorine" in check_probe(row)["violated_params"]


def test_pool_free_chlorine_in_range_is_compliant():
    row = pd.Series({"domain": "basseinid", "free_chlorine": 1.0})  # within [0.5, 1.5]
    assert "free_chlorine" not in check_probe(row)["violated_params"]


def test_pool_pseudomonas_any_count_violates():
    row = pd.Series({"domain": "basseinid", "pseudomonas": 5.0})
    verdict = check_probe(row)
    assert "pseudomonas" in verdict["violated_params"]


def test_pool_staphylococci_over_threshold_violates():
    row = pd.Series({"domain": "basseinid", "staphylococci": 50.0})  # norm 20
    assert "staphylococci" in check_probe(row)["violated_params"]


# ── Phase 10 R2: coliforms detection rule ────────────────────────────────────


def test_coliforms_positive_violates_in_drinking_water():
    """coliforms > 0 must be a violation for veevark/joogivesi (EU 2020/2184)."""
    row = pd.Series({"domain": "veevark", "coliforms": 1.0})
    verdict = check_probe(row)
    assert "coliforms" in verdict["violated_params"]
    assert verdict["any_violation"] is True


def test_coliforms_positive_violates_in_drinking_source():
    row = pd.Series({"domain": "joogivesi", "coliforms": 5.0})
    assert "coliforms" in check_probe(row)["violated_params"]


def test_coliforms_positive_violates_in_pool():
    row = pd.Series({"domain": "basseinid", "coliforms": 1.0})
    assert "coliforms" in check_probe(row)["violated_params"]


def test_coliforms_zero_is_compliant():
    row = pd.Series({"domain": "veevark", "coliforms": 0.0})
    assert "coliforms" not in check_probe(row)["violated_params"]


def test_coliforms_rule_skipped_for_supluskoha():
    """EU 2006/7/EC bathing-water directive does not regulate coliforms.

    Only e_coli and enterococci are bathing-water indicators; total coliforms
    are not a parameter of the directive. So a supluskoha probe with
    coliforms > 0 must NOT be flagged by the audit checker.
    """
    row = pd.Series({"domain": "supluskoha", "coliforms": 999.0})
    verdict = check_probe(row)
    assert "coliforms" not in verdict["violated_params"]
    assert verdict["any_violation"] is False


def test_coliforms_unmeasured_does_not_violate():
    """Missing coliforms column must be tolerated, not flagged."""
    row = pd.Series({"domain": "veevark", "e_coli": 100.0})
    verdict = check_probe(row)
    assert "coliforms" in verdict["unmeasured_norm_params"]
    assert "coliforms" not in verdict["violated_params"]


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


# ── Phase 10 R3: bathing-water 95-percentile aggregation ─────────────────────


def _bathing_fixture(probes):
    """Helper: build a small DataFrame for the aggregation tests.

    `probes` is a list of dicts with keys:
        location_key, sample_date (str), e_coli, enterococci, compliant
    """
    rows = []
    for p in probes:
        rows.append(
            {
                "domain": "supluskoha",
                "location_key": p["location_key"],
                "sample_date": pd.Timestamp(p["sample_date"]),
                "e_coli": p.get("e_coli"),
                "enterococci": p.get("enterococci"),
                "compliant": p.get("compliant"),
            }
        )
    return pd.DataFrame(rows)


def test_bathing_aggregation_one_spike_does_not_violate():
    """A single high probe inside an otherwise clean season is hidden_pass
    under per-probe rules but agree_pass under EU-2006/7/EC 95-percentile.
    """
    df = _bathing_fixture(
        [
            {"location_key": "harku jarv", "sample_date": "2024-06-01", "e_coli": 50, "enterococci": 20, "compliant": 1},
            {"location_key": "harku jarv", "sample_date": "2024-07-01", "e_coli": 60, "enterococci": 25, "compliant": 1},
            {"location_key": "harku jarv", "sample_date": "2024-08-01", "e_coli": 700, "enterococci": 30, "compliant": 1},  # spike below "Sufficient" 900
            {"location_key": "harku jarv", "sample_date": "2024-09-01", "e_coli": 80, "enterococci": 25, "compliant": 1},
        ]
    )
    aggregated = audit_dataframe_with_bathing_aggregation(df)
    # 95p of [50, 60, 700, 80] = 610 < 900 → no violation; all rows agree_pass
    assert (aggregated["bucket"] == "agree_pass").all()


def test_bathing_aggregation_persistent_high_does_violate():
    """A whole season above the 95p threshold must still be flagged."""
    df = _bathing_fixture(
        [
            {"location_key": "stroomi rand", "sample_date": "2024-06-01", "e_coli": 1000, "enterococci": 30, "compliant": 0},
            {"location_key": "stroomi rand", "sample_date": "2024-07-01", "e_coli": 1100, "enterococci": 35, "compliant": 0},
            {"location_key": "stroomi rand", "sample_date": "2024-08-01", "e_coli": 1200, "enterococci": 40, "compliant": 0},
        ]
    )
    aggregated = audit_dataframe_with_bathing_aggregation(df)
    assert (aggregated["bucket"] == "agree_violate").all()


def test_bathing_aggregation_per_season_independent():
    """Two seasons at the same location must be aggregated independently."""
    df = _bathing_fixture(
        [
            # 2023 — clean
            {"location_key": "pikakari", "sample_date": "2023-07-01", "e_coli": 100, "enterococci": 20, "compliant": 1},
            {"location_key": "pikakari", "sample_date": "2023-08-01", "e_coli": 120, "enterococci": 25, "compliant": 1},
            # 2024 — persistent contamination
            {"location_key": "pikakari", "sample_date": "2024-07-01", "e_coli": 2000, "enterococci": 50, "compliant": 0},
            {"location_key": "pikakari", "sample_date": "2024-08-01", "e_coli": 2200, "enterococci": 60, "compliant": 0},
        ]
    )
    aggregated = audit_dataframe_with_bathing_aggregation(df)
    by_year = aggregated.set_index("sample_date")
    assert by_year.loc["2023-07-01", "bucket"] == "agree_pass"
    assert by_year.loc["2023-08-01", "bucket"] == "agree_pass"
    assert by_year.loc["2024-07-01", "bucket"] == "agree_violate"
    assert by_year.loc["2024-08-01", "bucket"] == "agree_violate"


def test_bathing_aggregation_enterococci_alone_violates():
    df = _bathing_fixture(
        [
            {"location_key": "loksa", "sample_date": "2024-06-01", "e_coli": 100, "enterococci": 200, "compliant": 0},
            {"location_key": "loksa", "sample_date": "2024-07-01", "e_coli": 100, "enterococci": 350, "compliant": 0},  # > 330
            {"location_key": "loksa", "sample_date": "2024-08-01", "e_coli": 100, "enterococci": 400, "compliant": 0},
        ]
    )
    aggregated = audit_dataframe_with_bathing_aggregation(df)
    assert (aggregated["bucket"] == "agree_violate").all()


def test_bathing_aggregation_passthrough_for_other_domains():
    """Non-supluskoha rows must be unchanged by the aggregator."""
    df = pd.DataFrame(
        [
            {
                "domain": "veevark",
                "location_key": "tartu kesklinn",
                "sample_date": pd.Timestamp("2024-06-01"),
                "e_coli": 600.0,  # > 500 NORMS
                "compliant": 0,
            }
        ]
    )
    aggregated = audit_dataframe_with_bathing_aggregation(df)
    # veevark with e_coli > 500 → agree_violate, unchanged.
    assert aggregated["bucket"].iloc[0] == "agree_violate"


def test_bathing_aggregation_skips_when_location_key_missing():
    """If location_key is absent, aggregator falls back to per-probe verdicts."""
    df = pd.DataFrame(
        [
            {
                "domain": "supluskoha",
                "sample_date": pd.Timestamp("2024-06-01"),
                "e_coli": 700.0,  # > 500 per-probe → would flag
                "compliant": 1,
            }
        ]
    )
    aggregated = audit_dataframe_with_bathing_aggregation(df)
    # No location_key column → no aggregation → per-probe verdict (hidden_pass).
    assert aggregated["bucket"].iloc[0] == "hidden_pass"


def test_pool_turbidity_threshold_from_norms_pool():
    row = pd.Series(
        {"domain": "basseinid", "turbidity": NORMS_POOL["turbidity"] + 0.01}
    )
    assert "turbidity" in check_probe(row)["violated_params"]
