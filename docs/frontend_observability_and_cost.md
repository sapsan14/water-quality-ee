# Frontend Observability and Cost Strategy

## Current instrumentation

- Client events via `sendBeacon` in `frontend/app/lib/analytics.ts`.
- Events:
  - `dashboard_open`
  - `filters_changed`

Set `NEXT_PUBLIC_ANALYTICS_ENDPOINT` to enable event delivery.

## Recommended Cloudflare endpoint

- Use a lightweight Worker endpoint for ingestion.
- Store counters/aggregates in Workers KV or forward to external analytics.
- Keep payload small (event name + timestamp + compact metadata).
- Example Worker handler: `docs/cloudflare_worker_analytics_example.js`.

## Cost posture

- Phase now: Cloudflare Pages Free + static snapshot JSON.
- Optional Worker Free: up to 100k requests/day for basic telemetry.
- Scale-up trigger: sustained traffic or need for richer API -> Workers Paid ($5/month base).

## Decision gates for paid plan

Move to paid when one or more conditions hold:

1. Daily requests approach free caps.
2. Need for server-side personalization or complex API aggregation.
3. Need longer retention/advanced observability pipeline.
