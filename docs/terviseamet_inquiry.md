# Cooperation letter to Terviseamet — water quality open data

> **Status: DRAFT.** Rewritten as a cooperation proposal (Phase 13). Awaits:
> author signature, supervisor sign-off, Estonian translation. See
> `docs/phase_10_findings.md` for the full audit narrative and
> `docs/learning_journey.md` for the project story.

## Intended recipients

- Terviseamet open-data team (vtiav.sm.ee maintainers)
- CC: project supervisor

## Subject line

Open-source water quality risk map + findings from 69,536 probes — cooperation offer

---

## Body

Lugupeetud Terviseameti meeskond, / Dear Terviseamet team,

### Who we are

We are a student team at TalTech (Masinõpe / Machine Learning course) that has spent the past several months building a complete data pipeline and public citizen service on top of your open-data water quality feeds at `vtiav.sm.ee/index.php/opendata/`.

The result is **[h2oatlas.ee](https://h2oatlas.ee)** — an interactive public map showing the latest water quality status and probabilistic risk assessment for **2,196 locations** across Estonia: swimming sites, pools & SPA, drinking water networks, and drinking water sources. All code is open-source: [github.com/sapsan14/water-quality-ee](https://github.com/sapsan14/water-quality-ee).

We write to share some findings that may be useful to you, to ask a few questions about the data structure, and to offer our tools and willingness to collaborate.

---

### What we found — and what we fixed on our side

While validating our pipeline, we built a deterministic norm checker that compares every probe's `hinnang` label against the published parameter values using EU and Estonian thresholds. Three discoveries:

**1. We corrected our own pool norms (may be relevant to you).**
Our initial free-chlorine range for pools was [0.2, 0.6] mg/l. Empirical validation against 339 compliant pool probes showed that 85% had free chlorine between 0.6 and 1.9 mg/l — all flagged as false alarms by our system. We re-verified against Sotsiaalministri 31.07.2019 määrus nr 49 (Lisa 4) and corrected to **[0.5, 1.5] mg/l**. Similarly, combined chlorine was corrected from ≤ 0.4 to **≤ 0.5 mg/l**.

If any of your downstream systems, dashboards, or third-party consumers reference similar threshold tables, our empirical analysis and the 288 false-positive cases may be a useful cross-check.

**2. 86.2% of labels are reproducible from published data; 3.1% are not.**
After our corrections, our checker agrees with the official `hinnang` on **59,958 of 69,536 probes** (86.2%). However, **2,164 probes (3.1%)** are labelled `ei vasta nõuetele` even though no published parameter exceeds any applicable norm. We call these "hidden violations" — the compliance decision cannot be reproduced from the open-data feed alone.

Temporal cross-referencing shows this is partly a **measurement frequency effect**: for `veevark`, 97.9% of "missing" chemistry parameters are measured at the same site in other probes (quarterly chemistry vs per-probe microbiology). This is not a data error — it reflects the monitoring schedule.

**3. Your XML is complete — our parser loses nothing.**
We scanned every XML child tag under `<proovivott>` across 160 MB of production files (4 domains × 6 years). All 9 unparsed tags are metadata (inspector names, protocol IDs, sampling methodology). Zero measurement parameters are lost by our parser.

---

### What we'd like to understand

These questions would help us accurately describe the data in our project report and on h2oatlas.ee:

**Q1.** Is the open-data XML a complete mirror of each probe's lab record, or a published subset? If a subset — is the selection documented?

**Q2.** Is `hinnang` derived solely from the published parameters, or can it incorporate additional data or contextual information not in the XML?

**Q3.** Do different site types have different mandatory parameter profiles by design? (We observe that supluskoha probes never include chemistry parameters, while basseinid probes often lack microbiology.)

**Q4.** Chemistry parameters (nitrates, chlorides, sulfates) in `veevargi_veeproovid` appear in only 5–7% of probes. Is this a quarterly measurement schedule, or are they measured but not always published?

**Q5.** Is there a documented publication-frequency policy we could reference in our limitations section?

**Q6.** How frequently does Terviseamet update the opendata XML files on vtiav.sm.ee? Is it real-time (as new lab results arrive), daily, weekly, or at another cadence? Our citizen service ([h2oatlas.ee](https://h2oatlas.ee)) currently refreshes data and retrains models **weekly** (every Monday) and on the **1st of each month**, via automated GitHub Actions. If your data updates more frequently, we would be happy to increase our refresh cadence to match. What update frequency would you consider appropriate for a public-facing service like ours?

---

### What we offer

We would be happy to share any of the following:

- **Open-source audit toolkit** (`src/audit/label_vs_norms.py`, 250 lines) — a deterministic checker that can be run on any new data dump to instantly verify norm compliance against official labels. It imports thresholds directly from the feature table, so it stays in sync automatically. Could be useful for your own QA or for third-party data consumers.

- **[h2oatlas.ee](https://h2oatlas.ee)** — a public citizen map built entirely on your data. We're happy to adjust it based on your feedback — add disclaimers, correct domain labels, or link to your official pages.

- **Audit artifacts** — the probe-level parquet file with 69,536 rows, bucket classifications, and unmeasured-parameter signatures. Available for your inspection.

- **Collaboration** — if Terviseamet has data quality initiatives, documentation projects, intern or cooperation opportunities, or simply wants a student team's fresh perspective on the opendata pipeline, we are genuinely interested. This project started as a course assignment but has grown into something we care about.

---

### Context

This project is part of the TalTech Masinõpe (Machine Learning) course. Our priority metric is **Recall on violations** — a false negative means predicting water is safe when it is not. The best model (LightGBM) achieves **AUC = 0.984** and catches **94.9% of violations** at 80% precision on a temporal test set (trained on ≤2024, tested on 2025+).

We want to be clear: we are not criticizing the open-data feed — we think it is excellent, and our entire project depends on it. We are writing because we believe sharing these findings and tools is more useful than keeping them in a course report.

Suur tänu teile avatud andmete haldamise eest, / Thank you for maintaining the open-data feed,

`<author name>`
`<author email>`
[h2oatlas.ee](https://h2oatlas.ee) · [GitHub](https://github.com/sapsan14/water-quality-ee)

---

## Attachments checklist (before sending)

- [x] Numbers populated from full-corpus audit (69,536 probes, 2,164 hidden violations)
- [x] Three concrete probe examples (veevark / basseinid / supluskoha)
- [x] Pool norms correction documented with empirical evidence
- [x] XML parity scan results (zero measurement params lost)
- [x] Temporal analysis: veevark 97.9% frequency variance
- [x] Model Card (`docs/model_card.md`) — Mitchell-style model documentation
- [x] Datasheet (`docs/datasheet.md`) — Gebru-style data-provenance record
- [x] AI Act voluntary self-assessment (`docs/ai_act_self_assessment.md`) — risk tier + triggers
- [x] Per-domain metrics in `notebooks/05_evaluation.ipynb` (AI Act Art 15 disaggregation)
- [x] Public data-gap notice banner live on h2oatlas.ee (Phase 1.5 of compliance roadmap)
- [ ] Drift monitor output (Phase 2)
- [ ] Human-oversight decision tree (Phase 2)
- [ ] FRIA-light (Phase 2)
- [ ] Signed `.aep` snapshot URL (Phase 3)
- [ ] Estonian translation of the letter body
- [ ] Attach audit notebook + parquet artifact (or link to repo)
- [ ] Project supervisor sign-off
- [ ] Send to: Terviseamet open-data team (email TBD)

---

## Addendum — questions raised during Phase 1 documentation work

As we formalised the project documentation (Phase 1 of the AI Act compliance roadmap — see
`docs/ai_act_self_assessment.md`), new concrete questions emerged that we would include in the final
letter. This section is updated continuously as Phases 2–3 progress; the final version sent to
Terviseamet will consolidate them.

### A1 — Schema stability and location renames (from Datasheet §7)

**Q7.** We observed year-over-year location renames that produce duplicate apparent sites unless a
normalisation step is applied (e.g. "Harku järve supluskoht" in 2021 → "Harku järve rand" in 2025;
"veevärk" → "ühisveevärk"). We handle this via `normalize_location()` in `src/data_loader.py`. Does
Terviseamet maintain a crosswalk between historical and current site names, or is the rename policy
documented? A published mapping would let downstream consumers avoid silent data-quality regressions.

**Q8.** What is the retention policy for opendata XML files? Are older years ever republished with
corrections (e.g. after a regulatory audit)? We would like to pin the exact file version used when
signing snapshots (Phase 3), so a stable versioning guarantee — or a statement that files are
append-only after publication — would be valuable.

### A2 — Role classification under AI Act (from self-assessment §4)

**Q9.** We have classified h2oatlas.ee as **not** a high-risk AI system under EU AI Act Annex III
§2(a) on the basis that it is a post-hoc visualisation, not a safety component. The full reasoning
is in `docs/ai_act_self_assessment.md` §4. Do you (or your legal team) see the classification
differently? If you plan to deploy internal analytical models on top of open data, the same
self-assessment template is reusable; we are happy to share the blank template.

### A3 — Per-domain weakness (from Model Card §7 and `notebooks/05_evaluation.ipynb`)

**Q10.** Our per-domain evaluation shows the model is weakest on `joogivesi` (n = 376 probes), where
Recall on class 0 falls below the full-corpus average. Some of the drop likely reflects the small
sample size, but some may be because drinking-water sources (wells, springs) have domain-specific
parameter profiles we are not fully capturing. Is there published guidance on the canonical
parameter set for joogivesi probes beyond what appears in the XML?

### A4 — Documented probe refresh lag (from Datasheet §7)

**Q11.** We plan to publish signed snapshots weekly (every Monday) plus the 1st of each month. If
your publication cadence is different or varies by domain, we would be glad to tune our cadence to
avoid serving users a fresher-looking snapshot than the underlying data actually justifies. A
statement of typical end-to-end lag (sampling → lab → publication) would be useful.

### A5 — Drift-monitor findings (from `scripts/drift_monitor.py`)

Our CI drift monitor (PSI on each of the 15 numeric parameters + KL divergence on the label)
compares the training window (2021–2024) to the most recent year. Whenever the monitor reports WARN
or ALERT, we hold the snapshot and investigate. We would like to correlate our detections with any
methodological changes you are aware of:

**Q12.** Are there years where the analytical method, accredited lab panel, or reporting threshold
changed for any of the 15 parameters? A short changelog (even informal) would let us label drift
events as "known methodology change" rather than "unknown regression" and avoid false alerts.

**Q13.** The label distribution (`compliant` derived from `hinnang`) shifts ~3 pp between 2024 and
2025 in our corpus. Do you observe the same in your internal figures? If yes, is the cause
operational (more sampling of high-risk sites) or definitional (threshold change)?

### A6 — Human oversight proposal (from `docs/human_oversight.md`)

We have drafted a three-party decision tree (citizen / maintainer / Terviseamet). The Terviseamet
branch describes how you could use the `prediction_id` + `feature_hash` fields (Phase 2 artefacts in
our snapshot) to reproduce any model output a citizen asks about.

**Q14.** Is this workflow useful to you? If yes, we can add a short section to h2oatlas.ee that
links back to a Terviseamet contact point; if no, we will document the branch as a suggestion only.

### A7 — FRIA-light and child-safety mitigation (from `docs/fria_light.md`)

Children are a disproportionate user group for pools and bathing sites. Our FRIA-light flags this
as residual risk R1 and lists mitigations (UI ordering, data-gap banner, per-domain metrics).

**Q15.** Does Terviseamet already produce any fundamental-rights or DPIA documentation on your own
public-facing dashboards? If yes, we would like to align language and scope. If no, our FRIA-light
template is reusable.

### A8 — Signed snapshot provenance (from `scripts/sign_snapshot.py` + `docs/key_management.md`)

Every published snapshot on h2oatlas.ee now ships with a co-located `.aep` evidence package: a
canonicalised payload, a SHA-256 digest, an RSA-PSS-4096 signature, and the X.509 certificate used
to sign it. Verification runs entirely in the user's browser on the `/verify` page (no server
round-trip needed).

The signing backend is the deployed Aletheia service (originally `eatf.duckdns.org`, being moved to
Hetzner). A local-fallback signer exists for development and for the backend downtime window.

**Q16.** We are happy to extend the same signing chain to any public XML file Terviseamet publishes.
The benefit for you: downstream consumers (including h2oatlas.ee, journalists, researchers) can
cryptographically verify that an XML they downloaded is the original, not a tampered copy. A pilot
on one domain (say `basseinid`) is ~1 day of work on our side. Would this be useful to you?

**Q17.** We do not yet hold a trusted third-party CA cert; the current key is self-signed. If
Terviseamet already has — or is in the process of acquiring — a domain-validated certificate for
`vtiav.sm.ee`, we could use it (or a derived intermediate) as the trust anchor for `.aep` packages
that reference your data. This would tie the evidence chain to your organisation's public identity
rather than ours.

