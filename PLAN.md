# План проекта — Качество воды в Эстонии

**8 этапов от идеи до финальной презентации**

---

## Этап 0 — Подготовка окружения

**Цель:** всё работает локально, данные доступны.

### Задачи:
- [ ] `pip install -r requirements.txt` (или `conda env create`)
- [ ] Проверить доступность XML-эндпоинтов (запустить `src/data_loader.py`)
- [ ] Скачать и сохранить XML в `data/raw/`
- [ ] Убедиться, что Jupyter открывает ноутбуки

### Файлы:
- `requirements.txt`
- `src/data_loader.py`

### Выход:
- `data/raw/supluskoha_YYYY.xml` — скачан и проверен
- `data/raw/veevark_YYYY.xml` — скачан и проверен

---

## Этап 1 — Постановка задачи

**Цель:** чёткое описание задачи, которое можно защитить перед преподавателем.

### Вопросы для ответа:
1. Что предсказываем? (`vastavus`: jah/ei → 1/0)
2. Почему это важно? (здоровье, плавание, публичные данные)
3. Какой baseline? (наивный классификатор — всегда "норма")
4. Что значит ошибка типа I и II в контексте задачи?
   - False Positive: сказали "опасно", а вода нормальная → лишняя тревога
   - **False Negative: сказали "нормально", а вода опасная → купаешься в E. coli 🦠**

### Выход:
- Раздел "Постановка задачи" в финальном отчёте
- Метрика приоритизации: **Recall** (класс 0 = нарушение)

---

## Этап 2 — Загрузка и парсинг данных

**Цель:** сырые XML → чистый pandas DataFrame.

### Шаги:
1. Скачать XML по всем нужным доменам
2. Распарсить XML: каждая строка = одна проба воды
3. Нормализовать названия полей (эстонский → понятное английское/русское)
4. Создать столбец `domain` (supluskoha / veevark / bassein)
5. Сохранить в `data/processed/raw_combined.csv`

### Ожидаемые столбцы:

```python
[
  'sample_id',      # уникальный ID пробы
  'location',       # название места
  'county',         # maakond (уезд)
  'sample_date',    # дата
  'domain',         # откуда данные
  # параметры качества (зависят от домена):
  'e_coli',
  'enterococci',
  'nitrates',
  'ph',
  'turbidity',
  # ... другие
  'compliant'       # ЦЕЛЕВАЯ ПЕРЕМЕННАЯ: 1/0
]
```

### Файлы:
- `src/data_loader.py` — основной загрузчик
- `notebooks/01_eda_supluskoha.ipynb` — первое знакомство с данными

---

## Этап 3 — Разведочный анализ (EDA)

**Цель:** понять данные изнутри. Не строить модели — смотреть, думать, задавать вопросы.

### Что исследовать:

**Базовая статистика:**
- Размер датасета (сколько проб, сколько нарушений)
- Распределение по доменам и годам
- Баланс классов: `compliant.value_counts()`

**Параметры:**
- Гистограммы для каждого числового параметра
- Box plots: норма vs нарушение для каждого параметра
- Correlation matrix (heatmap)

**Географический срез:**
- Нарушения по уездам (bar chart)
- Временная динамика: стало лучше или хуже?

**Интересные вопросы:**
- Какие места/уезды нарушают нормы чаще всего?
- Сезонность: лето хуже/лучше зимы?
- Какой параметр чаще всего нарушает норму?

### Выход:
- `notebooks/02_eda_full.ipynb` с визуализациями
- Список инсайтов для финального отчёта

---

## Этап 4 — Предобработка данных

**Цель:** датасет, пригодный для обучения модели.

### Шаги:

#### 4.1 Работа с пропущенными значениями
```python
# Стратегия 1: медианная замена (числовые параметры)
from sklearn.impute import SimpleImputer
imputer = SimpleImputer(strategy='median')

# Стратегия 2: отдельная колонка-индикатор пропуска
df['e_coli_missing'] = df['e_coli'].isna().astype(int)
```

#### 4.2 Кодирование категориальных признаков
```python
# Уезд → числовой код или One-Hot
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
le = LabelEncoder()
df['county_encoded'] = le.fit_transform(df['county'])
```

#### 4.3 Инженерия признаков
```python
# Временные признаки
df['month'] = pd.to_datetime(df['sample_date']).dt.month
df['season'] = df['month'].map({
    12: 'winter', 1: 'winter', 2: 'winter',
    3: 'spring', 4: 'spring', 5: 'spring',
    6: 'summer', 7: 'summer', 8: 'summer',
    9: 'autumn', 10: 'autumn', 11: 'autumn'
})

# Отношение к норме
df['e_coli_ratio'] = df['e_coli'] / 500  # 500 = норматив для внутренних вод
```

#### 4.4 Разделение данных
```python
from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
```

#### 4.5 Масштабирование
```python
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)  # только transform, не fit!
```

### Файлы:
- `notebooks/03_preprocessing.ipynb`
- `src/features.py` — повторно используемые функции предобработки

---

## Этап 5 — Обучение моделей

**Цель:** обучить минимум 2 модели, сравнить результаты.

### Модель 1: Logistic Regression (baseline)

