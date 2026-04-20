# Human Oversight — decision tree for h2oatlas.ee

> **EU AI Act Art 14 (voluntary adoption).** This document describes *who decides what*
> around h2oatlas.ee and its ML outputs: the citizen, the project maintainers, and
> Terviseamet. It exists to keep the model layer firmly in the advisory position,
> never the authoritative one.
>
> **Scope.** The model is `docs/model_card.md`. The data provenance is
> `docs/datasheet.md`. The regulatory posture is `docs/ai_act_self_assessment.md`.
> **What this file adds:** an explicit oversight flow so a human, not the model, is
> always the decider when a decision has real-world consequences.

## 1. Three signals on the map

Each map pin surfaces three independent signals. Users should treat them in this order:

| # | Signal | Source | Authority |
|---|---|---|---|
| 1 | **Official `hinnang`** (the green / red dot, "compliant" / "violation") | Terviseamet laboratory result | Authoritative |
| 2 | **Model P(violation)** (the 4-model risk layer) | ML classifier over published parameters | Advisory, probabilistic |
| 3 | **Data-gap notice** (the blue banner) | Audit corpus 3.1% hidden violations | Epistemic warning |

When the three disagree, (1) wins. The UI is designed to put (1) first, (2) second, and (3) as an always-visible footnote. See `frontend/app/components/DataGapNotice.tsx`.

## 2. Decision tree — citizen

```
Am I making a real-world decision about water?
│
├─ Yes: drinking, swimming, filling a pool
│   │
│   ├─ Does (1) say "violation" for the site?
│   │      → Trust (1). Do not use the water until Terviseamet updates.
│   │
│   ├─ Does (1) say "compliant" but (2) says P(violation) ≥ 0.5?
│   │      → Trust (1) but treat (2) as a reason to re-check the site date.
│   │        If the sample is > 2 weeks old, consider using an alternate site.
│   │        Do NOT conclude the water is unsafe based on (2) alone.
│   │
│   ├─ Does (1) say "compliant" and (2) says P(violation) < 0.5?
│   │      → Use the water with normal precautions.
│   │
│   └─ Is (1) missing or stale?
│          → Treat the site as unknown. The model layer is not a substitute.
│            Contact Terviseamet or consult the source catalogue.
│
└─ No: browsing, reporting, educational reading
    → Read all three signals freely; disagreements are the point of the tool.
```

**What h2oatlas.ee will never tell you:** whether the water is safe *right now*, beyond the most recent published sample. A per-sample probability is not a real-time safety guarantee.

## 3. Decision tree — project maintainers

```
An incoming signal or report needs a response.
│
├─ Drift monitor (scripts/drift_monitor.py) returns WARN or ALERT in CI
│   │
│   ├─ Label KL divergence ≥ 0.15?
│   │      → Regulator likely changed labelling methodology.
│   │        Do NOT auto-publish the snapshot.
│   │        Open an issue referencing docs/terviseamet_inquiry.md Q5 / Q6.
│   │
│   ├─ A single feature PSI ≥ 0.25?
│   │      → Feature distribution changed. Likely measurement-method change.
│   │        Hold the snapshot. Post a short diagnostic in the issue before rebuild.
│   │
│   └─ Warn-only (PSI 0.1–0.25)?
│          → Publish the snapshot but annotate the workflow run.
│            Review at the next release checkpoint.
│
├─ Third party (citizen, researcher, Terviseamet) reports a wrong value
│   │
│   ├─ Is the dispute about (1) the official label?
│   │      → Defer to Terviseamet. We do not alter official labels.
│   │        Open an issue, link to the probe ID + prediction_id.
│   │
│   ├─ Is the dispute about (2) the model probability?
│   │      → Fetch the prediction_id. Re-run the model with the same inputs.
│   │        If the probability matches the report: explain how the model reads it.
│   │        If not: investigate (feature_hash mismatch → data drift or code change).
│   │
│   └─ Is the dispute about site location / coordinates?
│          → Fix via coordinate_overrides.json; rebuild snapshot.
│
└─ .aep signature verification fails for a published snapshot
    → Treat as integrity incident. See docs/key_management.md §incident-response.
      Pull the affected snapshot, rotate keys if compromise is suspected,
      and publish a post-mortem before restoring service.
```

## 4. Decision tree — Terviseamet (suggested)

A proposal for Terviseamet's use, not a unilateral prescription. Included here so the flow is explicit before we propose formal cooperation.

```
A citizen or external consumer asks about a discrepancy between h2oatlas.ee
risk probability and Terviseamet's official hinnang.
│
├─ Check whether the probe is in the 3.1% hidden_violation slice.
│      → If yes: the discrepancy is expected and reflects published data gaps,
│        not a model fault. Point the asker to docs/phase_10_findings.md.
│
├─ Check the prediction_id + feature_hash from the map.
│      → If the fields are absent, the snapshot predates Phase 2; ignore the report.
│        If present, maintainers can reproduce the exact input vector.
│
└─ If the model output is clearly misleading in a user-safety sense:
    → Contact the maintainers; they will adjust the UI or add caveats.
      The model output is not the authoritative signal and can be tuned.
```

## 5. Oversight obligations we take on

Drawing from AI Act Art 14(4) ("measures enabling the natural person to whom human oversight is assigned to…") even though we are not formally high-risk:

| Sub-point (Art 14(4)) | Our fulfilment |
|---|---|
| (a) properly understand the capacities and limitations of the AI system | Model Card + Datasheet + Learning Journey |
| (b) remain aware of the possible tendency of automation bias | UI orders signals: official > model > banner; risk colour is explicitly labelled |
| (c) correctly interpret the AI system's output | 4-level metrics guide (`docs/ml_metrics_guide.md`) + SHAP explanations per prediction |
| (d) decide, in any particular situation, not to use the AI system | Users can always ignore the model layer; the map defaults to the official layer |
| (e) intervene on the operation of the AI system or interrupt the system | Maintainers can pull a snapshot via CI rollback; Terviseamet can request takedown |

## 6. Oversight we explicitly do **not** take on

- Triage of individual public-health complaints — these belong to Terviseamet.
- Replying to legal or regulatory questions about the model — those belong to TalTech / project supervisor.
- Real-time supervision: there is no on-call rotation; the deployment is a weekly batch.
