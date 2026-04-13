# Качество воды в Эстонии — ML-проект курса Masinõpe

<div align="center">

[![Tests](https://img.shields.io/github/actions/workflow/status/sapsan14/water-quality-ee/tests.yml?branch=main&style=for-the-badge&logo=githubactions&logoColor=white&label=tests)](https://github.com/sapsan14/water-quality-ee/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Colab](https://img.shields.io/badge/Open_in_Colab-F9AB00?style=for-the-badge&logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/sapsan14/water-quality-ee/blob/main/notebooks/colab_quickstart.ipynb)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![Jupyter](https://img.shields.io/badge/Jupyter-F37626?style=for-the-badge&logo=jupyter&logoColor=white)](https://jupyter.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)

[![Data source](https://img.shields.io/badge/Data-Terviseamet-0063AF?style=for-the-badge)](https://vtiav.sm.ee/index.php/?active_tab_id=A)
[![Estonia](https://img.shields.io/badge/Estonia-opendata-0072CE?style=for-the-badge)](https://en.wikipedia.org/wiki/Estonia)

</div>

**Автор:** Anton Sokolov  
**Курс:** Masinõpe (TalTech, весна 2026)  
**Дата старта:** 2026-04-13  
**Язык обучения:** русский → эстонский (переход в процессе курса)

---

## Идея проекта

Эстония — страна у моря, с тысячами озёр, реками, минеральнымм источниками, публичными местами для купания, СПА и бассейнами. Государство собирает данные о качестве воды — и публикует их в открытом доступе. Задача: научить модель отличать безопасную воду от опасной, основываясь на химических и биологических показателях.

Личная мотивация: я люблю купаться в море, озёрах, термальных бассейнах. Если ML может предсказать, безопасно ли место — это полезно напрямую, не абстрактно.

---

## Задача машинного обучения

**Тип:** Бинарная классификация  
**Вопрос:** По химическим и биологическим показателям пробы воды — соответствует ли она нормативам?  
**Целевая переменная:** `compliant` (1 = норма, 0 = нарушение)

| Класс | Значение |
|-------|----------|
| 1 | Проба соответствует всем нормативам |
| 0 | Хотя бы один показатель превышает норму |

---

## Данные

**Источник:** Terviseamet (Департамент здоровья Эстонии) — [vtiav.sm.ee](https://vtiav.sm.ee/index.php/?active_tab_id=A)

Пять доменов данных (все в XML формате):

| Домен | Описание | Файл |
|-------|----------|------|
| Supluskohad | Места для купания (море, озёра) | `supluskoha_uuringud.xml` |
| Veevärk | Водопроводная вода | `veevargi_uuringud.xml` |
| Basseinid | Плавательные бассейны | `basseini_uuringud.xml` |
| Joogiveeallikad | Источники питьевой воды | `joogiveeallikas_uuringud.xml` |
| Mineraalvesi | Минеральная/природная вода | `mineraalvee_uuringud.xml` |

**Полная документация источников:** [DATA_SOURCES.md](DATA_SOURCES.md)

---

## Google Colab

Полный сценарий для облака — ноутбук **[notebooks/colab_quickstart.ipynb](notebooks/colab_quickstart.ipynb)**:

1. Загрузите репозиторий на **GitHub** (или используйте zip: *File → Upload* в Colab).
2. В `colab_quickstart.ipynb` укажите свой `REPO_URL` и выполните ячейки: клонирование в `/content/water-quality-ee`, `pip install -r requirements.txt`, `pip install -e .`, проверка `load_domain`.
3. Остальные ноутбуки **01→06** открывайте из файлового браузера Colab; в начале сессии в них выполните `%cd /content/water-quality-ee` (если kernel стартовал в другой папке). Для `06_advanced_models.ipynb` дополнительно: `pip install lightgbm shap`.

**GPU:** модели в `04_models.ipynb` — *scikit-learn*; они **не используют GPU**. Colab с T4 не ускорит LR/Random Forest. GPU имело бы смысл при отдельных GPU-библиотеках (XGBoost-GPU, PyTorch и т.д.).

После публикации на GitHub можно добавить в свой форк кнопку «Open in Colab» (замените `YOUR_USER`):

`https://colab.research.google.com/github/YOUR_USER/water-quality-ee/blob/main/notebooks/colab_quickstart.ipynb`

---

## Структура проекта

```
water-quality-ee/
├── README.md              # этот файл
├── DATA_SOURCES.md        # полный каталог источников данных
├── PLAN.md                # пошаговый план (8 этапов)
│
├── notebooks/
│   ├── colab_quickstart.ipynb    # старт в Google Colab (клон + pip + проверка)
│   ├── 00_polnoye_rukovodstvo.ipynb  # сквозное руководство (опционально)
│   ├── 01_eda_supluskoha.ipynb    # разведочный анализ: места купания
│   ├── 02_eda_full.ipynb          # EDA: load_all() (+ joogivesi / joogiveeallikas)
│   ├── 03_preprocessing.ipynb     # предобработка, feature engineering
│   ├── 04_models.ipynb            # обучение моделей
│   ├── 05_evaluation.ipynb        # оценка, интерпретация, итог
│   └── 06_advanced_models.ipynb   # LightGBM, темпоральный split, калибровка, SHAP
│
├── scripts/
│   └── warm_county_geocode_cache.py  # долгий прогон кэша уездов (Nominatim)
│
├── src/
│   ├── data_loader.py    # загрузка и парсинг XML
│   ├── county_infer.py   # инференс уезда (XML → overrides → кэш → опц. геокодер)
│   ├── features.py       # извлечение признаков
│   └── evaluate.py       # метрики и визуализация
│
├── data/
│   ├── raw/              # скачанные XML файлы (не в git)
│   ├── processed/        # joblib/кэши (не в git)
│   └── reference/        # справочники (напр. location → county)
│
└── docs/
    ├── normy.md          # нормативы по каждому параметру
    └── glosarij.md       # словарь терминов RU/ET/EN
```

---

## Технический стек

- **Python 3.11+**
- **pandas** — работа с данными
- **scikit-learn** — модели и пайплайны
- **matplotlib / seaborn** — визуализация
- **lxml / xml.etree** — парсинг XML
- **geopy** (опционально) — геокодирование для заполнения `county`, если включить `geocode_county=True`
- **lightgbm / shap** (опционально) — ноутбук `06_advanced_models.ipynb`
- **Jupyter Notebook** — интерактивный анализ

---

## Модели

1. **Logistic Regression** — baseline, интерпретируемость
2. **Random Forest** — основная модель, feature importance
3. **Gradient Boosting** (sklearn) — в `04_models.ipynb`
4. **LightGBM** + калибровка + SHAP — в `06_advanced_models.ipynb`

---

## Метрики оценки

Данные могут быть несбалансированными (опасных проб меньше, чем безопасных):

| Метрика | Причина выбора |
|---------|----------------|
| F1-score | Баланс precision/recall при дисбалансе |
| ROC-AUC | Общая разделяющая способность |
| Precision / Recall | Отдельно для интерпретации |
| Confusion Matrix | Наглядность ошибок |

**Приоритет:** минимизировать False Negatives (опасная вода, которую модель пропустила).

---

## Требования курса (TalTech Masinõpe)

Проект покрывает все необходимые компоненты:

- [x] Описание задачи и обоснование выбора данных
- [x] EDA с визуализацией
- [x] Предобработка данных
- [x] Обучение минимум 2 моделей
- [x] Сравнение метрик
- [x] Интерпретация результатов
- [x] Финальный отчёт / презентация

---

## Гражданский сервис (карта + прогноз)

Отдельная папка **[citizen-service/](citizen-service/)**: Streamlit-приложение с картой точек (открытые места купания и бассейны/СПА), официальным статусом и слоем прогноза модели. Сбор снимка данных и план деплоя (GitHub Actions + Streamlit Cloud) описаны в `citizen-service/README.md` и `citizen-service/PLAN.md`.

---

## Связи

- Дневник: [2026-04-13](../../life/2026-04-13.md)
- Курс: TalTech Masinõpe 2026
