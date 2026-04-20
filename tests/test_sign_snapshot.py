"""Smoke tests for scripts/sign_snapshot.py (AI Act Art 12 Phase 3).

Verifies the sign → verify round-trip in local_dev mode and ensures tamper
detection rejects a modified payload. Backend-HTTP mode is not covered here;
it requires a live Aletheia backend and is exercised end-to-end in CI.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

cryptography = pytest.importorskip("cryptography")  # noqa: F841  (side effect: skip without dep)
from sign_snapshot import sign_locally, verify_local, canonicalize, sha256_hex  # noqa: E402


@pytest.fixture
def tmp_keydir(tmp_path, monkeypatch):
    """Isolate keys in a tmp dir so tests don't collide with local dev state."""
    keydir = tmp_path / "keys"
    keydir.mkdir()
    monkeypatch.setenv("ALETHEIA_LOCAL_KEY_PATH", str(keydir / "sign_private.pem"))
    monkeypatch.setenv("ALETHEIA_LOCAL_CERT_PATH", str(keydir / "sign_cert.pem"))
    yield keydir


def _example_payload() -> dict:
    return {
        "generated_at": "2026-04-20T00:00:00Z",
        "model_version": "citizen-2026.test",
        "places": [
            {"id": "p1", "location": "Example", "prediction_id": "abc123"},
            {"id": "p2", "location": "Other", "prediction_id": "def456"},
        ],
    }


def test_sign_then_verify_is_ok(tmp_keydir):
    aep = sign_locally(_example_payload())
    ok, reason = verify_local(aep)
    assert ok is True, reason
    assert reason == "ok"


def test_aep_contains_expected_entries(tmp_keydir):
    aep = sign_locally(_example_payload())
    with zipfile.ZipFile(io.BytesIO(aep)) as zf:
        names = set(zf.namelist())
    assert {"payload.json", "manifest.json", "signature.b64", "cert.pem", "pubkey_spki.der"}.issubset(names)


def test_manifest_reports_payload_digest(tmp_keydir):
    payload = _example_payload()
    expected = sha256_hex(canonicalize(payload))
    aep = sign_locally(payload)
    with zipfile.ZipFile(io.BytesIO(aep)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["payload_digest_sha256"] == expected
    assert manifest["algorithm"] == "RSA-PSS-4096/SHA-256"
    assert manifest["mode"] == "local_dev"


def test_tamper_payload_fails_verification(tmp_keydir):
    aep = sign_locally(_example_payload())
    mem = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(aep)) as zin:
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "payload.json":
                    # Flip a single byte after the closing brace to keep JSON shape intact.
                    data = data.replace(b'"id":"p1"', b'"id":"pX"')
                zout.writestr(name, data)
    ok, reason = verify_local(mem.getvalue())
    assert ok is False
    assert "digest mismatch" in reason


def test_tamper_signature_fails_verification(tmp_keydir):
    aep = sign_locally(_example_payload())
    mem = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(aep)) as zin:
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "signature.b64":
                    # Swap two bytes near the middle to damage the signature but keep it base64-parseable.
                    raw = bytearray(data)
                    mid = len(raw) // 2
                    raw[mid], raw[mid + 1] = raw[mid + 1], raw[mid]
                    data = bytes(raw)
                zout.writestr(name, data)
    ok, reason = verify_local(mem.getvalue())
    assert ok is False
    assert "signature" in reason or "digest" in reason


def test_missing_entries_fail_verification(tmp_keydir):
    aep = sign_locally(_example_payload())
    mem = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(aep)) as zin:
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                if name == "signature.b64":
                    continue
                zout.writestr(name, zin.read(name))
    ok, reason = verify_local(mem.getvalue())
    assert ok is False
    # Either "malformed" (KeyError in the read loop) or explicit "signature" wording.
    assert any(token in reason for token in ("malformed", "signature"))
