"use client";

import { useEffect, useState } from "react";
import { track } from "../lib/analytics";
import { buildPlaceUrl } from "../lib/url-state";

type Lang = "ru" | "et" | "en";

type Props = {
  placeId: string;
  placeName: string;
  county: string | null;
  lang: Lang;
};

const t = {
  share: { ru: "Поделиться", et: "Jaga", en: "Share" },
  copy: { ru: "Скопировать ссылку", et: "Kopeeri link", en: "Copy link" },
  copied: { ru: "Скопировано", et: "Kopeeritud", en: "Copied" },
  facebook: { ru: "Поделиться в Facebook", et: "Jaga Facebookis", en: "Share on Facebook" },
  linkedin: { ru: "Поделиться в LinkedIn", et: "Jaga LinkedInis", en: "Share on LinkedIn" },
  nativeShare: { ru: "Поделиться…", et: "Jaga…", en: "Share…" },
};

function pickShareText(placeName: string, county: string | null, lang: Lang): string {
  const where = county ? `${placeName} (${county})` : placeName;
  if (lang === "et") return `${where} — H2O Atlas, Eesti veekvaliteedi kaart`;
  if (lang === "en") return `${where} — H2O Atlas, Estonian water-quality map`;
  return `${where} — H2O Atlas, карта качества воды Эстонии`;
}

export default function ShareButtons({ placeId, placeName, county, lang }: Props) {
  const [copied, setCopied] = useState(false);
  const [canNativeShare, setCanNativeShare] = useState(false);

  useEffect(() => {
    setCanNativeShare(typeof navigator !== "undefined" && typeof navigator.share === "function");
  }, []);

  const url = buildPlaceUrl(placeId);
  const text = pickShareText(placeName, county, lang);

  const open = (network: string, href: string) => {
    track("share_click", { network, place_id: placeId });
    window.open(href, "_blank", "noopener,noreferrer,width=640,height=540");
  };

  const onFacebook = () =>
    open("facebook", `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`);

  const onLinkedIn = () =>
    open("linkedin", `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`);

  const onCopy = async () => {
    track("share_click", { network: "copy", place_id: placeId });
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — silently no-op */
    }
  };

  const onNative = async () => {
    track("share_click", { network: "native", place_id: placeId });
    try {
      await navigator.share({ title: placeName, text, url });
    } catch {
      /* user cancelled — no-op */
    }
  };

  return (
    <div className="shareButtons" role="group" aria-label={t.share[lang]}>
      <span className="shareButtonsLabel">{t.share[lang]}:</span>
      {canNativeShare ? (
        <button type="button" className="shareBtn shareBtnNative" onClick={onNative} aria-label={t.nativeShare[lang]}>
          {/* iOS-style share glyph */}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
            <polyline points="16 6 12 2 8 6" />
            <line x1="12" y1="2" x2="12" y2="15" />
          </svg>
          <span>{t.nativeShare[lang]}</span>
        </button>
      ) : null}
      <button type="button" className="shareBtn shareBtnFb" onClick={onFacebook} aria-label={t.facebook[lang]}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3v3h-3v6.95c5.05-.5 9-4.76 9-9.95z" />
        </svg>
        <span>Facebook</span>
      </button>
      <button type="button" className="shareBtn shareBtnLi" onClick={onLinkedIn} aria-label={t.linkedin[lang]}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14zM8.34 18.34V10.5H5.67v7.84h2.67zM7 9.34a1.55 1.55 0 1 0 0-3.1 1.55 1.55 0 0 0 0 3.1zm11.34 9V14a3.5 3.5 0 0 0-3.5-3.5 3.04 3.04 0 0 0-2.7 1.5v-1.5H9.67v7.84h2.67v-4.33c0-.92.55-1.83 1.66-1.83 1.1 0 1.67.91 1.67 1.83v4.33h2.67z" />
        </svg>
        <span>LinkedIn</span>
      </button>
      <button type="button" className="shareBtn shareBtnCopy" onClick={onCopy} aria-label={t.copy[lang]}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
        <span>{copied ? t.copied[lang] : t.copy[lang]}</span>
      </button>
    </div>
  );
}
