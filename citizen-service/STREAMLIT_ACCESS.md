# Доступ к приложению (Streamlit Community Cloud)

## Проверка репозитория на токены

- В подпапках проекта **нет** Streamlit API-токенов и нет `secrets.toml` в git.
- В репозитории лежит только `citizen-service/.streamlit/config.toml` (цвета темы и `headless`) — секретов не содержит.
- Для этого приложения **не требуются** Cloud Secrets: данные карты читаются из закоммиченного `citizen-service/artifacts/snapshot.json`.

Если позже понадобятся ключи (например, для платного геокода в CI), задавайте их в **Streamlit Cloud → App settings → Secrets**, а в репозитории держите только шаблон без значений.

## URL после публикации

Streamlit Community Cloud выдаёт адрес вида:

**`https://<subdomain>.streamlit.app`**

`<subdomain>` задаётся при создании приложения или в **Settings → General → App URL** (если доступно в вашем плане).

### Текущая ссылка на задеплоенное приложение

Заполните после первого успешного деплоя (скопируйте из браузера или из дашборда [share.streamlit.io](https://share.streamlit.io)):

| | |
|--|--|
| **Публичный URL** | *вставьте сюда, например `https://water-quality-ee.streamlit.app`* |

Тот же URL имеет смысл продублировать в корневом `README.md` в блоке «Гражданский сервис».

## Кто может открыть приложение

- Если репозиторий **публичный** и приложение создано как **public app**, карту может открыть любой пользователь по ссылке.
- Ограничение доступа (private app / SSO) зависит от плана Streamlit и настроек workspace — см. [документацию Streamlit Cloud](https://docs.streamlit.io/streamlit-community-cloud).
