# Деплой на Streamlit Community Cloud

## Предварительно

В репозитории должен быть **`citizen-service/artifacts/snapshot.json`**. Для быстрого деплоя и CI достаточно **`build_citizen_snapshot.py --map-only`**: Streamlit показывает карту и официальные статусы без `citizen_model.joblib`. Полный прогон добавляет прогноз RF. `*.joblib` можно не коммитить.

**Токены:** в репозитории нет Streamlit-токенов и нет `secrets.toml` (см. [STREAMLIT_ACCESS.md](STREAMLIT_ACCESS.md)). Подключение к GitHub при деплое делается через OAuth в браузере на [share.streamlit.io](https://share.streamlit.io), а не через строку в коде.

## Шаги (создание приложения вручную)

Автоматически «запушить в облако» из git нельзя: нужен один раз зайти под своим GitHub-аккаунтом.

1. Откройте [share.streamlit.io](https://share.streamlit.io) → **Sign in** → GitHub.
2. **New app** → выберите репозиторий (например `sapsan14/water-quality-ee`), ветку **`main`**.
3. **Main file path:** `citizen-service/app/streamlit_app.py`
4. **Python version:** 3.11 (рекомендуется).
5. **Requirements file:** `requirements.streamlit.txt` (файл в **корне** репозитория).
6. **Deploy.** Дождитесь логов сборки; при успехе откроется вкладка с приложением.

**Advanced settings** (при необходимости): корень репо оставьте по умолчанию; рабочий каталог приложения определяется путём к `streamlit_app.py`.

## URL и документация доступа

После деплоя URL будет вида **`https://<subdomain>.streamlit.app`**. Скопируйте его в [STREAMLIT_ACCESS.md](STREAMLIT_ACCESS.md) и при желании в корневой `README.md` (блок «Гражданский сервис»).

## Проверка локально (как на облаке)

Из **корня** репозитория:

```bash
pip install -r requirements.streamlit.txt
streamlit run citizen-service/app/streamlit_app.py
```

## После деплоя

- При ошибке импорта убедитесь, что в Cloud выбран **`requirements.streamlit.txt`** из корня репо.
- Обновление карты: пересоберите снимок, закоммитьте новый `snapshot.json`, Cloud подтянет после push (или **Reboot app** в настройках).
- Файл **`citizen-service/.streamlit/config.toml`** подхватывается автоматически (тема оформления).
