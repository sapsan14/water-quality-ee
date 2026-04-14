# Deploy to Cloudflare Pages

## Settings

- Framework preset: `Next.js`
- Root directory: `frontend`
- Build command: `npm run build && npx @cloudflare/next-on-pages@1`
- Build output directory: `.vercel/output/static`
- Node version: `20`

## Environment variables

- Optional analytics endpoint:
  - `NEXT_PUBLIC_ANALYTICS_ENDPOINT=https://<your-worker-domain>/ingest`

## Data refresh flow

1. Run GitHub Action `Citizen snapshot` in `full` mode (it now exports frontend JSON automatically).
2. Confirm commit contains updated `frontend/public/data/snapshot.frontend.json`.
3. Push to `main` to trigger `Deploy Frontend to Cloudflare Pages`.

## Required GitHub Secrets

- `CLOUDFLARE_API_TOKEN` — token with Pages deploy permissions.
- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare account ID.
- `CLOUDFLARE_PAGES_PROJECT` — Pages project name.
