# EU AI Act — Voluntary Self-Assessment

> **Status:** voluntary self-assessment, not a formal declaration of conformity.
> **Regulation:** Regulation (EU) 2024/1689 (EU AI Act), adopted 13 June 2024, phased application through 2026–2027.
> **Scope:** h2oatlas.ee — the public citizen service built on this repository.
> **Last reviewed:** 2026-04-20.

## 1. Executive summary

| Question | Answer |
|---|---|
| Is the system within scope of the AI Act? | **In scope** (Art 3(1) AI system definition met). |
| Does a scope exclusion apply (Art 2)? | **Partially** — Art 2(6) scientific R&D exclusion applies to notebooks and research outputs but **not** to the public deployment at h2oatlas.ee. |
| Is the system a prohibited practice (Art 5)? | **No.** |
| Is the system high-risk (Art 6, Annex III)? | **No, in the current configuration.** See §4 for triggers. |
| Is the system a general-purpose AI model (Art 51)? | **No.** |
| Does Art 50 (transparency) apply? | **Arguably yes** — the model output is presented to users and labelled as an AI-generated probability. Fulfilled by UI disclaimers. |
| Do we follow voluntary codes of conduct (Art 95)? | **Yes** — this repository (Model Card, Datasheet, FRIA-light, cryptographic provenance). |

**Bottom line:** no mandatory AI Act obligations bind the project in its current configuration. We adopt the high-risk documentation stack voluntarily for educational, presentational, and future-proofing reasons.

## 2. Is it an AI system?

Art 3(1) defines an AI system as *a machine-based system that, for explicit or implicit objectives, infers, from the input it receives, how to generate outputs such as predictions, content, recommendations, or decisions that can influence physical or virtual environments, with varying levels of autonomy*.

Our system meets the definition:

- **Machine-based:** LightGBM / Random Forest / Gradient Boosting / Logistic Regression (`src/features.py` + `best_model.joblib`).
- **Objective:** binary classification of compliance (`compliant`).
- **Inference:** from 15 laboratory parameters + engineered features to P(violation).
- **Output:** a probability rendered on a public map.
- **Autonomy:** inference pipeline runs without human intervention in the weekly CI build.

## 3. Does a scope exclusion apply?

### Art 2(6) — scientific research and development

*The Regulation does not apply to AI systems or AI models, including their output, specifically developed and put into service for the sole purpose of scientific research and development.*

- **Notebooks and research artefacts** (`notebooks/`, `docs/report.md`, `docs/learning_journey.md`) are within this exclusion.
- **h2oatlas.ee as a public service** is **not** within this exclusion — it serves the public, not research.

The project therefore carries a split character: research exemption for research outputs, no exemption for the deployed citizen service.

### Art 2(8) — testing in real-world conditions

Not invoked: we are not running a regulatory pre-market test.

### Other exclusions (military, national security, personal use) — not applicable.

## 4. Is it a high-risk AI system?

### Art 6(1) — Annex I product-safety

Not applicable. No regulated product is integrated with the system.

### Art 6(2) — Annex III use cases

Annex III lists areas where AI systems are automatically high-risk. Relevant entries considered:

- **Annex III §2(a)** — safety components in the management and operation of critical digital infrastructure, road traffic, or the supply of water, gas, heating and electricity.

**Assessment for h2oatlas.ee:**

A *safety component* is defined by Art 3(14) as a component whose failure or malfunctioning endangers the health, safety or security of persons or property. The public map:

- Does not issue control commands to water infrastructure.
- Does not gate access to public services.
- Does not trigger alerts to utilities or health authorities.
- Is a post-hoc visualisation of already-public data plus a probabilistic estimator.

The official Terviseamet `hinnang` remains authoritative and is displayed first; the ML layer is presented as a **second**, probabilistic view with explicit disclaimers.

**Conclusion:** the system is **not** a safety component under Art 3(14), therefore **not** high-risk under Annex III §2(a).

Other Annex III entries (§5 access to essential services, §6 law enforcement, §7 migration, §8 administration of justice, §4 employment, §3 education) do not apply.

### Art 6(3) — the "non-significant risk" carve-out

