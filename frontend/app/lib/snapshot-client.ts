import type { FrontendSnapshot } from "./types";

// The snapshot used to be read on the server and passed as a prop to the
// client <Dashboard>. Because the prop crossed the RSC boundary, the entire
// ~7 MB JSON was serialized into the RSC payload on every cold load, blocking
// hydration on mobile networks.
//
// We now fetch it from the browser against /data/snapshot.frontend.json. The
// file is served with `Cache-Control: public, max-age=31536000, immutable`
// via frontend/public/_headers, so repeat visits pay zero bytes — but because
// of the `immutable` directive we MUST change the URL whenever the file
// contents change, otherwise the browser never re-fetches. NEXT_PUBLIC_SNAPSHOT_VERSION
// is stamped at build time in next.config.mjs from CF_PAGES_COMMIT_SHA /
// GITHUB_SHA / Date.now(). Every deploy = new query string = fresh fetch.
//
// The in-flight promise is memoized so React 19 strict-mode double-effects
// (and future concurrent-render retries) do not trigger a second network
// request.

const SNAPSHOT_VERSION = process.env.NEXT_PUBLIC_SNAPSHOT_VERSION || "dev";
export const SNAPSHOT_URL = `/data/snapshot.frontend.json?v=${SNAPSHOT_VERSION}`;

let inflight: Promise<FrontendSnapshot> | null = null;

export function loadSnapshot(): Promise<FrontendSnapshot> {
  if (inflight) return inflight;
  inflight = fetch(SNAPSHOT_URL, { cache: "force-cache" })
    .then((res) => {
      if (!res.ok) throw new Error(`snapshot fetch failed: ${res.status}`);
      return res.json() as Promise<FrontendSnapshot>;
    })
    .catch((err) => {
      // Allow a retry on next call after a failure.
      inflight = null;
      throw err;
    });
  return inflight;
}
