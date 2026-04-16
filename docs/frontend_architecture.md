# Frontend Architecture (Cloudflare + Next.js)

## Goal

Build a fast, professional public UI with production-grade UX while keeping ML inference in batch mode.

## Target stack

- `frontend/`: Next.js 15 (App Router) + TypeScript.
- Styling: Tailwind CSS + design tokens via CSS variables.
- UI components: lightweight local components (`app/components/*`), extensible to shadcn/ui later.
- Map: Leaflet (react-leaflet) with marker clustering and domain filters.
- Data source: precomputed JSON from `citizen-service/artifacts/snapshot.json`.
- Hosting: Cloudflare Pages (static-first).

## Runtime boundaries

- No model inference in browser or edge on free tier.
- `citizen_model.joblib` stays in offline batch pipeline only.
- Public frontend consumes precomputed probabilities and derived risk labels.

## Deployment model

1. Build/update snapshot via existing Python pipeline.
2. Export frontend-optimized JSON into `frontend/public/data/`.
3. Deploy Next.js app to Cloudflare Pages.
4. Optional: add Workers API for analytics collection and future server-side features.

## Why this architecture

- Full UX control over the interface.
- CDN distribution for static assets and map data.
- Predictable free-tier costs with precomputed probabilities.
- Clean path to paid scale-up (Workers Paid) without re-architecture.
