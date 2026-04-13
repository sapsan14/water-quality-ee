# Гражданский сервис: карта качества воды

Интерфейс для жителей: **точки на карте** — **купание** (`supluskoha`), **бассейны / СПА** (`basseinid`), **водопровод** (`veevark`), **источники питьевой воды** opendata (`joogivesi` / joogiveeallika), плюс официальные данные и **прогноз модели**. Минеральная вода (`mineraalvesi`) в opendata годовыми файлами пока не публикуется — в снимке нет.

## Быстрый старт

Из корня репозитория (нужны скачанные XML, см. основной `README.md`):

```bash
pip install -r requirements.txt -r citizen-service/requirements.txt
python citizen-service/scripts/build_citizen_snapshot.py
# опционально: точные координаты (медленно)
python citizen-service/scripts/build_citizen_snapshot.py --geocode-limit 150
streamlit run citizen-service/app/streamlit_app.py
```

Артефакты:

- `artifacts/snapshot.json` — последняя проба по каждому месту, координаты, официальный статус, `model_violation_prob`
- `artifacts/citizen_model.joblib` — imputer + RF (для будущего онлайн-пересчёта)
- `data/geocode_cache.json` — кэш Nominatim (создаётся при `--geocode-limit > 0`)

## Деплой

Кратко: **Streamlit Community Cloud** с корнем приложения `citizen-service/app/streamlit_app.py`, зависимости из двух `requirements.txt` или один объединённый. В репозиторий можно коммитить только `snapshot.json` (не сырой XML). Подробности — [PLAN.md](PLAN.md).
