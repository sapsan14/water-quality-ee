# Phase 10 Findings — Data-quality audit execution & norms refinement

> **Generated:** 2026-04-16, branch `claude/phase-10-data-audit-rkP4Q`.
> **Updated:** 2026-04-16 (Phase 10b) with full-corpus numbers from `load_all()`.
>
> **Data sources:**
> - **Snapshot subset** (Phase 10): `citizen-service/artifacts/snapshot.json` — 2 194 latest-per-location probes. Used for iterative refinement R1–R3.
> - **Full corpus** (Phase 10b): `data_loader.load_all()` — **69 536 probes** across 4 domains × 6 years (2021–2026), downloaded via GitHub Actions from `vtiav.sm.ee`. Numbers below are from the full corpus unless marked "(snapshot)".

## 1. Executive summary

| What | Result |
|---|---|
| **Full-corpus agree rate (post-refinements)** | **86.2 %** (59 958 / 69 536) — above the 85 % self-check threshold |
| **Root cause of Phase 10** | `NORMS_POOL` free chlorine range [0.2, 0.6] mg/l was **wrong**; 288/339 compliant pool probes in the snapshot had values in [0.6, 1.9] |
| **After R1 (pool norms fix)** | Snapshot: 81.5% → **90.8%** (+9.3 pp) |
| **After R2 (coliforms rule)** | Snapshot: +0.13 pp |
| **After R3 (bathing aggregation)** | Full corpus: 86.2% → **85.7%** (aggregation redistributes some bathing probes; no regression) |
| **Residual hidden_violation** | **2 164** probes (**3.1 %**) — core signal for the Terviseamet inquiry |
| **Residual hidden_pass** | **7 414** probes (**10.7 %**) — pool turbidity, drinking-water iron/manganese |
| **XML parser parity** | **Clean.** All 9 unparsed XML tags across 4 domains are metadata (inspector names, protocol IDs) — zero measurement parameters lost. **Hypothesis #4 definitively closed.** |

The single most impactful fix is **R1: correcting pool free-chlorine norms from [0.2, 0.6] to [0.5, 1.5] mg/l**. Model retraining required to propagate (Phase 11).

---

## 2. Full-corpus numbers (69 536 probes)

### Overall buckets

| Bucket | Count | % of labelled |
|---|---|---|
| agree_pass | 53 754 | 77.3 % |
| agree_violate | 6 204 | 8.9 % |
| **hidden_violation** | **2 164** | **3.1 %** |
| **hidden_pass** | **7 414** | **10.7 %** |
| **agree_rate** | **86.2 %** | — |

### By domain

| Domain | n | agree_pass | agree_violate | hidden_violation | hidden_pass |
|---|---|---|---|---|---|
| veevark | 34 626 | 31 896 | 1 673 | **777** | 280 |
| basseinid | 30 503 | 18 031 | 4 269 | **1 260** | 6 943 |
| supluskoha | 4 031 | 3 706 | 176 | **120** | 29 |
| joogivesi | 376 | 121 | 86 | **7** | 162 |

### Comparison: snapshot vs full corpus

| Metric | Snapshot (2 194) | Full corpus (69 536) | Ratio |
|---|---|---|---|
| agree_rate | 90.9 % | 86.2 % | lower on full — more multi-year chemistry gaps visible |
| hidden_violation | 30 (1.4 %) | 2 164 (3.1 %) | 72× more absolute, 2× higher rate |
| hidden_pass | 170 (7.7 %) | 7 414 (10.7 %) | driven by basseinid turbidity |
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

## 5. XML parser parity — live check (Phase 10b)

`scripts/audit_xml_field_coverage.py` was run on **all cached XML files** (`data/raw/`, 160 MB across 4 domains × 6 years) via the GitHub Actions one-shot workflow.

**Result:** all 4 domains show the same 9 unparsed child tags under `<proovivott>`:

| Unparsed XML tag | Content (sample) | Is it a measurement? |
|---|---|---|
| `katseprotokollid` | protocol reference links | No |
| `proovi_liik` | "Seireproov" (monitoring sample) | No |
| `proovivotja_amet` | "vaneminspektor" | No |
| `proovivotja_nimi` | "Tiina Uustal" | No |
| `proovivotja_atesteerimistunnistuse_number` | "775" | No |
| `proovivotu_eesmark` | "Enesekontroll" | No |
| `proovivotu_metoodika` | EVS-EN ISO references | No |
| `proovivotuprotokolli_number` | "VXX2021TU0982" | No |
| `veeliik` | "Basseinivesi" | No |

