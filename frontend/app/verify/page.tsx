"use client";

import { useState } from "react";
import { verifyAep, type VerifyResult } from "./aep";

type UiLang = "ru" | "et" | "en";

const copy: Record<UiLang, {
  title: string;
  intro: string;
  dropLabel: string;
  verifyLive: string;
  waiting: string;
  signedAt: string;
  algorithm: string;
  digest: string;
  mode: string;
  okBadge: string;
  failBadge: string;
  more: string;
  noFile: string;
  useFile: string;
  postQuantum: string;
  postQuantumIncluded: string;
  postQuantumNotIncluded: string;
  rsaLegacy: string;
  agent: string;
  aletheiaUuid: string;
}> = {
  ru: {
    title: "Проверка снимка",
    intro:
      "На этой странице можно убедиться, что опубликованный снимок карты не был изменён после подписания. " +
      "Проверка проходит полностью у вас в браузере (Web Crypto API), без запросов к серверу подписи.",
    dropLabel: "Перетащите .aep сюда или выберите файл",
    verifyLive: "Проверить текущий снимок",
    waiting: "Проверяем…",
    signedAt: "Подписано",
    algorithm: "Основной алгоритм",
    digest: "SHA-256 payload",
    mode: "Режим подписания",
    okBadge: "Подпись действительна",
    failBadge: "Ошибка проверки",
    more: "Подробнее о процессе",
    noFile: "Файл не выбран.",
    useFile: "Выбран файл",
    postQuantum: "Постквантовая подпись",
    postQuantumIncluded: "ML-DSA-65 ✓",
    postQuantumNotIncluded: "не включена",
    rsaLegacy: "Легаси RSA",
    agent: "Агент",
    aletheiaUuid: "Aletheia UUID",
  },
  et: {
    title: "Snapshot'i verifikaator",
    intro:
      "Sellel lehel saab kontrollida, et avaldatud snapshot pole pärast allkirjastamist muudetud. " +
      "Kogu kontroll toimub teie brauseris (Web Crypto API), allkirjastamise serverisse päringut ei tehta.",
    dropLabel: "Tirige .aep fail siia või valige fail",
    verifyLive: "Kontrolli praegust snapshot'i",
    waiting: "Kontrollin…",
    signedAt: "Allkirjastatud",
    algorithm: "Põhialgoritm",
    digest: "SHA-256 payload",
    mode: "Allkirjastamise režiim",
    okBadge: "Allkiri kehtiv",
    failBadge: "Verifikaatori viga",
    more: "Rohkem protsessi kohta",
    noFile: "Faili pole valitud.",
    useFile: "Valitud fail",
    postQuantum: "Kvantijärgne allkiri",
    postQuantumIncluded: "ML-DSA-65 ✓",
    postQuantumNotIncluded: "puudub",
    rsaLegacy: "Vana RSA",
    agent: "Agent",
    aletheiaUuid: "Aletheia UUID",
  },
  en: {
    title: "Snapshot verifier",
    intro:
      "Use this page to confirm that the published snapshot has not been altered after signing. " +
      "The check runs entirely in your browser (Web Crypto API); no request is sent to the signing backend.",
    dropLabel: "Drop a .aep file here or choose a file",
    verifyLive: "Verify the current snapshot",
    waiting: "Verifying…",
    signedAt: "Signed at",
    algorithm: "Primary algorithm",
    digest: "SHA-256 payload",
    mode: "Signing mode",
    okBadge: "Signature valid",
    failBadge: "Verification failed",
    more: "More about the process",
    noFile: "No file chosen.",
    useFile: "Chosen file",
    postQuantum: "Post-quantum signature",
    postQuantumIncluded: "ML-DSA-65 ✓",
    postQuantumNotIncluded: "not included",
    rsaLegacy: "Legacy RSA",
    agent: "Agent",
    aletheiaUuid: "Aletheia UUID",
  },
};

function detectLang(): UiLang {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem("water.ui.lang");
  const v = String(stored ?? navigator.language ?? "").toLowerCase();
  if (v.startsWith("ru")) return "ru";
  if (v.startsWith("et")) return "et";
  return "en";
}

