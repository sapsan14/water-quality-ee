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

Raw XML is not in git. The loader pulls **opendata** year files (`…/opendata/supluskoha_veeproovid_YYYY.xml`, `veevargi_veeproovid_YYYY.xml`), caches them as `data/raw/{domain}_{year}.xml`, and merges recent years.

```bash
python src/data_loader.py          # test download + sample
```

```python
from src.data_loader import load_domain, load_all
df = load_domain("supluskoha")
df_all = load_all()                # supluskoha + veevark
```

## Running notebooks

```bash
jupyter notebook
```

Notebooks are numbered sequentially (01→05) and should be run in order.

**Imports:** after `pip install -e .`, `data_loader` is on `sys.path` for the same interpreter as the Jupyter kernel. If you skipped editable install, the notebook falls back to `git rev-parse`, `WATER_QUALITY_EE_ROOT`, or walking up from `cwd` — that can fail if the kernel runs on another host or `cwd` is `/tmp`. **Pick the project’s `.venv` as the notebook kernel**, then `pip install -e .` using that venv’s `pip`.

Do not rely on `*_executed.ipynb` copies for editing — they can lag behind; use `01_eda_supluskoha.ipynb`, etc.

## Google Colab

Use **`notebooks/colab_quickstart.ipynb`**: set `REPO_URL`, run clone + `pip install -r requirements.txt` + `pip install -e .`, then open `01`…`05` from the file browser. If a notebook’s cwd is not the repo root, run `%cd /content/water-quality-ee` (or your Drive path) first. Optional: mount Drive and set `PROJECT_ON_DRIVE` in the quickstart for a persistent `data/raw/` cache. sklearn models do not use Colab GPU.

## Data domains

Five water domains defined in `src/data_loader.DOMAINS`. Only `supluskoha` and `veevark` have parsers implemented (`PARSERS` dict). Remaining domains (`basseinid`, `joogivesi`, `mineraalvesi`) need parsers added to `data_loader.py` following the same pattern.

## Architecture

**Data flow:**
1. `src/data_loader.py` — downloads XML from vtiav.sm.ee, caches to `data/raw/`, parses to DataFrame. Each domain has a dedicated `parse_<domain>()` function. Target variable: `vastavus` field (`jah`→1, `ei`→0); any `ei` in a sample → `compliant=0`.
2. `src/features.py` — takes raw DataFrame, adds time features, ratio-to-norm features, missing indicators, encodes categoricals. `build_dataset()` is the main entry point → returns `(X, y)`. Norms are defined in the `NORMS` dict.
3. `src/evaluate.py` — model evaluation utilities: `evaluate_model()`, `compare_models()`, and plot functions for confusion matrix, ROC curves, feature importance. Note: `plot_roc_curve()` expects `y_test` inside each result dict but `evaluate_model()` doesn't store it — pass it manually.

**Key conventions:**
- Estonian number format: commas as decimal separators (handled by `_float()` in data_loader)
- `compliant=None` for samples with no `vastavus` field — these are dropped in `build_dataset()`
- Imputation and scaling in `features.impute_and_scale()` — always `fit` on train only

## Notebooks plan

| Notebook | Purpose |
|----------|---------|
| `01_eda_supluskoha.ipynb` | EDA for swimming locations |
| `02_eda_full.ipynb` | Full EDA: supluskoha + veevark, save `raw_combined.csv` |
| `03_preprocessing.ipynb` | `build_dataset`, train/test split, impute/scale → `ml_ready.joblib` |
| `04_models.ipynb` | Logistic Regression + Random Forest → `trained_models.joblib` |
| `05_evaluation.ipynb` | Confusion matrix, ROC, feature importance |

## Domain knowledge

- See `docs/normy.md` for regulatory thresholds by parameter
- See `docs/glosarij.md` for RU/ET/EN terminology glossary
- `features.NORMS` encodes the key thresholds used for ratio features
