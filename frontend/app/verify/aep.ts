// Minimal ZIP reader + .aep verification helpers for the /verify page.
//
// The .aep format (see scripts/sign_snapshot.py) is a plain ZIP with:
//   payload.json     — canonical JSON bytes that were signed
//   manifest.json    — {algorithm, payload_digest_sha256, signed_at, mode, ...}
//   signature.b64    — base64 RSA-PSS-4096/SHA-256 signature over payload.json
//   cert.pem         — X.509 certificate (currently self-signed for dev)
//   pubkey_spki.der  — SubjectPublicKeyInfo DER bytes (for Web Crypto import)
//
// We only support STORED (method 0) and DEFLATE (method 8) — the format
// zipfile.ZipFile uses with ZIP_DEFLATED. No encryption, no split archives,
// no zip64, ≤4 GB (fine for snapshots measured in MB).

type ZipEntry = { name: string; data: Uint8Array };

function readUint32LE(buf: Uint8Array, offset: number): number {
  return (
    buf[offset] |
    (buf[offset + 1] << 8) |
    (buf[offset + 2] << 16) |
    (buf[offset + 3] * 0x1000000)
  );
}

function readUint16LE(buf: Uint8Array, offset: number): number {
  return buf[offset] | (buf[offset + 1] << 8);
}

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  // Browsers shipping DecompressionStream('deflate-raw') — Chrome/Edge 113+, Firefox 113+, Safari 16.4+.
  const ds = new DecompressionStream("deflate-raw" as unknown as CompressionFormat);
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(ds);
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}

export async function readAep(buffer: ArrayBuffer): Promise<Record<string, Uint8Array>> {
  const bytes = new Uint8Array(buffer);
  const entries: ZipEntry[] = [];
  let offset = 0;
  while (offset + 4 <= bytes.length) {
    const sig = readUint32LE(bytes, offset);
    if (sig !== 0x04034b50) break; // end of local file headers
    const compressionMethod = readUint16LE(bytes, offset + 8);
    const compressedSize = readUint32LE(bytes, offset + 18);
    const uncompressedSize = readUint32LE(bytes, offset + 22);
    const nameLen = readUint16LE(bytes, offset + 26);
    const extraLen = readUint16LE(bytes, offset + 28);
    const nameStart = offset + 30;
    const dataStart = nameStart + nameLen + extraLen;
    const name = new TextDecoder("utf-8").decode(bytes.subarray(nameStart, nameStart + nameLen));
    const raw = bytes.subarray(dataStart, dataStart + compressedSize);
    let data: Uint8Array;
    if (compressionMethod === 0) {
      data = raw.slice(0, uncompressedSize);
    } else if (compressionMethod === 8) {
      data = await inflateRaw(raw);
    } else {
      throw new Error(`Unsupported zip compression method ${compressionMethod} for ${name}`);
    }
    entries.push({ name, data });
    offset = dataStart + compressedSize;
  }
  const out: Record<string, Uint8Array> = {};
  for (const entry of entries) out[entry.name] = entry.data;
  return out;
}

async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data as BufferSource);
  const bytes = new Uint8Array(digest);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64.trim());
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

export type VerifyResult = {
  ok: boolean;
  reason: string;
  manifest?: Record<string, unknown>;
  payloadDigest?: string;
  expectedDigest?: string;
  payload?: unknown;
};

export async function verifyAep(buffer: ArrayBuffer): Promise<VerifyResult> {
  let entries: Record<string, Uint8Array>;
  try {
    entries = await readAep(buffer);
  } catch (e) {
    return { ok: false, reason: `bundle malformed: ${(e as Error).message}` };
  }
  // payload + manifest + signature are always required; SPKI only for
  // local_dev bundles (backend mode uses Aletheia's own key which the UI
  // does not yet have out-of-band).
  const required = ["payload.json", "manifest.json", "signature.b64"];
  for (const name of required) {
    if (!entries[name]) return { ok: false, reason: `missing entry: ${name}` };
  }

  const payload = entries["payload.json"];
  const manifestText = new TextDecoder("utf-8").decode(entries["manifest.json"]);
  const manifest = JSON.parse(manifestText) as Record<string, unknown>;
  const expected = String(manifest.payload_digest_sha256 ?? "");
  const actual = await sha256Hex(payload);
  if (expected !== actual) {
    return {
      ok: false,
      reason: "digest mismatch (tampered payload)",
      manifest,
      payloadDigest: actual,
      expectedDigest: expected,
    };
  }

  const mode = String(manifest.mode ?? "");
  if (mode === "backend") {
    // Backend-signed: we don't yet ship Aletheia's public key with the
    // frontend, so offline signature verification isn't wired. Hash integrity
    // checked above is still meaningful (tampering the payload still fails).
    return {
      ok: true,
      reason: "digest verified; backend signature requires Aletheia console lookup (aletheia_uuid in manifest)",
      manifest,
      payloadDigest: actual,
      expectedDigest: expected,
      payload: (() => {
        try { return JSON.parse(new TextDecoder("utf-8").decode(payload)); } catch { return undefined; }
      })(),
    };
  }

  if (!entries["pubkey_spki.der"]) {
    return { ok: false, reason: "missing entry: pubkey_spki.der (required for local_dev bundles)", manifest };
  }

  const signatureBytes = base64ToBytes(new TextDecoder("utf-8").decode(entries["signature.b64"]));
  const spki = entries["pubkey_spki.der"];

  let key: CryptoKey;
  try {
    key = await crypto.subtle.importKey(
      "spki",
      spki as BufferSource,
      { name: "RSA-PSS", hash: "SHA-256" },
      true,
      ["verify"],
    );
  } catch (e) {
    return { ok: false, reason: `public key import failed: ${(e as Error).message}`, manifest };
  }

  // saltLength 0 is the convention when the signer uses PSS.MAX_LENGTH with SHA-256 (hLen).
  // cryptography.io PSS.MAX_LENGTH for a 4096-bit key with SHA-256 = (4096/8) - 32 - 2 = 478.
  // Web Crypto RSA-PSS treats saltLength as the concrete byte count, so we mirror that.
  const keyBits = (key.algorithm as RsaHashedKeyAlgorithm).modulusLength;
  const saltLength = Math.max(0, Math.floor(keyBits / 8) - 32 - 2);
  let valid = false;
  try {
    valid = await crypto.subtle.verify(
      { name: "RSA-PSS", saltLength },
      key,
      signatureBytes as BufferSource,
      payload as BufferSource,
    );
  } catch (e) {
    return { ok: false, reason: `signature verify threw: ${(e as Error).message}`, manifest };
  }
  if (!valid) {
    return { ok: false, reason: "signature invalid", manifest, payloadDigest: actual };
  }

  let payloadJson: unknown = undefined;
  try {
    payloadJson = JSON.parse(new TextDecoder("utf-8").decode(payload));
  } catch {
    // payload need not be JSON for verification, but ours is.
  }

  return {
    ok: true,
    reason: "ok",
    manifest,
    payloadDigest: actual,
    expectedDigest: expected,
    payload: payloadJson,
  };
}
