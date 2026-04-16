# Data gaps: reproducibility of the `hinnang` label from open data

> **Status.** Method and tooling are in place; numeric findings are populated by running `notebooks/07_data_gaps_audit.ipynb` against a fresh `data/raw/` cache. This document is the method-and-interpretation reference — the audit notebook and the parquet artifact at `data/audit/divergences_<date>.parquet` are the numeric authorities.

## Why this exists

`docs/ml_framing.md` §1 and `docs/report.md` §7 (limitation 7) both state that the `compliant` label is a deterministic function of the measured parameters against published norms: if a probe is labelled `ei vasta nõuetele`, at least one of the published parameters should exceed its printed threshold.

This invariant is empirically testable. For every probe in `load_all()` we re-derive a deterministic verdict from `features.NORMS` and `features.NORMS_POOL` and compare it to the `compliant` field. Any disagreement is evidence that **the open-data slice alone cannot reproduce the official compliance decision** — either because parameters are withheld, because aggregation rules differ, or because the parser is dropping a field.

The original motivation was the reflection note at `sapsan14/life:reflect/2026-04-15_health-data-gaps.md`, which identified two such divergences and hypothesised five possible explanations. This audit generalises from those two anchors to the whole dataset.

## Method

Three independent checks, all in this repository:

1. **`src/audit/label_vs_norms.py`** — reuses `features.NORMS` / `features.NORMS_POOL` directly (single source of truth, no copies) and classifies every probe into one of four buckets:

   | Bucket | `compliant` | deterministic check | interpretation |
   |---|---|---|---|
   | `agree_pass` | 1 | no violation | routine |
   | `agree_violate` | 0 | violation | routine |
   | `hidden_violation` | 0 | **no** violation | open-data alone cannot reproduce the label |
   | `hidden_pass` | 1 | violation | threshold or aggregation rule mismatch |

2. **`scripts/audit_xml_field_coverage.py`** — walks every cached `data/raw/{domain}_{year}.xml`, enumerates every child tag under `<proovivott>` / `<uuring>`, and flags which tags the parsers in `data_loader.py` currently extract. Rules out the trivial explanation that the parser is dropping a published field before we attribute anything to upstream.

3. **`notebooks/07_data_gaps_audit.ipynb`** — runs the checker against `load_all()`, reports bucket rates per domain × year, profiles the missing-parameter signatures of `hidden_violation` probes, and exports a probe-level artifact at `data/audit/divergences_<date>.parquet`.

### Double-verification stance

- The module pulls thresholds from `features.NORMS` at import time, so edits to the feature table propagate to the audit — there is no second copy to drift.
- `tests/test_label_vs_norms.py` pins 26 behavioural expectations (clean compliant / high E. coli / pool vs. drinking turbidity / pH range / pool-only parameters ignored outside pool domain / bucket logic / regression against `features.NORMS`).
- The notebook includes a self-check: `agree_pass + agree_violate` must cover at least 85 % of labelled probes, otherwise the checker has drifted from `add_ratio_features` and the audit is treated as invalid.

## Known caveats

- **Single-probe approximation for bathing waters.** EU 2006/7/EC classifies bathing sites on a 90/95-percentile across multiple probes, not per-probe. A `hidden_pass` result inside `supluskoha` is partly expected behaviour of the directive and is reported separately in the notebook.
- **Drinking-water stricter rules not applied.** `NORMS["e_coli"] = 500` is the bathing-water threshold; EU 2020/2184 requires 0 CFU/100 mL for drinking water. `features.add_ratio_features` does not distinguish; neither does the checker, by design, so that "the model sees X as a violation" and "the audit marks X as violating" cannot diverge. A drinking-water probe with `e_coli ∈ (0, 500]` passes both checks even though it is technically non-compliant.
- **No `coliforms` check.** `coliforms` has no threshold in `NORMS`. It is a very strong predictor in the model (see `docs/report.md` §6.1) but the deterministic checker leaves it unused to stay consistent with `add_ratio_features`.

These caveats mean the raw `hidden_*` counts over-state real gaps on bathing waters and under-state them on drinking water. They must be read alongside the per-domain breakdown in the notebook, not aggregated blindly.

## Evidence-ranked revisit of the reflection-note hypotheses

The reflection note at `sapsan14/life:reflect/2026-04-15_health-data-gaps.md` listed five working hypotheses for why model predictions and the official label would diverge on probes with partially missing parameters. The audit now has evidence for each — populated from Phase 10 (audit execution), Phase 10b (full-corpus + XML parity), and Phase 13 (temporal analysis).

| # | Hypothesis | Evidence (Phases 10–13) | Status |
|---|---|---|---|
| 1 | **Partial publication** — internal logs complete, open-data exports a subset | 45.1% of unmeasured param-instances in hidden_violation are *never* measured at the same site. Dominant for supluskoha (97.9% — chemistry not required by EU 2006/7/EC) and basseinid (63% never-at-site). | **Supported** |
| 2 | **Selective measurement by site type** — different objects have different mandatory profiles | Supluskoha consistently lacks chemistry; basseinid lacks microbiology at some sites. But temporal analysis (Phase 13) shows much of this is periodic, not per-site-type. | **Partially supported** |
| 3 | **Measurement frequency variance** — seasonal / periodic measurements absent at snapshot time | **54.9% of unmeasured param-instances** ARE measured at the same site in other probes (`scripts/temporal_hidden_violation_analysis.py`). For veevark: 97.9% — chemistry is periodic (quarterly). For joogivesi: 78.4%. Hidden_violation uniform across months (not seasonal). | **Strongly supported** |
| 4 | **Export error** — trivial parser / ETL bugs lose fields | Live XML parity scan on 160 MB production data (Phase 10b): all 9 unparsed tags are metadata. Zero measurement parameters lost. | **Definitively closed** |
| 5 | **Compliance calculated on unpublished data** — internal dataset is wider | veevark sid 377387: all 14 params published and clean, label=violation. With #4 closed and #3 explaining periodic gaps, these residual cases can only be explained by unpublished data. | **Strong examples** |

## Reproducing the audit

```bash
pip install -e .
python src/data_loader.py           # warms data/raw/
python scripts/audit_xml_field_coverage.py   # writes data/audit/xml_field_inventory.csv
jupyter notebook notebooks/07_data_gaps_audit.ipynb
# → data/audit/divergences_<YYYY-MM-DD>.parquet
```

The audit is reproducible: re-running it on a later snapshot shows whether a given `hidden_violation` was a transient open-data publishing lag or a persistent gap.

## Cross-references

- Module: `src/audit/label_vs_norms.py`
- Tests: `tests/test_label_vs_norms.py`
- Notebook: `notebooks/07_data_gaps_audit.ipynb`
- XML parity check: `scripts/audit_xml_field_coverage.py`
- Temporal analysis: `scripts/temporal_hidden_violation_analysis.py` (Phase 13)
- Audit findings: `docs/phase_10_findings.md`
- Cooperation letter: `docs/terviseamet_inquiry.md`
- Framing caveat: `docs/ml_framing.md` § 2.5 (open-data subset caveat)
- Learning journey: `docs/learning_journey.md`
- Original motivation: `sapsan14/life:reflect/2026-04-15_health-data-gaps.md`
