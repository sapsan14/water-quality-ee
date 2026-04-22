"use client";

import { useEffect, useState } from "react";

type Lang = "ru" | "et" | "en";

type Sidecar = {
  mode?: string;
  signed_at?: string;
  aletheia_uuid?: string;
  aletheia_id?: number;
  tsa_token_included?: boolean;
};

type Props = {
  lang: Lang;
};

function labelFor(lang: Lang, mode: string | undefined): string {
  if (mode === "backend") {
    return lang === "ru" ? "Подписано" : lang === "et" ? "Allkirjastatud" : "Signed";
  }
  return lang === "ru" ? "Подписано (dev)" : lang === "et" ? "Allkirjastatud (dev)" : "Signed (dev)";
}

export default function SignedBadge({ lang }: Props) {
  const [sig, setSig] = useState<Sidecar | null>(null);

  useEffect(() => {
    const stamp = process.env.NEXT_PUBLIC_SNAPSHOT_VERSION || "dev";
    const url = `/data/snapshot.sig.json?v=${encodeURIComponent(stamp)}`;
    let cancelled = false;
    fetch(url, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!cancelled) setSig(j);
      })
      .catch(() => {
        if (!cancelled) setSig(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!sig || !sig.signed_at) return null;

  const title = [
    `mode=${sig.mode ?? "?"}`,
    `signed_at=${sig.signed_at}`,
    sig.aletheia_uuid ? `aletheia_uuid=${sig.aletheia_uuid}` : null,
    sig.tsa_token_included ? "TSA=true" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <a
      href="/verify"
      className="signedBadge"
      title={title}
      aria-label={title}
    >
      <span className="signedBadgeIcon" aria-hidden="true">🔒</span>
      <span className="signedBadgeLabel">{labelFor(lang, sig.mode)}</span>
    </a>
  );
}