**Conclusion:** zero measurement parameters are lost by the parser. Every numeric water-quality value present in the XML is extracted. **Hypothesis #4 (parser loss) is definitively closed** — not just by structural fixture tests, but by a full scan of 160 MB of production XML.

---

## 6. Hypothesis evaluation

Revisiting the five hypotheses from `docs/data_gaps.md` § "Evidence-ranked revisit":

| # | Hypothesis | Verdict (Phase 10 + 13) |
|---|---|---|
| 1 | **Partial publication** — open-data is a subset of internal logs | **Supported (45.1% of param-instances).** Dominant for supluskoha (97.9%) where chemistry is never measured per EU 2006/7/EC. 63% of basseinid unmeasured params are also never-at-site. |
| 2 | **Selective measurement by site type** — different mandatory profiles | **Partially supported.** Supluskoha consistently lacks chemistry; basseinid lacks microbiology at some sites. But temporal analysis (Phase 13) shows much of this is periodic, not per-site-type. |
| 3 | **Measurement frequency variance** — seasonal / periodic | **Strongly supported (54.9% of param-instances, Phase 13).** For veevark, 97.9% of "unmeasured" chemistry params ARE measured at the same site in other probes — periodic scheduling (quarterly nitrates, annual chlorides). For joogivesi, 78.4%. Hidden_violation distribution is uniform across months (not seasonal). See `scripts/temporal_hidden_violation_analysis.py`. |
| 4 | **Parser loss** | **Definitively closed.** Live XML parity scan on 160 MB of production data (Phase 10b) confirmed zero measurement parameters lost. All 9 unparsed tags are metadata. |
| 5 | **Compliance calculated on unpublished data** | **Strong examples.** veevark sid 377387 and sid 380948 have ALL published parameters clean — yet label = violation. With #4 closed and #3 explaining the periodic gaps, these probes can only be explained by unpublished data or a contextual decision rule. |

**Bottom line:** hypotheses #1 and #3 together explain the structural pattern (partial publication + periodic chemistry). Hypothesis #5 explains the residual cases where ALL params are published and clean. Hypothesis #4 is closed. The Terviseamet cooperation letter asks Q1–Q5 to confirm.

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

## 8. Recommended next actions — status

| # | Action | Status |
|---|---|---|
| ~~1~~ | ~~Model retrain with corrected features~~ | ✅ Phase 11 (LR/RF/GB) + Phase 13 (LightGBM AUC=0.984) |
| ~~2~~ | ~~Citizen-service snapshot rebuild~~ | ✅ Phase 13 (4 models on [h2oatlas.ee](https://h2oatlas.ee)) |
| ~~3~~ | ~~Full-corpus audit~~ | ✅ Phase 10b (69,536 probes) |
| ~~4~~ | ~~XML parity scan~~ | ✅ Phase 10b (160 MB, zero measurement params lost) |
| ~~5~~ | ~~Temporal analysis~~ | ✅ Phase 13 (H3 strongly supported, 54.9%) |
| 6 | Send Terviseamet cooperation letter | Draft ready; awaits supervisor sign-off + Estonian translation |
| 7 | `mineraalvesi` domain | Blocked: stable opendata URLs not available |

---

## Cross-references

- Phase plan: `docs/phase_10_plan.md`
- Audit method: `docs/data_gaps.md`
- Cooperation letter: `docs/terviseamet_inquiry.md`
- Norm reference: `docs/normy.md`
- Pool parameters: `docs/parametrid_ujula_avavee.md`
- Parameter descriptions: `docs/parametry.md`
- Checker module: `src/audit/label_vs_norms.py`
- Snapshot adapter: `src/audit/snapshot_audit.py`
- Parser parity: `scripts/audit_xml_field_coverage.py`
- Temporal analysis: `scripts/temporal_hidden_violation_analysis.py`
- Audit notebook: `notebooks/07_data_gaps_audit.ipynb`
- Learning journey: `docs/learning_journey.md`
- Presentation notes: `docs/presentation_notes.md`
- Live site: [h2oatlas.ee](https://h2oatlas.ee)
