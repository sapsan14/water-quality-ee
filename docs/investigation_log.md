# Investigation Log — Data-Quality Audit Thought Process

> **Purpose.** This document preserves the *analytical reasoning chain* behind the
> data-quality audit (Phases 9–13). It is intended for the final TalTech Masinõpe
> presentation: to show not just *what* we found, but *how we got there*, including
> wrong turns, self-corrections, and the moments where intuition was overridden by
> evidence.
>
> Companion documents: `learning_journey.md` (narrative arc), `phase_10_findings.md`
> (numeric results), `terviseamet_inquiry.md` (cooperation letter).

---

## Entry 0 — The reflection note (2026-04-15)

**Trigger.** While reviewing h2oatlas.ee, two specific probes were noticed where
the official label said "violation" but every published parameter was within norms.
This was documented in `sapsan14/life:reflect/2026-04-15_health-data-gaps.md` as
a personal reflection, not a formal finding.

**Five working hypotheses** were formulated:

1. Partial publication — internal lab records are wider than the XML export
2. Selective measurement — different site types have different mandatory panels
3. Measurement frequency — chemistry measured quarterly, micro every probe
4. Parser/export error — our pipeline or Terviseamet's export drops fields
5. Compliance on unpublished data — `hinnang` uses info not in the XML

**Discipline rule adopted:** "double-verify before any hypothesis." No hypothesis
asserted until evidence supports it; always rule out our own bugs before attributing
anything to the external data source.

---

## Entry 1 — First snapshot audit and the three surprises (Phase 10, day 1)

**What we did.** Built `src/audit/label_vs_norms.py` — a deterministic checker
that imports `NORMS` and `NORMS_POOL` directly from `features.py` (single source
of truth). Ran it against the citizen-service snapshot (2,194 probes, one latest
per location).

**Expected:** agree rate ~95%, a handful of hidden_violation to investigate.

**Got:**

| Bucket           | Count | % of labelled |
|------------------|------:|---------------|
| agree_pass       | 1,648 | 75.1%         |
| agree_violate    |   140 |  6.4%         |
| hidden_pass      |   377 | 17.2%         |
| hidden_violation |    29 |  1.3%         |
| **agree rate**   |       | **81.5%**     |

**Self-check threshold: 85%. Result: 81.5% — FAIL.**

This was the first surprise: the checker disagreed with Terviseamet on nearly
1 in 5 probes. Something was fundamentally wrong — and the question was whether
"wrong" was upstream or in our own code.

### Surprise 1: 288 false positives from wrong pool chlorine norms

Investigation of hidden_pass showed 288 of 377 were basseinid probes with
`free_chlorine` flagged. Distribution of free chlorine in compliant pool probes:

```
p1=0.46  p5=0.50  median=0.94  p95=1.40  p99=1.60  max=1.90 mg/l
```

Our `NORMS_POOL["free_chlorine_max"] = 0.6` meant that **85% of compliant pool
probes were above our upper threshold**. The constant was wrong, not the data.

**Source of the bug:** the initial NORMS_POOL values were copied from a secondary
reference without cross-checking against the actual Estonian regulation
(Sotsiaalministri 31.07.2019 määrus nr 49, Lisa 4), which specifies 0.5–1.5 mg/l.

**Impact of the fix (R1):** agree rate jumped from 81.5% to 90.8% (+9.3pp).
This single constant correction was the most impactful finding of the entire project.

**Lesson:** The ML model had been trained with the wrong `free_chlorine_deviation`
feature, inflating pool violation probabilities for every user of h2oatlas.ee.
The model still achieved AUC > 0.98 — it "learned around" the wrong norm by
downweighting the feature. **A well-performing model can mask a wrong constant.**

### Surprise 2: coliforms was missing from the norm table

10 of the 29 initial hidden_violation probes had `coliforms > 0` in drinking water,
but `features.NORMS` had no entry for coliforms at all. EU 2020/2184 requires
coliforms = 0 for drinking water. Our checker couldn't flag it because the threshold
didn't exist.

**Fix (R2):** added `coliforms > 0 → violation` for non-bathing domains in the
audit checker. This was the first audit-only rule — not yet mirrored in
`features.add_ratio_features` — creating a documented divergence between what the
model sees and what the audit checks.

