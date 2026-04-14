# Координаты и API-ключи: что автоматизировано и что сделать один раз

Сырые XML Terviseamet **не содержат** широты/долготы. Координаты и дозаполнение уезда (`--infer-county`) используют **только OpenCage Geocoding** при заданном `OPENCAGE_API_KEY`. **Google Geocoding, In-ADS и Nominatim в коде не вызываются.** Кэши пишутся в `citizen-service/data/` и `data/processed/` и могут коммититься CI.

## Уже автоматически (без ключа)

- **GitHub Actions** — workflow [Citizen snapshot](../.github/workflows/citizen-snapshot.yml): по расписанию и вручную качает XML, собирает снимок с `--resolve-coordinates`, пушит обновлённые `snapshot.json` и кэши. **Новые HTTP-геокоды без `OPENCAGE_API_KEY` не выполняются** — остаются закоммиченные кэши и fallback (центроид уезда / `approximate_ee`).
- **Локально** — из корня репозитория:

```bash
chmod +x scripts/refresh_citizen_geo.sh   # один раз
./scripts/refresh_citizen_geo.sh --map-only
```

Переменная **`GEOCODE_HTTP_LIMIT`** (по умолчанию `8000`) задаёт лимит HTTP-запросов за один прогон.

## OpenCage Geocoding API

1. Зарегистрируйтесь на [OpenCage](https://opencagedata.com/) и создайте API-ключ.
2. Локально: в корневой `.env` добавьте `OPENCAGE_API_KEY=…` (файл не в git).
3. **GitHub Actions**: **Settings** → **Secrets** → **Actions** → secret **`OPENCAGE_API_KEY`**.

Квоты и тарифы — в личном кабинете OpenCage. Между запросами по умолчанию пауза **~0.55 с**; переопределение: **`OPENCAGE_MIN_DELAY_SEC`** (не ниже ~0.15 в коде; при **429** поставьте **1.0**). Успешные ответы и промахи пишутся в `county_geocode_cache.json` / `coordinate_resolve_cache.json` — **повторный HTTP для тех же ключей не выполняется** (в т.ч. после `miss: true`). При `geocode_county=True` лимит HTTP по умолчанию снят (`geocode_limit=None`).

### Локальная сборка

```bash
export OPENCAGE_API_KEY="…"
./scripts/refresh_citizen_geo.sh --map-only
```

### Streamlit Community Cloud

Приложение **читает координаты из закоммиченного** `snapshot.json`; в рантайме геокодер не вызывается. Секрет в Streamlit для карты **не обязателен**, если снимок обновляется через CI или локально и пушится в `main`.

## Логи и безопасность

При **`--log-level DEBUG`** логгеры **urllib3** подняты до **WARNING**, чтобы в вывод не попадали URL с `?key=…`. **Не публикуйте ключи** в чатах и issue; при утечке перевыпустите ключ в OpenCage.

## Лимиты

- **OpenCage**: условия использования и квоты — на [opencagedata.com](https://opencagedata.com/).
