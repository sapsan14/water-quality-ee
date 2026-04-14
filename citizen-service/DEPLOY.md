# Деплой на Streamlit Community Cloud

## Предварительно

В репозитории должен быть **`citizen-service/artifacts/snapshot.json`**. GitHub Actions (**Citizen snapshot**) по расписанию и вручную собирает полный снимок (данные + 4 модели + координаты) и коммитит в `main`: `snapshot.json`, **`citizen_model.joblib`**, кэши в `citizen-service/data/`. Коммиты с `[skip ci]` не запускают тесты повторно. **Streamlit Community Cloud**, если приложение привязано к репо, после такого push обновляет деплой автоматически.

Для быстрого локального снимка без обучения ML: **`build_citizen_snapshot.py --map-only`** — карта и официальные статусы; вероятности моделей в JSON при этом не пересчитываются.

**Токены:** в репозитории нет Streamlit-токенов и нет `secrets.toml` (см. [STREAMLIT_ACCESS.md](STREAMLIT_ACCESS.md)). Подключение к GitHub при деплое делается через OAuth в браузере на [share.streamlit.io](https://share.streamlit.io), а не через строку в коде.

Конфиг темы: в корне репо есть **`.streamlit/config.toml`** — Community Cloud его подхватывает (см. [документацию](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)).

## Быстрый старт (вставка URL файла)

1. [share.streamlit.io](https://share.streamlit.io) → войти через **GitHub** (первый раз — разрешить доступ к репозиториям, желательно к `water-quality-ee`).
2. **Create app** → «Yup, I have an app» → **Paste GitHub URL** и вставьте **ровно** (ветка `main`, ваш форк подставьте при необходимости):

   `https://github.com/sapsan14/water-quality-ee/blob/main/citizen-service/app/streamlit_app.py`

3. **Advanced settings** → **Python version:** 3.11 (или оставьте 3.12 по умолчанию Cloud).
4. **Requirements file:** вручную укажите **`requirements.streamlit.txt`** (лежит в **корне** репозитория, не в `citizen-service/`).
5. **Deploy.** Дождитесь логов справа; при ошибке импорта проверьте п.4.

Если поле requirements не подставилось автоматически, без него Cloud установит только Streamlit — приложение упадёт на `pandas` / `folium`.

## Шаги (если заполняете поля вручную)

Автоматически «запушить в облако» из git без браузера нельзя: один раз нужен вход на Streamlit.

1. Откройте [share.streamlit.io](https://share.streamlit.io) → **Sign in** → GitHub.
2. **New app** → репозиторий **`sapsan14/water-quality-ee`** (или ваш форк), ветка **`main`**.
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
- Обновление карты и моделей: либо запустите workflow **Citizen snapshot** в GitHub Actions (он закоммитит артефакты), либо соберите локально и закоммитьте `snapshot.json` / кэши; Cloud подтянет после push (или **Reboot app**).
- Файл **`citizen-service/.streamlit/config.toml`** подхватывается автоматически (тема оформления).
