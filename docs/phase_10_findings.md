# Phase 10 Findings — Data-quality audit execution & norms refinement

> **Generated:** 2026-04-16, branch `claude/phase-10-data-audit-rkP4Q`.
>
> **Data source:** `citizen-service/artifacts/snapshot.json` — 2 194 latest-per-location
> probes across four domains (veevark 1 321, basseinid 619, supluskoha 186, joogivesi 68).
> The opendata feed at `vtiav.sm.ee` was unreachable from the sandbox (403), so the
> audit used the pre-built citizen-service snapshot instead of `data_loader.load_all()`.
> Numbers are qualitatively representative of the full corpus but the absolute counts
> should be refreshed when `data/raw/` is next populated on a developer machine.

## 1. Executive summary

| What | Result |
|---|---|
| **Baseline agree rate** | 81.5 % (1 788 / 2 194) — below the 85 % self-check threshold |
| **Root cause** | `NORMS_POOL` free chlorine range [0.2, 0.6] mg/l was **wrong**; 288 of 339 compliant pool probes had values in [0.6, 1.9] |
| **After R1 (pool norms fix)** | **90.8 %** (+9.3 pp) — above self-check |
| **After R2 (coliforms rule)** | **90.9 %** (+0.1 pp) — 9 veevark hidden_violation → agree_violate |
| **After R3 (bathing aggregation)** | **90.9 %** (no-op on 1-probe-per-location snapshot; code ready for full corpus) |
| **Residual hidden_violation** | 30 probes (1.4 %) — core signal for the Terviseamet inquiry |
| **Residual hidden_pass** | 170 probes (7.7 %) — mostly pool turbidity (88) and drinking-water iron/manganese |

The single most impactful fix in Phase 10 is **R1: correcting pool free-chlorine norms from [0.2, 0.6] to [0.5, 1.5] mg/l** (Sotsiaalministri 31.07.2019 määrus nr 49, Lisa 4). This is a user-facing bug that inflated violation probabilities for pools in the citizen service. Model retraining is required to propagate it (Phase 11).

---

## 2. Refinement delta table

| Metric | Baseline | After R1 | After R2 | After R3 |
|---|---|---|---|---|
| agree_pass | 1 648 | 1 862 | 1 855 | 1 855 |
| agree_violate | 140 | 129 | 139 | 139 |
| **hidden_violation** | 29 | 40 | **30** | **30** |
| **hidden_pass** | 377 | 163 | 170 | 170 |
| **agree_rate** | **0.815** | **0.908** | **0.909** | **0.909** |

### R1 — Pool norms correction

**What changed.** `features.NORMS_POOL`:
- `free_chlorine_min`: 0.2 → **0.5** mg/l
- `free_chlorine_max`: 0.6 → **1.5** mg/l
- `combined_chlorine`: 0.4 → **0.5** mg/l

**Evidence.** Distribution of `free_chlorine` in compliant basseinid probes (n = 339):
p1 = 0.46, p5 = 0.50, median = 0.94, p95 = 1.40, p99 = 1.60, max = 1.90 mg/l.
The old upper bound 0.6 fell below the 5th percentile of compliant values.

**Impact.** +214 agree_pass, −214 hidden_pass; agree_rate +9.3 pp. The 11 newly exposed hidden_violation are cases where the old tight norm artificially made the checker agree with the violation label.

**Downstream consequences.** The citizen-service model was trained with the wrong `free_chlorine_deviation` feature (deviation from [0.2, 0.6] instead of [0.5, 1.5]). Pool risk probabilities displayed to users are systematically too high. Model retrain is Phase 11.

### R2 — Coliforms detection rule

**What changed.** `src/audit/label_vs_norms.py` now applies `coliforms > 0 → violation` for non-bathing domains (veevark, joogivesi, basseinid). EU 2006/7/EC does not regulate coliforms for bathing waters, so supluskoha is excluded.

**Why audit-only.** Adding `coliforms_detected` to `features.add_ratio_features` would break the saved `best_model.joblib` (feature mismatch). Deferred to Phase 11 model retrain.

**Impact.** +10 agree_violate (9 veevark + 1 basseinid), −10 hidden_violation, +7 hidden_pass (7 basseinid + 1 joogivesi where coliforms > 0 but label = compliant). Net agree_rate +0.13 pp.

### R3 — Bathing-water 95-percentile aggregation

