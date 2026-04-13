"""
Гражданский интерфейс: карта по точкам (купание, бассейны/СПА, водопровод, источники питьевой воды),
таблица, официальные данные vs прогнозы 4 моделей (LR, RF, GradBoost, LightGBM).
Запуск из корня репозитория:
  pip install -r requirements.streamlit.txt
  streamlit run citizen-service/app/streamlit_app.py
Снимок: `build_citizen_snapshot.py --map-only` — карта без обучения; полный прогон добавляет
  lr_violation_prob / rf_violation_prob / gb_violation_prob / lgbm_violation_prob.
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

DEFAULT_PLACE_KIND_LABELS = {
    "swimming": "Купание (открытая вода)",
    "pool_spa": "Бассейн / СПА",
    "drinking_water": "Питьевая вода (водопровод)",
    "drinking_source": "Питьевая вода (источник / озеро / родник)",
    "other": "Прочее",
}

KIND_OUTLINE = {
    "swimming": "#0369a1",
    "pool_spa": "#7c3aed",
    "drinking_water": "#b45309",
    "drinking_source": "#047857",
    "other": "#64748b",
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

MODEL_KEYS = ["lr", "rf", "gb", "lgbm"]
MODEL_PROB_COLS = {k: f"{k}_violation_prob" for k in MODEL_KEYS}
MODEL_LABELS_DEFAULT = {
    "lr": "Logistic Regression",
    "rf": "Random Forest",
    "gb": "Gradient Boosting",
    "lgbm": "LightGBM",
}
MODEL_COLORS = {
    "lr": "#6366f1",
    "rf": "#0369a1",
    "gb": "#b45309",
    "lgbm": "#15803d",
}


@st.cache_data(show_spinner=False)
def load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.is_file():
        return None
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _available_models(snap: dict) -> list[str]:
    """Список моделей, которые реально присутствуют в снимке."""
    declared = snap.get("available_models") or []
    if declared:
        return [m for m in MODEL_KEYS if m in declared]
    places = snap.get("places") or []
    if not places:
        return []
    found = []
    for m in MODEL_KEYS:
        col = MODEL_PROB_COLS[m]
        if any(isinstance(p.get(col), (int, float)) for p in places):
            found.append(m)
    return found


def snapshot_has_model_predictions(snap: dict) -> bool:
    hmp = snap.get("has_model_predictions")
    if hmp is True:
        return True
    if hmp is False:
        return False
    return bool(_available_models(snap))


def official_color(compliant: int) -> str:
    return "#22c55e" if compliant == 1 else "#ef4444"


def model_color(prob_violation: float) -> str:
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
        lines.append(
            f"<tr><td style='padding:2px 8px 2px 0'>{html.escape(label)}</td>"
            f"<td><b>{val}</b></td></tr>"
        )
    return "<table style='font-size:12px;border-collapse:collapse'>" + "".join(lines) + "</table>"


def _matched_addr_html(p: dict) -> str:
    m = p.get("geocode_matched_address")
    if not m:
        return ""
    return f"<small>Найденный адрес (геокодер): {html.escape(str(m))}</small><br/>"


def _model_comparison_html(p: dict, available_models: list[str], model_labels: dict[str, str]) -> str:
    """HTML-таблица с прогнозами всех моделей для popup."""
    if not available_models:
        return "<i>Прогнозы моделей недоступны (снимок собран с --map-only)</i>"
    rows = []
    for m in available_models:
        col = MODEL_PROB_COLS[m]
        prob = p.get(col)
        label = model_labels.get(m, m)
        color = MODEL_COLORS.get(m, "#64748b")
        if isinstance(prob, (int, float)):
            bar_w = int(float(prob) * 80)
            risk = "высокий" if float(prob) > 0.5 else "низкий"
            risk_color = "#ef4444" if float(prob) > 0.5 else "#22c55e"
            rows.append(
                f"<tr>"
                f"<td style='padding:2px 6px 2px 0;font-size:11px;color:{color}'><b>{html.escape(label)}</b></td>"
                f"<td style='padding:2px 4px;font-size:11px'>{float(prob):.2f}</td>"
                f"<td style='padding:2px 4px'>"
                f"<div style='width:{bar_w}px;height:8px;background:{color};border-radius:3px;display:inline-block'></div>"
                f"</td>"
                f"<td style='padding:2px 4px;font-size:11px;color:{risk_color}'>{risk}</td>"
                f"</tr>"
            )
        else:
            rows.append(
                f"<tr><td style='color:{color};font-size:11px'><b>{html.escape(label)}</b></td>"
                f"<td colspan='3'><i style='font-size:11px'>нет данных</i></td></tr>"
            )
    if not rows:
        return "<i>Нет данных моделей</i>"
    header = (
        "<tr><th style='text-align:left;font-size:11px;padding:0 6px 4px 0'>Модель</th>"
        "<th style='font-size:11px;padding:0 4px 4px'>P(нарушение)</th>"
        "<th></th><th style='font-size:11px'>Риск</th></tr>"
    )
    return (
        "<b style='font-size:12px'>Прогнозы моделей (риск нарушения):</b><br/>"
        "<table style='border-collapse:collapse;margin-top:4px'>"
        + header
        + "".join(rows)
        + "</table>"
        + "<small style='color:#666'>Не официальная оценка Terviseamet.</small>"
    )


def _filtered_places(
    places: list[dict],
    kinds_filter: set[str],
    counties_filter: set[str] | None,
) -> list[dict]:
    out = []
    for p in places:
        if _place_kind(p) not in kinds_filter:
            continue
        c = p.get("county")
        key = (str(c).strip() if c else "") or "__none__"
        if counties_filter is not None and key not in counties_filter:
            continue
        out.append(p)
    return out


def build_map(
    places: list[dict],
    color_mode: str,
    kinds_filter: set[str],
    use_cluster: bool,
    counties_filter: set[str] | None = None,
    *,
    has_model_predictions: bool = True,
    available_models: list[str] | None = None,
    model_labels: dict[str, str] | None = None,
    selected_model: str = "rf",
    data_catalog_url: str | None = None,
) -> folium.Map:
    available_models = available_models or []
    model_labels = model_labels or MODEL_LABELS_DEFAULT

    m = folium.Map(location=[58.65, 25.5], zoom_start=7, tiles=None)
    folium.TileLayer("CartoDB Positron", name="Карта (светлая)", control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(m)

    cluster = MarkerCluster(name="Места", disable_clustering_at_zoom=11) if use_cluster else None

    radius_by_kind = {
        "swimming": 9,
        "pool_spa": 8,
        "drinking_water": 6,
        "drinking_source": 7,
        "other": 7,
    }

    catalog_href = html.escape(data_catalog_url or "https://vtiav.sm.ee/index.php/opendata/", quote=True)

    plotted = 0
    for p in _filtered_places(places, kinds_filter, counties_filter):
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        kind = _place_kind(p)
        border = KIND_OUTLINE.get(kind, "#64748b")

        if color_mode == "official" or not has_model_predictions:
            fill = official_color(int(p["official_compliant"]))
            color_title = "Официальный статус"
        else:
            prob_col = MODEL_PROB_COLS.get(selected_model, "model_violation_prob")
            prob = p.get(prob_col)
            if prob is None:
                prob = p.get("model_violation_prob")
            fill = model_color(float(prob) if isinstance(prob, (int, float)) else 0.0)
            color_title = f"Прогноз: {model_labels.get(selected_model, selected_model)}"

        dom_label = DOMAIN_LABELS.get(p["domain"], p.get("domain", "—"))
        kind_label = DEFAULT_PLACE_KIND_LABELS.get(kind, kind)
        meas = p.get("measurements") if isinstance(p.get("measurements"), dict) else {}
        sid = p.get("sample_id")
        sid_line = f"ID пробы: {html.escape(str(sid))}<br/>" if sid else ""

        models_html = _model_comparison_html(p, available_models, model_labels)

        popup_html = f"""
        <div style="max-width:340px;font-size:13px">
        <b>{html.escape(str(p.get("location") or "—"))}</b><br/>
        <span style="color:#444">{html.escape(kind_label)}</span><br/>
        <i style="font-size:12px">{html.escape(dom_label)}</i><br/>
        <hr style="margin:6px 0"/>
        {sid_line}
        Дата пробы: {html.escape(str(p.get("sample_date") or "—"))}<br/>
        Уезд: {html.escape(str(p.get("county") or "не указан"))}<br/>
        Официально: {"соответствует" if p.get("official_compliant") == 1 else "<b style='color:#ef4444'>нарушение</b>"}<br/>
        <small>Источник координат: {html.escape(str(p.get("coord_source", "?")))}</small><br/>
        {_matched_addr_html(p)}
        <small><a href="{catalog_href}" target="_blank" rel="noopener">Каталог opendata Terviseamet</a></small>
        <hr style="margin:6px 0"/>
        {models_html}
        <hr style="margin:6px 0"/>
        <b>Параметры пробы (последняя)</b><br/>
        {_measurements_html(meas)}
        </div>
        """

        r = radius_by_kind.get(kind, 8)
        marker = folium.CircleMarker(
            location=[lat, lon],
            radius=r,
            color=border,
            weight=3,
            fill=True,
            fill_color=fill,
            fill_opacity=0.88,
            popup=folium.Popup(popup_html, max_width=360),
            tooltip=f"{str(p.get('location', ''))[:42]} · {color_title}",
        )
        if cluster is not None:
            marker.add_to(cluster)
        else:
            marker.add_to(m)
        plotted += 1

    if cluster is not None:
        cluster.add_to(m)

    if plotted == 0:
        folium.Marker([58.65, 25.5], popup="Нет точек для выбранных фильтров").add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def _render_model_comparison_tab(places: list[dict], available_models: list[str], model_labels: dict) -> None:
    """Таб со сравнением прогнозов всех моделей в виде таблицы."""
    if not available_models:
        st.warning("Прогнозы моделей отсутствуют в снимке. Пересоберите без флага `--map-only`.")
        return

    rows = []
    for p in places:
        row: dict = {
            "location": p.get("location", ""),
            "domain": p.get("domain", ""),
            "county": p.get("county", ""),
            "sample_date": p.get("sample_date", ""),
            "official_compliant": p.get("official_compliant"),
        }
        for m in available_models:
            col = MODEL_PROB_COLS[m]
            prob = p.get(col)
            row[f"{model_labels.get(m, m)} P(нарушение)"] = (
                round(float(prob), 3) if isinstance(prob, (int, float)) else None
            )
        # Согласие/несогласие моделей
        probs = [p.get(MODEL_PROB_COLS[m]) for m in available_models if isinstance(p.get(MODEL_PROB_COLS[m]), (int, float))]
        if len(probs) >= 2:
            preds = [1 if pr > 0.5 else 0 for pr in probs]
            row["Согласие моделей"] = "да" if len(set(preds)) == 1 else "расхождение"
        rows.append(row)

    df = pd.DataFrame(rows)

    st.subheader("Сравнение прогнозов всех моделей")
    search = st.text_input("Поиск по названию места", key="compare_search")
    if search.strip():
        df = df[df["location"].astype(str).str.contains(search.strip(), case=False, na=False)]

    disagreement_only = st.checkbox("Показать только точки с расхождением моделей", value=False)
    if disagreement_only and "Согласие моделей" in df.columns:
        df = df[df["Согласие моделей"] == "расхождение"]

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        f"Прогнозы по {len(available_models)} моделям: "
        + ", ".join(model_labels.get(m, m) for m in available_models)
        + ". Значение — вероятность нарушения (0 = безопасно, 1 = нарушение)."
    )


def main() -> None:
    st.set_page_config(page_title="Качество воды (гражданский вид)", layout="wide")
    snap = load_snapshot()

    st.title("Качество воды в Эстонии — точки на карте")

    if snap is None:
        st.error(
            "Нет файла снимка данных. Соберите его из корня репозитория:\n\n"
            "`python citizen-service/scripts/build_citizen_snapshot.py --map-only` — только карта (быстро).\n\n"
            "`python citizen-service/scripts/build_citizen_snapshot.py` — полный снимок + 4 модели (LR, RF, GB, LightGBM)."
        )
        return

    has_model = snapshot_has_model_predictions(snap)
    avail_models = _available_models(snap) if has_model else []
    model_labels: dict[str, str] = {**MODEL_LABELS_DEFAULT, **(snap.get("model_labels") or {})}

    if has_model:
        models_str = ", ".join(model_labels.get(m, m) for m in avail_models)
        st.caption(
            f"Данные Terviseamet (открытый XML). Прогнозы — отдельные ML-модели ({models_str}); "
            "это не официальное заключение Terviseamet."
        )
    else:
        st.caption(
            "Данные Terviseamet (открытый XML). Карта и официальные статусы; "
            "прогнозы моделей появятся после полной сборки снимка (без флага --map-only)."
        )

    st.info(snap.get("disclaimer", ""))

    places = snap.get("places", [])
    n_places = len(places)
    n_approx = sum(1 for p in places if p.get("coord_source") == "approximate_ee")
    if n_places and n_approx / n_places >= 0.2:
        st.warning(
            f"У **{n_approx}** из **{n_places}** точек координаты **приблизительные** "
            f"(`coord_source: approximate_ee`). Пересоберите с `--infer-county` и/или `--geocode-limit …`."
        )

    kind_labels = {**DEFAULT_PLACE_KIND_LABELS, **(snap.get("place_kinds") or {})}

    rows_for_df = []
    for p in places:
        d = dict(p)
        pk = _place_kind(d)
        d["place_kind"] = pk
        d["Тип места"] = kind_labels.get(pk, pk)
        rows_for_df.append(d)
    df_full = pd.json_normalize(rows_for_df, sep="_")

    tabs_list = ["Карта", "Таблица", "Сравнение моделей", "О сервисе"]
    tab_map, tab_table, tab_compare, tab_about = st.tabs(tabs_list)

    with tab_map:
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            if has_model and avail_models:
                color_options = ["official"] + avail_models
                color_format = {
                    "official": "Официальный статус",
                    **{m: f"Прогноз: {model_labels.get(m, m)}" for m in avail_models},
                }
                color_mode = st.radio(
                    "Раскраска точек",
                    options=color_options,
                    format_func=lambda x: color_format.get(x, x),
                    horizontal=True,
                )
            else:
                color_mode = "official"
                st.markdown("**Раскраска:** только по официальному статусу.")
        with c2:
            use_cluster = st.checkbox("Кластеризация маркеров", value=True)
        with c3:
            st.caption("Нажмите маркер для параметров пробы и прогнозов всех моделей.")

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

        selected_model = color_mode if color_mode != "official" else "rf"

        m_map = build_map(
            places,
            color_mode,
            kinds_filter,
            use_cluster=use_cluster,
            has_model_predictions=has_model,
            available_models=avail_models,
            model_labels=model_labels,
            selected_model=selected_model,
            data_catalog_url=snap.get("data_catalog_url"),
        )
        st_folium(m_map, width=None, height=560, returned_objects=[])

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
        if color_mode != "official" and has_model:
            st.markdown(
                f"Легенда прогноза **{model_labels.get(selected_model, selected_model)}**: "
                "**зелёный** — риск нарушения низкий, **красный** — высокий."
            )
        else:
            st.markdown("Легенда: **зелёный** — официально соответствует, **красный** — зафиксировано нарушение.")

    with tab_table:
        search = st.text_input("Поиск по названию места", key="table_search")
        view = df_full.copy()
        if search.strip() and "location" in view.columns:
            view = view[view["location"].astype(str).str.contains(search.strip(), case=False, na=False)]
        pref = [
            "location",
            "Тип места",
            "domain",
            "county",
            "sample_date",
            "official_compliant",
            "lr_violation_prob",
            "rf_violation_prob",
            "gb_violation_prob",
            "lgbm_violation_prob",
            "coord_source",
        ]
        if not has_model:
            pref = [c for c in pref if "violation_prob" not in c]
        cols = [c for c in pref if c in view.columns]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        st.caption("Полные измерения и сравнение моделей — во всплывающем окне маркера на карте.")

    with tab_compare:
        _render_model_comparison_tab(places, avail_models, model_labels)

    with tab_about:
        st.markdown(
            """
