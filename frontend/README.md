# Frontend (Next.js + Cloudflare Pages)

Новый публичный UI для citizen-service с упором на скорость, UX и контроль дизайна.

## Быстрый старт

```bash
cd frontend
npm install
npm run dev
```

Перед запуском убедитесь, что существует `public/data/snapshot.frontend.json`:

```bash
python3 citizen-service/scripts/export_frontend_snapshot.py
```

## Font: Proxima Nova (.woff2)

For consistent typography on all devices, add licensed font files to:
`frontend/public/fonts/`

Required filenames:
- `ProximaNova-Regular.woff2`
- `ProximaNova-Semibold.woff2`
- `ProximaNova-Bold.woff2`

If files are missing, app falls back to system fonts.

Default free alternative is enabled: `Source Sans 3` (via `next/font/google` in `app/layout.tsx`).

## Скрипты

- `npm run dev` — локальная разработка.
- `npm run build` — production-сборка.
- `npm run start` — запуск production-сервера.
- `npm run lint` — ESLint.
- `npm run typecheck` — TypeScript type-check.

## Деплой в Cloudflare Pages

1. Root directory: `frontend`
2. Build command: `npm run build && npx @cloudflare/next-on-pages@1`
3. Output directory: `.vercel/output/static`
4. Node version: 20+

Подробный чеклист: `frontend/DEPLOY_CLOUDFLARE.md`.

## Analytics / observability

Если задан `NEXT_PUBLIC_ANALYTICS_ENDPOINT`, фронтенд отправляет события через `sendBeacon`:
- `dashboard_open`
- `filters_changed`

Это можно направить в Cloudflare Worker endpoint.

## GitHub Actions

- `Citizen snapshot` автоматически экспортирует `frontend/public/data/snapshot.frontend.json`.
- `Frontend CI` проверяет `lint + typecheck + build`.
- `Deploy Frontend to Cloudflare Pages` деплоит `main` в Cloudflare Pages (нужны secrets).
