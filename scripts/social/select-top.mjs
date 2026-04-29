#!/usr/bin/env node
/**
 * Pick the top N places to post about this week.
 *
 * Strategy:
 *   1. Read frontend/public/data/snapshot.frontend.json (source of truth).
 *   2. Read state/social-last-post.json — { id: ISO_DATE } mapping of when
 *      we last posted each place. Skip anything posted in the last 30 days
 *      so we don't spam the same lake every week.
 *   3. Rank by:
 *        a. fresh violations (official_compliant === 0 AND not previously posted)
 *        b. risk_level === "high" with model_violation_prob ≥ 0.7
 *        c. medium-risk fallback if (a) and (b) yield nothing
 *   4. Emit JSON array on stdout — consumed by post-fb.mjs / post-linkedin.mjs.
 *
 * Usage:
 *   node scripts/social/select-top.mjs [--limit N]
 */
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");

const SNAPSHOT_PATH = resolve(ROOT, "frontend/public/data/snapshot.frontend.json");
const STATE_PATH = resolve(ROOT, "state/social-last-post.json");
const COOLDOWN_DAYS = 30;

function parseArgs(argv) {
  const out = { limit: 3 };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--limit") out.limit = Number(argv[++i] || 3);
  }
  return out;
}

function loadJson(path, fallback) {
  if (!existsSync(path)) return fallback;
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (err) {
    process.stderr.write(`warn: failed to parse ${path}: ${err.message}\n`);
    return fallback;
  }
}

function daysSince(iso) {
  if (!iso) return Infinity;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return Infinity;
  return (Date.now() - t) / (1000 * 60 * 60 * 24);
}

function rankScore(p) {
  // Higher = more interesting to post about.
  let score = 0;
  if (p.official_compliant === 0) score += 100;
  if (p.risk_level === "high") score += 60;
  else if (p.risk_level === "medium") score += 30;
  if (typeof p.model_violation_prob === "number") score += p.model_violation_prob * 20;
  // Recency: fresher samples are more newsworthy.
  if (p.sample_date) {
    const age = daysSince(p.sample_date);
    if (age < 60) score += 15;
    else if (age < 180) score += 5;
  }
  // Drinking water gets a small bump — higher public-interest impact.
  if (p.domain === "veevark" || p.domain === "joogivesi") score += 10;
  return score;
}

function main() {
  const args = parseArgs(process.argv);
  const snapshot = loadJson(SNAPSHOT_PATH, null);
  if (!snapshot || !Array.isArray(snapshot.places)) {
    process.stderr.write("error: snapshot.frontend.json missing or malformed\n");
    process.exit(2);
  }
  const state = loadJson(STATE_PATH, { posts: {} });
  const recentlyPosted = new Set(
    Object.entries(state.posts || {})
      .filter(([, iso]) => daysSince(iso) < COOLDOWN_DAYS)
      .map(([id]) => id)
  );

  const candidates = snapshot.places
    .filter((p) => !recentlyPosted.has(p.id))
    .filter((p) => p.official_compliant === 0 || p.risk_level === "high" || p.risk_level === "medium")
    .map((p) => ({ p, score: rankScore(p) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, args.limit)
    .map(({ p }) => ({
      id: p.id,
      location: p.location,
      county: p.county,
      domain: p.domain,
      place_kind: p.place_kind,
      official_compliant: p.official_compliant,
      risk_level: p.risk_level,
      model_violation_prob: p.model_violation_prob,
      sample_date: p.sample_date,
    }));

  process.stdout.write(JSON.stringify(candidates, null, 2) + "\n");
}

main();
