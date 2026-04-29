#!/usr/bin/env node
/**
 * Merge a fresh batch of posted IDs into state/social-last-post.json.
 *
 * Usage:
 *   cat fb.json li.json | node scripts/social/update-state.mjs
 * (multiple JSON objects on stdin, one per line group; or a single JSON map)
 *
 * The script keeps a rolling history of the last 200 posted IDs to bound
 * the file size — older entries are pruned.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");
const STATE_PATH = resolve(ROOT, "state/social-last-post.json");
const MAX_ENTRIES = 200;

async function readStdin() {
  let raw = "";
  for await (const chunk of process.stdin) raw += chunk;
  return raw.trim();
}

function parseAllJson(blob) {
  // Accept either a single JSON object/array, or multiple newline-separated
  // JSON objects (concatenated by `cat fb.json li.json`).
  const out = [];
  // Try as one JSON value first.
  try {
    const v = JSON.parse(blob);
    return Array.isArray(v) ? [v] : [v];
  } catch {
    // fall through to streaming parse
  }
  let depth = 0;
  let buf = "";
  for (const ch of blob) {
    buf += ch;
    if (ch === "{" || ch === "[") depth++;
    else if (ch === "}" || ch === "]") {
      depth--;
      if (depth === 0) {
        const piece = buf.trim();
        buf = "";
        if (!piece) continue;
        try {
          out.push(JSON.parse(piece));
        } catch {
          // skip malformed chunk
        }
      }
    }
  }
  return out;
}

async function main() {
  const blob = await readStdin();
  if (!blob) {
    process.stderr.write("update-state: empty stdin, nothing to merge\n");
    return;
  }
  const incoming = parseAllJson(blob);
  const merged = {};
  for (const obj of incoming) {
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const [id, _postId] of Object.entries(obj)) {
        merged[id] = new Date().toISOString();
      }
    }
  }

  const state = existsSync(STATE_PATH)
    ? JSON.parse(readFileSync(STATE_PATH, "utf8"))
    : { posts: {} };
  const posts = { ...(state.posts || {}), ...merged };

  // Prune to MAX_ENTRIES newest.
  const sorted = Object.entries(posts)
    .sort(([, a], [, b]) => Date.parse(b) - Date.parse(a))
    .slice(0, MAX_ENTRIES);
  const pruned = Object.fromEntries(sorted);

  mkdirSync(dirname(STATE_PATH), { recursive: true });
  writeFileSync(
    STATE_PATH,
    JSON.stringify({ updated_at: new Date().toISOString(), posts: pruned }, null, 2) + "\n",
    "utf8"
  );
  process.stderr.write(`update-state: wrote ${Object.keys(pruned).length} entries to ${STATE_PATH}\n`);
}

main().catch((err) => {
  process.stderr.write(`fatal: ${err.stack || err.message}\n`);
  process.exit(1);
});