**Impact:** +10 agree_violate, −10 hidden_violation, net +0.13pp.

### Surprise 3: 4 probes had zero measured parameters

4 hidden_violation probes had `n_measured_norm_params = 0` — the XML listed them
as violations but published no parameter values at all. These cannot be checked
and should not be counted as "unexplained violations." They are simply data without
enough information to reason about.

**What we did NOT do:** add an `unchecked` bucket. This remains a known limitation
(see Entry 5 below).

---

## Entry 2 — Debugging the intuition: "don't pools just not measure drinking-water params?"

A natural question arose: are the hidden_violations just a domain mismatch? Pools
measure chlorine, pH, turbidity — not nitrates, chlorides, sulfates. If we're
checking pool probes against drinking-water chemistry norms, and those params are
NaN, is that a gap or just the nature of pool monitoring?

**Answer after investigation:** partially right for hidden_pass, wrong for
hidden_violation.

- **hidden_pass (377 → 174 after R1):** mostly pool turbidity and free_chlorine.
  This IS the domain-specific norms gap. Pools have stricter turbidity (0.5 NTU
  vs 4.0) and a different chlorine standard. After correcting NORMS_POOL values
  (R1), most of these disappeared. The remaining ones are boundary cases
  (turbidity = 0.5 NTU exactly, combined_chlorine = 0.5 exactly).

- **hidden_violation (29 probes):** these are probes where `compliant = 0` but
  ALL measured params are within norms. The missing params (chemistry in pools,
  chemistry in drinking water probes tested for micro only) are missing — but the
  params that ARE present show no violation. The question becomes: was there a
  violation on a parameter that wasn't published?

**Key structural finding:** all 23 basseinid hidden_violations have e_coli missing.
`NORMS_POOL["e_coli"] = 0` — any detection is a violation for pools. If e_coli
was measured and positive but not published, that would explain the label.

---

## Entry 3 — Robustness check: do stricter drinking-water rules change anything?

**Concern raised (2026-04-16):** `NORMS["e_coli"] = 500` (bathing water). For
drinking water, EU 2020/2184 requires 0. For pools, `NORMS_POOL["e_coli"] = 0`.
But the checker uses 500 for all non-pool domains. Does this inflate
hidden_violation?

**Test:** re-ran the snapshot audit with hypothetical stricter rules:
- `e_coli = 0` for veevark / joogivesi
- `enterococci = 0` for veevark / joogivesi
- `e_coli = 0` for basseinid (from NORMS_POOL, currently not applied)

**Result: zero hidden_violation probes resolved.**

Why:
- 2 veevark hidden_violations: sid 377574 has no measurements; sid 377387 already
  has e_coli=0.0, enterococci=0.0, coliforms=0.0 — all clean.
- 1 joogivesi: no measurements at all.
- 23 basseinid: e_coli is NaN in all 23 — the stricter rule needs a measured
  value to trigger.
- 2 supluskoha: e_coli = 144, 330 — these are bathing sites where the norm IS
  500, not 0.