export default function VerifyPage() {
  const [lang] = useState<UiLang>(() => detectLang());
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const t = copy[lang];

  async function verifyBuffer(buf: ArrayBuffer, label: string) {
    setBusy(true);
    setFileName(label);
    setResult(null);
    try {
      const r = await verifyAep(buf);
      setResult(r);
    } catch (e) {
      setResult({ ok: false, reason: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function onFile(file: File) {
    const buf = await file.arrayBuffer();
    void verifyBuffer(buf, file.name);
  }

  async function onVerifyLive() {
    const resp = await fetch("/data/snapshot.aep", { cache: "no-store" });
    if (!resp.ok) {
      setResult({ ok: false, reason: `live snapshot fetch failed: HTTP ${resp.status}` });
      setFileName("/data/snapshot.aep");
      return;
    }
    const buf = await resp.arrayBuffer();
    void verifyBuffer(buf, "/data/snapshot.aep");
  }

  return (
    <main style={{ maxWidth: 780, margin: "2rem auto", padding: "0 1rem", lineHeight: 1.55 }}>
      <h1 style={{ marginBottom: "0.5rem" }}>{t.title}</h1>
      <p style={{ color: "var(--water-muted, #555)" }}>{t.intro}</p>

      <section
        style={{
          marginTop: "1.25rem",
          padding: "1rem",
          border: "1px dashed rgba(0,0,0,0.25)",
          borderRadius: 8,
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) void onFile(f);
        }}
      >
        <label style={{ display: "block", cursor: "pointer" }}>
          <strong>{t.dropLabel}</strong>
          <input
            type="file"
            accept=".aep,application/zip,application/octet-stream"
            style={{ display: "block", marginTop: "0.5rem" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onFile(f);
            }}
          />
        </label>
        <div style={{ marginTop: "0.75rem" }}>
          <button
            type="button"
            onClick={() => void onVerifyLive()}
            style={{
              padding: "0.4rem 0.9rem",
              border: "1px solid currentColor",
              borderRadius: 4,
              background: "transparent",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            {t.verifyLive}
          </button>
        </div>
      </section>

      <section style={{ marginTop: "1rem" }}>
        {busy && <p>{t.waiting}</p>}
        {fileName && !busy && (
          <p style={{ fontSize: "0.875rem", color: "var(--water-muted, #555)" }}>
            {t.useFile}: <code>{fileName}</code>
          </p>
        )}
        {result && (
          <div
            role="status"
            style={{
              marginTop: "0.5rem",
              padding: "0.75rem 1rem",
              borderRadius: 6,
              background: result.ok ? "rgba(34, 139, 34, 0.08)" : "rgba(200, 30, 30, 0.08)",
              border: `1px solid ${result.ok ? "rgba(34, 139, 34, 0.35)" : "rgba(200, 30, 30, 0.35)"}`,
            }}
          >
            <strong>{result.ok ? t.okBadge : t.failBadge}</strong>
            <div style={{ fontSize: "0.875rem", marginTop: "0.25rem" }}>{result.reason}</div>
            {result.manifest && (
              <dl
                style={{
                  marginTop: "0.75rem",
                  display: "grid",
                  gridTemplateColumns: "max-content 1fr",
                  columnGap: "0.75rem",
                  rowGap: "0.25rem",
                  fontSize: "0.8125rem",
                }}
              >
                <dt>{t.signedAt}</dt>
                <dd>{String(result.manifest.signed_at ?? "")}</dd>
                <dt>{t.algorithm}</dt>
                <dd>{String(result.manifest.algorithm ?? "")}</dd>
                {/* Post-quantum row: highlighted green when ML-DSA-65 is present.
                    Hidden when there's no PQC info at all in the manifest (older
                    bundles); shown as "not included" when the field is explicitly
                    false so users can tell pre-PQC from PQC-disabled. */}
                {(result.manifest.pqc_signature_included !== undefined ||
                  Boolean(result.manifest.pqc_algorithm)) && (
                  <>
                    <dt>{t.postQuantum}</dt>
                    <dd
                      style={{
                        color: result.manifest.pqc_signature_included
                          ? "rgb(20, 110, 40)"
                          : "var(--water-muted, #555)",
                        fontWeight: result.manifest.pqc_signature_included
                          ? 600
                          : 400,
                      }}
                    >
                      {result.manifest.pqc_signature_included
                        ? t.postQuantumIncluded
                        : t.postQuantumNotIncluded}
                    </dd>
                  </>
                )}
                {result.manifest.rsa_legacy_signature_included !== undefined && (
                  <>
                    <dt>{t.rsaLegacy}</dt>
                    <dd style={{ color: "var(--water-muted, #555)" }}>
                      {result.manifest.rsa_legacy_signature_included
                        ? "✓"
                        : "—"}
                    </dd>
                  </>
                )}
                <dt>{t.mode}</dt>
                <dd>{String(result.manifest.mode ?? "")}</dd>
                {Boolean(result.manifest.agent_id) && (
                  <>
                    <dt>{t.agent}</dt>
                    <dd
                      style={{
                        wordBreak: "break-all",
                        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      }}
                    >
                      {String(result.manifest.agent_id)}
                    </dd>
                  </>
                )}
                {Boolean(result.manifest.aletheia_uuid) && (
                  <>
                    <dt>{t.aletheiaUuid}</dt>
                    <dd
                      style={{
                        wordBreak: "break-all",
                        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      }}
                    >
                      {String(result.manifest.aletheia_uuid)}
                    </dd>
                  </>
                )}
                {result.payloadDigest && (
                  <>
                    <dt>{t.digest}</dt>
                    <dd
                      style={{
                        wordBreak: "break-all",
                        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      }}
                    >
                      {result.payloadDigest}
                    </dd>
                  </>
                )}
              </dl>
            )}
          </div>
        )}
      </section>

      <p style={{ marginTop: "1.5rem", fontSize: "0.875rem" }}>
        <a
          href="https://github.com/sapsan14/water-quality-ee/blob/main/docs/key_management.md"
          target="_blank"
          rel="noreferrer"
        >
          {t.more}
        </a>
      </p>
    </main>
  );
}
