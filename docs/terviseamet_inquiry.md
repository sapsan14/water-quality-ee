# Draft inquiry to Terviseamet — open-data reproducibility

> **Status: DRAFT. Not sent.** Review, localise (Estonian / English bilingual recommended), replace `<PLACEHOLDER>` numbers from the latest `data/audit/divergences_<date>.parquet`, and confirm the author signature before delivery. This document is a working draft kept in the repository for auditability; it should not be treated as an official communication until it has been explicitly approved.

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

We find a small but non-trivial set of probes where they do not. For **<N_HIDDEN_VIOLATION>** probes out of approximately **<N_TOTAL_LABELLED>** labelled samples (**<PCT>%**), the official `hinnang` is `ei vasta nõuetele` but no published parameter in the open-data feed exceeds its printed norm. Example probe IDs (from `data/audit/divergences_<date>.parquet`):

- `<sample_id_1>` (`<domain_1>`, `<location_1>`, sampled `<date_1>`)
- `<sample_id_2>` (`<domain_2>`, `<location_2>`, sampled `<date_2>`)
- `<sample_id_3>` (`<domain_3>`, `<location_3>`, sampled `<date_3>`)

These are not model errors — no machine-learning is involved in detecting them. A simple `for each parameter: is value > threshold?` loop finds the same set. We would like help understanding the source of the divergence.

Before writing, we ruled out the most obvious in-repo explanations:

1. **Parser loss.** We audited every XML child tag under `<proovivott>` and confirmed that every field present in the files is either extracted by our parser or is structurally unrelated to compliance (timestamps, IDs, free-text comments). The script is `scripts/audit_xml_field_coverage.py` in the repository; happy to share its output.
2. **Feature-code drift.** Our norm thresholds are imported directly from the feature-engineering code that trains the model — there is no second copy of the numbers.
3. **Unit conversion.** Iron and manganese `ug/l` values are converted to `mg/l` at parse time.

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

- [ ] Replace `<N_HIDDEN_VIOLATION>`, `<N_TOTAL_LABELLED>`, `<PCT>` with the numbers from the most recent `data/audit/divergences_<date>.parquet`.
- [ ] Replace `<sample_id_N>` / `<location_N>` / `<date_N>` with three concrete, diverse examples (different domains, different years).
- [ ] Re-run `scripts/audit_xml_field_coverage.py` and confirm no `parsed=0` rows with non-trivial values remain — otherwise fix the parser first.
- [ ] Attach (or link) the audit notebook and parquet artifact.
- [ ] Translate to Estonian (optional but recommended).
- [ ] Project supervisor sign-off.
