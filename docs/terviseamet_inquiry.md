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

We are a student team at TalTech ([Masinõppe rakendamine tehniliste erialade spetsialistidele](https://taltech.ee/masinope_inseneridele) course) that has spent the past several months building a complete data pipeline and public citizen service on top of your open-data water quality feeds at `vtiav.sm.ee/index.php/opendata/`.

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

This project is part of the TalTech [Masinõppe rakendamine tehniliste erialade spetsialistidele](https://taltech.ee/masinope_inseneridele) course. Our priority metric is **Recall on violations** — a false negative means predicting water is safe when it is not. The best model (LightGBM) achieves **AUC = 0.984** and catches **94.9% of violations** at 80% precision on a temporal test set (trained on ≤2024, tested on 2025+).

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
- [ ] Estonian translation of the letter body
- [ ] Attach audit notebook + parquet artifact (or link to repo)
- [ ] Project supervisor sign-off
- [ ] Send to: Terviseamet open-data team (email TBD)