**What changed.** New function `audit_dataframe_with_bathing_aggregation()` replaces per-probe e_coli / enterococci checks for `domain == 'supluskoha'` with a per-(location_key × calendar year) 95th-percentile evaluation, matching EU 2006/7/EC classification logic.

**Impact on snapshot.** Zero: the citizen-service snapshot has one probe per location, so 95p = the value itself. The aggregator is a no-op.

**Impact on full corpus (expected).** On `load_all()` with 5+ probes per location-season, single spikes that currently produce `hidden_pass` on supluskoha will be absorbed by the aggregation and shift to `agree_pass`. The 6 unit tests (`test_bathing_aggregation_*`) verify this on multi-probe fixtures.

---

## 3. Residual hidden_violation — the inquiry signal

After all three refinements, **30 probes** remain where the official label says *ei vasta nõuetele* but no published parameter exceeds any norm in our checker.

| Domain | Count | Dominant unmeasured-parameter signature |
|---|---|---|
| basseinid | 22 | `e_coli` unmeasured in all 22; enterococci / staphylococci / pseudomonas unmeasured in 10. Chemistry (nitrites, fluoride, manganese…) systematically absent — expected for pool labs. |
| veevark | 4 | Two cases: all microbiology unmeasured; one case: **all 14 params published and clean** (sid 377387 — strongest evidence for hypothesis #5); one case: microbiology unmeasured. |
| supluskoha | 3 | Two cases: e_coli / enterococci measured and within "Excellent" (144 / 164 and 330 / 116); one case: zero measurements published. |
| joogivesi | 1 | Zero measurements published (sid 255628). |

### Three inquiry examples

Selected for the Terviseamet draft (`docs/terviseamet_inquiry.md`):

1. **veevark sid 377387** — Arkaadia Viljandi mnt veevärk, Tartu, 2025-12-08. All 14 params published, all clean. No norm violated. Label = violation. **The single strongest case for hypothesis #5** ("compliance calculated on unpublished data").
2. **basseinid sid 347163** — Ring spaa ja saunad / laste mänguala, Harju, 2024-11-29. Chemistry normal but entire microbiology profile absent. **Case for hypothesis #1** ("partial publication") and **Q3** ("do site types have different mandatory profiles?").
3. **supluskoha sid 366758** — Pedeli paisjärve supluskoht, Valga, 2025-08-17. e_coli = 144, enterococci = 164 — both inside "Excellent." **Case for hypothesis #2/Q2** ("is `hinnang` derived from contextual data?").

---

## 4. Residual hidden_pass — the checker-stricter gap

170 probes where the checker says "violation" but the official label says "compliant."

| Domain | Count | Top triggered parameters |
|---|---|---|
| basseinid | 105 | turbidity (88 of 105 — values 0.5–2.0 NTU vs norm 0.5), combined_chlorine (36, values 0.41–0.70 vs norm 0.5), pH (1) |
| veevark | 38 | turbidity (11), color (11), iron (7), chlorides (6), manganese (4) |
| joogivesi | 27 | manganese (21), iron (21), ammonium (5), turbidity (3) |
| supluskoha | 0 | — |

**Interpretation.** The dominant source is pool turbidity (88 cases). Compliant and violation basseinid distributions for turbidity are nearly identical (median 0.50 vs 0.30, max 2.0 vs 2.0), suggesting turbidity alone does not drive the official label — the lab applies a tolerance band or a combined assessment. The norm 0.5 NTU is correct per regulation; the discrepancy is an operational / assessment-method gap, not a data error.

For drinking water (veevark + joogivesi): iron / manganese are the main sources. Compliant drinking-water probes regularly exceed EU thresholds by small margins (iron 0.2–0.3, manganese 0.05–0.08). This may reflect operational tolerances or local derogations.

---

## 5. Hypothesis evaluation

Revisiting the five hypotheses from `docs/data_gaps.md` § "Evidence-ranked revisit":

| # | Hypothesis | Phase 10 verdict |
|---|---|---|
| 1 | **Partial publication** — open-data is a subset of internal logs | **Supported.** 22 basseinid hidden_violation have systematically absent microbiology (e_coli in all 22). 2 veevark and 1 joogivesi have zero measurements. |
| 2 | **Selective measurement by site type** — different mandatory profiles | **Partially supported.** Basseinid hidden_violation cluster around missing microbiology parameters that ARE measured for other pools, suggesting site-level variation, not domain-level policy. |
| 3 | **Measurement frequency variance** — seasonal / periodic | **Cannot evaluate.** The snapshot has one probe per location; temporal clustering analysis requires the full corpus. |
| 4 | **Parser loss** | **Ruled out (structurally).** `audit_xml_field_coverage.py` smoke-tested on fixtures; the script correctly identifies unparsed tags. Full XML parity scan pending (`data/raw/` unavailable in sandbox). |
| 5 | **Compliance calculated on unpublished data** | **Strongest single example.** veevark sid 377387 has all 14 params published and clean; label = violation. Unless the parser is dropping a field (hypothesis #4, unlikely per structural tests), this probe can only be explained by unpublished data or a metadata-level decision rule. |

**Bottom line for the inquiry:** hypotheses #1 and #5 are the leading explanations. The Terviseamet draft inquiry asks Q1–Q5 to discriminate between them.

---

## 6. Test coverage

| Suite | Before Phase 10 | After Phase 10 |
|---|---|---|
| `tests/test_label_vs_norms.py` | 26 | **38** (+6 coliforms R2, +6 bathing aggregation R3) |
| `tests/test_audit_xml_field_coverage.py` | 0 | **8** (new: fixture-based smoke tests) |
| Other test files | 46 | 46 (untouched) |
| **Total** | **72** | **92** |

All 92 tests pass on branch.

---

## 7. New / modified artifacts

| Path | Status | Purpose |
|---|---|---|
| `docs/phase_10_plan.md` | NEW | Phase plan with project history enumeration |
| `docs/phase_10_findings.md` | NEW | This document |
| `docs/terviseamet_inquiry.md` | MODIFIED | Placeholders filled with real numbers; status note updated |
| `docs/normy.md` | MODIFIED | Pool free_chlorine 0.5–1.5, combined_chlorine ≤ 0.5 |
| `docs/parametry.md` | MODIFIED | Same norms + Phase 10 annotation |
| `docs/parametrid_ujula_avavee.md` | MODIFIED | Same norms in NORMS_POOL summary table |
| `src/features.py` | MODIFIED | `NORMS_POOL` free_chlorine [0.5, 1.5], combined_chlorine 0.5 |
| `src/audit/label_vs_norms.py` | MODIFIED | R2 coliforms rule; R3 `audit_dataframe_with_bathing_aggregation()` |
| `src/audit/snapshot_audit.py` | NEW | Snapshot adapter for offline audit |
| `src/audit/__init__.py` | MODIFIED | Re-export new function |
| `tests/test_label_vs_norms.py` | MODIFIED | +12 tests (R2 + R3) |
| `tests/test_audit_xml_field_coverage.py` | NEW | 8 smoke tests for parser-parity script |
| `.gitignore` | MODIFIED | `data/audit/` added |

---

## 8. Recommended next actions (Phase 11+)

1. **Model retrain.** The `free_chlorine_deviation` feature was computed with the wrong range. Retrain all four models (LR, RF, GB, LightGBM) on corrected features. Add `coliforms_detected` to `RATIO_COLS` / `FEATURE_COLS` alongside the retrain.
2. **Citizen-service snapshot rebuild.** After retrain, run `build_citizen_snapshot.py` to propagate corrected pool probabilities.
3. **Full-corpus audit.** Run `notebooks/07_data_gaps_audit.ipynb` on `load_all()` with the corrected norms. Refresh the 30 → N hidden_violation count and update the inquiry before sending.
4. **XML parity scan.** Run `scripts/audit_xml_field_coverage.py` on a populated `data/raw/` to close hypothesis #4 with certainty (not just structurally).
5. **Send inquiry.** After supervisor sign-off and Estonian translation of `docs/terviseamet_inquiry.md`.
6. **Temporal analysis.** On the full corpus, evaluate hypothesis #3 (measurement frequency variance) by cross-referencing hidden_violation sample dates with per-parameter coverage-over-time plots per `location_key`.

---

## Cross-references

- Phase plan: `docs/phase_10_plan.md`
- Audit method: `docs/data_gaps.md`
- Inquiry draft: `docs/terviseamet_inquiry.md`
- Norm reference: `docs/normy.md`
- Pool parameters: `docs/parametrid_ujula_avavee.md`
- Parameter descriptions: `docs/parametry.md`
- Checker module: `src/audit/label_vs_norms.py`
- Snapshot adapter: `src/audit/snapshot_audit.py`
- Parser parity: `scripts/audit_xml_field_coverage.py`
- Audit notebook: `notebooks/07_data_gaps_audit.ipynb`
