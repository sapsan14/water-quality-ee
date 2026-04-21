#!/usr/bin/env python3
"""
sign_snapshot.py — Produce a signed `.aep` evidence package for a snapshot.

Primary path: call a deployed Aletheia backend (originally at eatf.duckdns.org,
being redeployed to Hetzner) via HTTP. The backend computes the canonical hash,
signs with its RSA-4096 key, optionally includes an RFC 3161 timestamp, and
returns the `.aep` package bytes.

Fallback: when ALETHEIA_BACKEND_URL is unset or the backend is unreachable, we
produce a locally signed `.aep` with the same file layout but mode="local_dev".
Keys are loaded from ALETHEIA_LOCAL_KEY_PATH (private) and a matching public
cert path, or generated on first run into data/keys/ (dev only).

This is Phase 3 of the EU AI Act compliance roadmap; see:
  - docs/ai_act_self_assessment.md §7 (Art 12 logging / traceability)
  - docs/model_card.md §1 (training pipeline commit)
  - docs/key_management.md (key lifecycle, rotation, incident response)

Usage:
  python scripts/sign_snapshot.py                                    # sign the default citizen snapshot
  python scripts/sign_snapshot.py --input path/to/snapshot.json      # sign an arbitrary JSON
  python scripts/sign_snapshot.py --output-dir citizen-service/artifacts
  python scripts/sign_snapshot.py --mode local                       # force local signing

Environment:
  ALETHEIA_BACKEND_URL   e.g. https://aletheia.example.ee (no trailing slash)
  ALETHEIA_API_KEY       bearer token for the sign endpoint
  ALETHEIA_LOCAL_KEY_PATH  PEM-encoded RSA private key for local fallback
  ALETHEIA_LOCAL_CERT_PATH  PEM-encoded X.509 cert for local fallback
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = ROOT / "citizen-service" / "artifacts" / "snapshot.json"
DEFAULT_OUTPUT_DIR = ROOT / "citizen-service" / "artifacts"
DEFAULT_KEY_DIR = ROOT / "data" / "keys"


# ── Canonicalisation (RFC 8785 JCS subset) ────────────────────────────────────
# We restrict ourselves to a deterministic sort-keys=True, separators=(',', ':'),
# ensure_ascii=False serialisation. This matches the Aletheia backend and is
# enough for our inputs (all JSON-safe primitives, numbers already rounded).


def canonicalize(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


# ── HTTP backend client ───────────────────────────────────────────────────────

# Aletheia backend contract (POST /api/sign). Confirmed against the live
# backend on 2026-04-21 — see commit history of scripts/sign_snapshot.py and
# docs/key_management.md for the session notes. Request / response shape is
# defined by SignController in the aletheia-ai repo. The backend canonicalises,
# hashes, signs (RSA-PSS-4096/SHA-256), optionally timestamps via RFC 3161,
# and stores the record. It does NOT return a self-contained `.aep` bundle —
# it returns JSON metadata. We package the JSON into our own `.aep` ZIP so
# the verifier UI and the on-disk format stay uniform across backend and
# local-dev signing modes.


def sign_via_backend(payload: dict, backend_url: str, api_key: str | None, timeout: float = 30.0) -> bytes:
    import requests

    canonical = canonicalize(payload)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    commit_sha = os.environ.get("GITHUB_SHA", "")[:12] or "unknown"
    # /api/sign's `response` field is "the text to sign" — we send the
    # canonicalised snapshot JSON as a string. `modelId` identifies the
    # signing-side grouping; we reuse the git SHA so every deploy is its own
    # logical model version in Aletheia's records.
    body = {
        "response": canonical.decode("utf-8"),
        "modelId": f"water-quality-ee/{commit_sha}",
        "prompt": "citizen-snapshot refresh (AI Act Art 12 evidence)",
    }
    resp = requests.post(
        backend_url.rstrip("/") + "/api/sign",
        headers=headers,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        timeout=timeout,
    )
    if not resp.ok:
        # Surface the backend's error body before raising. Without this we only
        # see "503 Server Error: ..." and have to round-trip with the backend
        # team to learn whether the request was malformed, the key was invalid,
        # the backend panicked, or something else. Truncated to 2 KiB so an
        # accidental HTML error page doesn't flood the Actions log.
        body_preview = (resp.text or "")[:2048]
        print(f"[sign_snapshot] backend returned {resp.status_code}: {body_preview}", file=sys.stderr)
    resp.raise_for_status()

    # Backend returns:
    #   { id, uuid, responseHash, signature, tsaToken, model, policyVersion, createdAt }
    # We wrap that response (plus the original payload) into the same `.aep`
    # ZIP shape used by local-dev signing so downstream consumers don't
    # special-case the mode.
    backend_resp = resp.json()
    return _bundle_from_backend_response(canonical, backend_resp)


def _bundle_from_backend_response(canonical_payload: bytes, backend_resp: dict) -> bytes:
    """
    Build a `.aep` ZIP from the backend's /api/sign JSON response.

    Layout:
      - payload.json        — the canonicalised snapshot bytes we sent
      - manifest.json       — `{algorithm, mode=backend, payload_digest_sha256,
                                signed_at, signer, aletheia_uuid, aletheia_id,
                                policy_version}`
      - signature.b64       — `backend_resp["signature"]` (base64 already)
      - backend_response.json — the full backend JSON for auditability / the
                                Aletheia console to look up the full record.
    Backend mode does NOT bundle cert.pem or pubkey_spki.der — the trust
    anchor for backend signatures is the Aletheia public key, distributed
    out-of-band via `frontend/public/trust/aletheia-pubkey.pem`. See
    docs/key_management.md §7.
    """
    digest = sha256_hex(canonical_payload)

    # Sanity check: if the backend returned a hash, compare against ours.
    backend_hash = str(backend_resp.get("responseHash") or "").lower()
    if backend_hash and backend_hash != digest:
        # Prefer the backend's hash in the manifest (that's the one the
        # signature was computed over) but log the divergence — it means
        # the backend canonicalises differently than we do.
        manifest_digest = backend_hash
        hash_note = f"local_hash_mismatch(local={digest}, backend={backend_hash})"
    else:
        manifest_digest = digest
        hash_note = None

    manifest = {
        "algorithm": "aletheia-backend/RSA-PSS-SHA-256",
        "payload_digest_sha256": manifest_digest,
        "signed_at": backend_resp.get("createdAt"),
        "mode": "backend",
        "aep_format_version": "0.1",
        "signer": str(backend_resp.get("model") or "aletheia"),
        "aletheia_id": backend_resp.get("id"),
        "aletheia_uuid": backend_resp.get("uuid"),
        "policy_version": backend_resp.get("policyVersion"),
        "tsa_token_included": bool(backend_resp.get("tsaToken")),
    }
    if hash_note:
        manifest["hash_note"] = hash_note

    signature_b64 = str(backend_resp.get("signature") or "")

    import io
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("payload.json", canonical_payload)
        zf.writestr("manifest.json", canonicalize(manifest))
        zf.writestr("signature.b64", signature_b64)
        zf.writestr("backend_response.json", canonicalize(backend_resp))
    return mem.getvalue()


# ── Local signer (fallback + dev) ─────────────────────────────────────────────


def _load_or_create_local_keys() -> tuple[Any, Any, bytes]:
    """
    Return (private_key, public_key, cert_pem_bytes). Lazy-imports cryptography.
    Creates a fresh self-signed RSA-4096 dev cert if none exists.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    priv_path = Path(os.environ.get("ALETHEIA_LOCAL_KEY_PATH", DEFAULT_KEY_DIR / "sign_private.pem"))
    cert_path = Path(os.environ.get("ALETHEIA_LOCAL_CERT_PATH", DEFAULT_KEY_DIR / "sign_cert.pem"))

    if priv_path.exists() and cert_path.exists():
        priv_pem = priv_path.read_bytes()
        cert_pem = cert_path.read_bytes()
        private_key = serialization.load_pem_private_key(priv_pem, password=None)
        cert = x509.load_pem_x509_certificate(cert_pem)
        return private_key, cert.public_key(), cert_pem

    # Create fresh dev key material. Not for production — see docs/key_management.md.
    DEFAULT_KEY_DIR.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "EE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "water-quality-ee (dev)"),
            x509.NameAttribute(NameOID.COMMON_NAME, "aletheia-local-dev"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
        .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    priv_path.write_bytes(priv_pem)
    cert_path.write_bytes(cert_pem)
    return private_key, cert.public_key(), cert_pem


def sign_locally(payload: dict) -> bytes:
    """Local `.aep` package: ZIP with payload.json + manifest.json + signature + cert + spki."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key, public_key, cert_pem = _load_or_create_local_keys()

    canonical = canonicalize(payload)
    digest = sha256_hex(canonical)
    signature = private_key.sign(
        canonical,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )

    spki_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    manifest = {
        "algorithm": "RSA-PSS-4096/SHA-256",
        "payload_digest_sha256": digest,
        "signed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode": "local_dev",
        "aep_format_version": "0.1",
        "signer": "aletheia-local-dev (self-signed)",
    }

    buf = _zip_bundle(
        payload_bytes=canonical,
        manifest_bytes=canonicalize(manifest),
        signature_b64=base64.b64encode(signature).decode("ascii"),
        cert_pem=cert_pem,
        pubkey_spki_der=spki_der,
    )
    return buf


def _zip_bundle(
    payload_bytes: bytes,
    manifest_bytes: bytes,
    signature_b64: str,
    cert_pem: bytes,
    pubkey_spki_der: bytes,
) -> bytes:
    import io

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("payload.json", payload_bytes)
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("signature.b64", signature_b64)
        zf.writestr("cert.pem", cert_pem)
        zf.writestr("pubkey_spki.der", pubkey_spki_der)
    return mem.getvalue()


# ── Verification (for round-trip tests and the /verify UI path) ───────────────


def verify_local(aep_bytes: bytes) -> tuple[bool, str]:
    """Round-trip verification for local_dev mode. Returns (ok, reason)."""
    import io

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature

    try:
        with zipfile.ZipFile(io.BytesIO(aep_bytes)) as zf:
            payload = zf.read("payload.json")
            manifest_bytes = zf.read("manifest.json")
            sig_b64 = zf.read("signature.b64").decode("ascii")
            cert_pem = zf.read("cert.pem")
    except (KeyError, zipfile.BadZipFile) as e:
        return False, f"bundle malformed: {e}"

    manifest = json.loads(manifest_bytes)
    if manifest.get("mode") != "local_dev":
        return False, f"unsupported mode in local verifier: {manifest.get('mode')}"
    expected_digest = manifest.get("payload_digest_sha256", "")
    actual_digest = sha256_hex(payload)
    if expected_digest != actual_digest:
        return False, f"digest mismatch: {expected_digest} vs {actual_digest}"

    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
        cert.public_key().verify(
            base64.b64decode(sig_b64),
            payload,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError) as e:
        return False, f"signature invalid: {e}"
    return True, "ok"


# ── Driver ────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Sign a snapshot JSON into a `.aep` evidence package.")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument(
        "--mode",
        choices=("auto", "backend", "local"),
        default="auto",
        help="auto=backend when ALETHEIA_BACKEND_URL set, else local; backend=fail if backend missing.",
    )
    ap.add_argument("--verify", action="store_true", help="After signing, verify the produced .aep locally (dev only).")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"[sign_snapshot] input not found: {args.input}", file=sys.stderr)
        return 2

    payload = json.loads(args.input.read_text(encoding="utf-8"))

    backend_url = os.environ.get("ALETHEIA_BACKEND_URL", "").strip()
    api_key = os.environ.get("ALETHEIA_API_KEY", "").strip() or None

    aep_bytes: bytes | None = None
    used_mode: str
    if args.mode == "local" or (args.mode == "auto" and not backend_url):
        aep_bytes = sign_locally(payload)
        used_mode = "local_dev"
    else:
        try:
            aep_bytes = sign_via_backend(payload, backend_url, api_key)
            used_mode = "backend"
        except Exception as e:  # network, 4xx/5xx, backend down
            if args.mode == "backend":
                print(f"[sign_snapshot] backend mode required but failed: {e}", file=sys.stderr)
                return 1
            print(f"[sign_snapshot] backend unreachable ({e}); falling back to local_dev", file=sys.stderr)
            aep_bytes = sign_locally(payload)
            used_mode = "local_dev"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / (args.input.stem + ".aep")
    out_path.write_bytes(aep_bytes)
    print(f"[sign_snapshot] mode={used_mode} wrote {out_path} ({len(aep_bytes)} bytes)")

    if args.verify:
        if used_mode == "local_dev":
            ok, reason = verify_local(aep_bytes)
            print(f"[sign_snapshot] verify: ok={ok} reason={reason}")
            if not ok:
                return 1
        else:
            print("[sign_snapshot] verify: backend mode — look up aletheia_uuid in the Aletheia console; online-verify path not yet wired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