### Зачем это

На карте — **отдельные точки**: купальные места, **бассейны / СПА**, **водопровод** (`veevärk`),
**источники питьевой воды** (`joogiveeallikas`). У каждой точки — дата пробы, статус,
прогнозы **четырёх моделей** и **параметры** последней пробы.

**Минеральная вода** (`mineraalvesi`): годовых XML в opendata Terviseamet нет — в снимок не попадает.

### Четыре модели

| Модель | Описание |
|--------|----------|
| **Logistic Regression** | Линейный базовый классификатор. Интерпретируемый, быстрый. |
| **Random Forest** | Ансамбль деревьев. Устойчивый к выбросам и пропускам. |
| **Gradient Boosting** | Последовательный бустинг. Обычно точнее на несбалансированных данных. |
| **LightGBM** | Градиентный бустинг Microsoft. Быстрее, нативная обработка NaN. |

Все модели обучены на **одних данных** (все годы). Значение `P(нарушение)` — вероятность класса "нарушение" (0 = безопасно, 1 = точно нарушение). Порог по умолчанию: 0.5.

Расхождение между моделями — признак **пограничного случая**: одни параметры сигнализируют о нарушении, другие — нет.

### Координаты

Без платных API: **Nominatim** (кэш), **центроид уезда** и **приблизительная точка**
(`approximate_ee`). Водопроводные точки часто геокодируются грубо.

### Обновление данных

GitHub Actions по расписанию: `citizen-snapshot.yml` (еженедельно по понедельникам 05:00 UTC).
"""
        )


if __name__ == "__main__":
    main()
