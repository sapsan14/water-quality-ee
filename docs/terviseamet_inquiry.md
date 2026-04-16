# Draft inquiry to Terviseamet — open-data reproducibility

> **Status: DRAFT (Phase 10b — full-corpus numbers populated).** All numerical
> placeholders have been filled from the full-corpus audit on **69 536 probes**
> (`data/audit/divergences_full_2026-04-16.parquet`), downloaded via GitHub Actions
> from `vtiav.sm.ee` on 2026-04-16. Author signature, supervisor sign-off, and
> Estonian translation are still pending before delivery. See
> `docs/phase_10_findings.md` for the full audit narrative.

## Intended recipients

- Terviseamet open-data team (vtiav.sm.ee maintainers)
- CC: project supervisor, if relevant

## Subject

Open-data reproducibility of water-quality compliance decisions — request for clarification

## Tone and framing

- Engineering collaboration, not accusation. We are users of the open-data feed who have built a reproducible pipeline on top of it, and we've noticed a pattern we'd like help interpreting.
- No claim about internal processes or policy intent. We describe only what we observe externally and list hypotheses; we do not assert which is correct.
- Offer concrete artifacts (notebook, parquet of probe IDs) so the answer can be verified, not just discussed.

---

## Body (draft)

Dear Terviseamet team,