**Broader check:** among all 61 drinking-water violations in the snapshot, zero
have e_coli > 0 (they're already flagged by other params), and only 1 has
enterococci > 0 (already in agree_violate via another violation).

**Conclusion:** the terviseamet_inquiry.md numbers are **robust**. The
e_coli/enterococci gap is a real code-level issue worth fixing for correctness,
but it does not inflate the hidden_violation count. The inquiry letter's "2,164
hidden violations on 69,536 probes" figure will not decrease from this fix.

---

## Entry 4 — XML parity closes hypothesis #4 (Phase 10b)

**Question:** before attributing gaps to Terviseamet, prove our parser doesn't
drop fields.

**Challenge:** the developer was working from a sandboxed environment with no
outbound HTTP to `vtiav.sm.ee`. Could not download raw XML.

**Solution:** built a one-shot GitHub Actions workflow that downloaded 160 MB of
production XML (4 domains × 6 years), ran the `audit_xml_field_coverage.py`
script, and committed results back to the branch.

**Result:** all 9 unparsed XML tags across all 4 domains are metadata (inspector
names, protocol IDs, sampling methodology). **Zero measurement parameters lost.**

**Hypothesis #4: definitively closed.** Not by argument, but by evidence — a
full scan of every production XML file.

---

## Entry 5 — Full corpus confirms at scale (Phase 10b)

With network access restored via GitHub Actions, the audit ran on the full
`load_all()` corpus: **69,536 probes** across 4 domains × 6 years (2021–2026).

| Bucket           | Count  | %     |
|------------------|-------:|------:|
| agree_pass       | 53,754 | 77.3% |
| agree_violate    |  6,204 |  8.9% |
| hidden_violation |  2,164 |  3.1% |
| hidden_pass      |  7,414 | 10.7% |
| **agree rate**   |        | **86.2%** |

Agree rate: 86.2% — above the 85% self-check threshold. The snapshot (90.8%) was
optimistic because it only included the latest probe per location, biased toward
recent (better-documented) samples.

**Snapshot vs corpus ratio:** 29 hidden_violation in 2,194 probes (1.3%) →
2,164 in 69,536 (3.1%). The rate doubles because the corpus includes historical
probes with sparser measurement profiles.

---

## Entry 6 — Temporal analysis resolves the frequency question (Phase 13)

**The question that kept nagging:** why are parameters missing in hidden_violation
probes? Hypothesis #1 says "never published." Hypothesis #3 says "published in
other probes at the same site."

**Method:** for each hidden_violation probe's unmeasured parameter, check whether
the same `(location_key, domain, parameter)` has a non-null value in any other
probe in the 69,536-probe corpus.

**Result:**

| Domain     | H1: never at site | H3: measured elsewhere | Reading                      |
|------------|------------------:|----------------------:|------------------------------|
| veevark    |              2.1% |               **97.9%** | Chemistry is periodic        |
| supluskoha |           **97.9%** |                 2.1% | Chemistry never measured     |
| basseinid  |             63.0% |                37.0% | Mixed                        |
| joogivesi  |             21.6% |               **78.4%** | Similar to veevark           |
| **Overall**|           **45.1%** |              **54.9%** | Both hypotheses contribute   |

**Key insight:** veevark nitrates are measured quarterly, not every probe. A probe
fails on a parameter measured last quarter but not today — the open data shows the
failure label but not the failing measurement (it's in a different probe record).
This is the monitoring regime's structure, not a data error.

---

## Entry 7 — The strongest evidence: sid 377387

`veevark sid 377387` — Arkaadia Viljandi mnt veevärk, Tartu, 2025-12-08.

**All 14 norm parameters measured and clean:**

| Parameter       | Value  | Norm    | Ratio |
|-----------------|--------|---------|-------|
| e_coli          | 0.0    | 500     | 0.000 |
| enterococci     | 0.0    | 200     | 0.000 |
| coliforms       | 0.0    | 0*      | 0.000 |
| iron            | 0.13   | 0.2     | 0.650 |
| manganese       | 0.046  | 0.05    | 0.920 |
| pH              | 8.2    | 6.0–9.0 | in range |
| turbidity       | 0.5    | 4.0     | 0.125 |
| color           | 3.0    | 20.0    | 0.150 |
| nitrates        | 0.2    | 50.0    | 0.004 |
| nitrites        | 0.01   | 0.5     | 0.020 |
| ammonium        | 0.098  | 0.5     | 0.196 |
| fluoride        | 0.75   | 1.5     | 0.500 |
| chlorides       | 5.3    | 250.0   | 0.021 |
| sulfates        | 2.1    | 250.0   | 0.008 |

Official label: **ei vasta nõuetele** (non-compliant).

No published parameter exceeds any norm. Not even close — the highest ratio is
manganese at 0.920. With hypothesis #4 closed (parser loses nothing), this probe
can only be explained by hypothesis #5: the compliance decision was based on data
not present in the open XML.

This is the single strongest case for the Terviseamet inquiry.

---

## Entry 8 — The boundary cases (combined_chlorine = 0.5)

Four basseinid hidden_violation probes have `combined_chlorine = 0.5` — exactly
at the regulatory limit (`NORMS_POOL["combined_chlorine"] = 0.5`, check: `> 0.5`).

If Terviseamet interprets the regulation as strict `< 0.5` (i.e., 0.5 is already
a violation), these 4 probes would shift to `agree_violate`. This is a marginal
semantic question about whether the limit is inclusive or exclusive.

**Status:** documented, not resolved. This is a detail for the Terviseamet
conversation, not a code fix. The checker uses `>` (exclusive upper bound),
matching the standard convention of "≤ limit means compliant."

---

## Entry 9 — What we nearly got wrong

### 9a. Nearly wrote to Terviseamet with our own bugs

The initial snapshot audit (81.5% agree rate) was below the self-check threshold.
If we had sent the inquiry letter at that point, we would have reported 377
"unexplained passes" — of which 288 were caused by our wrong free_chlorine norm.
The letter would have included our own bugs as evidence of data gaps.

**The self-check saved us.** The 85% threshold forced investigation before
attribution.

### 9b. Nearly inflated the hidden_violation count

The concern that `e_coli = 500` for drinking water might inflate
hidden_violation was legitimate. We tested it explicitly (Entry 3) and found
zero impact on the snapshot. This robustness check took 20 minutes and would have
prevented a potentially embarrassing footnote in the inquiry letter.

### 9c. Nearly counted "no measurements" as "hidden violations"

3 probes with `n_measured_norm_params = 0` are in the hidden_violation bucket.
They have no published parameters at all — the checker has nothing to disagree
with. Calling them "hidden violations" overstates the finding. They should be
in a separate `unchecked` bucket. (Not yet implemented.)

---

## Entry 10 — Final inventory of hidden_violation (snapshot, 29 probes)

After all refinements and the robustness check, here is the honest categorization:

| Category                                    | Count | Interpretation |
|---------------------------------------------|------:|----------------|
| No measurements at all                      |     3 | `unchecked` — no conclusion possible |
| Bathing water, within "Excellent" class     |     2 | Possible 95p aggregation or contextual assessment |
| Pool, microbiology missing (e_coli = NaN)   |    23 | Likely unmeasured/unpublished micro — can't verify |
| Drinking water, all 14 params clean         |     1 | **Strongest H5 evidence** (sid 377387) |
| **Total**                                   | **29**|  |

Of the 23 pool probes: 9 have ≥10 params measured and clean (strong signal),
14 have 4–9 params (moderate signal). 4 have `combined_chlorine = 0.5` at boundary.

**On the full corpus (69,536 probes): 2,164 hidden_violation (3.1%).**
Temporal analysis (Phase 13) shows 54.9% are measurement-frequency variance,
45.1% are never-at-site parameters. These proportions are robust to the proposed
norm fixes.

---

## Entry 11 — Self-assessment: what we can and cannot claim

### We CAN claim:

- The open-data XML is complete for the fields it contains (XML parity: zero
  measurement params lost).
- 86.2% of compliance labels are reproducible from published parameters alone.
- 3.1% of probes (2,164) have a "violation" label with no published parameter
  exceeding any applicable norm.
- For veevark, 97.9% of "missing" chemistry is periodic (measured at same site
  in other probes). This is monitoring schedule, not data suppression.
- One probe (sid 377387) has all 14 parameters published and clean, yet is labelled
  non-compliant. This cannot be explained by any of hypotheses #1–#4.

### We CANNOT claim:

- That Terviseamet's labels are wrong (they may have unpublished data).
- That the open-data feed is incomplete (it may be by design).
- What the compliance algorithm is (we can only observe its inputs and outputs).
- That 2,164 is the "true" count — some fraction may be explainable by boundary
  rounding, local derogations, or assessment rules we don't know about.

---

## Cross-references

| Document                   | Relationship |
|----------------------------|-------------|
| `learning_journey.md`      | Narrative arc for presentation |
| `phase_10_findings.md`     | Numeric results and delta tables |
| `data_gaps.md`             | Methodology and hypothesis framework |
| `terviseamet_inquiry.md`   | Cooperation letter (draft) |
| `presentation_notes.md`    | Speaker cheat sheet |
| `src/audit/label_vs_norms.py` | The checker module |
| `notebooks/07_data_gaps_audit.ipynb` | Audit execution |
