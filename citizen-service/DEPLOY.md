# Деплой на Streamlit Community Cloud

## Предварительно

В репозитории должен быть **`citizen-service/artifacts/snapshot.json`**. Для быстрого деплоя и CI достаточно **`build_citizen_snapshot.py --map-only`**: Streamlit показывает карту и официальные статусы без `citizen_model.joblib`. Полный прогон добавляет прогноз RF. `*.joblib` можно не коммитить.

## Шаги

1. Войдите на [share.streamlit.io](https://share.streamlit.io) и подключите GitHub-репозиторий.
2. **Main file path:** `citizen-service/app/streamlit_app.py`
3. **Branch:** `main` (или ваша ветка).
4. **Python version:** 3.11 (рекомендуется).
5. **Requirements file:** `requirements.streamlit.txt` (в **корне** репозитория — подтягивает основной `requirements.txt` и пакеты карты).

## Проверка локально (как на облаке)

Из **корня** репозитория:

```bash
pip install -r requirements.streamlit.txt
streamlit run citizen-service/app/streamlit_app.py
```

## После деплоя

- При ошибке импорта убедитесь, что в Cloud выбран **`requirements.streamlit.txt`** из корня репо.
- Обновление карты: пересоберите снимок, закоммитьте новый `snapshot.json`, Cloud подтянет после push (или «Reboot app»).
