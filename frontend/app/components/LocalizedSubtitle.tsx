"use client";

import { useEffect, useState } from "react";

type UiLang = "ru" | "et" | "en";

const textByLang: Record<UiLang, string> = {
  et: "Eesti veekvaliteedi kaart avaandmete ja ML-hinnangutega.",
  ru: "Карта качества воды Эстонии на основе открытых данных и ML-оценок.",
  en: "Estonia water quality map powered by open data and ML assessments."
};

const normalizeLang = (value: string | null | undefined): UiLang => {
  const v = String(value || "").toLowerCase();
  if (v.startsWith("ru")) return "ru";
  if (v.startsWith("et")) return "et";
  return "en";
};

export default function LocalizedSubtitle() {
  const [lang, setLang] = useState<UiLang>(() => {
    if (typeof window !== "undefined") {
      const fromStorage = window.localStorage.getItem("water.ui.lang");
      if (fromStorage) return normalizeLang(fromStorage);
    }
    if (typeof navigator !== "undefined") return normalizeLang(navigator.language);
    return "en";
  });

  useEffect(() => {
    const onLangChanged = (e: Event) => {
      const evt = e as CustomEvent<{ lang?: string }>;
      setLang(normalizeLang(evt.detail?.lang));
    };
    window.addEventListener("water-ui-lang-changed", onLangChanged as EventListener);
    return () => window.removeEventListener("water-ui-lang-changed", onLangChanged as EventListener);
  }, []);

  return <>{textByLang[lang]}</>;
}
