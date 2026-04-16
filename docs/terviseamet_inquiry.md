# Cooperation letter to Terviseamet — water quality open data

> **Status: DRAFT.** Phase 14 numbers verified (69,536 probes, 2,207 hidden
> violations, 85.7% agree rate). Ready for supervisor review and sending.

## Summary

Deterministic norm checker audited 69,536 probes across 4 domains × 6 years:
- **85.7%** of `hinnang` labels are reproducible from published parameters
- **2,207 probes (3.2%)** are labelled `ei vasta nõuetele` with no published parameter exceeding any norm
- **XML parity:** zero measurement parameters lost by our parser (160 MB scanned)
- **Temporal analysis:** 54.9% of unmeasured params are measured at the same site in other probes

## Letter drafts (gitignored, not in repo)

| File | Language | Contents |
|------|----------|----------|
| `notes/terviseamet_kiri_et.md` | Estonian | Full letter text, ready for sending |
| `notes/terviseamet_kiri_ru.md` | Russian | Author review copy |
| `notes/terviseamet_lisad.md` | Estonian | Attachments checklist + links |
| `notes/terviseamet_contacts.md` | Russian | Contact research + sending strategy |
| `notes/email_ago.md` | Estonian | Supervisor review request |

## Checklist

- [x] Numbers from Phase 14 full-corpus audit (2026-04-16)
- [x] Pool norms correction documented
- [x] XML parity scan: zero measurement params lost
- [x] Temporal analysis: veevark 97.9% frequency variance
- [x] Estonian translation (`notes/terviseamet_kiri_et.md`)
- [x] Russian review copy (`notes/terviseamet_kiri_ru.md`)
- [x] Attachments inventory (`notes/terviseamet_lisad.md`)
- [x] Supervisor email drafted (`notes/email_ago.md`)
- [ ] Supervisor sign-off
- [ ] Send to Terviseamet

## Cross-references

- Audit results: `data/audit/full_corpus_summary.json`
- Divergences: `data/audit/full_corpus_divergences.csv` (9,966 rows)
- Method: `docs/data_gaps.md`
- Findings: `docs/phase_10_findings.md`
- Investigation: `docs/investigation_log.md`
