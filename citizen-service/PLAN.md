# План: открытый код, автообновление, карта

## Цели

- Понятный **гражданский** текст и визуализация, без подмены официальных формулировок Terviseamet.
- Два слоя: **официальный статус** из данных и **прогноз ML** с подписью «оценка модели».
- **Карта**: отдельные **точки** (последняя проба на место), раскраска по официальному статусу или прогнозу; фильтры: **купание**, **бассейн/СПА**, **водопровод**, **источники питьевой воды** (`joogivesi`). Во всплывающем окне — дата, уезд, ключевые измерения из XML.
- **Кластеризация** Folium при большом числе точек (veevark + joogivesi); отключается при необходимости.

## Архитектура

| Компонент | Роль |
|-----------|------|
| `src/data_loader.py` | Загрузка и кэш XML |
| `src/features.py` | `build_dataset_with_meta()` — признаки + привязка к `location` / `domain` |
| `citizen-service/scripts/build_citizen_snapshot.py` | Офлайн-сбор: последняя проба на точку, RF, координаты |
| `citizen-service/app/streamlit_app.py` | UI: Folium + таблица |
| `citizen-service/artifacts/snapshot.json` | Небольшой файл для деплоя и Git |

## Координаты

1. Кэш **Nominatim** (бесплатно, с задержкой) — запрос `"{location}, Estonia"`.
2. Fallback: **центроид уезда** + лёгкий jitter (`county_centroids.py`), если геокода нет.

## GitHub Actions (черновик)

- Триггер: `schedule` (например раз в сутки) + `workflow_dispatch`.
- Шаги: `actions/checkout`, setup Python, `pip install -r requirements.txt -r citizen-service/requirements.txt`, при необходимости `python src/data_loader.py` или вызов загрузки из скрипта с `use_cache=False`, затем `python citizen-service/scripts/build_citizen_snapshot.py` без большого `--geocode-limit` (или с секретом и отдельным редким workflow для геокода).
- Коммит только `citizen-service/artifacts/snapshot.json` (и при необходимости `citizen_model.joblib`) через `stefanzweifel/git-auto-commit-action` или аналог — при включении нужен `GITHUB_TOKEN` с правом на push.

Файл-заготовка: `.github/workflows/citizen-snapshot.yml`.

## Streamlit Cloud

- Репозиторий публичный, путь к файлу: `citizen-service/app/streamlit_app.py`.
- Указать зависимости (объединённый файл или основной + дополнительный — по документации Streamlit).
- Холодный старт и лимиты — заложить в README для пользователей.

## Юридически / этично

- В интерфейсе и в `snapshot.json` — дисклеймер: прогноз не является официальным заключением; источник данных — открытые XML Terviseamet.
