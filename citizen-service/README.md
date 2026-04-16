# Гражданский сервис: карта качества воды

Интерфейс для жителей: **точки на карте** — **купание** (`supluskoha`), **бассейны / СПА** (`basseinid`), **водопровод** (`veevark`), **источники питьевой воды** opendata (`joogivesi` / joogiveeallika), плюс официальные данные и **оценка вероятности нарушения модели**. Минеральная вода (`mineraalvesi`) в opendata годовыми файлами пока не публикуется — в снимке нет.

## Что показывает сервис

Сервис предоставляет **два слоя информации** по каждой точке:

| Слой | Что показывает | Источник |
|------|---------------|----------|
| **Официальный статус** | Соответствует / не соответствует нормам (последняя проба) | Поле `hinnang` в XML Terviseamet |
| **Оценка модели** | P(нарушение) ∈ [0, 1] — вероятность нарушения по Random Forest | ML-модель, обученная на всём датасете |

### Что сервис НЕ делает

- **Не прогнозирует будущее**: показывает оценку **последней пробы**, а не прогноз на завтра
- **Не заменяет Terviseamet**: дисклеймер в интерфейсе — «это оценка модели, а не официальное заключение»
- **Не даёт медицинских рекомендаций**: только визуализация данных и рисков
- **Не предсказывает загрязнители вне 15 измеряемых параметров**: модель работает в пространстве лабораторных измерений

Подробнее о том, что предсказывает модель: [`docs/ml_framing.md`](../docs/ml_framing.md).

## Быстрый старт

Из корня репозитория (нужны скачанные XML, см. основной `README.md`):

```bash
pip install -r requirements.txt -r citizen-service/requirements.txt
# быстро: карта и официальные статусы без обучения RF
python citizen-service/scripts/build_citizen_snapshot.py --map-only
# экспорт frontend-оптимизированного JSON для web UI
python citizen-service/scripts/export_frontend_snapshot.py
# полный снимок: то же + прогноз Random Forest и citizen_model.joblib
python citizen-service/scripts/build_citizen_snapshot.py
# опционально: попробовать добавить домен mineraalvesi (если доступен в источнике)
python citizen-service/scripts/build_citizen_snapshot.py --include-mineraalvesi
# автоматически: OpenCage и уезд (OPENCAGE_API_KEY в .env) — см. GEO_SECRETS.md
./scripts/refresh_citizen_geo.sh --map-only
```

Полностью без ручных флагов геокодирования: **GitHub Actions → Citizen snapshot** (cron или ручной запуск) уже собирает снимок с `--resolve-coordinates` и коммитит кэши. Секрет **OPENCAGE_API_KEY**: [GEO_SECRETS.md](GEO_SECRETS.md).
Рекомендуется также задать **GEOAPIFY_API_KEY** — основной провайдер геокодинга (OpenCage используется как fallback).

Артефакты:

- `artifacts/snapshot.json` — последняя проба по каждому месту, координаты, официальный статус; при полном прогоне — ещё `model_violation_prob` и поле `has_model_predictions: true` (`--map-only` оставляет `has_model_predictions: false` и без вероятностей по точкам)
- `artifacts/citizen_model.joblib` — imputer + RF (только после полного прогона, не перезаписывается в режиме `--map-only`)
- `data/geocode_cache.json` — кэш простого геокода (создаётся при `--geocode-limit > 0`)
- `../frontend/public/data/snapshot.frontend.json` — precomputed контракт данных для нового Next.js интерфейса

Логи: у скрипта сборки флаг **`--log-level`** (`INFO` / `DEBUG`); в лог пишутся этапы сборки, HTTP-геокод и попадания в кэш координат.

### Ручная проверка координат (queue + overrides)

1) Сформировать очередь проблемных точек:

```bash
python citizen-service/scripts/generate_coordinate_review_queue.py
```

Артефакты:
- `artifacts/coordinate_review_queue.csv` — список точек для проверки (ссылки на Google Maps)
- `artifacts/coordinate_review_queue.json` — то же в JSON
- `artifacts/coordinate_review_summary.json` — сводка по количеству
- `data/coordinate_overrides.template.json` — шаблон ручных правок

2) Создать `citizen-service/data/coordinate_overrides.json` по шаблону:
- `action: "set_manual"` + `lat/lon` для ручной фиксации
- `action: "hide"` чтобы убрать точку с карты

Или полуавтоматически из CSV-очереди:

```bash
python citizen-service/scripts/apply_coordinate_review_queue.py
```

Скрипт читает колонки `action`, `manual_lat`, `manual_lon`, `review_note` из
`artifacts/coordinate_review_queue.csv` и обновляет `data/coordinate_overrides.json`.

3) Пересобрать snapshot:

```bash
python citizen-service/scripts/build_citizen_snapshot.py --map-only
```

В `snapshot.json` добавляется блок `coordinate_override_stats` (сколько оверрайдов применено и скрыто).

Примечание: при сборке snapshot скрипт также подтягивает адреса из paged-страниц
`active_tab_id=U` и `active_tab_id=JV` (кэш `data/paged_address_cache.json`) и
использует их как дополнительный fallback для геокодинга проблемных точек.

## Объяснение модели

В приложении есть вкладка **«О модели»** с понятным объяснением:
- Как модель принимает решения
- 4 уровня оценки: ROC-AUC, Precision/Recall, калибровка, SHAP
- Главные предикторы нарушений (SHAP-анализ)
- Как читать цвета маркеров на карте

Подробнее: [`docs/ml_metrics_guide.md`](../docs/ml_metrics_guide.md)

## Деплой и доступ

- Web frontend (Next.js) деплоится на Cloudflare Pages — см. [`frontend/README.md`](../frontend/README.md).
- В репозиторий можно коммитить `snapshot.json` (не сырой XML). Общий план — [PLAN.md](PLAN.md).
