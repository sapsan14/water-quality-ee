# Глоссарий терминов RU / ET / EN

## Домены данных

| Русский | Эстонский | Английский |
|---------|-----------|------------|
| Место для купания | Supluskoht | Bathing place |
| Водопроводная вода | Veevärk | Water supply / tap water |
| Бассейн | Bassein | Swimming pool |
| Источник питьевой воды | Joogiveeallikas | Drinking water source |
| Минеральная вода | Mineraalvesi | Mineral water |

## Параметры качества воды

| Русский | Эстонский | Английский | Единица |
|---------|-----------|------------|---------|
| Кишечная палочка | E. coli | E. coli | КОЕ/100 мл |
| Кишечные энтерококки | Enterokokid | Intestinal enterococci | КОЕ/100 мл |
| Синезелёные водоросли | Tsüanobakterid | Cyanobacteria | кл/мл |
| Прозрачность | Läbipaistvus | Transparency/Turbidity | м |
| Мутность | Hägusus | Turbidity | NTU |
| Нитраты | Nitraadid | Nitrates | мг/л |
| Нитриты | Nitritid | Nitrites | мг/л |
| Аммоний | Ammoonium | Ammonium | мг/л |
| Фторид | Fluoriid | Fluoride | мг/л |
| Марганец | Mangaan | Manganese | мг/л |
| Железо | Raud | Iron | мг/л |
| Хлориды | Kloriidid | Chlorides | мг/л |
| Сульфаты | Sulfaadid | Sulfates | мг/л |
| Цветность | Värvus | Colour | мг Pt/л |
| Жёсткость | Karedus | Hardness | мг Ca/л |
| Кислотность | pH | pH | — |
| Свободный хлор | Vaba kloor | Free chlorine | мг/л |
| Колиформы | Kolibakterid | Coliforms | КОЕ/100 мл |

## Термины ML в контексте задачи

| Термин | Значение в контексте проекта |
|--------|------------------------------|
| `compliant` | Целевая переменная: 1 = проба в норме, 0 = нарушение |
| `vastavus` | Эстонское поле XML: jah (да/норма) / ei (нет/нарушение) |
| `class_weight='balanced'` | Коррекция дисбаланса классов в sklearn |
| False Negative | Опасная вода классифицирована как безопасная — худший исход |
| False Positive | Нормальная вода классифицирована как опасная — лишняя тревога |
| Recall (класс 0) | Доля реальных нарушений, которые модель нашла |

## Административные единицы Эстонии (maakond = уезд)

| Эстонский | Русский |
|-----------|---------|
| Harju maakond | Харьюский уезд (Таллинн) |
| Tartu maakond | Тартуский уезд |
| Pärnu maakond | Пярнуский уезд |
| Ida-Viru maakond | Ида-Вирумааский уезд (Нарва) |
| Lääne maakond | Ляэнеский уезд |
| Võru maakond | Выруский уезд |
| Saare maakond | Сааремааский уезд |
| Lääne-Viru maakond | Ляэне-Вирумааский уезд |
| Rapla maakond | Раплаский уезд |
| Järva maakond | Ярваский уезд |
| Jõgeva maakond | Йыгеваский уезд |
| Põlva maakond | Пылваский уезд |
| Valga maakond | Валгаский уезд |
| Viljandi maakond | Вильяндиский уезд |
| Hiiu maakond | Хийуский уезд |
