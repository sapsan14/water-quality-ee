# Learning Journey — from opendata XML to probabilistic risk estimator

> **Purpose.** This document narrates the project's learning arc for the final TalTech Masinõpe presentation. It is not a log of commits but a story: what we set out to do, what we discovered along the way, what surprised us, and what we now understand differently. Technical details live in the artifacts linked from each section.
>
> **Live demo:** [h2oatlas.ee](https://h2oatlas.ee) — public citizen map of water quality risk across Estonia (2,196 locations, 4 domains, 4 ML models).

---

## Act I — Building the pipeline (Phases 1–6)

### What we started with

Raw XML files from Terviseamet's opendata portal (`vtiav.sm.ee`), one per domain per year. A binary label: `hinnang` = "vastab nõuetele" (pass) or "ei vasta nõuetele" (violation). No documentation of what goes into the label. No API, no schema, no data dictionary. Estonian number format with commas. Location names that change between years.

### What we built

A reproducible pipeline from raw XML to trained classifier:

1. **Data loader** (`src/data_loader.py`) — downloads, caches, parses XML for 4 domains, handles Estonian decimal commas, `µg/l → mg/l` conversion, cross-year location name normalization (`normalize_location()`).
2. **Feature engineering** (`src/features.py`) — ratio-to-norm features, domain-conditional pool norms (`NORMS_POOL`), missing-value indicators (turned out to be surprisingly predictive), time features.
3. **Model zoo** — LogReg, RandomForest, GradientBoosting, LightGBM. Temporal split (train ≤2024, test 2025+). SHAP for interpretability. Calibrated probabilities.
4. **Citizen service** — Streamlit → Next.js map showing per-location latest sample with official status and model risk assessment.

### What we learned

- **Missing indicators are features, not noise.** `iron_missing=1` doesn't mean "iron wasn't measured because it's fine" — it means "this probe is from a site type that doesn't measure iron," which is itself predictive of the compliance profile. The model uses these signals heavily (SHAP top-10).
- **Ratio features beat raw values.** `iron_ratio = iron / 0.2` tells the model how close a measurement is to its regulatory threshold. This domain encoding outperforms raw numeric values, especially for cross-domain training where thresholds differ.
- **Temporal split is essential.** Random split AUC = 0.994; temporal split AUC = 0.981. The gap is small but honest: we're predicting next year's violations from this year's patterns, not memorizing the dataset.

---

## Act II — The citizen service and the norms question (Phases 7–9)

### What happened

We built a public map to visualize model predictions alongside official Terviseamet data. This forced us to confront a question we had been avoiding: **can we reproduce the official compliance label from the published parameters alone?**

The answer should be yes — `hinnang` is supposedly a deterministic function of the measured values against published norms. If E. coli > 500, the label should be "non-compliant." Simple.

So we built a deterministic checker (`src/audit/label_vs_norms.py`) that applies the exact same norms the model uses, and compared its verdict to the official label on every probe. The result was a surprise.

### The audit infrastructure (Phase 9)

- **`src/audit/label_vs_norms.py`** — imports `NORMS` and `NORMS_POOL` directly from `features.py` (single source of truth; no second copy to drift).
- **`scripts/audit_xml_field_coverage.py`** — walks every XML tag to verify the parser doesn't silently drop measurement fields.
- **`notebooks/07_data_gaps_audit.ipynb`** — orchestrates the audit on the full corpus.
- **`docs/terviseamet_inquiry.md`** — draft engineering inquiry to Terviseamet (the people who create the data we're modeling).

---

## Act III — The audit reveals our own bugs first (Phase 10)

### The surprise

We expected the audit to show that Terviseamet's data has gaps. Instead, it first showed that **our norms were wrong**.

**Baseline agree rate: 81.5%** — below the 85% self-check threshold we had set. The checker disagreed with the official label on nearly 1 in 5 probes. Something was deeply off.

### Refinement R1 — The free chlorine bug

Investigation revealed that **288 of 339 compliant pool probes had free chlorine values above our upper threshold of 0.6 mg/l**. Distribution of compliant pool free chlorine: p1=0.46, median=0.94, p95=1.40, max=1.90.

Our `NORMS_POOL["free_chlorine_max"] = 0.6` was categorically wrong. The actual Estonian regulation (Sotsiaalministri 31.07.2019 määrus nr 49, Lisa 4) specifies **0.5–1.5 mg/l** for swimming pools. Combined chlorine was similarly too strict (0.4 → 0.5).

**After fixing: agree rate jumped from 81.5% to 90.8% (+9.3 percentage points).** This single correction was the most impactful finding of the entire project.

**Impact:** the citizen-service model had been trained with the wrong `free_chlorine_deviation` feature, inflating violation probabilities for every pool in Estonia. Users of the map were seeing systematically exaggerated risk for pools. This is a user-facing data quality bug discovered by a systematic audit, not by visual inspection or user complaints.

### Refinement R2 — Coliforms rule

Added `coliforms > 0 → violation` for non-bathing domains (EU 2020/2184 drinking water directive). This resolved 9 of 13 veevark hidden_violation cases and added +0.13pp to agree rate.

### Refinement R3 — Bathing water 95-percentile aggregation

Implemented EU 2006/7/EC's per-(location × season) 95th-percentile evaluation for bathing waters. On the single-probe-per-location snapshot this was a no-op, but on the full corpus it correctly handles seasonal spikes at beaches.

### The residual signal

After all three refinements, **30 probes (1.4% of the snapshot)** remain where the official label says "non-compliant" but no published parameter exceeds any norm. On the full corpus of 69,536 probes: **2,164 probes (3.1%)**.

These are the probes for the Terviseamet inquiry — the cases where the open data alone cannot reproduce the compliance decision.

---

## Act IV — XML parity closes hypothesis #4 (Phase 10b)

### The question

Before we could blame Terviseamet's data for missing parameters, we had to prove our parser doesn't silently drop them. The audit_xml_field_coverage script was built in Phase 9 but could only be smoke-tested in the sandbox (no network access to vtiav.sm.ee).

### The solution

Created a one-shot GitHub Actions workflow that downloaded 160 MB of production XML (4 domains × 6 years), ran the live parity scan, and committed the results back to the branch. This was necessary because the developer was working from an Android tablet via Claude UI with no local filesystem access.

### The result

All 9 unparsed XML tags across all 4 domains are **metadata** — inspector names, protocol IDs, sampling methodology. **Zero measurement parameters are lost by the parser.** Hypothesis #4 (parser loss) is definitively closed — not by argument, but by evidence.

---

## Act V — Model retrain (Phase 11)

### What changed

With the corrected norms and the new `coliforms_detected` feature, we retrained all models on 69,536 probes (temporal split: train ≤2024, test 2025+).

| Model | AUC | Recall(violations) | Precision(violations) |
|---|---|---|---|
| LR | 0.947 | 0.890 | 0.560 |
| **RF** | **0.981** | **0.929** | **0.791** |
| GB | 0.982 | 0.887 | 0.887 |

Best model: **Random Forest** with optimised threshold → **Recall 91.8% at Precision 80.0%**. The citizen-service snapshot was rebuilt with corrected predictions for all 2,196 locations.

---

## What we learned — the meta-lessons

### 1. Audit your assumptions, not just your code

We had high-quality code with tests, CI, and code review. The bug was not in the code — it was in a **constant** (`free_chlorine_max = 0.6` instead of `1.5`). No unit test catches a wrong constant unless you test it against external ground truth. The deterministic audit was that ground truth.

### 2. The model can mask data bugs

The ML model was trained on the wrong norms and still achieved AUC > 0.98. It "learned around" the wrong free chlorine threshold by downweighting that feature and relying on other correlated signals. A model that performs well on its training distribution can hide systematic errors in the feature pipeline. Only a deterministic, threshold-by-threshold comparison against official labels reveals these errors.

### 3. Open data is not self-documenting

Terviseamet publishes 69,536 probes across 6 years — a generous dataset by any standard. But:
- The `hinnang` label is not a simple function of the published parameters (3.1% of probes cannot be reproduced).
- The regulation source for pool norms is not linked from the data.
- Location names change between years with no mapping table.
- Some domains measure different parameter profiles with no published schema.

We learned to treat open data as a **starting point for investigation**, not a finished product.

### 4. The deterministic checker is the project's most valuable artifact

Not the model, not the map, not the notebooks. The `label_vs_norms.py` checker — 250 lines of if/else against published norms — is the piece that:
- Found the free chlorine bug (saving 288 false positives in the citizen service)
- Quantified 2,164 probes where the published data can't explain the label
- Provided concrete examples for the Terviseamet inquiry
- Will catch any future norm drift automatically (single source of truth with `features.NORMS`)

### 5. Sandbox constraints drive creative solutions

The audit ran in a cloud sandbox with no outbound HTTP and no local filesystem access. This forced us to:
- Use the citizen-service snapshot (2,194 probes) as a stand-in for the full corpus during iterative development
- Build a one-shot GitHub Actions workflow to download data remotely
- Design the audit pipeline to work on both snapshot and full corpus with the same code

These constraints improved the architecture: the snapshot adapter, the bathing aggregation, and the GitHub Actions audit workflow are all reusable for CI-triggered data quality checks.

---

## Project phase summary

| Phase | What | Key deliverable |
|---|---|---|
| 1 | Data foundation | `src/data_loader.py` — 4-domain parser with cross-year normalization |
| 2 | EDA | Notebooks 01–02: domain distributions, seasonal patterns, missing-value profiles |
| 3 | Feature engineering | `NORMS`, `NORMS_POOL`, ratio features, missing indicators, `build_dataset()` |
| 4 | Baseline models | LR / RF / GB with random split; `trained_models.joblib` |
| 5 | Evaluation | Confusion, ROC, threshold optimization; `evaluate.py` |
| 6 | Advanced modelling | LightGBM + temporal split + SHAP + calibration; `best_model.joblib` |
| 7 | Citizen service v0 | Streamlit map + 4-domain geocoding cascade + snapshot builder |
| 8 | Frontend | Next.js mobile/desktop UX, model tooltips, info dialogs (~40 PRs) |
| 9 | Audit infrastructure | Deterministic checker + draft inquiry + parser parity script + audit notebook |
| **10** | **Audit execution** | **Found free_chlorine bug (+9.3pp agree rate), 2,164 hidden_violation on 69k probes, XML parity clean** |
| **11** | **Model retrain** | **Corrected features, RF AUC=0.981, citizen snapshot rebuilt** |
| **12** | **Presentation docs** | **learning_journey.md, report.md updated, frontend snapshot for h2oatlas.ee** |
| **13** | **Temporal analysis + LightGBM + Terviseamet** | **H3 confirmed (54.9%), LightGBM AUC=0.984, cooperation letter** |

---

## Act VI — Temporal analysis resolves the frequency question (Phase 13)

### The question

Phase 10 identified 2,164 probes where the official label says "violation" but the published parameters are clean. But *why* are the relevant parameters missing? Are they **never measured** at that site (partial publication, hypothesis #1)? Or are they measured **in other months** but just not in the probe that got the violation label (frequency variance, hypothesis #3)?

### The method

For each hidden_violation probe's unmeasured parameter, we checked whether the same parameter has a non-null value in **any other probe** at the same `(location_key, domain)` across the full 69,536-probe corpus.

### The result

**Hypothesis #3 is strongly supported: 54.9% of unmeasured parameter instances ARE measured at the same site in other probes.** But the pattern is strikingly domain-specific:

| Domain | H1 (never at site) | H3 (measured elsewhere) | Interpretation |
|---|---|---|---|
| **veevark** | 2.1% | **97.9%** | Chemistry (nitrates, chlorides, sulfates) is periodic — measured quarterly or annually, not every probe. Microbiology every probe. |
| **supluskoha** | **97.9%** | 2.1% | Chemistry is simply never measured at bathing sites — EU 2006/7/EC only requires e_coli + enterococci. |
| **basseinid** | 63.0% | 37.0% | Mixed: e_coli systematically absent at some pools; chemistry periodic. |
| **joogivesi** | 21.6% | **78.4%** | Similar to veevark — drinking water chemistry is periodic. |

**Key insight for the presentation:** the 2,164 hidden_violation probes are not data errors — they reflect a **structural feature of the monitoring regime**: microbiology is tested every time, chemistry is tested periodically. When a probe fails on a chemistry parameter not measured that day, the open data can't show why.

Hidden_violation is uniformly distributed across months (no seasonal clustering), confirming this is a publication schedule effect, not a seasonal phenomenon.

---

## Act VII — LightGBM completes the model zoo (Phase 13)

### 4-model comparison (temporal split: train ≤2024, test 2025+)

| Model | AUC | Recall(violations) | Precision(violations) | Notes |
|---|---|---|---|---|
| LR | 0.947 | 0.890 | 0.560 | Baseline; low precision |
| RF | 0.981 | 0.929 | 0.791 | Phase 11 best; good balance |
| GB | 0.982 | 0.887 | **0.887** | Best precision at default threshold |
| **LightGBM** | **0.984** | 0.796→**0.949*** | 0.947→**0.800*** | **Best AUC; with threshold: best recall** |

*With optimised threshold (0.0224): maximises recall at precision ≥ 80%.

**LightGBM is the new best model** — it catches **94.9% of violations** while maintaining 80% precision. The citizen service at [h2oatlas.ee](https://h2oatlas.ee) now shows predictions from all 4 models.

---

## Recommended next actions

| Priority | What | Status |
|---|---|---|
| ~~1~~ | ~~Temporal analysis on full corpus~~ | ✅ Phase 13: H3 strongly supported (54.9%) |
| ~~2~~ | ~~LightGBM retrain~~ | ✅ Phase 13: AUC=0.984, Recall=0.949 with threshold |
| ~~3~~ | ~~Frontend snapshot update~~ | ✅ Phase 13: h2oatlas.ee shows 4 models |
| 4 | Send Terviseamet cooperation letter (supervisor sign-off + Estonian translation) | Draft rewritten as cooperation proposal |
| 5 | `mineraalvesi` domain | Add when stable opendata URLs appear |

---

## Cross-references

| Document | Purpose |
|---|---|
| `docs/phase_10_plan.md` | Phase enumeration and step list |
| `docs/phase_10_findings.md` | Audit results: delta tables, hypothesis verdicts, inquiry examples |
| `docs/terviseamet_inquiry.md` | Draft inquiry to Terviseamet (populated with real numbers) |
| `docs/data_gaps.md` | Audit methodology and 5-hypothesis framework |
| `docs/ml_framing.md` | What the model predicts vs what it cannot |
| `docs/ml_metrics_guide.md` | ROC-AUC, Precision/Recall, Calibration, SHAP explained |
| `docs/report.md` | Final project report |
| `docs/normy.md` | Regulatory thresholds by parameter |
| `docs/parametry.md` | Parameter descriptions with health context |
