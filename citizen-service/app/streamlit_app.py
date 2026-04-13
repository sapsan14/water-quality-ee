"""
Гражданский интерфейс: карта по точкам (купание, бассейны/СПА, водопровод, источники питьевой воды),
таблица, официальные данные vs прогноз модели.
Запуск из корня репозитория:
  pip install -r citizen-service/requirements.txt
  streamlit run citizen-service/app/streamlit_app.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "citizen-service" / "artifacts" / "snapshot.json"

DOMAIN_LABELS = {
    "supluskoha": "Открытая вода (supluskohad)",
    "basseinid": "Бассейны / СПА / ujula (basseinid)",
    "veevark": "Питьевая вода — водопровод (veevärk)",
    "joogivesi": "Питьевая вода — источник (joogiveeallikas)",
}

# Короткие ярлыки типа места (если в snapshot нет place_kinds — только ключи)
DEFAULT_PLACE_KIND_LABELS = {
    "swimming": "Купание (открытая вода)",
    "pool_spa": "Бассейн / СПА",
    "drinking_water": "Питьевая вода (водопровод)",
    "drinking_source": "Питьевая вода (источник / озеро / родник)",
    "other": "Прочее",
}

MEASUREMENT_LABELS_RU = {
    "e_coli": "E. coli, КОЕ/100 мл",
    "enterococci": "Энтерококки, КОЕ/100 мл",
    "coliforms": "Колиформы, КОЕ/100 мл",
    "ph": "pH",
    "transparency": "Прозрачность",
    "turbidity": "Мутность (NTU)",
    "color": "Цветность",
    "nitrates": "Нитраты, мг/л",
    "nitrites": "Нитриты, мг/л",
    "ammonium": "Аммоний, мг/л",
    "fluoride": "Фторид, мг/л",
    "manganese": "Марганец, мг/л",
    "iron": "Железо, мг/л",
    "chlorides": "Хлориды, мг/л",
    "sulfates": "Сульфаты, мг/л",
    "free_chlorine": "Свободный хлор",
    "combined_chlorine": "Связанный хлор",
    "pseudomonas": "Pseudomonas",
    "staphylococci": "Staphylococcus",
    "oxidizability": "Окисляемость",
    "colonies_37c": "Колонии при 37 °C",
}


def load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.is_file():
        return None
    with open(SAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def official_color(compliant: int) -> str:
    return "#22c55e" if compliant == 1 else "#ef4444"


def model_color(prob_violation: float) -> str:
    """Градиент: низкий риск → зелёный, высокий → красный."""
    p = max(0.0, min(1.0, prob_violation))
    r = int(255 * p)
    g = int(255 * (1 - p))
    return f"#{r:02x}{g:02x}40"


def _place_kind(p: dict) -> str:
    k = p.get("place_kind")
    if k:
        return str(k)
    dom = p.get("domain", "")
    if dom == "supluskoha":
        return "swimming"
    if dom == "basseinid":
        return "pool_spa"
    if dom == "veevark":
        return "drinking_water"
    if dom == "joogivesi":
        return "drinking_source"
    return "other"


def _measurements_html(m: dict) -> str:
    if not m:
        return "<i>Нет числовых параметров в этой записи снимка</i>"
    lines = []
    for key in sorted(m.keys()):
        label = MEASUREMENT_LABELS_RU.get(key, key)
        val = html.escape(str(m[key]))
        lines.append(f"<tr><td style='padding:2px 8px 2px 0'>{html.escape(label)}</td><td><b>{val}</b></td></tr>")
    return "<table style='font-size:12px;border-collapse:collapse'>" + "".join(lines) + "</table>"


def build_map(
    places: list[dict],
    color_mode: str,
    kinds_filter: set[str],
    use_cluster: bool,
) -> folium.Map:
    m = folium.Map(location=[58.65, 25.5], zoom_start=7, tiles="CartoDB positron")
    cluster = MarkerCluster(name="Места", disable_clustering_at_zoom=11) if use_cluster else None

    radius_by_kind = {
        "swimming": 9,
        "pool_spa": 8,
        "drinking_water": 6,
        "drinking_source": 7,
        "other": 7,
    }

    plotted = 0
    for p in places:
        kind = _place_kind(p)
        if kind not in kinds_filter:
            continue
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        if color_mode == "official":
            color = official_color(int(p["official_compliant"]))
            title = "Официальный статус"
        else:
            color = model_color(float(p["model_violation_prob"]))
            title = "Прогноз модели (риск нарушения)"

        dom_label = DOMAIN_LABELS.get(p["domain"], p.get("domain", "—"))
        kind_label = DEFAULT_PLACE_KIND_LABELS.get(kind, kind)
        meas = p.get("measurements") if isinstance(p.get("measurements"), dict) else {}

        popup_html = f"""
        <div style="max-width:320px;font-size:13px">
        <b>{html.escape(str(p.get("location") or "—"))}</b><br/>
        <span style="color:#444">{html.escape(kind_label)}</span><br/>
        <i style="font-size:12px">{html.escape(dom_label)}</i><br/>
        <hr style="margin:6px 0"/>
        Дата пробы: {html.escape(str(p.get("sample_date") or "—"))}<br/>
        Уезд: {html.escape(str(p.get("county") or "не указан"))}<br/>
        Официально: {"соответствует" if p.get("official_compliant") == 1 else "нарушение"}<br/>
        Вероятность нарушения (модель): {float(p.get("model_violation_prob", 0)):.2f}<br/>
        <small>Источник координат: {html.escape(str(p.get("coord_source", "?")))}</small>
        <hr style="margin:6px 0"/>
        <b>Параметры пробы (последняя)</b><br/>
        {_measurements_html(meas)}
        </div>
        """

        r = radius_by_kind.get(kind, 8)
        marker = folium.CircleMarker(
            location=[lat, lon],
            radius=r,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.88,
            popup=folium.Popup(popup_html, max_width=340),
            tooltip=f"{str(p.get('location', ''))[:42]} · {title}",
        )
        if cluster is not None:
            marker.add_to(cluster)
        else:
            marker.add_to(m)
        plotted += 1

    if cluster is not None:
        cluster.add_to(m)

    if plotted == 0:
        folium.Marker(
            [58.65, 25.5],
            popup="Нет точек для выбранных фильтров",
        ).add_to(m)

    return m


def main() -> None:
    st.set_page_config(page_title="Качество воды (гражданский вид)", layout="wide")
    snap = load_snapshot()

    st.title("Качество воды в Эстонии — точки на карте")
    st.caption(
        "Данные Terviseamet (открытый XML). Прогноз — отдельная модель машинного обучения; "
        "это не официальное заключение Terviseamet."
    )

    if snap is None:
        st.error(
            f"Нет файла снимка данных. Соберите его из корня репозитория:\n\n"
            f"`python citizen-service/scripts/build_citizen_snapshot.py`\n\n"
            f"Для точных координат добавьте: `--geocode-limit 200` (медленно, уважайте Nominatim)."
        )
        return

    st.info(snap.get("disclaimer", ""))

    places = snap.get("places", [])
    kind_labels = {**DEFAULT_PLACE_KIND_LABELS, **(snap.get("place_kinds") or {})}

    rows_for_df = []
    for p in places:
        d = dict(p)
        pk = _place_kind(d)
        d["place_kind"] = pk
        d["Тип места"] = kind_labels.get(pk, pk)
        rows_for_df.append(d)
    df = pd.json_normalize(rows_for_df, sep="_")

    tab_map, tab_table, tab_about = st.tabs(["Карта", "Таблица", "О сервисе"])

    with tab_map:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            color_mode = st.radio(
                "Раскраска точек",
                options=["official", "model"],
                format_func=lambda x: "По официальному статусу" if x == "official" else "По прогнозу модели (риск)",
                horizontal=True,
            )
        with c2:
            use_cluster = st.checkbox(
                "Кластеризация маркеров (удобно при тысячах точек водопровода)",
                value=True,
            )
        with c3:
            st.caption("Каждая точка — отдельное место; нажмите маркер для параметров пробы и статуса.")

        st.subheader("Типы объектов")
        fc1, fc2, fc3, fc4 = st.columns(4)
        kinds_filter: set[str] = set()
        with fc1:
            if st.checkbox(kind_labels.get("swimming", "Купание"), value=True):
                kinds_filter.add("swimming")
        with fc2:
            if st.checkbox(kind_labels.get("pool_spa", "Бассейн / СПА"), value=True):
                kinds_filter.add("pool_spa")
        with fc3:
            if st.checkbox(kind_labels.get("drinking_water", "Питьевая (водопровод)"), value=True):
                kinds_filter.add("drinking_water")
        with fc4:
            if st.checkbox(kind_labels.get("drinking_source", "Питьевая (источник)"), value=True):
                kinds_filter.add("drinking_source")
        if st.checkbox(kind_labels.get("other", "Прочее"), value=False):
            kinds_filter.add("other")

        if not kinds_filter:
            st.warning("Выберите хотя бы один тип объектов.")
            kinds_filter.add("swimming")

        m = build_map(places, color_mode, kinds_filter, use_cluster=use_cluster)
        st_folium(m, width=None, height=560, returned_objects=[])

        n_on_map = sum(
            1
            for p in places
            if _place_kind(p) in kinds_filter
            and p.get("lat") is not None
            and p.get("lon") is not None
        )
        st.markdown(
            f"**Точек на карте:** {n_on_map} (всего в снимке: {len(places)}). "
            f"Снимок: `{snap.get('generated_at', '?')}`."
        )
        if color_mode == "model":
            st.markdown(
                "Легенда прогноза: **зелёный** — модель считает риск нарушения низким, **красный** — высоким."
            )
        else:
            st.markdown("Легенда: **зелёный** — официально соответствует, **красный** — зафиксировано нарушение.")

    with tab_table:
        search = st.text_input("Поиск по названию места")
        view = df.copy()
        if search.strip() and "location" in view.columns:
            view = view[view["location"].astype(str).str.contains(search.strip(), case=False, na=False)]
        pref = [
            "location",
            "Тип места",
            "domain",
            "county",
            "sample_date",
            "official_compliant",
            "model_violation_prob",
            "coord_source",
        ]
        cols = [c for c in pref if c in view.columns]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        st.caption("Полные измерения смотрите во всплывающем окне маркера на карте.")

    with tab_about:
        st.markdown(
            """