We have built a reproducible data pipeline on top of the open-data XML feeds at `https://vtiav.sm.ee/index.php/opendata/` (`supluskoha_veeproovid_YYYY.xml`, `veevargi_veeproovid_YYYY.xml`, `basseini_veeproovid_YYYY.xml`, `joogiveeallika_veeproovid_YYYY.xml`) as part of a public student project on water-quality monitoring. Full source is at [water-quality-ee repository](https://github.com/sapsan14/water-quality-ee).

As part of validating our pipeline, we cross-checked every probe's `hinnang` label against a deterministic norm check derived directly from the parameter values published in the same XML files, using the thresholds in `docs/normy.md` (EU 2006/7/EC for bathing waters, EU 2020/2184 for drinking water, Estonian regulations for pools). We expected these two assessments to agree on every probe.

We find a non-trivial set of probes where they do not. On the **full corpus** of **69 536** labelled probes across 4 domains × 6 years (2021–2026), **2 164 probes (3.1 %)** have an official `hinnang` of `ei vasta nõuetele` but no published parameter in the open-data feed exceeds its printed norm — even after we corrected our own pool free-chlorine and combined-chlorine norms (which had been internally too strict — see below) and added a coliform-detection rule. The breakdown: basseinid 1 260, veevark 777, supluskoha 120, joogivesi 7. Three concrete examples (from `data/audit/divergences_full_2026-04-16.parquet`, all from different domains, counties and years):

- **`377387`** (`veevark`, *Arkaadia Viljandi mnt veevärk*, Tartu maakond, sampled 2025-12-08). Strongest case. All 14 published parameters are present and clean: e_coli=0, enterococci=0, pH=8.2, nitrates=0.2, nitrites=0.01, ammonium=0.098, fluoride=0.75, manganese=0.046, iron=0.13, turbidity=0.5, color=3, coliforms=0, chlorides=5.3, sulfates=2.1. Every value is well below its norm, yet `hinnang = ei vasta nõuetele`.
- **`347163`** (`basseinid`, *Ring spaa ja saunad — laste mänguala*, Harju maakond, sampled 2024-11-29). Pool with normal pH (7.0), turbidity (0.3), free chlorine (1.3, inside the operational range), combined chlorine (0.4) and oxidizability (4.5). The full microbiology profile (e_coli, enterococci, staphylococci, pseudomonas, coliforms) is **not present** in the open-data XML for this probe. The non-compliant verdict cannot be reproduced from the published parameters because the relevant ones are missing.
- **`366758`** (`supluskoha`, *Pedeli paisjärve supluskoht*, Valga maakond, sampled 2025-08-17). Bathing site with e_coli=144 and enterococci=164 — both inside the EU 2006/7/EC "Excellent" thresholds (≤ 500 / ≤ 200 CFU/100 mL). No other parameters are published for the probe. Yet `hinnang = ei vasta nõuetele`.

These are not model errors — no machine-learning is involved in detecting them. A simple `for each parameter: is value > threshold?` loop finds the same set. We would like help understanding the source of the divergence.

Before writing, we ruled out the most obvious in-repo explanations:

1. **Parser loss.** We ran `scripts/audit_xml_field_coverage.py` against all cached XML files (160 MB across 4 domains × 6 years). All 9 unparsed tags are metadata (inspector names, protocol IDs, sampling methodology) — zero measurement parameters are lost. The full inventory is at `data/audit/xml_field_inventory.csv`.
2. **Feature-code drift.** Our norm thresholds are imported directly from the feature-engineering code that trains the model — there is no second copy of the numbers. The audit module `src/audit/label_vs_norms.py` re-uses `features.NORMS` / `features.NORMS_POOL` at import time so any threshold edit propagates automatically.
3. **Unit conversion.** Iron and manganese `ug/l` values are converted to `mg/l` at parse time.
4. **Our own pool norms.** We initially had `free_chlorine` set to a [0.2, 0.6] mg/l operational range and `combined_chlorine` ≤ 0.4 mg/l. Empirically validated against your published `hinnang` field on 2 194 probes, those bounds were too strict: 288 of 339 compliant pool probes had free chlorine in the [0.6, 1.9] mg/l band, and 25 % of compliant pool combined-chlorine values exceeded 0.4 mg/l. We re-verified against Sotsiaalministri 31.07.2019 määrus nr 49 Lisa 4 and updated our table to `free_chlorine` 0.5–1.5 mg/l and `combined_chlorine` ≤ 0.5 mg/l. After this fix the deterministic checker agrees with the official `hinnang` on **86.2 %** of the full 69 536-probe corpus (and 90.9 % on a smaller 2 194-probe snapshot used during iterative development), and the residual 2 164 hidden_violation probes above are what we are writing about.

That leaves a few external explanations we cannot distinguish from the public side alone. Could you help us understand which apply?

**Q1.** Is the open-data XML feed published at `vtiav.sm.ee/index.php/opendata/` a complete mirror of the internal laboratory record for each probe, or does it contain a subset of parameters? If it is a subset, is the subset published per probe documented somewhere?

**Q2.** Is the official `hinnang` decision for a probe derived from the parameters that appear in the published XML, or can it be based on additional parameters or contextual information that is not included in the public feed?

**Q3.** Do different site types (supluskoha, veevärk, joogivee allikas, bassein) have different mandatory parameter profiles — i.e., parameters that are either not measured or not published for some site types by design?

**Q4.** Some parameters (e.g. nitrates, chlorides, sulfates in `veevargi_veeproovid`) appear in only 5–7 % of samples. Is this seasonality (e.g. annual measurements reported only on one probe per year), or are they measured more often but not always published?

**Q5.** Is there a documented publication-frequency policy per parameter (e.g. "microbiology on every probe, chemistry on a quarterly schedule")? If so, we'd love to reference it in our project's limitations section.

We're happy to share our audit notebook and the anonymised parquet of example probe IDs so you can inspect the specific cases. The intent is not to criticise the open-data feed — we think it's excellent and use it directly in our project — but to understand the structural relationship between what is published and how the compliance decision is made, so that we can correctly describe it to readers of our project report.

Thank you for your time and for maintaining the open-data feed,

`<author name>`  
`<author email>`  
`<project link>`

---

## Attachment checklist (before sending)

- [x] Replace `<N_HIDDEN_VIOLATION>`, `<N_TOTAL_LABELLED>`, `<PCT>` — populated to **2 164 / 69 536 / 3.1 %** from `data/audit/divergences_full_2026-04-16.parquet` (Phase 10b).
- [x] Replace `<sample_id_N>` / `<location_N>` / `<date_N>` — three diverse examples picked covering veevark / basseinid / supluskoha across Tartu / Harju / Valga counties.
- [x] Re-run `scripts/audit_xml_field_coverage.py` against populated `data/raw/` (160 MB, 4 domains × 6 years). Result: zero measurement parameters lost. Output: `data/audit/xml_field_inventory.csv`.
- [x] Re-run audit on the full `load_all()` corpus (69 536 probes). Numbers updated.
- [ ] Attach (or link) the audit notebook and parquet artifact.
- [ ] Translate to Estonian (optional but recommended).
- [ ] Project supervisor sign-off.
