# Доступ к приложению (Streamlit Community Cloud)

## Автообновление приложения в облаке

После привязки приложения к ветке **`main`** Streamlit Community Cloud **сам пересобирает** приложение при каждом **push** в эту ветку (обычно в течение 1–3 минут). Отдельный деплой из браузера не нужен.

В этом репозитории GitHub Action **Citizen snapshot** по расписанию коммитит обновлённый `citizen-service/artifacts/snapshot.json` → это тоже **push в `main`** → Streamlit подхватит новый коммит. При необходимости можно вручную нажать **Reboot app** в настройках приложения на [share.streamlit.io](https://share.streamlit.io).

Программно «нажать Deploy» без браузера в бесплатном Community Cloud не предусмотрено; автоматизация = **git push** в подключённую ветку.

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