### Зачем это

На карте — **отдельные точки**: купальные места, **бассейны / СПА / ujula**, **водопровод** (`veevärk`),
**источники питьевой воды** (`joogiveeallikas`, opendata). У каждой точки — дата пробы, статус, оценка модели и
**параметры** последней пробы (если были в XML).

**Минеральная вода** (`mineraalvesi`): годовых XML в каталоге opendata у Terviseamet сейчас нет (только HTML-страница
каталога) — в снимок не попадает.

### Два слоя информации

1. **Официальный статус** — как в исходных данных (`compliant` из оценки соответствия нормам).
2. **Прогноз модели** — вероятность класса «нарушение» по Random Forest на признаках учебного пайплайна.
   Это **ориентир**, а не решение инспекции.

### Координаты

Без платных API: **Nominatim** (кэш), **центроид уезда** и при отсутствии данных — **приблизительная** точка
(`approximate_ee`). Для водопровода название точки часто геокодируется грубо; накапливайте кэш с `--geocode-limit`.

### Обновление данных

Рекомендуется **GitHub Actions** по расписанию: скачать XML, выполнить `build_citizen_snapshot.py`, публиковать
`citizen-service/artifacts/snapshot.json`. Подробности — `citizen-service/PLAN.md`.
"""
        )


if __name__ == "__main__":
    main()
