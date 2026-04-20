# Key management for signed snapshots

> **Context.** Phase 3 of the AI Act compliance roadmap signs each
> `snapshot.json` into a `.aep` evidence package. Signing is delegated to the
> Aletheia backend (`eatf.duckdns.org` → Hetzner). A local fallback signer
> using self-signed RSA-4096 keys exists for development and for the backend
> downtime window. This file documents how those keys are managed, rotated,
> and handled in an incident.

## 1. Key material in use

| Role | Where | Algorithm | Lifetime |
|---|---|---|---|
| **Backend signing key** | Aletheia backend (Hetzner) | RSA-4096 + SHA-256 (PSS) | Until rotation event |
| **Backend certificate** | Issued by Aletheia's internal CA / self-signed (Phase 3) | X.509 v3 | 12 months |
| **Local dev key** | `data/keys/sign_private.pem` (gitignored, auto-generated on first run of `sign_snapshot.py --mode local`) | RSA-4096 + SHA-256 | 12 months (cert `not_after`) |
| **Public verifier key** | `frontend/public/trust/aletheia-pubkey.pem` (checked into the frontend repo) | Extracted from the backend certificate | Refreshed on rotation |

The project deliberately does **not** own the root trust anchor. The backend owns the signing key; we only hold the public key and the verifier.

## 2. Locations checked into git

- `frontend/public/trust/aletheia-pubkey.pem` — PEM-encoded public key of the current backend signer.
- `frontend/public/trust/previous-pubkeys.json` — array of `{pubkey_pem, retired_at}` so the verifier can still check historical snapshots after rotation.

**Never commit** a private key. `.gitignore` includes `data/keys/` explicitly; CI secret injection uses `ALETHEIA_LOCAL_KEY_PATH` pointing at a runner-local path.

## 3. GitHub Actions secrets

| Secret name | Content | Used by |
|---|---|---|
| `ALETHEIA_BACKEND_URL` | `https://aletheia.example.ee` (no trailing slash) | `scripts/sign_snapshot.py` in the citizen-snapshot workflow |
| `ALETHEIA_API_KEY` | Bearer token for the `/api/evidence/sign` endpoint | same |
| `ALETHEIA_LOCAL_KEY` | PEM-encoded RSA private key (only for fallback runs) | written to a tmpfile by the workflow; deleted at step end |
| `ALETHEIA_LOCAL_CERT` | Matching X.509 cert PEM | same |

Secrets are scoped to the `citizen-snapshot` environment and not exposed to other workflows.

## 4. Rotation policy

### Backend key

Rotate annually, or immediately after any suspected compromise, or whenever the backend host changes (e.g. the Hetzner migration).

**Procedure:**

1. Aletheia backend generates a new RSA-4096 key and issues a new X.509 certificate.
2. Operator downloads the new public key PEM.
3. Open a PR into this repository that:
   - Adds the old pubkey to `frontend/public/trust/previous-pubkeys.json` with `retired_at = <ISO timestamp>`.
   - Replaces `frontend/public/trust/aletheia-pubkey.pem` with the new key.
   - Bumps the `pubkey_version` string in the verifier UI.
4. Merge; CI rebuilds and deploys the frontend.
5. New snapshots are signed with the new key; old snapshots remain verifiable via `previous-pubkeys.json`.

### Local dev key

Rotate when `data/keys/sign_cert.pem` nears `not_after`. Delete both files and re-run `sign_snapshot.py` — a fresh dev cert is generated automatically. Dev certs are never installed as trust anchors on the live frontend.

## 5. Storage

| Material | Storage |
|---|---|
| Backend private key | Aletheia backend HSM / encrypted filesystem; never exits the backend |
| Backend certificate | Exported PEM committed to this repo after each rotation |
| Local dev private key | `data/keys/sign_private.pem` — chmod 600; gitignored |
| GitHub Actions secrets | GitHub-encrypted, scoped to the `citizen-snapshot` environment |
| Previous public keys | `frontend/public/trust/previous-pubkeys.json` — human-readable JSON, committed |

## 6. Incident response

Trigger: any of the following —

- A published `.aep` fails local verification when the snapshot content is believed genuine.
- `ALETHEIA_BACKEND_URL` returns invalid signatures or truncated bundles.
- A `previous-pubkeys.json` entry is modified outside a rotation PR.
- Suspicion or disclosure that `ALETHEIA_LOCAL_KEY` was exposed in a public log.

**Steps:**

1. **Freeze publication.** Disable the citizen-snapshot workflow via the GitHub Actions UI.
2. **Pull the affected artefact.** Remove the signed `.aep` from the frontend CDN cache (via the deploy pipeline's "invalidate" action) and tag the corresponding git commit as `COMPROMISED-YYYY-MM-DD`.
3. **Rotate.** Issue a new backend certificate (see §4), revoke the old one via the internal CA's revocation mechanism.
4. **Post-mortem.** Open a public issue describing what happened, which snapshots are affected, and how verification now works. Link from the `/verify` page.
5. **Restore publication.** Once a new key is in place and at least one fresh snapshot has been signed and verified, re-enable the workflow.

Do **not** publish retroactive "back-signed" snapshots; the point of the evidence chain is that a signature at time T proves the state at time T.

## 7. Verifier trust model

The `/verify` page uses two paths:

- **Offline path.** Fetches `frontend/public/trust/aletheia-pubkey.pem` plus `previous-pubkeys.json`, verifies the signature via Web Crypto API. No backend call.
- **Online path.** Sends the `.aep` to `ALETHEIA_BACKEND_URL/api/evidence/verify`, which returns a structured `{ok, signer, chain, timestamp}` response. Useful for RFC 3161 timestamp verification.

A sanity-check rule for users: if both paths disagree, trust the **offline** result (the committed public key is the source of truth for this repository's users).

## 8. Out of scope for this document

- Key management practices internal to the Aletheia backend (documented in the `aletheia-ai` repository).
- OCSP responder / CRL distribution points — not deployed yet; will be added when the backend is integrated with a public CA rather than self-signing.
- HSM / cloud KMS integration.

## 9. Change log

| Date | Change |
|---|---|
| 2026-04-20 | Initial document; covers local_dev signer and Aletheia backend HTTP client. |
