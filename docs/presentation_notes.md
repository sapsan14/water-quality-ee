# Presentation Notes — TalTech [Masinõppe rakendamine](https://taltech.ee/masinope_inseneridele) Final

> Speaker cheat sheet. Numbers, story arc, demo script, potential Q&A.
> Companion to `docs/learning_journey.md` (full narrative) and `docs/report.md` (full report).

## Key numbers (cheat sheet)

| What | Number |
|---|---|
| Total probes | **69,536** |
| Domains | **4** (supluskoha, veevark, basseinid, joogivesi) |
| Years | **6** (2021–2026) |
| Features | **72** (21 raw params + 17 ratio/deviation + 21 missing indicators + 13 categorical/temporal) |
| Violations (class 0) | **8,368** (12.0%) |
| Compliant (class 1) | **61,168** (88.0%) |
| Best model | **LightGBM** — AUC **0.984**, Recall(violations) **94.9%** @ Precision 80% |
| Citizen service locations | **2,196** on [h2oatlas.ee](https://h2oatlas.ee) |
| Audit agree rate | **86.2%** (after norm corrections) |
| Hidden violations | **2,164** (3.1%) — can't be reproduced from published data |
| Pool norms bug | free_chlorine [0.2, 0.6] → **[0.5, 1.5]** mg/l — **288 false positives fixed** |
| XML parser parity | **0 measurement params lost** (160 MB scanned) |
| Temporal analysis | **54.9%** of unmeasured params = frequency variance (measured elsewhere at same site) |

## Story arc (~15 min talk)

### 1. Problem statement (2 min)
- Terviseamet publishes water quality data for all of Estonia
- Each probe: lab measurements + binary label (pass/fail)
- **Question:** can we predict violations from measurements? And can we build a public tool for citizens?
- **Priority:** Recall on violations — a false negative means "safe" water that isn't

### 2. What we built (3 min)
- Pipeline: XML → parser → features → 4 models (LR, RF, GB, LightGBM)
- **Show h2oatlas.ee** — click a pin, show official status vs model risk
- Temporal split (train ≤2024, test 2025+) — honest evaluation
- Missing indicators as features (surprise: `iron_missing` is top-10 predictor)

### 3. The audit — our own bugs first (4 min)
- Built a deterministic checker: "can I reproduce the label from published params?"
- **Expected:** yes → **Got:** 81.5% agreement — something is wrong
- **Root cause:** our pool chlorine norms were wrong (0.2–0.6 vs real 0.5–1.5 mg/l)
- After fix: **90.8%** → still 3.1% unexplainable
- XML parity scan on 160 MB: zero parser data loss
- **The deterministic checker, not the ML model, found the most impactful bug**

### 4. Temporal analysis — why 3.1% can't be explained (3 min)
- 2,164 probes where label=violation but all published params are clean
- Cross-referenced: is the "missing" param ever measured at same site?
- **veevark: 97.9% → periodic chemistry** (quarterly nitrates, not every probe)
- **supluskoha: 97.9% → never measured** (bathing directive only requires e_coli + enterococci)
- **Conclusion:** monitoring regime structure, not data errors

### 5. Results & lessons (3 min)
- LightGBM: AUC 0.984, catches 94.9% of violations
- **5 meta-lessons** (see learning_journey.md):
  1. Audit assumptions, not just code
  2. Models can mask data bugs
  3. Open data is not self-documenting
  4. The checker is the most valuable artifact
  5. Constraints drive creative solutions
- Terviseamet cooperation letter drafted — sharing tools and findings

## Demo script for h2oatlas.ee

1. **Open map** → show 4 domain pins (swimming=blue, pool=purple, drinking=green, source=orange)
2. **Click a pool** → show official status + model violation probability (should be low after norm fix)
3. **Toggle model layer** → show LR vs RF vs GB vs LightGBM predictions
4. **Find a "hidden violation" location** (sid 377387, Arkaadia Viljandi mnt veevärk) → all params clean, label=violation
5. **Show filter chips** → filter by domain, by alert status

## Potential Q&A

**Q: If the label is a function of the parameters, isn't the model just learning the thresholds?**
A: Partially — yes, and that's expected. But the model adds value in three ways: (1) handles missing values (60% of probes miss some params), (2) captures cross-parameter correlations the deterministic check misses, (3) provides calibrated probabilities, not just pass/fail.

**Q: Why not just use the deterministic checker instead of ML?**
A: The checker only works when all parameters are measured. For 22,755 probes (33%) coliforms is missing; for 46,000+ probes (66%) chemistry is partial. The ML model can still predict risk from whatever IS available.

**Q: How do you handle the class imbalance (12% violations)?**
A: `class_weight='balanced'` + threshold optimization. We prioritize Recall (catch violations) over Precision (avoid false alarms).

**Q: What's the citizen service for?**
A: Decision support, not decision making. It shows: "based on the latest sample, here's the estimated risk." It explicitly does NOT replace official assessments.

**Q: Why did you contact Terviseamet?**
A: Not to report bugs — to understand the structural relationship between published data and compliance decisions. We offer them tools (audit checker, h2oatlas.ee map) in exchange for clarity.

## Technical talking points (if asked)

- **Temporal split vs random split:** AUC 0.984 (temporal) vs 0.994 (random) — the gap is honest
- **SHAP:** iron (1.217), color (0.751), coliforms (0.591) are top-3 global predictors
- **Calibration:** Isotonic regression after prediction — turns raw probabilities into reliable ones
- **Threshold tuning:** `best_threshold_max_recall_at_precision(min_precision=0.80)` — cost-sensitive
- **Single source of truth:** NORMS in features.py → used by model AND audit checker → no drift possible
