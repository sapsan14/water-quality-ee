#!/usr/bin/env node
/**
 * Post to LinkedIn (personal profile or organization page) via the
 * official Posts API.
 *
 * Required env:
 *   LINKEDIN_ACCESS_TOKEN - OAuth 2.0 access token with `w_member_social`
 *                           (personal profile) or `w_organization_social`
 *                           (organization page). See SOCIAL_SETUP.md.
 *   LINKEDIN_AUTHOR_URN   - "urn:li:person:<id>" (personal) or
 *                           "urn:li:organization:<id>" (org page).
 *
 * Flags: same shape as post-fb.mjs (--dry-run, --lang).
 *
 * Outputs posted-id mapping on stdout: { "<place_id>": "<urn:li:share:...>" }.
 */
import { renderPostBody } from "./render-text.mjs";

const SITE = "https://h2oatlas.ee";

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
  const placeUrl = `${SITE}/?place=${encodeURIComponent(c.id)}`;
  const payload = {
    author: env.LINKEDIN_AUTHOR_URN,
    commentary: body,
    visibility: "PUBLIC",
    distribution: { feedDistribution: "MAIN_FEED", targetEntities: [], thirdPartyDistributionChannels: [] },
    content: {
      article: {
        source: placeUrl,
        title: c.county ? `${c.location} (${c.county})` : c.location,
        description: "H2O Atlas — Estonian water-quality map",
      },
    },
    lifecycleState: "PUBLISHED",
    isReshareDisabledByAuthor: false,
  };
  const res = await fetch("https://api.linkedin.com/rest/posts", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.LINKEDIN_ACCESS_TOKEN}`,
      "content-type": "application/json",
      "linkedin-version": "202405",
      "x-restli-protocol-version": "2.0.0",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`LinkedIn post failed (HTTP ${res.status}): ${text}`);
  }
  // The post URN is returned in the `x-restli-id` response header.
  const postUrn = res.headers.get("x-restli-id") || "";
  return postUrn;
}

async function main() {
  const args = parseArgs(process.argv);
  const candidates = await readStdin();
  if (!Array.isArray(candidates) || candidates.length === 0) {
    process.stderr.write("nothing to post\n");
    process.stdout.write("{}\n");
    return;
  }

  const env = {
    LINKEDIN_ACCESS_TOKEN: process.env.LINKEDIN_ACCESS_TOKEN,
    LINKEDIN_AUTHOR_URN: process.env.LINKEDIN_AUTHOR_URN,
  };
  if (!args.dryRun && (!env.LINKEDIN_ACCESS_TOKEN || !env.LINKEDIN_AUTHOR_URN)) {
    process.stderr.write("error: LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN required (or pass --dry-run)\n");
    process.exit(2);
  }

  const posted = {};
  for (const c of candidates) {
    const body = renderPostBody(c, args.lang);
    if (args.dryRun) {
      process.stderr.write(`\n[DRY-RUN] LinkedIn post for place ${c.id} (${c.location}):\n`);
      process.stderr.write(body + "\n---\n");
      posted[c.id] = `dryrun_${c.id}`;
      continue;
    }
    try {
      const urn = await postOne(c, body, env);
      process.stderr.write(`✓ LinkedIn post ${urn} for place ${c.id}\n`);
      posted[c.id] = urn || "posted";
      await new Promise((r) => setTimeout(r, 5000));
    } catch (err) {
      process.stderr.write(`✗ LinkedIn post failed for place ${c.id}: ${err.message}\n`);
    }
  }
  process.stdout.write(JSON.stringify(posted, null, 2) + "\n");
}

main().catch((err) => {
  process.stderr.write(`fatal: ${err.stack || err.message}\n`);
  process.exit(1);
});
