#!/usr/bin/env node
/**
 * Post to a Facebook Page via the Graph API.
 *
 * Reads candidate JSON array from stdin (output of select-top.mjs) and
 * posts each candidate as a separate `link` post to the configured Page.
 *
 * Required env:
 *   FB_PAGE_ID            - numeric Page ID
 *   FB_PAGE_ACCESS_TOKEN  - long-lived Page access token (see SOCIAL_SETUP.md)
 *
 * Optional flags:
 *   --dry-run   Print intended requests instead of calling Graph API.
 *               Useful for local testing — no token required.
 *   --lang LANG Language for the post body (en|ru, default en).
 *
 * On success, writes posted-id mapping to stdout as JSON
 *   { "<place_id>": "<fb_post_id>", ... }
 * so the parent workflow can update state/social-last-post.json.
 */
import { renderPostBody } from "./render-text.mjs";

function parseArgs(argv) {
  const out = { dryRun: false, lang: "en" };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--dry-run") out.dryRun = true;
    else if (argv[i] === "--lang") out.lang = argv[++i] || "en";
  }
  return out;
}

async function readStdin() {
  let raw = "";
  for await (const chunk of process.stdin) raw += chunk;
  if (!raw.trim()) return [];
  return JSON.parse(raw);
}

async function postOne(c, body, env) {
  const url = `${SITE}/?place=${encodeURIComponent(c.id)}`;
  const params = new URLSearchParams({
    message: body,
    link: url,
    access_token: env.FB_PAGE_ACCESS_TOKEN,
  });
  const res = await fetch(`https://graph.facebook.com/v18.0/${encodeURIComponent(env.FB_PAGE_ID)}/feed`, {
    method: "POST",
    body: params,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || !json.id) {
    throw new Error(`Facebook post failed (HTTP ${res.status}): ${JSON.stringify(json)}`);
  }
  return json.id;
}

const SITE = "https://h2oatlas.ee";

async function main() {
  const args = parseArgs(process.argv);
  const candidates = await readStdin();
  if (!Array.isArray(candidates) || candidates.length === 0) {
    process.stderr.write("nothing to post\n");
    process.stdout.write("{}\n");
    return;
  }

  const env = {
    FB_PAGE_ID: process.env.FB_PAGE_ID,
    FB_PAGE_ACCESS_TOKEN: process.env.FB_PAGE_ACCESS_TOKEN,
  };
  if (!args.dryRun && (!env.FB_PAGE_ID || !env.FB_PAGE_ACCESS_TOKEN)) {
    process.stderr.write("error: FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN required (or pass --dry-run)\n");
    process.exit(2);
  }

  const posted = {};
  for (const c of candidates) {
    const body = renderPostBody(c, args.lang);
    if (args.dryRun) {
      process.stderr.write(`\n[DRY-RUN] FB post for place ${c.id} (${c.location}):\n`);
      process.stderr.write(body + "\n---\n");
      posted[c.id] = `dryrun_${c.id}`;
      continue;
    }
    try {
      const postId = await postOne(c, body, env);
      process.stderr.write(`✓ FB post ${postId} for place ${c.id}\n`);
      posted[c.id] = postId;
      // Gentle pacing — Graph API is happy with one post / few seconds,
      // but be polite.
      await new Promise((r) => setTimeout(r, 5000));
    } catch (err) {
      process.stderr.write(`✗ FB post failed for place ${c.id}: ${err.message}\n`);
    }
  }
  process.stdout.write(JSON.stringify(posted, null, 2) + "\n");
}

main().catch((err) => {
  process.stderr.write(`fatal: ${err.stack || err.message}\n`);
  process.exit(1);
});
