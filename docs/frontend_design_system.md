# Frontend Design System Baseline

## Principles

- Fast first paint with static data.
- High contrast dark UI for map-centric workflows.
- Clear semantic states for risk and official status.
- Simple interaction model: search + domain filter + risk filter.

## Tokens

Defined in `frontend/app/globals.css`:

- Background and panels: `--bg`, `--panel`, `--panel-soft`
- Typography: `--text`, `--muted`
- Semantic colors: `--good`, `--warn`, `--bad`
- Accent: `--brand`

## Components (MVP)

- Dashboard layout (`2-column`, mobile fallback to `1-column`)
- Filter controls (`input/select`)
- KPI cards (`Visible`, `High risk`, `Low risk`)
- Semantic badges (`compliant`, `violation`, `risk`)
- Map markers color-coded by risk level
- Scrollable data table for quick inspection

## UX rules

- Filters are instant and client-side (`search_text` precomputed).
- Map and table reflect same filtered dataset.
- Unknown model probability is always explicit (`risk_level=unknown`, `n/a`).
