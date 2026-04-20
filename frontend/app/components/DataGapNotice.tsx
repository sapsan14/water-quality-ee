"use client";

import { useEffect, useState } from "react";

type UiLang = "ru" | "et" | "en";

const STORAGE_KEY = "water.ui.dataGapNoticeDismissed";

const copyByLang: Record<UiLang, { title: string; body: string; dismiss: string; more: string }> = {
  ru: {
    title: "Как читать эту карту",
    body:
      "Официальный вердикт Terviseamet и вероятностная оценка модели — это два разных сигнала. " +
      "В 3,1% проб (аудит 69 536 проб) модель не может воспроизвести официальный вердикт по опубликованным параметрам: " +
      "метка опирается на контекст, которого нет в открытых данных. Модель не заменяет лабораторный анализ и " +
      "не является медицинским заключением.",
    dismiss: "Понятно",
    more: "Подробнее",
  },
  et: {
    title: "Kuidas seda kaarti lugeda",
    body:
      "Terviseameti ametlik hinnang ja mudeli tõenäosuslik hinnang on kaks eri signaali. " +
      "3,1% juhtudel (auditi tulemus 69 536 proovist) ei suuda mudel avaandmete põhjal ametlikku hinnangut reprodutseerida: " +
      "hinnang tugineb kontekstile, mida avaandmetes pole. Mudel ei asenda laborianalüüsi ega ole meditsiiniline hinnang.",
    dismiss: "Selge",
    more: "Loe lisaks",
  },
  en: {
    title: "How to read this map",
    body:
      "Terviseamet's official verdict and the model's probabilistic estimate are two distinct signals. " +
      "In 3.1% of probes (audit of 69,536 samples) the model cannot reproduce the official verdict from published parameters: " +
      "the label relies on context not present in the open data. The model does not replace a lab analysis and is not a medical assessment.",
    dismiss: "Got it",
    more: "Read more",
  },
};

const normalizeLang = (value: string | null | undefined): UiLang => {
  const v = String(value || "").toLowerCase();
  if (v.startsWith("ru")) return "ru";
  if (v.startsWith("et")) return "et";
  return "en";
};

export default function DataGapNotice() {
  const [lang, setLang] = useState<UiLang>(() => {
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem("water.ui.lang");
      if (stored) return normalizeLang(stored);
    }
    if (typeof navigator !== "undefined") return normalizeLang(navigator.language);
    return "en";
  });
  const [visible, setVisible] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(STORAGE_KEY) !== "1";
  });

  useEffect(() => {
    const onLangChanged = (e: Event) => {
      const evt = e as CustomEvent<{ lang?: string }>;
      setLang(normalizeLang(evt.detail?.lang));
    };
    window.addEventListener("water-ui-lang-changed", onLangChanged as EventListener);
    return () => window.removeEventListener("water-ui-lang-changed", onLangChanged as EventListener);
  }, []);

  if (!visible) return null;

  const copy = copyByLang[lang];

  const dismiss = () => {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // localStorage unavailable (private mode, etc.) — dismiss only for the session.
    }
    setVisible(false);
  };

  return (
    <aside
      role="note"
      aria-label={copy.title}
      style={{
        padding: "0.75rem 1rem",
        background: "var(--water-notice-bg, rgba(23, 176, 255, 0.08))",
        borderBottom: "1px solid var(--water-notice-border, rgba(23, 176, 255, 0.24))",
        color: "var(--water-notice-fg, inherit)",
        fontSize: "0.875rem",
        lineHeight: 1.45,
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", gap: "1rem", alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 auto" }}>
          <strong style={{ display: "block", marginBottom: 4 }}>{copy.title}</strong>
          <span>{copy.body}</span>{" "}
          <a
            href="https://github.com/sapsan14/water-quality-ee/blob/main/docs/phase_10_findings.md"
            target="_blank"
            rel="noreferrer"
          >
            {copy.more}
          </a>
          .
        </div>
        <button
          type="button"
          onClick={dismiss}
          style={{
            flex: "0 0 auto",
            border: "1px solid currentColor",
            borderRadius: 4,
            background: "transparent",
            color: "inherit",
            padding: "0.25rem 0.75rem",
            cursor: "pointer",
            fontSize: "0.8125rem",
          }}
        >
          {copy.dismiss}
        </button>
      </div>
    </aside>
  );
}
