# Datasheet — Water Quality Estonia Corpus

> **Structure:** Gebru et al. 2021, *Datasheets for Datasets*.
> Companion to `docs/model_card.md`. Covers the 69,536-probe corpus served by `src/data_loader.load_all()`.

## 1. Motivation

### Why was the dataset created?

Estonian Terviseamet (Health Board) publishes laboratory sampling results for regulated water sites as annual XML files on [vtiav.sm.ee/index.php/opendata/](https://vtiav.sm.ee/index.php/opendata/). We assembled those files into a versioned corpus for a binary classifier that estimates P(violation) on the most recent sample per site.

The corpus is a secondary dataset built on a primary public source. We add: parsing, multi-year concatenation, location-key normalisation, county inference, label audit, and feature engineering.

### Who created the dataset and who funded it?

Primary data is produced by Terviseamet and the accredited laboratories they contract with. The derived corpus and the code that produces it were created by a TalTech Masinõpe student team in 2026; there is no external funding.

### Any other comments?

The dataset is not redistributed as a static file; it is reproduced on demand from Terviseamet's upstream. Our repository only caches intermediate XML in `data/raw/` on CI runners. Downstream artefacts (`snapshot.json`, `.aep` signature packages) are published under MIT licence.

## 2. Composition

### What do the instances represent?

Each row is **one water sample** taken at a monitored site on a specific date. Four site categories (domains) are present:

| Domain | Meaning |
|---|---|
| `supluskoha` | Outdoor swimming (sea, lake, river). Bathing-water category under EU 2006/7/EC. |
| `basseinid` | Indoor pools, SPAs, paddling pools. Regulated under Sotsiaalministri määrus nr 49/2019. |
| `veevark` | Drinking-water distribution network taps. Under EU 2020/2184. |
| `joogivesi` | Drinking-water sources (wells, springs, intakes). Under EU 2020/2184. |

### How many instances are there in total?

**69,536 labelled probes** (2021–2026, four domains).

| Domain | n | % of corpus |
|---|---:|---:|
| veevark | 34,626 | 49.8% |
| basseinid | 30,503 | 43.9% |
| supluskoha | 4,031 | 5.8% |
| joogivesi | 376 | 0.5% |

### Is this a sample from a larger set?

Yes. It is the subset Terviseamet elects to publish as opendata. Inspector names, protocol references, and some metadata tags are present in the XML but do not expose the full internal lab records. The 3.1% `hidden_violation` residual (labels that cannot be reproduced from published parameters — see `docs/phase_10_findings.md` §3) is circumstantial evidence that at least some compliance decisions use unpublished inputs.

### What data does each instance consist of?

- Identifier fields: `sample_id`, `location`, `location_key` (normalised), `county`, `domain`, `sample_date`.
- 15 numeric measurements: `e_coli`, `enterococci`, `coliforms`, `ph`, `turbidity`, `color`, `transparency`, `iron`, `manganese`, `nitrates`, `nitrites`, `ammonium`, `fluoride`, `chlorides`, `sulfates`, plus pool-specific `staphylococci`, `pseudomonas`, `free_chlorine`, `combined_chlorine`, `oxidizability`, `colonies_37c`.
- Categorical: `season`, `is_summer`, `year`, `month` (derived from `sample_date`).
- Target: `compliant ∈ {0, 1}` derived from Terviseamet's `hinnang` string (`"ei vasta nõuetele"` → 0, `"vastab"` → 1, else → NaN).

Full parameter descriptions: `docs/parametry.md`. Regulatory thresholds: `docs/normy.md`.

### Is there a label?

Yes: `compliant`. Derivation is deterministic from the XML `hinnang` field in `src/data_loader.py::_compliant_from_hinnang`. Rows with `hinnang` absent or unrecognised are dropped in `build_dataset()`.

### Is any information missing?

Yes, heavily and by design:

- **supluskoha probes never publish chemistry** (~98% of chemistry fields empty) — expected under EU 2006/7/EC.
- **basseinid probes often lack microbiology** — the mandatory pool profile is chemistry-driven.
- **veevark chemistry is 5–7% populated per probe** but 97.9% of the "missing" values ARE measured at the same site in a different probe (quarterly schedule vs per-probe microbiology).

The `*_missing` binary indicators in `features.add_missing_indicators` let the model learn from the absence pattern itself.

### Are there dependencies between instances?

Yes:

- Same physical site yields many probes over time.
- `location` strings are renamed year-over-year; `location_key` collapses variants. Always aggregate by `location_key`, never by raw `location`.
- Bathing-water classification under EU 2006/7/EC uses 95th-percentile windows over a four-year rolling set of probes, not individual probes. The audit module applies this correctly (`audit_dataframe_with_bathing_aggregation`); the feature pipeline does not (it treats probes independently, which is the correct assumption for a per-probe classifier but not for reproducing bathing-water status labels).

### Are there recommended data splits?

Yes — **temporal**. Train ≤ 2024, test ≥ 2025. The model's purpose is generalisation to samples the lab has not yet produced; random splits overestimate performance because a site's probes cluster in feature space.

### Errors, sources of noise, redundancies?

- Estonian decimal separator (comma) — handled in parsing.
- Stale location names — handled via `location_key`.
- Wrong `NORMS_POOL` free-chlorine bounds before Phase 10 — corrected in Phase 11 retrain.
- Residual 3.1% `hidden_violation` (possible unpublished-data violations) and 10.7% `hidden_pass` (possible operational tolerance bands). See `docs/phase_10_findings.md`.

### Is the dataset self-contained?

No. The parsing pipeline fetches Terviseamet XML on demand. If Terviseamet removes or restructures opendata files, the corpus cannot be rebuilt. We partially mitigate by caching `data/raw/` XML in CI runs but not in the repo.

### Does the dataset contain confidential / sensitive data?

No. It is published as opendata. The only personal data present (inspector names in `<proovivotja_nimi>`) is not used by the model and not re-exported to the map.

## 3. Collection process

### How was the data acquired?

Directly observable laboratory measurements from accredited Estonian labs, submitted to Terviseamet and aggregated into the opendata XML stream. Our pipeline (`src/data_loader.py`) downloads the per-year, per-domain XML files and parses them into a pandas DataFrame.

### What mechanisms were used to collect it?

HTTP GET from `vtiav.sm.ee` using the URL convention `{domain}_veeproovid_{YYYY}.xml`. Files are cached in `data/raw/` for idempotent re-runs.

### Over what timeframe?

Site measurements: 2021–2026 (six full years plus the year-to-date). Download: every run of `data_loader` or the scheduled CI job (weekly + 1st of month).

### Does the dataset relate to people?

Only via the public monitoring of public water sites. No data about the water users is recorded.

### Were any ethical review processes conducted?

Not applicable: public-sector opendata, no human subjects.

## 4. Preprocessing / cleaning / labelling

- Numeric parsing: Estonian comma → decimal point in `src/data_loader.py::_parse_number`.
- Date parsing: `sample_date` from XML `proovi_kuupaev` tag, dtype `datetime64[ns]`.
- Location normalisation: `src/data_loader.py::normalize_location` strips suffixes, lowercases, collapses whitespace → `location_key`.
- County inference: `src/county_infer.py::infer_county` (lookup + optional OpenCage geocoding; see `citizen-service/GEO_SECRETS.md`).
- Label derivation: deterministic from `hinnang` (see §2 above).
- Ratio features: each measurement divided by the corresponding norm in `features.NORMS` (or `features.NORMS_POOL` for basseinid). pool-specific pH range handled separately.
- Missing indicators: `f"{col}_missing"` binary flags for all 15+ numeric parameters.
- Imputation and scaling (`features.impute_and_scale`) are fit on train only.

Every preprocessing step is pure-Python and reproducible from the XML inputs.

## 5. Uses

### Intended uses

- Training the compliance classifier family (see Model Card).
- Data-quality audit (`src/audit/label_vs_norms.py`) of Terviseamet's open-data pipeline.
- Civic-tech visualisation on [h2oatlas.ee](https://h2oatlas.ee).
- Course work and teaching examples (TalTech Masinõpe, 2026).

### Tasks the dataset could support

- Binary compliance classification (current).
- Bathing-water classification under EU 2006/7/EC 95p rolling aggregation.
- Drift analysis over time (2021 baseline vs 2025–2026 shift).
- Deterministic auditing of any future Terviseamet data dump.

### Tasks the dataset should NOT be used for

- Medical / clinical decision making.
- Predicting unmeasured contaminants (viruses, pesticides, PFAS).
- Safety automation or operational control of treatment plants.
- Re-identification of individuals; the dataset has no such data but the principle is stated for completeness.

### Are there any known biases?

- **Sampling bias:** sites with historical violations may be sampled more often. The open data does not expose sampling schedules.
- **Periodic chemistry bias:** `veevark` chemistry is quarterly-to-annual; a new site without historical chemistry triggers many missing features, and the missing-indicators may act as a proxy for "new site".
- **Label asymmetry:** 3.1% `hidden_violation` cases may include decisions based on unpublished context (field notes, re-samples) that the model cannot observe.

## 6. Distribution

### How will the dataset be distributed?

The corpus is not redistributed as a file. Users reproduce it on demand by running `python src/data_loader.py`. Derived artefacts (`snapshot.json`, `.aep`) are published from the CI pipeline.

### Under what licence?

- Primary XML: Terviseamet opendata licence — public, free reuse with attribution.
- Derived code and artefacts in this repository: MIT (see `LICENSE`).

### Any export restrictions?

None known.

## 7. Maintenance

### Who maintains the dataset?

The student team at TalTech, 2026. Contact: [GitHub issues](https://github.com/sapsan14/water-quality-ee/issues).

### How often is it updated?

Upstream: TBD — Terviseamet's opendata refresh cadence is an open question (inquiry Q6 in `docs/terviseamet_inquiry.md`). Our pipeline polls weekly + on the 1st of each month.

### Is the dataset versioned?

Yes, via:

- Git commit SHAs for the code that produces it.
- `.aep` signature packages (Phase 3 of compliance roadmap) that bind a specific `snapshot.json` content hash to a commit, model version, and timestamp.

### Will older versions continue to be supported?

Snapshots older than ~12 months are not actively rebuilt but remain in the git history and as `.aep` artefacts. The deterministic audit checker works on any snapshot without model retraining.

### Any errata or known issues?

- Pre-Phase-11 snapshots carry an incorrect `free_chlorine_deviation` feature (pool norms [0.2, 0.6] instead of [0.5, 1.5]) — pool risk probabilities are systematically too high in those artefacts. See `docs/phase_10_findings.md` §R1.
- `mineraalvesi` (mineral water) domain is not included because stable opendata URLs are not available.

## 8. Open questions for Terviseamet

These questions cannot be resolved from the published data and are carried in `docs/terviseamet_inquiry.md`:

- Is the XML a complete mirror of each probe's record, or a curated subset? (Q1)
- Is `hinnang` derived only from published parameters, or also from unpublished context? (Q2)
- Are different site types governed by different mandatory parameter profiles? (Q3)
- What is the measurement schedule for chemistry parameters in `veevark`? (Q4)
- What is the documented publication-frequency policy? (Q5)
- What is the authoritative refresh cadence to synchronise our weekly rebuild with? (Q6)
- **New (Phase 1):** Is there a documented retention policy for opendata XML? Are older years ever republished with corrections?
- **New (Phase 1):** What is the policy for renaming a site (e.g. "supluskoht" → "rand") — is a crosswalk published, or must consumers infer it?
