# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Binary classification ML project for a TalTech Masinõpe (Machine Learning) course. Goal: predict whether a water sample complies with Estonian health norms (`compliant`: 1 = pass, 0 = violation). Data comes from Terviseamet (Estonian Health Department) in XML format via [vtiav.sm.ee](https://vtiav.sm.ee).

**Priority metric: Recall on class 0 (violations)** — a False Negative means predicting water is safe when it contains E. coli.

## Setup

```bash
pip install -r requirements.txt
pip install -e .   # обязательно: импорт data_loader из любого cwd + корректные пути к data/
```

Raw XML is not in git. The loader pulls **opendata** year files (`supluskoha_veeproovid_YYYY.xml`, `veevargi_veeproovid_YYYY.xml`, `basseini_veeproovid_YYYY.xml`, `joogiveeallika_veeproovid_YYYY.xml`), caches them as `data/raw/{domain}_{year}.xml`, and merges recent years.

```bash
python src/data_loader.py          # test download + sample
```

```python
from src.data_loader import load_domain, load_all
df = load_domain("supluskoha")
df_all = load_all()                # default: supluskoha + veevark + basseinid + joogivesi
df_two = load_all(["supluskoha", "veevark"])  # явный список доменов
```

## Running notebooks

```bash
jupyter notebook
```

Notebooks are numbered sequentially (01→06) and should be run in order.

**Imports:** after `pip install -e .`, `data_loader` is on `sys.path` for the same interpreter as the Jupyter kernel. If you skipped editable install, the notebook falls back to `git rev-parse`, `WATER_QUALITY_EE_ROOT`, or walking up from `cwd` — that can fail if the kernel runs on another host or `cwd` is `/tmp`. **Pick the project’s `.venv` as the notebook kernel**, then `pip install -e .` using that venv’s `pip`.

Do not rely on `*_executed.ipynb` copies for editing — they can lag behind; use `01_eda_supluskoha.ipynb`, etc.

## Google Colab

Use **`notebooks/colab_quickstart.ipynb`**: set `REPO_URL`, run clone + `pip install -r requirements.txt` + `pip install -e .`, then open `01`…`06` from the file browser. If a notebook’s cwd is not the repo root, run `%cd /content/water-quality-ee` (or your Drive path) first. Optional: mount Drive and set `PROJECT_ON_DRIVE` in the quickstart for a persistent `data/raw/` cache. sklearn models do not use Colab GPU.

## Data domains

Five water domains defined in `src/data_loader.DOMAINS`. **Parsers in `PARSERS`:** `supluskoha`, `veevark`, `basseinid`, `joogivesi` (opendata + legacy where applicable). **`mineraalvesi`:** no reliable opendata year files found yet — not wired in `load_all()`.

**County:** opendata often leaves `maakond` empty. `load_domain` / `load_all` can fill `county` via `src/county_infer.py` (`infer_county=True`, optional Nominatim with `geocode_county=True`). For modeling without leakage, use `engineer_features` → split → `fit_county_mapping(train)` → `encode_categoricals(df, county_mapping=...)` (see notebook 03). `build_dataset(df)` still fits county on all rows for backward compatibility.

## Architecture

**Data flow:**
1. `src/data_loader.py` — downloads XML from vtiav.sm.ee, caches to `data/raw/`, parses to DataFrame. Target variable from `hinnang` in opendata (`"ei vasta"` → 0, `"vastab"` → 1).
2. `src/features.py` — time features, ratio-to-norm features, missing indicators, categoricals. `build_dataset()` → `(X, y)`; `build_dataset_with_meta()` → `(X, y, meta)` for citizen snapshot (location, measurements, etc.). Norms in `NORMS`.
3. `src/evaluate.py` — `evaluate_model()`, `compare_models()`, plots; **`temporal_cv_metrics()`** (TimeSeriesSplit); **`best_threshold_max_recall_at_precision()`** for violation thresholding.

**Key conventions:**
- Estonian number format: commas as decimal separators (handled in data_loader)
- `compliant=None` for samples without `hinnang` — dropped in `build_dataset()`
- Imputation and scaling in `features.impute_and_scale()` — always `fit` on train only
- `enterococci` and `transparency` mostly in `supluskoha`; rich chemistry in `veevark`

## Citizen service

`citizen-service/` — Streamlit map of **per-location points** (latest sample): swimming (`supluskoha`), pools/SPA (`basseinid`), drinking water network (`veevark`). Build: `python citizen-service/scripts/build_citizen_snapshot.py`. See `citizen-service/README.md`.

## Notebooks plan

| Notebook | Purpose |
|----------|---------|
| `01_eda_supluskoha.ipynb` | EDA for swimming locations |
| `02_eda_full.ipynb` | Full EDA: `load_all()` (four opendata domains), `raw_combined.csv` |
| `03_preprocessing.ipynb` | `build_dataset`, train/test split, impute/scale → `ml_ready.joblib` |
| `04_models.ipynb` | Logistic Regression + Random Forest + GradientBoosting + GridSearchCV RF → `trained_models.joblib` |
| `05_evaluation.ipynb` | Confusion matrix, ROC, feature importance |
| `06_advanced_models.ipynb` | LightGBM + temporal split + TimeSeriesSplit CV + calibration + threshold + SHAP → `best_model.joblib` |

## Domain knowledge

- See `docs/normy.md` for regulatory thresholds by parameter
- See `docs/glosarij.md` for RU/ET/EN terminology glossary
- See `docs/parametry.md` for detailed descriptions of every water parameter (what it measures, health effects, typical sources, norms across domains)
- See `docs/report.md` for the final project report (EDA insights, methodology, model results, interpretation, limitations)
- `features.NORMS` encodes the key thresholds used for ratio features

## Tests

```bash
pip install -e . pytest && pytest tests/
```

CI: `.github/workflows/tests.yml`.
