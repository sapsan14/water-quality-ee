# Phase 10 — Data-quality audit execution & norms refinement

> **Status.** Plan committed at start of phase. `docs/phase_10_findings.md` will be populated step-by-step as evidence accrues.
>
> **Branch.** `claude/phase-10-data-audit-rkP4Q`
>
> **Ancestor of work.** Phases 1–9 (see enumeration below).

## Where this phase sits in the project history

The project is structured as a sequence of self-contained phases, each leaving behind code, notebooks, tests and documentation. Counting only the phases that landed substantive deliverables on `main`:

| # | Phase | What it left behind |
|---|---|---|
| 1 | **Data foundation** | `src/data_loader.py` parsers (supluskoha/veevark/basseinid/joogivesi/mineraalvesi), opendata cache, `county_infer`, `normalize_location()` for cross-year dedup. |
| 2 | **Exploratory analysis** | `notebooks/01_eda_supluskoha.ipynb`, `notebooks/02_eda_full.ipynb`, `data/processed/raw_combined.csv`. |
| 3 | **Feature engineering** | `src/features.py` — `NORMS`, `NORMS_POOL`, `add_ratio_features`, `add_time_features`, `add_missing_indicators`, `build_dataset[_with_meta]`. Notebook `03_preprocessing.ipynb`. |
| 4 | **Baseline models** | LogReg / RandomForest / GradientBoosting / `GridSearchCV` in `notebooks/04_models.ipynb`, persisted as `trained_models.joblib`. |
| 5 | **Evaluation** | `src/evaluate.py` (`temporal_cv_metrics`, `best_threshold_max_recall_at_precision`), confusion / ROC / feature-importance plots, `notebooks/05_evaluation.ipynb`, `docs/report.md` skeleton. |
| 6 | **Advanced modelling** | LightGBM + temporal split + calibration + SHAP + decision threshold in `notebooks/06_advanced_models.ipynb`, `best_model.joblib`. |
| 7 | **Citizen service v0** | `citizen-service/` Streamlit app + `build_citizen_snapshot.py` + 4-domain geocoding cascade (In-ADS, Google, Nominatim, OpenCage), Streamlit Cloud deploy. |
| 8 | **Frontend** | Next.js public site with map, mobile/desktop UX, model-overview tooltips, info dialogs, accessibility polish (~40 merged PRs, #22–#69). |
| 9 | **Audit infrastructure** | `src/audit/label_vs_norms.py` deterministic checker, `tests/test_label_vs_norms.py` (26 tests), `scripts/audit_xml_field_coverage.py` parser-parity tool, `notebooks/07_data_gaps_audit.ipynb`, `docs/data_gaps.md`, `docs/terviseamet_inquiry.md` **DRAFT**. |

So this phase is **Phase 10**.

## What Phase 10 has to do (and why)

Phase 9 built the *tools* to test the invariant "the official `hinnang` label is reproducible from the published parameters alone." Phase 10 actually runs them, refines two known caveats, and turns the results into a presentation-ready narrative.

The end state of Phase 10 is:

1. A **clean parser-parity report** that lets us truthfully say "we are not losing data on our side."
2. A **populated audit parquet** (`data/audit/divergences_<date>.parquet`) and a Terviseamet inquiry whose `<PLACEHOLDER>`s are filled with real numbers and real probe IDs.
3. Two **norms refinements** with measured impact:
   - `coliforms` threshold added to `NORMS` (currently absent from the deterministic checker, although coliforms is a top-5 SHAP feature in the model — see `docs/report.md` §6.1).
   - 95-percentile aggregation per `(location_key × bathing season)` for `supluskoha`, matching how EU 2006/7/EC actually classifies bathing waters. Without this, every `supluskoha` `hidden_pass` is partly an artifact of the directive, not a data problem.
4. A **single document** (`docs/phase_10_findings.md`) that the project presentation can quote from, with tables, deltas, and a verdict on the five hypotheses from `docs/data_gaps.md` §"Evidence-ranked revisit."

## Steps

| # | Step | Deliverable | Blocking? |
|---|---|---|---|
| 0 | Phase plan (this doc) | `docs/phase_10_plan.md` | — |
| 1 | **Parser parity (B).** Run `scripts/audit_xml_field_coverage.py` against the cached `data/raw/`. If any `parsed=0` row carries a non-empty `sample_value`, fix `src/data_loader.py`. | `data/audit/xml_field_inventory.csv` + (if needed) parser fix | **Blocks Step 2** |
| 2 | **Audit execution (A).** Run the audit checker against `load_all()`. Persist `data/audit/divergences_<YYYY-MM-DD>.parquet`. Inspect the `bucket × domain × year` distribution. Pick three diverse `hidden_violation` examples. Fill placeholders in `docs/terviseamet_inquiry.md`. | populated parquet + completed inquiry draft | **Blocks Step 5 narrative** |
| 3 | **Coliforms threshold (C).** Research the right value for drinking water; add to `features.NORMS`; update `src/audit/label_vs_norms.py` to include it; **re-run** the audit and record the delta in `hidden_violation` and `agree_violate`. | feature update + tests + delta table | informational |
| 4 | **Bathing-water aggregation (D).** Implement 95-percentile aggregation per `(location_key × bathing season)` for `supluskoha` in the checker. Re-run; record the `hidden_pass` delta. | new aggregator + delta table | informational |
| 5 | **Presentation doc.** Write `docs/phase_10_findings.md`: narrative, parser-parity outcome, audit numbers, hypothesis evaluation, two refinement deltas, recommended next actions. Cross-link from `docs/data_gaps.md` and `docs/report.md`. | presentation-ready findings doc | — |
| 6 | **Delivery.** Commit, push to `claude/phase-10-data-audit-rkP4Q`, open draft PR. | merged PR (after review) | — |

## Out of scope (explicitly)

These are **not** part of Phase 10 — they would each justify their own phase:

- Re-training the model with refined norms (would be Phase 11).
- Sending the actual inquiry to Terviseamet (requires supervisor sign-off; this phase only fills the draft).
- Adjusting `citizen-service` snapshot logic in response to refined norms.
- Linking probes to health-outcome data.
- Anything to do with the frontend.

## Reproducibility ground rules

- All code paths import thresholds from `src/features.NORMS` / `NORMS_POOL` — no second copies. Any threshold change touches one place.
- The audit notebook's self-check (`agree_pass + agree_violate ≥ 85 %`) must remain green throughout. If a refinement drops the agreement rate, the refinement is wrong, not the data.
- Every refinement is gated by a delta table in `docs/phase_10_findings.md`. We record what changed, not just the new state.
- All artifacts (`data/audit/*.csv`, `data/audit/*.parquet`) are gitignored or committed only if they are small and stable. Code and docs are committed; bulky raw artifacts are reproduced from `make audit`.
