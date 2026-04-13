"""
Гражданский интерфейс: карта по точкам (купание, бассейны/СПА, водопровод, источники питьевой воды),
таблица, официальные данные vs прогноз модели.
Запуск из корня репозитория:
  pip install -r requirements.streamlit.txt
  streamlit run citizen-service/app/streamlit_app.py
Снимок: `build_citizen_snapshot.py --map-only` — карта без обучения RF; полный прогон добавляет model_violation_prob.
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

# Обводка маркера по типу места (заливка — по официальному статусу или модели)
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


@st.cache_data(show_spinner=False)
def load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.is_file():
        return None
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def snapshot_has_model_predictions(snap: dict) -> bool:
    """True, если в снимке есть прогноз модели по точкам (полный прогон build_citizen_snapshot)."""
    hmp = snap.get("has_model_predictions")
    if hmp is True:
        return True
    if hmp is False:
        return False
    places = snap.get("places") or []
    if not places:
        return False
    return any(isinstance(p.get("model_violation_prob"), (int, float)) for p in places)


def _model_prob_popup_line(p: dict, has_model_predictions: bool) -> str:
    if not has_model_predictions:
        return "<i>Прогноз модели не включён в снимок (пересоберите без --map-only)</i>"
    prob = p.get("model_violation_prob")
    if isinstance(prob, (int, float)):
        return f"Вероятность нарушения (модель): {float(prob):.2f}"
    return "<i>Нет model_violation_prob в точке</i>"


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


def _matched_addr_html(p: dict) -> str:
    m = p.get("geocode_matched_address")
    if not m:
        return ""
    return (
        "<small>Найденный адрес (геокодер): "
        f"{html.escape(str(m))}</small><br/>"
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
    data_catalog_url: str | None = None,
) -> folium.Map:
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

    catalog_href = data_catalog_url or "https://vtiav.sm.ee/index.php/opendata/"
    catalog_href = html.escape(catalog_href, quote=True)

    plotted = 0
    for p in _filtered_places(places, kinds_filter, counties_filter):
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        kind = _place_kind(p)
        border = KIND_OUTLINE.get(kind, "#64748b")
        if color_mode == "official" or not has_model_predictions:
            fill = official_color(int(p["official_compliant"]))
            title = "Официальный статус"
        else:
            prob = p.get("model_violation_prob")
            fill = model_color(float(prob) if isinstance(prob, (int, float)) else 0.0)
            title = "Прогноз модели (риск нарушения)"

        dom_label = DOMAIN_LABELS.get(p["domain"], p.get("domain", "—"))
        kind_label = DEFAULT_PLACE_KIND_LABELS.get(kind, kind)
        meas = p.get("measurements") if isinstance(p.get("measurements"), dict) else {}
        sid = p.get("sample_id")
        sid_line = f"ID пробы: {html.escape(str(sid))}<br/>" if sid else ""

        popup_html = f"""
        <div style="max-width:320px;font-size:13px">
        <b>{html.escape(str(p.get("location") or "—"))}</b><br/>
        <span style="color:#444">{html.escape(kind_label)}</span><br/>
        <i style="font-size:12px">{html.escape(dom_label)}</i><br/>
        <hr style="margin:6px 0"/>
        {sid_line}
        Дата пробы: {html.escape(str(p.get("sample_date") or "—"))}<br/>
        Уезд: {html.escape(str(p.get("county") or "не указан"))}<br/>
        Официально: {"соответствует" if p.get("official_compliant") == 1 else "нарушение"}<br/>
        {_model_prob_popup_line(p, has_model_predictions)}<br/>
        <small>Источник координат: {html.escape(str(p.get("coord_source", "?")))}</small><br/>
        {_matched_addr_html(p)}
        <small><a href="{catalog_href}" target="_blank" rel="noopener">Каталог opendata Terviseamet</a></small>
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

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def _render_diagnostics(places: list, has_model: bool, snap: dict) -> None:
    """Вкладка «Диагностика»: обнаруженные проблемы мониторинга и ограничения модели."""
    from datetime import datetime, timezone

    snap_time_str = snap.get("generated_at", "")
    try:
        snap_time = datetime.fromisoformat(snap_time_str)
        if snap_time.tzinfo is None:
            snap_time = snap_time.replace(tzinfo=timezone.utc)
    except Exception:
        snap_time = datetime.now(timezone.utc)

    def age_days(p: dict) -> int | None:
        sd = p.get("sample_date")
        if not sd:
            return None
        try:
            dt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (snap_time - dt).days
        except Exception:
            return None

    st.subheader("Диагностика качества мониторинга")
    st.markdown(
        "Здесь отображаются **потенциальные пробелы в надзоре** — места, которые требуют "
        "внимания либо со стороны Terviseamet (давно без пробы), либо в части модели (ограничения)."
    )

    dedup_note = snap.get("dedup_note")
    if dedup_note:
        st.info(f"ℹ️ **Дедупликация имён:** {dedup_note}")

    # ── 1. Незакрытые нарушения ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⚠️ Незакрытые нарушения")
    st.markdown(
        "Места, где **последняя официальная проба — нарушение** и с тех пор нет новых данных (> 30 дней). "
        "Вода была признана несоответствующей нормам, но в открытых данных нет подтверждения устранения."
    )

    open_violations = []
    for p in places:
        if p.get("official_compliant") != 0:
            continue
        if p.get("domain") not in ("supluskoha", "veevark", "joogivesi"):
            continue
        age = age_days(p)
        if age is not None and age > 30:
            open_violations.append({
                "Место": p.get("location", "—"),
                "Тип": DOMAIN_LABELS.get(p.get("domain", ""), p.get("domain", "—")),
                "Последняя проба": p.get("sample_date", "—")[:10] if p.get("sample_date") else "—",
                "Дней назад": age,
                "Риск (модель)": round(p["model_violation_prob"], 2)
                if has_model and isinstance(p.get("model_violation_prob"), (int, float))
                else "—",
            })

    open_violations.sort(key=lambda x: x["Дней назад"], reverse=True)
    if open_violations:
        st.error(f"Найдено **{len(open_violations)}** мест с незакрытым нарушением.")
        st.dataframe(
            pd.DataFrame(open_violations),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("Незакрытых нарушений не обнаружено.")

    # ── 2. Давно не проверялись ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🕐 Места без свежей пробы")

    # Пороги с учётом сезонности: купальные места не проверяются зимой,
    # поэтому «норма» — проба в последнем сезоне, т.е. ≤ 540 дней (~1.5 года).
    # Бассейны работают круглый год — порог строже.
    domain_thresholds = {
        "supluskoha": (540, "пропущен целый купальный сезон — нужна проба в текущем/прошлом году"),
        "veevark": (365, "питьевая вода должна проверяться регулярно"),
        "joogivesi": (365, "источники питьевой воды — редко проверяются"),
        "basseinid": (365, "бассейны работают круглый год"),
    }

    for domain, (threshold_days, reason) in domain_thresholds.items():
        stale = [
            p for p in places
            if p.get("domain") == domain and (age_days(p) or 0) > threshold_days
        ]
        total = sum(1 for p in places if p.get("domain") == domain)
        if not total:
            continue
        pct = len(stale) / total * 100
        label = DOMAIN_LABELS.get(domain, domain)
        msg = f"**{label}**: {len(stale)} из {total} точек без пробы > {threshold_days} дней ({pct:.0f}%) — {reason}"
        if pct >= 50:
            st.error(msg)
        elif pct >= 25:
            st.warning(msg)
        else:
            st.info(msg)

    # Топ самых «заброшенных» купальных мест
    stale_swim = sorted(
        [p for p in places if p.get("domain") == "supluskoha" and (age_days(p) or 0) > 365],
        key=lambda x: age_days(x) or 0,
        reverse=True,
    )
    if stale_swim:
        with st.expander(f"Купальные места без пробы > 1 года ({len(stale_swim)} шт.)"):
            rows = [
                {
                    "Место": p.get("location", "—"),
                    "Дней без пробы": age_days(p),
                    "Последняя проба": p.get("sample_date", "—")[:10] if p.get("sample_date") else "—",
                    "Официально": "норма" if p.get("official_compliant") == 1 else "нарушение",
                }
                for p in stale_swim
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── 3. Ограничения модели для бассейнов ────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏊 Ограничения модели для бассейнов (`basseinid`)")
    st.markdown(
        """
Для бассейнов, ujula и СПА модель **не обучена на бассейновых нормах** до пересборки снимка.
В предыдущей версии это приводило к **192 ложным тревогам** из 527 нормальных проб (Precision = 0.32).

**Корневая причина:** нормативы для бассейнов существенно отличаются от питьевой воды:

| Параметр | Норма водопровод | Норма бассейн |
|---|---|---|
| Мутность (turbidity) | 4.0 NTU | **0.5 NTU** (в 8× строже) |
| Свободный хлор | не нормируется | **0.2–0.6 мг/л** (диапазон) |
| Связанный хлор | не нормируется | **≤ 0.4 мг/л** |
| Стафилококки | не нормируется | **≤ 20 КОЕ/100 мл** |
| Pseudomonas | не нормируется | **0 КОЕ/100 мл** |

**Статус исправления:** `src/features.py` обновлён — добавлены `NORMS_POOL` и domain-conditional
ratio-признаки (`turbidity_ratio` теперь зависит от домена, добавлены `staphylococci_ratio`,
`pseudomonas_detected`, `free_chlorine_deviation`, `combined_chlorine_ratio`).
Для применения исправления необходима **пересборка снимка** (`build_citizen_snapshot.py`).
"""
    )

    if has_model:
        pool_places = [p for p in places if p.get("domain") == "basseinid"]
        pool_ok = [p for p in pool_places if p.get("official_compliant") == 1]
        pool_fp = [p for p in pool_ok if isinstance(p.get("model_violation_prob"), (int, float)) and p["model_violation_prob"] > 0.5]
        if pool_fp:
            st.warning(
                f"В **текущем снимке** обнаружено **{len(pool_fp)}** бассейнов, "
                f"где модель даёт риск > 0.5 при официальной норме (возможные ложные тревоги). "
                f"Пересоберите снимок после обновления `features.py` для корректных прогнозов."
            )
        else:
            st.success("Снимок собран с исправленными нормами — ложных тревог для бассейнов не обнаружено.")

    # ── 4. Источники питьевой воды (joogivesi) ─────────────────────────────────
    st.markdown("---")
    st.markdown("### 💧 Источники питьевой воды (`joogiveeallikas`) — критическая зона")
    joogi = [p for p in places if p.get("domain") == "joogivesi"]
    if joogi:
        ages = [age_days(p) for p in joogi if age_days(p) is not None]
        stale_1y = sum(1 for a in ages if a > 365)
        if ages:
            import statistics as _stats
            median_age = int(_stats.median(ages))
            st.error(
                f"**{stale_1y} из {len(joogi)}** источников питьевой воды не проверялись более 1 года "
                f"(медиана возраста пробы: **{median_age} дней ≈ {median_age // 365} лет**)."
            )
            st.markdown(
                "Это наибольшая проблема в мониторинге: источники из природных водоёмов и родников "
                "попадают в категорию `joogivesi`, но в opendata XML обновляются редко. "
                "Рекомендуется сравнить с регистром Terviseamet напрямую."
            )


def main() -> None:
    st.set_page_config(page_title="Качество воды (гражданский вид)", layout="wide")
    snap = load_snapshot()

    st.title("Качество воды в Эстонии — точки на карте")

    if snap is None:
        st.error(
            "Нет файла снимка данных. Соберите его из корня репозитория:\n\n"
            "`python citizen-service/scripts/build_citizen_snapshot.py --map-only` — только карта и официальные статусы (быстро).\n\n"
            "`python citizen-service/scripts/build_citizen_snapshot.py` — полный снимок + прогноз RF.\n\n"
            "Точнее координаты: `--infer-county` (maakond из кэша/Nominatim) и/или `--geocode-limit 200` "
            "(медленно, уважайте Nominatim)."
        )
        return

    has_model = snapshot_has_model_predictions(snap)
    if has_model:
        st.caption(
            "Данные Terviseamet (открытый XML). Прогноз — отдельная модель машинного обучения; "
            "это не официальное заключение Terviseamet."
        )
    else:
        st.caption(
            "Данные Terviseamet (открытый XML). Карта и официальные статусы доступны сразу; "
            "слой прогноза модели появится после полной сборки снимка (без флага --map-only)."
        )

    st.info(snap.get("disclaimer", ""))

    places = snap.get("places", [])
    n_places = len(places)
    n_approx = sum(1 for p in places if p.get("coord_source") == "approximate_ee")
    if n_places and n_approx / n_places >= 0.2:
        st.warning(
            f"У **{n_approx}** из **{n_places}** точек координаты **не привязаны к реальному месту на местности** "
            f"(`coord_source: approximate_ee`): в данных часто нет maakond/геокода, а снимок собран без Nominatim. "
            "Точки разбросаны по Эстонии только для обзора. Для реальных координат пересоберите: "
            "`python citizen-service/scripts/build_citizen_snapshot.py --infer-county` и/или `--geocode-limit …`."
        )

    kind_labels = {**DEFAULT_PLACE_KIND_LABELS, **(snap.get("place_kinds") or {})}

    rows_for_df = []
    for p in places:
        d = dict(p)
        pk = _place_kind(d)
        d["place_kind"] = pk
        d["Тип места"] = kind_labels.get(pk, pk)
        rows_for_df.append(d)
    df = pd.json_normalize(rows_for_df, sep="_")

    tab_map, tab_table, tab_model, tab_about = st.tabs(["Карта", "Таблица", "О модели", "О сервисе"])

    with tab_map:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if has_model:
                color_mode = st.radio(
                    "Раскраска точек",
                    options=["official", "model"],
                    format_func=lambda x: "По официальному статусу" if x == "official" else "По прогнозу модели (риск)",
                    horizontal=True,
                )
            else:
                color_mode = "official"
                st.markdown("**Раскраска:** только по официальному статусу (в снимке нет прогноза модели).")
                st.caption("Быстрый снимок: `build_citizen_snapshot.py --map-only`. Полный прогон без флага добавит слой модели.")
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

        m = build_map(
            places,
            color_mode,
            kinds_filter,
            use_cluster=use_cluster,
            has_model_predictions=has_model,
            data_catalog_url=snap.get("data_catalog_url"),
        )
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
        if color_mode == "model" and has_model:
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
        if not has_model:
            pref = [c for c in pref if c != "model_violation_prob"]
        cols = [c for c in pref if c in view.columns]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        st.caption("Полные измерения смотрите во всплывающем окне маркера на карте.")

    with tab_model:
        st.markdown("## Как работает модель и как читать прогноз")

        st.markdown(
            """
Прогноз модели — это **вероятность нарушения** (от 0 до 1) для каждой точки на карте.
Чем ближе к **1** — тем выше риск нарушения; чем ближе к **0** — тем модель увереннее,
что вода соответствует нормам.

---

### 4 уровня оценки ML-модели

В этом проекте мы используем **4 уровня** для понимания качества модели:

| Уровень | Вопрос | Метрика |
|---------|--------|---------|
| 1 | Умеет ли модель **вообще** разделять чистую и грязную воду? | **ROC-AUC** (0.988 — отлично) |
| 2 | Какие **ошибки** она делает? | **Recall** (0.956) — пропускает 4.4% нарушений |
| 3 | Можно ли **доверять** вероятностям? | **Калибровка** (isotonic regression) |
| 4 | **Почему** она приняла решение? | **SHAP** — вклад каждого параметра |
"""
        )

        with st.expander("ROC-AUC — разделение классов", expanded=False):
            st.markdown(
                """
**ROC-AUC** показывает, насколько хорошо модель **ранжирует** пробы: грязные должны
получать высокий score, чистые — низкий.

- **AUC = 0.5** — случайное угадывание (монетка)
- **AUC = 0.9+** — отлично
- **AUC = 0.988** (наш LightGBM) — в 98.8% случаев модель правильно ранжирует пару
  «грязная проба + чистая проба»

*ROC-кривая и числа — в ноутбуке `06_advanced_models.ipynb`.*
"""
            )

        with st.expander("Precision / Recall — баланс ошибок", expanded=False):
            st.markdown(
                """
Два вида ошибок:

| Тип | Что это | Последствия |
|-----|---------|-------------|
| **False Positive** (ложная тревога) | Чистую воду назвали грязной | Лишняя проверка |
| **False Negative** (пропуск) | Грязную воду назвали чистой | **Люди в опасности!** |

- **Precision** = из всего «нарушение» — сколько реально нарушений? (0.881)
- **Recall** = из всех реальных нарушений — сколько нашли? (**0.956**)

Для безопасности воды **Recall важнее**: лучше ложная тревога, чем пропущенное загрязнение.

**Порог принятия решения** подбирается функцией `best_threshold_max_recall_at_precision()`:
максимальный Recall при Precision ≥ 0.70.
"""
            )

        with st.expander("Калибровка вероятностей", expanded=False):
            st.markdown(
                """
Если модель говорит P(нарушение) = 0.90, это должно значить: в ~90% таких случаев
реально будет нарушение.

Без калибровки LightGBM **занижает** вероятности нарушений (среднее P ≈ 0.045 для
реальных нарушений). После **isotonic regression**: P ≈ 0.114 — ближе к реальной доле
нарушений (~7.9%).

Калиброванные вероятности позволяют **осознанно** выбирать порог алерта:
- «поднять Recall до 0.97+ при Precision ≈ 0.70» — это реально достижимо.

*Графики калибровки (reliability diagrams) — в ноутбуке `06_advanced_models.ipynb`.*
"""
            )

        with st.expander("SHAP — объяснение решений модели", expanded=False):
            st.markdown(
                """
**SHAP** (SHapley Additive exPlanations) отвечает на вопрос:
*«Сколько каждый параметр **внёс** в конкретное предсказание?»*

Пример разложения:
```
baseline (средний риск):         0.30
+ iron (железо высокое)        → +0.28
+ coliforms (бактерии)         → +0.18
+ turbidity (мутность)         → +0.12
− ph (pH в норме)              → −0.06
= итого                        → 0.82
```

#### Главные предикторы нарушений (SHAP, LightGBM)

| Параметр | Влияние | Что это значит |
|----------|---------|----------------|
| **Железо** (iron) | Самый сильный | Высокое → нарушение (водопровод) |
| **Цветность** (color) | Очень сильный | Высокая → нарушение |
| **Колиформы** (coliforms) | Сильный | Фекальное загрязнение |
| **pH** | Средний | Отклонение от нормы 6.5–9.5 |
| **Энтерококки** (enterococci) | Средний | Кишечные бактерии |
| **Мутность** (turbidity) | Средний | Взвешенные частицы |
| **Месяц** (month) | Заметный | Лето → повышенный риск |

*Визуализации SHAP (beeswarm plot, bar plot) — в ноутбуке `06_advanced_models.ipynb`.*
"""
            )

        st.markdown("---")
        st.markdown(
            """
### О модели на карте

Модель на карте — это **Random Forest** (120 деревьев), обученный на всех доступных
данных Terviseamet для быстрого деплоя. Это **упрощённая** версия: основная модель
проекта — **LightGBM** с темпоральным split, калибровкой и SHAP (см. ноутбук 06).

**Как читать цвет маркера (режим «прогноз модели»):**
- 🟢 Зелёный — модель оценивает риск нарушения как **низкий**
- 🟡 Жёлтый — **средний** уровень риска
- 🔴 Красный — модель оценивает риск как **высокий**

> ⚠️ Прогноз модели — **не** официальное заключение Terviseamet.
> Это ориентир на основе машинного обучения.

Подробнее: [`docs/ml_metrics_guide.md`](https://github.com/user/water-quality-ee/blob/main/docs/ml_metrics_guide.md)
"""
        )

    with tab_about:
        st.markdown(
            """
### Зачем этот сервис

На карте — **отдельные точки**: купальные места, **бассейны / СПА / ujula**, **водопровод** (`veevärk`),
**источники питьевой воды** (`joogiveeallikas`, opendata). У каждой точки — дата последней пробы,
официальный статус Terviseamet, оценка модели и все измеренные параметры (если были в XML).

**Минеральная вода** (`mineraalvesi`): годовых XML в каталоге opendata у Terviseamet сейчас нет — в снимок не попадает.

---

### Почему здесь нужен ML, если нормативы и так жёсткие?

Интуиция подсказывает: достаточно пороговых правил — превышен хоть один параметр → вода плохая.
Так и работает официальное решение Terviseamet. Мы его не заменяем.

**Проблема — неполные данные.** В типичной пробе измерено 2–4 параметра из 15+:

| Параметр | Доля проб с измерением |
|---|---|
| Нитраты, нитриты, сульфаты | 5–7 % |
| pH | 36 % |
| Железо | 53 % |
| E. coli | 77 % |

Пороговое правило при неполных данных: *«нет данных — нет вывода»*.
Модель отвечает: *«по тому, что измерено + по факту отсутствия определённых измерений + по сезону
и типу места — вероятность нарушения составляет X %».*

**Пример:** проба водопровода, измерено только железо (0.18 мг/л, норма 0.2) и мутность (3.8 NTU, норма 4.0).
Оба формально не нарушают. Правило: «чисто». Модель: «такое сочетание "на грани" летом в этом уезде
исторически сопровождалось нарушениями по марганцу или цветности — риск 0.71».

**Что модель улавливает дополнительно к правилам:**
- Кросс-параметрические корреляции (железо + мутность вместе опаснее, чем каждый по отдельности)
- Информативность пропусков (если цветность не измерялась — это сигнал о типе объекта)
- Сезонность: летом в 4× больше нарушений в открытых водоёмах, чем весной
- Ранняя сигнализация: оценка риска до того, как все анализы готовы

**Честное ограничение:** если все параметры всегда измерялись бы, пороговое правило работало бы не хуже модели.
ML — инструмент работы с реальностью: неполными и гетерогенными данными из разных типов водоёмов.

---

### Два слоя информации

1. **Официальный статус** — как в исходных данных (`compliant` из оценки соответствия нормам).
2. **Оценка модели** — вероятность P(нарушение) ∈ [0, 1] по Random Forest на признаках учебного пайплайна
   (только если снимок собран **без** `--map-only`). Это **вспомогательный индикатор риска**, а не замена
   официальной оценки Terviseamet.

### Что модель может и чего не может

Модель — **вероятностный оценщик** в пространстве лабораторных измерений. Она отвечает на вопрос:
*«похож ли набор параметров этой пробы на шаблон нарушений из исторических данных?»*

Модель **не** предсказывает:
- Будущее качество воды (показана оценка **последней** пробы)
- Загрязнители, которые не были измерены (вирусы, токсины за пределами 15 параметров)
- Причины загрязнения (только статистические паттерны)

Цветовая шкала: **зелёный** (P < 0.3, низкий риск) → **жёлтый** (0.3–0.7, умеренный) → **красный** (> 0.7, высокий).

### Координаты

Без платных API: **Nominatim** (кэш `data/geocode_cache.json`), **центроид уезда** и при отсутствии
данных — **приблизительная** точка Эстонии (`approximate_ee`). Для водопровода название точки часто
геокодируется грубо; накапливайте кэш с `--geocode-limit 150`.

### Обновление данных

Рекомендуется **GitHub Actions** по расписанию: скачать XML, выполнить `build_citizen_snapshot.py`, публиковать
`citizen-service/artifacts/snapshot.json`. Подробности — `citizen-service/PLAN.md`.

### Документация и оценка модели

Подробное руководство по метрикам ML (ROC-AUC, Precision/Recall, калибровка, SHAP) —
во вкладке «О модели» выше и в файле `docs/ml_metrics_guide.md` в репозитории.
"""
        )


if __name__ == "__main__":
    main()
