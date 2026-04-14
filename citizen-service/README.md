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
# полный снимок: то же + прогноз Random Forest и citizen_model.joblib
python citizen-service/scripts/build_citizen_snapshot.py
# автоматически: OpenCage и уезд (OPENCAGE_API_KEY в .env) — см. GEO_SECRETS.md
./scripts/refresh_citizen_geo.sh --map-only
streamlit run citizen-service/app/streamlit_app.py
```

Полностью без ручных флагов геокодирования: **GitHub Actions → Citizen snapshot** (cron или ручной запуск) уже собирает снимок с `--resolve-coordinates` и коммитит кэши. Секрет **OPENCAGE_API_KEY**: [GEO_SECRETS.md](GEO_SECRETS.md).

Артефакты:

- `artifacts/snapshot.json` — последняя проба по каждому месту, координаты, официальный статус; при полном прогоне — ещё `model_violation_prob` и поле `has_model_predictions: true` (`--map-only` оставляет `has_model_predictions: false` и без вероятностей по точкам)
- `artifacts/citizen_model.joblib` — imputer + RF (только после полного прогона, не перезаписывается в режиме `--map-only`)
- `data/geocode_cache.json` — кэш простого геокода (создаётся при `--geocode-limit > 0`)

Логи: у скрипта сборки флаг **`--log-level`** (`INFO` / `DEBUG`); в лог пишутся этапы сборки, HTTP-геокод и попадания в кэш координат. Приложение Streamlit при старте страницы логирует сводку по снимку (число точек, разбивка `coord_source`, наличие `citizen_model.joblib`).

## Объяснение модели

В приложении есть вкладка **«О модели»** с понятным объяснением:
- Как модель принимает решения
- 4 уровня оценки: ROC-AUC, Precision/Recall, калибровка, SHAP
- Главные предикторы нарушений (SHAP-анализ)
- Как читать цвета маркеров на карте

Подробнее: [`docs/ml_metrics_guide.md`](../docs/ml_metrics_guide.md)

## Деплой и доступ

- Пошагово: **[DEPLOY.md](DEPLOY.md)** (создание приложения на [share.streamlit.io](https://share.streamlit.io), `requirements.streamlit.txt`, путь к `streamlit_app.py`).
- Публичный URL после публикации и заметки про токены: **[STREAMLIT_ACCESS.md](STREAMLIT_ACCESS.md)** — *вставьте туда ссылку вида `https://<subdomain>.streamlit.app` после первого деплоя*.
- В репозиторий можно коммитить `snapshot.json` (не сырой XML). Общий план — [PLAN.md](PLAN.md).
