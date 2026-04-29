"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const PLACE_PARAM = "place";

function readPlaceFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const sp = new URLSearchParams(window.location.search);
    const v = sp.get(PLACE_PARAM);
    return v && v.length > 0 && v.length < 200 ? v : null;
  } catch {
    return null;
  }
}

function writePlaceToUrl(id: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    if (id) {
      url.searchParams.set(PLACE_PARAM, id);
    } else {
      url.searchParams.delete(PLACE_PARAM);
    }
    // replaceState — no full reload, no RSC re-render, no scroll jump.
    // We deliberately do not use Next router here: the snapshot is fetched
    // client-side and the selected place is purely client state, so the
    // server-rendered page does not need to change.
    window.history.replaceState(window.history.state, "", url.toString());
  } catch {
    // Older browsers / sandboxed contexts may forbid replaceState — silent.
  }
}

/**
 * Drop-in replacement for `useState<string | null>(null)` that mirrors the
 * value into `?place=<id>` so locations are deep-linkable. Listens to
 * `popstate` so the Back button restores the previous selection.
 */
export function useSelectedPlaceUrl(): [string | null, (id: string | null | ((prev: string | null) => string | null)) => void] {
  const [selectedId, setSelectedIdState] = useState<string | null>(() => readPlaceFromUrl());
  const lastWritten = useRef<string | null>(selectedId);

  const setSelectedId = useCallback(
    (next: string | null | ((prev: string | null) => string | null)) => {
      setSelectedIdState((prev) => {
        const value = typeof next === "function" ? next(prev) : next;
        if (lastWritten.current !== value) {
          writePlaceToUrl(value);
          lastWritten.current = value;
        }
        return value;
      });
    },
    []
  );

  useEffect(() => {
    const onPop = () => {
      const fromUrl = readPlaceFromUrl();
      lastWritten.current = fromUrl;
      setSelectedIdState(fromUrl);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return [selectedId, setSelectedId];
}

/** Build a canonical absolute URL for a place — used by share buttons and OG meta. */
export function buildPlaceUrl(id: string | null, origin: string = "https://h2oatlas.ee"): string {
  if (!id) return origin;
  return `${origin}/?${PLACE_PARAM}=${encodeURIComponent(id)}`;
}
