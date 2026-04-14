# Frontend Data Contract

Файл: `frontend/public/data/snapshot.frontend.json`

Источник: `citizen-service/artifacts/snapshot.json`, экспорт через
`citizen-service/scripts/export_frontend_snapshot.py`.

## Root fields

- `generated_at: string`
- `has_model_predictions: boolean`
- `places_count: number`
- `place_kinds: Record<string, string>`
- `domains: string[]`
- `places: FrontendPlace[]`

## FrontendPlace

- `id: string`
- `location: string`
- `domain: string`
- `place_kind: string`
- `county: string | null`
- `sample_date: string | null`
- `official_compliant: number | null` (1/0/null)
- `coord_source: string | null`
- `lat: number`
- `lon: number`
- `model_violation_prob: number | null`
- `risk_level: "low" | "medium" | "high" | "unknown"`
- `has_model_prob: boolean`
- `search_text: string` (precomputed for быстрых фильтров)
- `measurements_count: number`

## Risk bucketing

Задаётся в экспортёре:

- `high`: `prob >= 0.7`
- `medium`: `0.4 <= prob < 0.7`
- `low`: `prob < 0.4`
- `unknown`: вероятность отсутствует