Even if a system falls within Annex III, it can be deemed non-high-risk if *it does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision-making*. Four sub-conditions listed in Art 6(3) (narrow procedural task; improving a completed human activity; detecting deviation patterns without replacing human assessment; preparatory task).

If ever reassessed as falling within Annex III, h2oatlas.ee would rely on the third limb: it detects patterns that deviate from the compliant distribution without replacing the official `hinnang`.

### Triggers that would move the system into high-risk

This list is explicit so reviewers can check whether any change crosses the line:

1. **Integration into Terviseamet's operational workflow** — e.g. the model output is used to schedule inspections, close beaches, recall water batches, or issue enforcement. → Annex III §2(a) safety component.
2. **Integration into a water utility's operational control** — e.g. the probability drives chlorination, valve actuation, or alarms. → Annex III §2(a).
3. **Use by a public authority for decision support on regulatory actions** — e.g. a ministry uses the probability to prioritise enforcement. → potentially Annex III §5 (access to essential public services) or §2(a), depending on the pipeline.
4. **"Placing on the market" as a commercial product** — selling the model or its output to utilities, insurers, or property services. → full provider obligations under Chapter III Section 2.
5. **Deployment by a public body in the EU** — regardless of high-risk status, Art 27 requires a Fundamental Rights Impact Assessment. We already hold a FRIA-light (`docs/fria_light.md`) ready.

## 5. Art 50 — transparency obligations

Art 50(1) requires providers of AI systems interacting with natural persons to ensure users are informed they are interacting with an AI system. Art 50(2)–(6) cover synthetic content and deep-fake labelling (not applicable here).

**How we fulfil Art 50(1):**

- The map UI labels the risk layer as "модель" / "model" in every locale.
- Disclaimer text on the landing page and in the per-location panel states that the risk assessment is a probabilistic estimate, not an official health assessment.
- The Phase-1 data-gap banner (planned) explicitly tells users that 3.1% of official violation labels cannot be reproduced from published data and that the model is therefore conservative on this slice.
- The `/verify` page (Phase 3) lets users inspect the exact snapshot, model version, and signing evidence.

## 6. Art 51 — general-purpose AI models

Not applicable: the models are narrow classifiers trained on a specific task.

## 7. Art 95 — voluntary codes of conduct

We adopt voluntary measures that mirror the high-risk documentation stack:

| Instrument | Artefact | Referenced Art |
|---|---|---|
| Risk management system | Phase 1–4 roadmap (planning file) | Art 9 |
| Data governance | `docs/datasheet.md`, `docs/phase_10_findings.md` | Art 10 |
| Technical documentation | `docs/model_card.md`, this file, `docs/report.md` | Art 11, Annex IV |
| Record-keeping / logs | `prediction_id`, `model_version`, `feature_hash` (Phase 2) + `.aep` snapshot signatures (Phase 3) | Art 12 |
| Transparency to users | UI disclaimers + `/verify` page | Art 13, Art 50 |
| Human oversight | `docs/human_oversight.md` (Phase 2) | Art 14 |
| Accuracy, robustness, cybersecurity | Per-domain metrics in `05_evaluation.ipynb`; drift monitor in CI; signed snapshots | Art 15 |
| Conformity assessment (voluntary) | This self-assessment | Art 43 |
| Fundamental rights impact | `docs/fria_light.md` (Phase 2) | Art 27 |

## 8. Obligations we **do not** take on

To avoid overclaiming, we flag what we explicitly do not do:

- No **CE marking** (Art 48). The system is not in an Annex I conformity-assessment regime.
- No **registration in the EU database** (Art 49, 71). Reserved for Annex III high-risk systems.
- No **post-market monitoring plan** per Art 72. Replaced by the drift monitor + manual review.
- No **serious incident reporting** per Art 73. There is no operational coupling whose failure would constitute a reportable incident.
- No **authorised representative** (Art 22). The maintainers are in the EU.

## 9. Review cadence

This self-assessment is reviewed when:

- Any of the triggers in §4 become active.
- A new version of the model is trained.
- Significant changes to h2oatlas.ee UI or scope occur.
- The EU AI Act is amended or Commission guidance is published.

Each review updates the "Last reviewed" date at the top of this file and is committed with the signed snapshot of that period so a reader can retrieve the exact assessment active when a given prediction was produced.
