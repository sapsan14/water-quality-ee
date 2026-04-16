# Источники данных — Качество воды Эстонии

**Провайдер:** Terviseamet (Департамент здоровья Эстонии)  
**Портал:** [vtiav.sm.ee](https://vtiav.sm.ee/index.php/?active_tab_id=A)  
**Формат:** XML  
**Обновление:** регулярное (данные лабораторных анализов)  
**Лицензия:** открытые государственные данные Эстонии

---

## География (maakond) и справочники в репозитории

- В opendata-XML поле **maakond** часто пустое; для признака `county` и карт используется **`src/county_infer.py`**: переопределения `data/reference/location_county_overrides.csv`, кэш `data/processed/county_geocode_cache.json`, при `geocode=True` — **OpenCage** (`OPENCAGE_API_KEY`).
- **Центроиды уездов** для fallback на карте: `citizen-service/county_centroids.py` (упрощённые координаты, не замена точного адреса).
- Официальные названия уездов (эт/англ) сверяйте с публичными справочниками Эстонии (например классификаторы на [riigiteataja.ee](https://www.riigiteataja.ee) / порталы РИК).
- В **ноутбуках 03 и 06** кодирование **`county_encoded`** строится **только по обучающей части** выборки; редкие уезды в test маппятся как `unknown`.

---

## 1. Supluskohad — Места для купания

**Описание:** Морские пляжи, озёра, реки — публичные места для купания. Мониторинг ведётся Департаментом здоровья в купальный сезон (июнь–август).

**XML endpoint:**
```
https://vtiav.sm.ee/index.php/?active_tab_id=A&lang=et&type=xml&area=supluskoha_uuringud
```

**Параметры анализа:**
- `E. coli` (КОЕ/100 мл) — кишечная палочка, основной индикатор фекального загрязнения
- `Enterokokid` (КОЕ/100 мл) — кишечные энтерококки
- `Cyanobacteria` — синезелёные водоросли (визуальная оценка + счёт клеток)
- `Läbipaistvus` — прозрачность воды (м)
- pH — кислотность (норма 6.0–9.0)

**Нормативы (EU Bathing Water Directive 2006/7/EC):**

| Параметр | Внутренние воды (отлично) | Прибрежные (отлично) |
|----------|--------------------------|----------------------|
| E. coli | ≤ 500 КОЕ/100 мл | ≤ 250 КОЕ/100 мл |
| Энтерококки | ≤ 200 КОЕ/100 мл | ≤ 100 КОЕ/100 мл |

**Почему интересно:** самый личный домен — я купаюсь именно в этих местах. Балтийское море, Пярну, Нарва-Йыэсуу, Ülemiste järv.

---

## 2. Veevärk — Водопроводная вода

**Описание:** Системы централизованного водоснабжения. Пробы из кранов, резервуаров, распределительных точек по всей Эстонии.

**XML endpoint:**
```
https://vtiav.sm.ee/index.php/?active_tab_id=A&lang=et&type=xml&area=veevargi_uuringud
```

**Параметры анализа (EU Drinking Water Directive 2020/2184):**

| Параметр | Тип | Норматив |
|----------|-----|----------|
| E. coli | микробиол. | 0 КОЕ/100 мл |
| Колиформы | микробиол. | 0 КОЕ/100 мл |
| Энтерококки | микробиол. | 0 КОЕ/100 мл |
| Нитраты (NO3) | хим. | ≤ 50 мг/л |
| Нитриты (NO2) | хим. | ≤ 0.5 мг/л |
| Аммоний (NH4) | хим. | ≤ 0.5 мг/л |
| Мутность | физ. | ≤ 4 NTU |
| pH | физ.-хим. | 6.5–9.5 |
| Цветность | физ. | ≤ 20 мг Pt/л |
| Марганец (Mn) | хим. | ≤ 0.05 мг/л |
| Железо (Fe) | хим. | ≤ 0.2 мг/л |
| Хлориды (Cl) | хим. | ≤ 250 мг/л |
| Сульфаты (SO4) | хим. | ≤ 250 мг/л |
| Фторид (F) | хим. | ≤ 1.5 мг/л |
| Жёсткость | хим. | — (информативно) |

**Почему интересно:** богатейший домен по набору параметров. Хорошая основа для multi-parameter модели.

---

## 3. Basseinid — Плавательные бассейны

**Описание:** Публичные бассейны, спа, аквапарки. Более строгий контроль, чем для открытых водоёмов.

**XML endpoint:**
```
https://vtiav.sm.ee/index.php/?active_tab_id=A&lang=et&type=xml&area=basseini_uuringud
```

**Opendata (годовые файлы, как у купален и водопровода):**
```
https://vtiav.sm.ee/index.php/opendata/basseini_veeproovid_YYYY.xml
```

Парсер в проекте: `load_domain("basseinid")` / `load_all()` (входит в объединённый датасет по умолчанию).

**Где это лежит у вас:** сырые годовые файлы — `data/raw/basseinid_YYYY.xml`. Файл `data/processed/raw_combined.csv` из ноутбука `02_eda_full.ipynb` содержит бассейны **только после** вызова `load_all()` (три домена); старый CSV на ~38k строк — без `basseinid`, его нужно пересоздать. В столбце `location` имя часто **длинное**, по объекту пробы (например `My Fitness Rävala pst 4 ujula suur bassein`, отдельно `… mullivann`) — поиск только по «My Fitness» или «Rävala» в таблице/CSV.

**Параметры анализа:**

| Параметр | Норматив |
|----------|----------|
| E. coli | 0 КОЕ/100 мл |
| Pseudomonas aeruginosa | 0 КОЕ/100 мл |
| Стафилококки | ≤ 20 КОЕ/100 мл |
| pH | 6.5–8.5 |
| Хлор свободный | 0.2–0.6 мг/л |
| Хлор связанный | ≤ 0.4 мг/л |
| Мутность | ≤ 0.5 NTU |
| Температура | ≤ 30°C (публичные) |

**Особенность:** параметры хлорирования — уникальный признак для бассейного домена.

---

## 4. Joogiveeallikad — Источники питьевой воды

**Описание:** Природные источники, колодцы, нецентрализованные системы. Мониторинг менее частый, данных меньше.

**Opendata (годовые XML, как у остальных доменов):**
```
https://vtiav.sm.ee/index.php/opendata/joogiveeallika_veeproovid_YYYY.xml
```

**Старый query-endpoint (часто отдаёт HTML, не сырые данные):**
```
https://vtiav.sm.ee/index.php/?active_tab_id=A&lang=et&type=xml&area=joogiveeallikas_uuringud
```

В проекте: `load_domain("joogivesi")` / `load_all()` (ключ домена в коде — **`joogivesi`**). Оценка `compliant` по полю протокола «Kvaliteediklass I» (1) vs «II/III» (0) и по «ei vasta» на показателях.

**Параметры:** часто как у veevärk (nitraat, pH, E. coli, …), плюс специфические поля в XML.

**Интерес:** сравнение природных источников vs централизованного водоснабжения.

---

## 5. Mineraalvesi — Минеральная и природная вода

**Описание:** Природные минеральные воды, спа-источники, термальные воды Эстонии.

**Важно:** на момент проверки (2026) **годовых файлов** вида `…_veeproovid_YYYY.xml` для минеральной воды в каталоге opendata не найдено (в отличие от supluskoha / veevärk / basseinid / joogiveeallika). Загрузчик в репозитории этот домен **не подключает** — только после появления стабильного URL opendata.

**Старый query-endpoint (часто HTML):**
```
https://vtiav.sm.ee/index.php/?active_tab_id=A&lang=et&type=xml&area=mineraalvee_uuringud
```

**Особенности:**
- Содержание минералов (Ca, Mg, Na, K, Fe, Mn, Si)
- Радиоактивность (в некоторых случаях)
- Газовый состав (CO2)
- Общая минерализация (ТДС)

**Интерес:** термальные воды — моя страсть. Хяадеместе, Пярну, Отепяэ.

---

## Структура XML-данных (общий шаблон)

Все источники используют схожую XML-структуру. Пример для supluskohad:

```xml
<uuringud>
  <uuring>
    <id>12345</id>
    <koht>Pirita rand</koht>
    <maakond>Harju maakond</maakond>
    <kuupaev>2025-07-15</kuupaev>
    <naiturid>
      <naiturid_e_coli>
        <vaartus>45</vaartus>
        <uhik>PMÜ/100ml</uhik>
        <norm>500</norm>
        <vastavus>jah</vastavus>  <!-- jah = да, ei = нет -->
      </naiturid_e_coli>
      <naiturid_enterokokid>
        <vaartus>12</vaartus>
        <uhik>PMÜ/100ml</uhik>
        <norm>200</norm>
        <vastavus>jah</vastavus>
      </naiturid_enterokokid>
    </naiturid>
  </uuring>
</uuringud>
```

**Ключевые поля:**
- `koht` / `asukoht` — место отбора пробы
- `maakond` — уезд (Harju, Tartu, Pärnu, ...)
- `kuupaev` — дата анализа
- `vaartus` — измеренное значение
- `norm` — предельное значение по нормативу
- `vastavus` — `jah` (соответствует) / `ei` (нарушение)

---

## Стратегия загрузки данных

### Приоритет доменов для первого этапа

1. **Supluskohad** — старт (компактный, понятный, личный)
2. **Veevärk** — основной (богатый набор параметров)
3. **Basseinid** — дополнительный
4. (4-5 — при необходимости расширения)

### Код загрузки

```python
import requests
from lxml import etree

BASE_URL = "https://vtiav.sm.ee/index.php/"
DOMAINS = {
    "supluskoha": "supluskoha_uuringud",
    "veevark":    "veevargi_uuringud",
    "basseinid":  "basseini_uuringud",
    "joogivesi":  "joogiveeallikas_uuringud",
    "mineraalvesi": "mineraalvee_uuringud",
}

params = {
    "active_tab_id": "A",
    "lang": "et",
    "type": "xml",
    "area": DOMAINS["supluskoha"]
}

response = requests.get(BASE_URL, params=params, timeout=30)
tree = etree.fromstring(response.content)
```

### Кэширование

Данные сохраняем в `data/raw/` как XML-файлы, чтобы не перегружать сервер:
```
data/raw/supluskoha_2025.xml
data/raw/veevark_2025.xml
data/raw/basseinid_2025.xml
```

Файлы не коммитим в git (`.gitignore`), регенерируем при необходимости.

---

## Известные ограничения данных

| Ограничение | Описание | Как справляться |
|-------------|----------|-----------------|
| Сезонность | Купальные места — только лето | Добавить признак `season` |
| Разные схемы XML | Каждый домен имеет свой формат | Отдельный парсер на домен |
| Пропущенные значения | Не все параметры измеряются в каждой пробе | Imputation / домен-специфичные модели |
| Дисбаланс классов | Нарушений меньше, чем норм | class_weight, SMOTE, порог классификации |
| Геоданные | Не всегда есть координаты | Кодировать через maakond (уезд) |
