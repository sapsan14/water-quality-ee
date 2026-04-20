# Fundamental Rights Impact Assessment (FRIA-light)

> **EU AI Act Art 27 (voluntary prefiguration).** Art 27 requires a FRIA only if
> the deployer is a public authority or a private operator of a public service,
> and only for Annex III high-risk systems. Neither condition applies to
> h2oatlas.ee in its current form. We produce this **FRIA-light** voluntarily
> because the moment a public body (Terviseamet, a municipality, a water
> utility) wanted to integrate the system, the same assessment would be
> required within weeks; having it ready makes that conversation faster.
>
> This is a **concise assessment**, deliberately under two printed pages. A
> full FRIA would expand §§4–6 considerably.

## 1. Deployment context

- **System.** Water-quality compliance risk estimator (`docs/model_card.md`).
- **Deployment.** [h2oatlas.ee](https://h2oatlas.ee) — public-facing map layered on top of Terviseamet open data. Operator: TalTech student team, 2026.
- **Users.** Members of the Estonian public; researchers; civic-tech observers.
- **Not deployed.** By Terviseamet, any municipality, any water utility, any healthcare provider. If any of those ever became the deployer, §§4–6 below must be expanded before launch.
- **Frequency and duration.** Public, continuous. Snapshot rebuild weekly + 1st of month.

## 2. In-scope categories of natural persons

- **Citizens consulting the map before using water** — direct audience.
- **Citizens whose residence address happens to be a monitored drinking-water site** — indirect audience (site name is visible, address is not).
- **Researchers / journalists** using the map as a secondary source.

Out-of-scope: Terviseamet staff, laboratory personnel, water-utility operators — they do not consume the map output.

## 3. Data sources summary

See `docs/datasheet.md`. The only personal data flowing through the pipeline is inspector names in the source XML; they are **not** included in any user-facing artefact and not used by the model.

## 4. Fundamental rights potentially affected

We scan the rights enumerated in the EU Charter of Fundamental Rights:

| Right | Relevance | Impact direction |
|---|---|---|
| Art 2 — right to life | Weak. The model does not replace safety decisions; Terviseamet's `hinnang` is primary. | **Positive** when it surfaces risk information earlier; **negative** if a user over-trusts a low probability. |
| Art 3 — physical integrity | Same as Art 2. | Same. |
| Art 7 — private and family life | None. No personal data about users; no tracking beyond anonymous analytics. | Neutral. |
| Art 8 — personal data | Minimal. Map locations are site-level, not people-level. | Neutral. |
| Art 11 — freedom of expression and information | Direct **positive**: the map expands access to water-quality information that was already public but hard to consume. | Positive. |
| Art 21 — non-discrimination | Low risk. Site-level signals do not classify people; geographic coverage is even across counties, but smaller counties may have fewer probes (data-quality dependency, not model bias). | Neutral / watch. |
| Art 24 — rights of the child | Children are frequent users of pools and bathing sites. A false "safe" signal is more consequential here. | **Negative** if over-trusted; mitigated by UI ordering official > model. |
| Art 35 — health care | The map is not healthcare, but it presents health-adjacent information. | Positive if used correctly. |
| Art 37 — environmental protection | The map can nudge communities towards cleaner water habits and reporting. | Positive. |
| Art 41 — good administration | Indirect. Greater transparency of regulator data supports this right. | Positive. |
| Art 47 — effective remedy | The map does not adjudicate. It is a visualisation. | Neutral. |

## 5. Risks and severity

Using a qualitative **likelihood × severity** matrix (L/M/H).

| Risk | Scenario | Likelihood | Severity | Residual score |
|---|---|---|---|---|
| R1 | User treats low P(violation) as certification of safety, ignores the official signal, and drinks/swims in water that Terviseamet flagged. | L | M | **Low** |
| R2 | User treats high P(violation) as proof the site is unsafe and avoids it despite `hinnang = compliant`. | M | L | **Low** |
| R3 | Model disagrees with `hinnang` systematically in a subgroup (e.g. pools with turbidity at 0.5–2.0 NTU) and users generalise the disagreement to all pools. | M | L | **Low** |
| R4 | Adversary distributes a forged snapshot that downplays a real violation. | L | H | **Medium** |
| R5 | Site renamed in XML → map appears to "lose" it → user concludes site is unmonitored. | M | L | **Low** |
| R6 | Minor / child-safety miscalibration: pool probabilities are systematically too high due to pre-Phase-11 free-chlorine bounds. | Resolved (Phase 11) | — | **Closed** |

## 6. Mitigations in place

| Risk | Mitigation | Location |
|---|---|---|
| R1 | UI displays official signal first; never uses the word "safe"; data-gap banner explicitly lists 3.1% unreproducible labels. | `frontend/app/components/DataGapNotice.tsx`; Dashboard renders official badge first. |
| R2 | Model layer labelled explicitly as "model"; risk colour has an AI disclaimer in the legend. | Dashboard; `docs/ml_framing.md`. |
| R3 | Per-domain metrics published so users and reviewers can see where the model disagrees. | `notebooks/05_evaluation.ipynb`; `docs/model_card.md` §7. |
| R4 | Signed `.aep` snapshots (Phase 3) + public verifier page. Public key committed to the frontend repo. | `scripts/sign_snapshot.py`, `frontend/app/verify/page.tsx`, `docs/key_management.md`. |
| R5 | `location_key` normalisation in `src/data_loader.py::normalize_location` collapses year-over-year renames. | `src/data_loader.py`. |
| R6 | Phase 11 retrain with corrected `NORMS_POOL`. Drift monitor in CI (`scripts/drift_monitor.py`) catches regressions. | `src/features.py`, `.github/workflows/citizen-snapshot.yml`. |

## 7. Oversight arrangements

See `docs/human_oversight.md` for the full three-party decision tree. In summary:

- **Citizens** decide whether to follow the signal.
- **Maintainers** decide whether to publish a snapshot (gated by drift monitor).
- **Terviseamet** can request takedown or correction at any time.

There is no automated decision-making in the Art 22 GDPR sense; the model never acts on anyone.

## 8. Residual risks accepted

- Users who ignore the UI ordering and read only the colour of the risk layer may form inaccurate beliefs. Accepted, because the alternative (removing the model layer) would discard the entire project contribution.
- 3.1% `hidden_violation` probes remain reachable on the map even though the model cannot explain them. Accepted and surfaced in the data-gap banner.

## 9. Review trigger

This FRIA-light is re-opened when any of the AI Act self-assessment triggers (`docs/ai_act_self_assessment.md` §4) fire, or annually, whichever comes first.

Last reviewed: 2026-04-20.
