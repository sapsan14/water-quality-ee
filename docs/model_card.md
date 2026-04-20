# Model Card — Water Quality Compliance Risk Estimator

> **Structure:** Mitchell et al. 2019, *Model Cards for Model Reporting*.
> Companion to `docs/datasheet.md` (data provenance), `docs/ai_act_self_assessment.md` (risk tier), `docs/fria_light.md` (fundamental-rights impact).

## 1. Model details

| Field | Value |
|---|---|
| **Model family** | Binary classifier over a fixed feature vector of ~70 columns |
| **Primary model** | LightGBM (gradient-boosted decision trees) — `best_model.joblib` |
| **Baselines** | Logistic Regression, Random Forest, sklearn GradientBoosting — `trained_models.joblib` |
| **Version** | 0.1.0 (aligns with `pyproject.toml`) |
| **Training pipeline commit** | Git SHA of the commit that produced the published `snapshot.json` — recorded in the signed evidence package (see `scripts/sign_snapshot.py`) |
| **Developer** | TalTech Masinõpe student team, 2026 |
| **Licence** | MIT (code + artefacts) |
| **Contact** | GitHub issues at [`sapsan14/water-quality-ee`](https://github.com/sapsan14/water-quality-ee) |
| **Citation** | `CITATION.cff` (Zenodo-compatible) |

The four trained models share one preprocessing stack (`src/features.py`) and one target definition (`compliant ∈ {0, 1}` from `hinnang`).

## 2. Intended use

### Primary intended use

Public decision support. Probability P(violation) for the most recent laboratory sample at a monitored site, rendered alongside the official Terviseamet `hinnang` on [h2oatlas.ee](https://h2oatlas.ee) so a citizen can see both signals side by side.

### Intended users

- Members of the public consulting the map before swimming or to contextualise their drinking-water supply.
- TalTech course reviewers assessing the project.
- Water-quality researchers and civic-tech developers wanting a worked pipeline on Estonian open data.

### Out-of-scope uses

The model must **not** be used for:

- Regulatory decision-making (closing a beach, recalling a batch of water, issuing enforcement).
- Medical or clinical advice.
- Replacing, pre-empting or overriding Terviseamet's official `hinnang`.
- Predicting future water quality beyond the most recent sample date.
- Generalising to water sources outside Estonia or to parameters outside the 15 measured ones.
- Safety-critical control loops (e.g. triggering chlorination, closing a valve).

Using the model for any of these is a category error: the target is a *historical label reproduction* task, not a physical model of water safety. See `docs/ml_framing.md`.

## 3. Factors

Relevant factors that affect model behaviour and were evaluated:

| Factor | Values | Notes |
|---|---|---|
| **Domain** | `supluskoha`, `veevark`, `basseinid`, `joogivesi` | Parameter availability differs sharply per domain (§6). |
| **Year** | 2021–2026 | Temporal validation split: train ≤ 2024, test ≥ 2025. |
| **Season** | winter / spring / summer / autumn | Bathing-site activity concentrated in summer. |
| **County (maakond)** | 15 Estonian counties + `unknown` | Leakage-safe encoding via `fit_county_mapping` on train only. |
| **Parameter measurement schedule** | Per-probe vs quarterly vs annual | Chemistry in `veevark` is 5–7% populated per probe but 97.9% of "missing" chemistry is measured at the same site on a different probe (periodic scheduling). |

Factors **not** evaluated: demographic subgroups of site users (not in the data), long-range temporal trends beyond 6 years, comparison with non-Estonian corpora.

## 4. Metrics

### Decision metrics

Priority metric: **Recall on class 0 (violation)**. A false negative on h2oatlas.ee displays low probability of violation for water that actually violates norms — this is the highest-harm error.

Operational metrics reported:

- ROC-AUC (class separation)
- Precision / Recall at the default 0.5 threshold
- Precision / Recall at `best_threshold_max_recall_at_precision(min_precision=0.7)` (decision-support threshold)
- Calibration curve + Brier score (LightGBM only, `06_advanced_models.ipynb`)
- SHAP values for per-prediction attribution (LightGBM only)

### Headline results (temporal split: train ≤ 2024, test ≥ 2025)

| Model | Recall₀ | Precision₀ | F1₀ | ROC-AUC |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.827 | 0.454 | 0.586 | 0.936 |
| Random Forest | 0.949 | 0.919 | 0.934 | 0.992 |
| Gradient Boosting | 0.954 | 0.946 | 0.950 | 0.994 |
| **LightGBM** | **0.956** | **0.881** | **0.917** | **0.988** |

LightGBM is published as `best_model.joblib` because of native missing-value handling and calibrated probabilities; its ROC-AUC is slightly below GB but the operational curve (Recall at fixed Precision) is equivalent.

### Per-domain metrics

Per-domain confusion matrices and Recall₀/Precision₀ are reported in `notebooks/05_evaluation.ipynb`. This surfaces weakness in `joogivesi` (small n, 376 probes) and strength in `veevark` (large n, rich chemistry).

## 5. Evaluation data

- **Corpus:** 69,536 labelled probes from four Terviseamet domains, 2021–2026. See `docs/datasheet.md` §3.
- **Split strategy:** temporal. Train ≤ 2024, test ≥ 2025. This is the relevant generalisation axis for a risk estimator that must work on samples the lab has not yet produced.
- **Secondary split:** `TimeSeriesSplit(n_splits=5)` CV on the training portion, reported in `06_advanced_models.ipynb`.
- **Per-domain evaluation:** `X_test.groupby('domain')` over the same trained model weights (no re-training).

Known caveat: the test period (2025–2026) contains an unusual share of violations (higher than the 2021–2024 baseline), reflecting a methodological change in labelling or a real-world shift we cannot distinguish from open data alone. See `docs/phase_10_findings.md` §4 and the Terviseamet inquiry (Q5, Q6).

## 6. Training data

- **Source:** Terviseamet opendata XML (`vtiav.sm.ee/index.php/opendata/`).
- **Feature engineering:** `src/features.py::engineer_features` — time features, ratio-to-norm, missing indicators, categorical encoding.
- **Target:** `compliant` derived from `hinnang` field (`"ei vasta nõuetele"` → 0, else → 1).
- **Class balance:** ~12% violations (class 0).
- **Missing-value policy:** median imputation via `SimpleImputer`, fit on train only. LightGBM uses native missing handling and ignores the imputed values for splits.
- **Scaling:** `RobustScaler`, fit on train only.
- **Location deduplication:** raw `location` contains year-over-year renames (e.g. "Harku järve supluskoht" → "Harku järve rand"); `location_key` normalisation via `src/data_loader.py::normalize_location` collapses these.

See `docs/datasheet.md` for full data provenance.

## 7. Quantitative analyses

### Disaggregated performance

Reported in `notebooks/05_evaluation.ipynb`:

- Per-domain confusion matrix × 4 models.
- Per-year breakdown on the test set (`year == 2025`, `year == 2026`).
- SHAP summary plots for LightGBM (global + per-domain).
- Calibration curve for LightGBM with isotonic regression overlay.

### Known performance gaps

- **joogivesi** has the smallest n (376 probes) and the highest proportion of `hidden_pass` (iron/manganese slightly exceeding EU threshold on label = compliant). Confidence intervals are wide.
- **basseinid** carries the `free_chlorine_deviation` feature, which was retrained in Phase 11 after the pool-norm correction (`NORMS_POOL` free_chlorine `[0.2, 0.6]` → `[0.5, 1.5]`). Pre-Phase-11 model artefacts are obsolete.

## 8. Ethical considerations

### Sensitive uses

The model displays a risk probability on a public map. Misreading that probability as a medical or binary safety signal could lead a user to swim in unsafe water or avoid safe water. The UI mitigates this by:

1. Always showing the official Terviseamet `hinnang` **first** and the model layer **second**.
2. Displaying explicit disclaimers ("This is not an official health assessment").
3. A `/verify` page (Phase 3 of the compliance roadmap) that lets users cryptographically verify the snapshot's integrity.

### Fairness

No demographic attributes of site users are present in the data. The model operates on site-level measurements, not on people. Geographic coverage is Estonia-wide; whether sites in smaller counties receive equivalent measurement frequency is a data-quality question for Terviseamet, not a model fairness issue.

### Legal basis

The data is published under Estonian open-data licence. Personal data (inspector names appearing in XML metadata) is not used by the model and not redistributed on the map.

### AI Act status

In its current configuration (public visualisation, no operational control, no regulatory decision), the system is **not** a high-risk AI system under EU AI Act Annex III. Applicable obligations: Art 50 (transparency, already fulfilled via UI disclaimers). See `docs/ai_act_self_assessment.md` for the full self-assessment and the list of triggers that would move the system into high-risk.

## 9. Caveats and recommendations

- The target `compliant` is a function of the same parameters the model sees. ROC-AUC > 0.99 on a random split is expected and does not indicate general physical understanding.
- 3.1% of probes are `hidden_violation` (label = violation, no published parameter exceeds any norm). The model cannot predict these from open data alone; see `docs/phase_10_findings.md` §3.
- 10.7% are `hidden_pass` (label = compliant, checker flags violation). Dominant source: pool turbidity at 0.5–2.0 NTU labelled compliant. Likely reflects an operational tolerance band the open data does not expose.
- Pool risk probabilities shown on h2oatlas.ee for probes trained with the pre-Phase-11 `NORMS_POOL` are systematically too high; Phase 11 retrain rectifies this for new snapshots.
- Schema drift: location names change year-over-year; aggregations by raw `location` are unsafe — use `location_key` only.
- **Recommended refresh:** weekly + first-of-month (current CI cadence in `.github/workflows/citizen-snapshot.yml`). Move sooner if Terviseamet confirms faster upstream updates (inquiry Q6).

## 10. Version history

| Version | Date | Notes |
|---|---|---|
| 0.1.0 | 2026-04-20 | First published Model Card; baseline LightGBM + three sklearn models; temporal split ≤ 2024 / ≥ 2025; pool-norm correction R1 applied. |

Future versions must update §4 metrics, §7 disaggregations, and §10 this table. The Model Card is checked into the repository alongside the model weights so users can retrieve the card that matches any `.aep`-signed snapshot by commit SHA.