```python
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

lr_pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('model', LogisticRegression(
        class_weight='balanced',  # важно при дисбалансе
        max_iter=1000,
        random_state=42
    ))
])

lr_pipeline.fit(X_train, y_train)
```

**Зачем:** простая, интерпретируемая, быстрая. Хороший baseline.

### Модель 2: Random Forest (основная)

```python
from sklearn.ensemble import RandomForestClassifier

rf_pipeline = Pipeline([
    ('model', RandomForestClassifier(
        n_estimators=100,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    ))
])

rf_pipeline.fit(X_train, y_train)
```

**Зачем:** не требует масштабирования, даёт feature importance, устойчив к пропускам.

### Подбор гиперпараметров

```python
from sklearn.model_selection import GridSearchCV

param_grid = {
    'model__n_estimators': [50, 100, 200],
    'model__max_depth': [None, 5, 10],
    'model__min_samples_leaf': [1, 5, 10]
}

grid_search = GridSearchCV(
    rf_pipeline,
    param_grid,
    cv=5,
    scoring='f1',
    n_jobs=-1
)
grid_search.fit(X_train, y_train)
```

### Файлы:
- `notebooks/04_models.ipynb`

---

## Этап 6 — Оценка и интерпретация

**Цель:** понять не только "насколько хорошо", но и "почему именно так".

### Метрики

```python
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve
)

y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

print(classification_report(y_test, y_pred, target_names=['Нарушение', 'Норма']))
print(f"ROC-AUC: {roc_auc_score(y_test, y_prob):.3f}")
```

### Confusion Matrix с интерпретацией

```
Predicted:    Нарушение    Норма
Actual:
Нарушение        TN          FP    ← FP = лишняя тревога
Норма            FN          TP    ← FN = купаешься в E. coli 🦠
```

### Feature Importance (Random Forest)

```python
importances = pd.Series(
    rf_pipeline['model'].feature_importances_,
    index=feature_names
).sort_values(ascending=False)

importances.head(10).plot(kind='barh', title='Топ-10 признаков')
```

### Файлы:
- `notebooks/05_evaluation.ipynb`
- `src/evaluate.py`

---

## Этап 7 — Финальный отчёт и презентация

**Цель:** упаковать работу так, чтобы её понял и преподаватель, и чиновник Terviseamet.

### Структура отчёта:

1. **Введение** — зачем это нужно, личная мотивация
2. **Данные** — источник, объём, описание параметров
3. **EDA** — ключевые инсайты + 3-5 графиков
4. **Методология** — preprocessing + модели
5. **Результаты** — таблица метрик, confusion matrix, ROC-кривая
6. **Интерпретация** — feature importance, какие параметры важнее всего
7. **Ограничения** — что не учли, где модель ошибается
8. **Выводы и следующие шаги**

### Презентация для курса:
- 10-15 слайдов
- Акцент на инсайты, не на технику
- "Какой параметр чаще всего нарушает норму в Харьюмаа?"

### Дополнительно (если будет сайт):
- Интерактивная карта нарушений
- Поиск по месту купания
- "Безопасно ли сегодня на Пирита?"

---

## Чеклист по этапам

| Этап | Статус | Ноутбук/файл |
|------|--------|--------------|
| 0. Окружение | [x] | `requirements.txt` — зависимости установлены, `pip install -e .` работает |
| 1. Постановка задачи | [x] | `PLAN.md`, `CLAUDE.md` — задача описана, метрика: Recall класса 0 |
| 2. Загрузка данных | [x] | `src/data_loader.py` — opendata XML скачивается и парсится, 38 594 проб |
| 3. EDA | [x] | `01_eda_supluskoha.ipynb`, `02_eda_full.ipynb` — выполнены с выводами |
| 4. Препроцессинг | [x] | `03_preprocessing.ipynb`, `src/features.py` — 53 признака, `ml_ready.joblib` |
| 5. Модели | [x] | `04_models.ipynb` — LR, RF, GradientBoosting, GridSearchCV RF |
| 6. Оценка | [x] | `05_evaluation.ipynb`, `src/evaluate.py` — матрица, ROC, feature importance |
| 7. Отчёт | [ ] | `docs/report.md` — **следующий шаг** |

### Ключевые результаты (данные: 38 594 проб, 2021–2026)

| Модель | Recall (нарушение) | ROC-AUC |
|--------|--------------------|---------|
| Logistic Regression | 0.81 | 0.924 |
| Random Forest | 0.91 | 0.985 |
| Gradient Boosting | ~0.89 | ~0.975 |

### Известные ограничения данных

- **county (maakond)** отсутствует в opendata XML — нет географического разреза
- **enterococci** и **transparency** есть только в supluskoha (4 031 проб)
- **nitrates/nitrites/ammonium/fluoride** заполнены лишь в ~5–13% случаев veevark

---

## Дедлайны (TalTech Masinõpe весна 2026)

- Промежуточный отчёт (EDA + описание данных): уточнить в Moodle
- Финальная сдача: уточнить в Moodle
- Презентация: уточнить в Moodle

*Пометка: добавить конкретные даты из Moodle, когда появятся.*
