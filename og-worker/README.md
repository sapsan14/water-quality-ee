# h2oatlas-og worker

Cloudflare Worker that renders 1200×630 Open Graph PNGs for h2oatlas.ee
per-place share previews.

## Routes

| Method | Path                | Behavior                                            |
|--------|---------------------|-----------------------------------------------------|
| GET    | `/og?place=<id>`    | PNG card for a place from `og-index.json`           |
| GET    | `/og`               | Default brand card (fallback)                        |
| GET    | `/` or `/health`    | `text/plain` health check                            |

## Local development

```bash
cd og-worker
npm install
npm run dev          # serves http://localhost:8787
# in another shell:
open "http://localhost:8787/og?place=1"
open "http://localhost:8787/og"        # default card
```

`wrangler dev` reads `[vars]` from `wrangler.toml`, so by default the
worker fetches `og-index.json` from production. To point at a local
preview deployment of the frontend, override:

```bash
OG_INDEX_URL="https://my-preview.h2oatlas.pages.dev/data/og-index.json" npm run dev
```

## Deploy

```bash
cd og-worker
npx wrangler login         # one-time
npx wrangler deploy
```

After the first deploy, add the custom hostname `og.h2oatlas.ee`:

1. Cloudflare dashboard → Workers & Pages → `h2oatlas-og` → **Settings → Triggers → Custom Domains** → Add `og.h2oatlas.ee`.
2. Uncomment the `routes` block in `wrangler.toml` once DNS resolves.

## Cache strategy

- The og-index JSON is cached on the worker edge for 1 hour and at
  Cloudflare's tiered cache for 1 hour (`cf.cacheTtl: 3600`). Snapshots
  rebuild weekly, so 1h is plenty.
- Rendered PNGs are returned with `cache-control: public, max-age=86400,
  immutable`. Callers append `&v=<snapshot-sha>` to invalidate on each
  deploy of the frontend.

## Why a separate worker?

Cloudflare Pages bundles have a hard 1 MB compressed limit. WASM
rasterizers (`workers-og` ≈ 600 KB) push the Pages bundle dangerously
close to that ceiling, especially with Next 16 server components. Keeping
the renderer as its own worker isolates the WASM and lets the Pages
bundle stay lean.
