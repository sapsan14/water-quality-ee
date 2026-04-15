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
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from branca.element import MacroElement
from folium.plugins import MarkerCluster
from jinja2 import Template
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "citizen-service" / "artifacts" / "snapshot.json"
MODEL_PATH = ROOT / "citizen-service" / "artifacts" / "citizen_model.joblib"

_LOG = logging.getLogger("citizen.streamlit")


def _ensure_streamlit_logging() -> None:
    """Одноразовая настройка: логи видны в терминале и в логах Streamlit Cloud."""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _log_snapshot_coordinate_health(snap: dict) -> None:
    """Сводка по снимку: сколько точек, откуда координаты, есть ли модель (каждый запуск страницы)."""
    _ensure_streamlit_logging()
    places = snap.get("places") or []
    n = len(places)
    by_src: dict[str, int] = {}
    missing = 0
    for p in places:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            missing += 1
        s = str(p.get("coord_source") or "none")
        by_src[s] = by_src.get(s, 0) + 1
    mtime = "n/a"
    if SNAPSHOT_PATH.is_file():
        mtime = datetime.fromtimestamp(SNAPSHOT_PATH.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    model_on_disk = MODEL_PATH.is_file()
    _LOG.info(
        "Снимок проверен: path=%s mtime=%s мест=%s без_lat/lon=%s coord_source=%s "
        "has_model_predictions=%s citizen_model.joblib=%s",
        SNAPSHOT_PATH,
        mtime,
        n,
        missing,
        by_src,
        snap.get("has_model_predictions"),
        model_on_disk,
    )

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

TRANSLATIONS: dict[str, dict[str, str]] = {
    "RU": {
        "page_title": "Качество воды (гражданский вид)",
        "title": "Качество воды — Эстония",
        "caption_model": "Данные Terviseamet (открытый XML). Прогнозы — отдельные ML-модели ({models}); это не официальное заключение Terviseamet.",
        "caption_nomodel": "Данные Terviseamet (открытый XML). Карта и официальные статусы; прогнозы моделей появятся после полной сборки снимка (без флага --map-only).",
        "tab_map": "Карта",
        "tab_table": "Таблица",
        "tab_compare": "Сравнение моделей",
        "nav_diagnostics": "Диагностика",
        "nav_about_model": "О модели",
        "nav_about_service": "О сервисе",
        "last_measured": "Последнее измерение",
        "no_snap": "Нет файла снимка данных.",
    },
    "EN": {
        "page_title": "Water Quality (citizen view)",
        "title": "Water Quality — Estonia",
        "caption_model": "Data: Terviseamet (open XML). Predictions — separate ML models ({models}); not an official Terviseamet assessment.",
        "caption_nomodel": "Data: Terviseamet (open XML). Map and official statuses only; model predictions available after full snapshot build (without --map-only).",
        "tab_map": "Map",
        "tab_table": "Table",
        "tab_compare": "Model Compare",
        "nav_diagnostics": "Diagnostics",
        "nav_about_model": "About Model",
        "nav_about_service": "About Service",
        "last_measured": "Last measured",
        "no_snap": "No snapshot file found.",
    },
    "ET": {
        "page_title": "Vee kvaliteet (kodanikuvaade)",
        "title": "Vee kvaliteet — Eesti",
        "caption_model": "Andmed: Terviseamet (avatud XML). Prognoosid — eraldi ML-mudelid ({models}); ei ole Terviseameti ametlik hinnang.",
        "caption_nomodel": "Andmed: Terviseamet (avatud XML). Kaart ja ametlikud staatused; mudelite prognoosid on saadaval pärast täielikku hetktõmmist (ilma --map-only).",
        "tab_map": "Kaart",
        "tab_table": "Tabel",
        "tab_compare": "Mudelite võrdlus",
        "nav_diagnostics": "Diagnostika",
        "nav_about_model": "Mudeli kohta",
        "nav_about_service": "Teenuse kohta",
        "last_measured": "Viimati mõõdetud",
        "no_snap": "Hetktõmmise fail puudub.",
    },
}


# ── CSS / JS for sliding filter panel ─────────────────────────────────────────

_PANEL_CSS = """<style>
/* == global font == */
html,body,[class*="css"],[data-testid="stAppViewContainer"]{
  font-family:"Proxima Nova","ProximaNova","Segoe UI",Roboto,sans-serif !important;
}

/* == sidebar: fixed overlay, never pushes main content == */
section[data-testid="stSidebar"]{
  position:fixed !important;
  top:0 !important; left:0 !important;
  height:100vh !important;
  z-index:1000 !important;
  overflow-y:auto !important;
  background:#ffffff !important;
  border-right:2px solid #0369a1 !important;
  border-radius:0 16px 16px 0 !important;
  box-shadow:6px 0 32px rgba(3,105,161,.18) !important;
  transition:transform .32s cubic-bezier(.4,0,.2,1) !important;
}
section[data-testid="stSidebar"][aria-expanded="false"]{
  transform:translateX(-110%) !important;
  box-shadow:none !important;
}

/* == main content: always full-width == */
section[data-testid="stMain"],.main{
  margin-left:0 !important; padding-left:0 !important; width:100% !important;
}
[data-testid="stAppViewBlockContainer"]{
  max-width:100% !important;
  padding-left:1rem !important; padding-right:1rem !important;
}

/* == hide Streamlit's own toggle buttons (still clickable via JS) == */
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"]{
  visibility:hidden !important;
  pointer-events:none !important;
  position:absolute !important;
}

/* == FAB: filter toggle == */
#fp-fab{position:fixed;top:70px;left:12px;z-index:1002;}
#fp-fab-btn{
  background:#0369a1;color:#fff;
  border:none;border-radius:10px;
  width:44px;height:44px;font-size:20px;
  cursor:pointer;
  box-shadow:0 3px 14px rgba(3,105,161,.35);
  transition:background .18s,transform .13s;
  display:flex;align-items:center;justify-content:center;line-height:1;
}
#fp-fab-btn:hover{background:#0284c7;transform:scale(1.07);}
#fp-fab-btn.is-open{background:#0c4a6e;}

/* == backdrop (unpinned mode) == */
#fp-backdrop{
  display:none;position:fixed;inset:0;
  z-index:999;background:rgba(0,0,0,.28);cursor:pointer;
}
#fp-backdrop.active{display:block;}

/* == sidebar header == */
.fp-header{
  display:flex;align-items:center;gap:8px;
  padding:14px 0 10px;margin-bottom:4px;
  border-bottom:1.5px solid #e2e8f0;
}
.fp-title{flex:1;font-size:15px;font-weight:700;color:#0369a1;letter-spacing:.01em;}
.fp-pin-btn{
  background:none;border:1.5px solid #e2e8f0;border-radius:7px;
  padding:3px 8px;cursor:pointer;font-size:15px;color:#0369a1;
  transition:border-color .15s,opacity .15s;line-height:1.3;
}
.fp-pin-btn:hover{border-color:#94a3b8;}
.fp-pin-btn.unpinned{opacity:.5;}

/* == compact icon-only action buttons in sidebar == */
section[data-testid="stSidebar"]
  [data-testid="stHorizontalBlock"] .stButton>button{
  padding:0 !important;
  font-size:18px !important;
  min-height:40px !important;
  border-radius:9px !important;
  line-height:1 !important;
}

/* == stats row below map == */
.fp-stats{
  display:flex;gap:8px;flex-wrap:wrap;
  margin-top:14px;padding:12px 14px;
  background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;
}
.fp-stat{
  flex:1;min-width:88px;background:#fff;
  border:1px solid #e2e8f0;border-radius:9px;
  padding:9px 10px;text-align:center;
  box-shadow:0 1px 3px rgba(0,0,0,.05);
}
.fp-stat-val{font-size:21px;font-weight:700;line-height:1.15;}
.fp-stat-lbl{font-size:10px;color:#64748b;margin-top:2px;
             text-transform:uppercase;letter-spacing:.04em;}
.sv-blue {color:#0369a1;}
.sv-red  {color:#ef4444;}
.sv-green{color:#16a34a;}
.sv-amber{color:#d97706;}
</style>
"""

_PANEL_JS_HTML = """\
<div id="fp-fab"><button id="fp-fab-btn" title="Фильтры" onclick="fpToggle()">⚙</button></div>
<div id="fp-backdrop" onclick="fpOnBackdrop()"></div>
<script>
(function(){
  var OK='fp_open',PK='fp_pinned';
  function isOpen()  {return localStorage.getItem(OK)!=='false';}
  function isPinned(){return localStorage.getItem(PK)!=='false';}
  function setOpen(v){localStorage.setItem(OK,v?'true':'false');}
  function setPin(v) {localStorage.setItem(PK,v?'true':'false');}
  function getSB()   {return document.querySelector('section[data-testid="stSidebar"]');}
  function isExp()   {var s=getSB();return s&&s.getAttribute('aria-expanded')==='true';}
  function nativeOpen(){
    var b=document.querySelector('[data-testid="collapsedControl"] button');
    if(b)b.click();
  }
  function nativeClose(){
    var s=getSB(),b=s&&s.querySelector('[data-testid="stSidebarCollapseButton"] button');
    if(b)b.click();
  }
  window.fpToggle=function(){
    if(isExp()){nativeClose();setOpen(false);}
    else{nativeOpen();setOpen(true);}
    setTimeout(sync,80);
  };
  window.fpOnBackdrop=function(){
    if(!isPinned()){nativeClose();setOpen(false);sync();}
  };
  window.fpTogglePin=function(){
    setPin(!isPinned());updatePin();sync();
  };
  window.fpNearMe=function(){
    if(!navigator.geolocation){alert('Геолокация недоступна в этом браузере');return;}
    navigator.geolocation.getCurrentPosition(function(p){
      var u=new URL(window.location.href);
      u.searchParams.set('geo_lat',p.coords.latitude.toFixed(6));
      u.searchParams.set('geo_lon',p.coords.longitude.toFixed(6));
      window.location.href=u.toString();
    },function(e){alert('Ошибка геолокации: '+e.message);});
  };
  function sync(){
    var bd=document.getElementById('fp-backdrop');
    if(bd)bd.className=(!isPinned()&&isExp())?'active':'';
    var fb=document.getElementById('fp-fab-btn');
    if(fb)fb.className=isExp()?'is-open':'';
  }
  function updatePin(){
    var b=document.getElementById('fp-pin-btn');
    if(!b)return;
    var p=isPinned();
    b.textContent=p?'📌':'📍';
    b.title=p?'Открепить панель':'Закрепить панель';
    b.className='fp-pin-btn'+(p?'':' unpinned');
  }
  function onRender(){
    sync();updatePin();
    if(isOpen()&&!isExp())nativeOpen();
    if(!isOpen()&&isExp())nativeClose();
  }
  new MutationObserver(function(muts){
    if(muts.some(function(m){return m.addedNodes.length||m.removedNodes.length;}))onRender();
  }).observe(document.body,{childList:true,subtree:false});
  function watchSB(){
    var sb=getSB();
    if(!sb){setTimeout(watchSB,150);return;}
    new MutationObserver(function(){sync();}).observe(sb,{attributes:true,attributeFilter:['aria-expanded']});
    onRender();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watchSB);
  else watchSB();
})();
</script>
"""

_PIN_BTN_HTML = (
    '<button id="fp-pin-btn" class="fp-pin-btn" onclick="fpTogglePin()"'
    ' title="Закрепить/открепить панель">📌</button>'
)

_NEAR_ME_BTN_HTML = (
    '<button onclick="fpNearMe()" title="Рядом со мной (нужен доступ к геолокации)"'
    ' style="background:#fff;border:1.5px solid #e2e8f0;border-radius:9px;'
    'width:100%;height:40px;cursor:pointer;font-size:18px;line-height:1;'
    'display:flex;align-items:center;justify-content:center;">📍</button>'
)


@st.cache_data(show_spinner=False)
def load_snapshot() -> dict | None:
    _ensure_streamlit_logging()
    if not SNAPSHOT_PATH.is_file():
        _LOG.warning("Файл снимка отсутствует: %s", SNAPSHOT_PATH)
        return None
    st_sz = SNAPSHOT_PATH.stat().st_size
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _LOG.info(
        "Снимок загружен с диска в кэш Streamlit (%s байт, generated_at=%s)",
        st_sz,
        (data or {}).get("generated_at"),
    )
    return data


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
    """Returns an HTML table of measurements, or empty string if no data."""
    if not m:
        return ""
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


def _compute_map_stats(filtered: list[dict], prob_col: str) -> dict:
    """Summary statistics for the currently visible / filtered places."""
    n_vis = sum(1 for p in filtered if p.get("lat") is not None)
    probs = [
        float(p[prob_col])
        for p in filtered
        if isinstance(p.get(prob_col), (int, float)) and p.get("lat") is not None
    ]
    n_mdl = len(probs)
    n_hi  = sum(1 for x in probs if x > 0.5)
    n_lo  = n_mdl - n_hi
    avg_p = (sum(probs) / n_mdl) if n_mdl else None

    cv     = [p.get("official_compliant") for p in filtered
              if p.get("official_compliant") is not None and p.get("lat") is not None]
    n_viol = sum(1 for v in cv if v == 0)
    n_val  = len(cv)
    health = int(round((1 - n_viol / n_val) * 100)) if n_val else None

    if avg_p is not None:
        if avg_p > 0.55:
            fc, fcc = "Критично", "#ef4444"
        elif avg_p > 0.25:
            fc, fcc = "Умеренно", "#d97706"
        else:
            fc, fcc = "Хорошо", "#16a34a"
    elif health is not None:
        if health < 60:
            fc, fcc = "Критично", "#ef4444"
        elif health < 85:
            fc, fcc = "Умеренно", "#d97706"
        else:
            fc, fcc = "Хорошо", "#16a34a"
    else:
        fc, fcc = "н/д", "#64748b"

    return dict(n_vis=n_vis, n_hi=n_hi, n_lo=n_lo, n_viol=n_viol,
                n_mdl=n_mdl, health=health, fc=fc, fcc=fcc, avg_p=avg_p)


def _render_stats_html(s: dict) -> str:
    avg_str = f"{s['avg_p']:.2f}" if s["avg_p"] is not None else "н/д"
    hi      = s["health"]
    hi_str  = f"{hi}/100" if hi is not None else "н/д"
    hi_col  = ("#16a34a" if (hi or 0) >= 85 else
               "#d97706" if (hi or 0) >= 60 else "#ef4444") if hi is not None else "#64748b"

    def card(v: str, lbl: str) -> str:
        return (f'<div class="fp-stat">'
                f'<div class="fp-stat-val">{v}</div>'
                f'<div class="fp-stat-lbl">{html.escape(lbl)}</div>'
                f'</div>')

    return (
        '<div class="fp-stats">'
        + card(f'<span class="sv-blue">{s["n_vis"]}</span>',    "Видимых")
        + card(f'<span class="sv-red">{s["n_hi"]}</span>',      "Высокий риск")
        + card(f'<span class="sv-green">{s["n_lo"]}</span>',    "Низкий риск")
        + card(f'<span class="sv-red">{s["n_viol"]}</span>',    "Офиц. нарушения")
        + card(f'<span class="sv-blue">{s["n_mdl"]}</span>',    "С моделью")
        + card(f'<span style="color:{hi_col}">{hi_str}</span>', "Индекс здоровья")
        + card(f'<span style="color:{s["fcc"]};font-size:14px">{html.escape(s["fc"])}</span>',
               "Прогноз")
        + card(f'<span class="sv-amber">{avg_str}</span>',      "Ср. P(нарушения)")
        + '</div>'
    )


def _sample_age_label(sample_date_str: str | None) -> str:
    """Человекочитаемый возраст пробы: '3 дня назад', '2 месяца назад' и т.д."""
    if not sample_date_str:
        return "дата неизвестна"
    try:
        dt = datetime.fromisoformat(sample_date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
    except Exception:
        return str(sample_date_str)[:10]
    if days < 0:
        return str(sample_date_str)[:10]
    if days == 0:
        return "сегодня"
    if days == 1:
        return "вчера"
    if days < 30:
        return f"{days} дн. назад"
    months = days // 30
    if months < 12:
        return f"~{months} мес. назад"
    years = days // 365
    return f"~{years} г. назад"


class _InvalidateSizeOnResize(MacroElement):
    """Calls map.invalidateSize() when the map container is resized (e.g. Streamlit fullscreen toggle).

    Without this, Leaflet keeps stale container dimensions, so popups and
    click targets appear shifted after entering/exiting fullscreen.
    """

    _template = Template("""
        {% macro script(this, kwargs) %}
            (function () {
                var map = {{ this._parent.get_name() }};
                var container = map.getContainer();
                if (window.ResizeObserver) {
                    new ResizeObserver(function () {
                        map.invalidateSize({animate: false});
                    }).observe(container);
                } else {
                    window.addEventListener('resize', function () {
                        setTimeout(function () { map.invalidateSize({animate: false}); }, 200);
                    });
                }
            })();
        {% endmacro %}
    """)


def _display_locations_for_overlaps(points: list[dict]) -> dict[int, tuple[float, float]]:
    """
    Раздвигаем маркеры с одинаковыми координатами, чтобы их можно было кликнуть по отдельности.
    Смещение только визуальное; данные в popup остаются исходными.
    """
    by_coord: dict[tuple[float, float], list[int]] = {}
    out: dict[int, tuple[float, float]] = {}
    for i, p in enumerate(points):
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        key = (round(float(lat), 7), round(float(lon), 7))
        by_coord.setdefault(key, []).append(i)

    for key, idxs in by_coord.items():
        base_lat, base_lon = key
        n = len(idxs)
        if n == 1:
            out[idxs[0]] = (base_lat, base_lon)
            continue
        radius = min(0.00055, 0.00028 + 0.00004 * n)
        for j, idx in enumerate(idxs):
            angle = (2 * math.pi * j) / n
            out[idx] = (
                base_lat + radius * math.sin(angle),
                base_lon + radius * math.cos(angle),
            )
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
    map_center: tuple[float, float] | None = None,
    map_zoom: int = 7,
    debug_focus_name: str | None = None,
    last_measured_label: str = "Last measured",
) -> folium.Map:
    available_models = available_models or []
    model_labels = model_labels or MODEL_LABELS_DEFAULT

    center = [58.65, 25.5]
    if map_center is not None:
        center = [float(map_center[0]), float(map_center[1])]
    m = folium.Map(location=center, zoom_start=int(map_zoom), tiles=None)
    folium.TileLayer("CartoDB Positron", name="Карта (светлая)", control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(m)

    cluster = MarkerCluster(name="Места", disable_clustering_at_zoom=11) if use_cluster else None

    radius_by_kind = {
        "swimming": 14,
        "pool_spa": 13,
        "drinking_water": 11,
        "drinking_source": 12,
        "other": 11,
    }

    catalog_href = html.escape(data_catalog_url or "https://vtiav.sm.ee/index.php/opendata/", quote=True)

    filtered = _filtered_places(places, kinds_filter, counties_filter)
    display_loc = _display_locations_for_overlaps(filtered)

    plotted = 0
    for i, p in enumerate(filtered):
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        dlat, dlon = display_loc.get(i, (float(lat), float(lon)))
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

        coord_src = str(p.get("coord_source", "?"))
        is_approx = coord_src == "approximate_ee"
        coord_line = (
            "<small style='color:#b45309'>⚠ Координаты приблизительные (нет геокода)"
            f" — {html.escape(coord_src)}</small><br/>"
            if is_approx
            else f"<small>Источник координат: {html.escape(coord_src)}</small><br/>"
        )

        sample_date_str = str(p.get("sample_date") or "")
        age_label = _sample_age_label(sample_date_str or None)
        try:
            age_days_val = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(sample_date_str.replace("Z", "+00:00"))
            ).days if sample_date_str else 999
        except Exception:
            age_days_val = 0
        if age_days_val > 90:
            freshness_style = "color:#b45309;font-weight:bold"
            freshness_icon = "⚠ "
        else:
            freshness_style = "color:#166534"
            freshness_icon = ""
        date_line = (
            f"Последняя проба: {html.escape(sample_date_str[:10] if sample_date_str else '—')} "
            f"<span style='{freshness_style}'>({freshness_icon}{html.escape(age_label)})</span><br/>"
        )

        models_html = _model_comparison_html(p, available_models, model_labels)

        focus_badge = ""
        if debug_focus_name and str(p.get("location") or "") == debug_focus_name:
            focus_badge = "<br/><small style='color:#1d4ed8'><b>DEBUG focus</b></small>"

        meas_html = _measurements_html(meas)
        if meas_html:
            meas_date_display = sample_date_str[:10] if sample_date_str else ""
            meas_heading = (
                f"{html.escape(last_measured_label)}: {html.escape(meas_date_display)}"
                if meas_date_display else html.escape(last_measured_label)
            )
            meas_section = (
                f"<hr style='margin:6px 0'/>"
                f"<b style='font-size:12px'>{meas_heading}</b><br/>"
                f"{meas_html}"
            )
        else:
            meas_section = ""

        popup_html = f"""
        <div style="max-width:340px;font-size:13px">
        <b>{html.escape(str(p.get("location") or "—"))}</b><br/>
        {focus_badge}
        <span style="color:#444">{html.escape(kind_label)}</span><br/>
        <i style="font-size:12px">{html.escape(dom_label)}</i><br/>
        <hr style="margin:6px 0"/>
        {sid_line}
        {date_line}
        Уезд: {html.escape(str(p.get("county") or "не указан"))}<br/>
        Официально: {"соответствует" if p.get("official_compliant") == 1 else "<b style='color:#ef4444'>нарушение</b>"}<br/>
        {coord_line}
        {_matched_addr_html(p)}
        <small><a href="{catalog_href}" target="_blank" rel="noopener">Каталог opendata Terviseamet</a></small>
        <hr style="margin:6px 0"/>
        {models_html}
        {meas_section}
        </div>
        """

        r = radius_by_kind.get(kind, 11)
        # Приблизительные координаты: пунктирная обводка маркера (dashArray)
        marker = folium.CircleMarker(
            location=[dlat, dlon],
            radius=r,
            color=border,
            weight=2 if is_approx else 3,
            dash_array="6 4" if is_approx else None,
            fill=True,
            fill_color=fill,
            fill_opacity=0.65 if is_approx else 0.92,
            popup=folium.Popup(popup_html, max_width=360),
            tooltip=f"{str(p.get('location', ''))[:42]} · {color_title}{'  ⚠ приблизит.' if is_approx else ''}",
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
    _InvalidateSizeOnResize().add_to(m)
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


def _render_diagnostics(places: list, has_model: bool, snap: dict) -> None:
    """Вкладка «Диагностика»: пробелы в мониторинге и ограничения модели."""
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
            dt = datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (snap_time - dt).days
        except Exception:
            return None

    st.subheader("Диагностика качества мониторинга")
    st.markdown(
        "Потенциальные пробелы в надзоре — места, которые требуют внимания "
        "со стороны Terviseamet (давно без пробы) или в части модели."
    )
    dedup_note = snap.get("dedup_note")
    if dedup_note:
        st.info(f"ℹ️ **Дедупликация имён:** {dedup_note}")

    # 1. Незакрытые нарушения
    st.markdown("---")
    st.markdown("### ⚠️ Незакрытые нарушения")
    st.markdown(
        "Места, где **последняя официальная проба — нарушение** и нет новых данных > 30 дней."
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
                "Последняя проба": (p.get("sample_date") or "—")[:10],
                "Дней назад": age,
                "Риск (модель)": round(p["model_violation_prob"], 2)
                if has_model and isinstance(p.get("model_violation_prob"), (int, float)) else "—",
            })
    open_violations.sort(key=lambda x: x["Дней назад"], reverse=True)
    if open_violations:
        st.error(f"Найдено **{len(open_violations)}** мест с незакрытым нарушением.")
        st.dataframe(pd.DataFrame(open_violations), use_container_width=True, hide_index=True)
    else:
        st.success("Незакрытых нарушений не обнаружено.")

    # 2. Давно не проверялись
    st.markdown("---")
    st.markdown("### 🕐 Места без свежей пробы")
    domain_thresholds = {
        "supluskoha": (540, "пропущен целый купальный сезон"),
        "veevark":    (365, "питьевая вода должна проверяться регулярно"),
        "joogivesi":  (365, "источники питьевой воды — редко проверяются"),
        "basseinid":  (365, "бассейны работают круглый год"),
    }
    for domain, (threshold_days, reason) in domain_thresholds.items():
        stale = [p for p in places if p.get("domain") == domain and (age_days(p) or 0) > threshold_days]
        total = sum(1 for p in places if p.get("domain") == domain)
        if not total:
            continue
        pct = len(stale) / total * 100
        label = DOMAIN_LABELS.get(domain, domain)
        msg = f"**{label}**: {len(stale)}/{total} точек без пробы > {threshold_days} дней ({pct:.0f}%) — {reason}"
        if pct >= 50:
            st.error(msg)
        elif pct >= 25:
            st.warning(msg)
        else:
            st.info(msg)
    stale_swim = sorted(
        [p for p in places if p.get("domain") == "supluskoha" and (age_days(p) or 0) > 365],
        key=lambda x: age_days(x) or 0, reverse=True,
    )
    if stale_swim:
        with st.expander(f"Купальные места без пробы > 1 года ({len(stale_swim)} шт.)"):
            rows = [{"Место": p.get("location", "—"), "Дней без пробы": age_days(p),
                     "Официально": "норма" if p.get("official_compliant") == 1 else "нарушение"}
                    for p in stale_swim]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 3. Бассейновые нормы
    st.markdown("---")
    st.markdown("### 🏊 Бассейны: pool-специфические нормы")
    st.markdown(
        "Нормы бассейнов (turbidity 0.5 NTU, хлор, стафилококки) отличаются от питьевой воды. "
        "`features.py` применяет `NORMS_POOL` при `domain=basseinid`."
    )
    if has_model:
        pool_ok = [p for p in places if p.get("domain") == "basseinid" and p.get("official_compliant") == 1]
        pool_fp = [p for p in pool_ok if isinstance(p.get("model_violation_prob"), (int, float)) and p["model_violation_prob"] > 0.5]
        if pool_fp:
            st.warning(f"**{len(pool_fp)}** бассейнов: модель риск > 0.5 при официальной норме — возможные ложные тревоги.")
        else:
            st.success("Ложных тревог для бассейнов не обнаружено.")

    # 4. Источники питьевой воды
    st.markdown("---")
    st.markdown("### 💧 Источники питьевой воды (`joogiveeallikas`)")
    joogi = [p for p in places if p.get("domain") == "joogivesi"]
    if joogi:
        ages = [a for p in joogi if (a := age_days(p)) is not None]
        stale_1y = sum(1 for a in ages if a > 365)
        if ages:
            import statistics as _stats
            median_age = int(_stats.median(ages))
            st.error(
                f"**{stale_1y}/{len(joogi)}** источников питьевой воды не проверялись > 1 года "
                f"(медиана: **{median_age} дней ≈ {median_age // 365} лет**)."
            )


def _render_about_model() -> None:
    """Standalone info page: how the model works and how to read predictions."""
    st.markdown("## Как работает модель и как читать прогноз")
    st.markdown(
        """
Прогноз модели — это **вероятность нарушения** (от 0 до 1) для каждой точки на карте.
Чем ближе к **1** — тем выше риск нарушения; чем ближе к **0** — тем модель увереннее,
что вода соответствует нормам.

---

### 4 уровня оценки ML-модели

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
**Порог** подбирается через `best_threshold_max_recall_at_precision()`: max Recall при Precision ≥ 0.70.
"""
        )
    with st.expander("Калибровка вероятностей", expanded=False):
        st.markdown(
            """
Если модель говорит P = 0.90, это должно значить: в ~90% таких случаев реально нарушение.
Используется **isotonic regression** — сырые вероятности RF могут быть занижены.
*Графики калибровки — в ноутбуке `06_advanced_models.ipynb`.*
"""
        )
    with st.expander("SHAP — объяснение решений модели", expanded=False):
        st.markdown(
            """
**SHAP** отвечает на вопрос: *«Сколько каждый параметр внёс в конкретное предсказание?»*

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
"""
        )
    st.markdown("---")
    st.markdown(
        """
### О модели на карте

Модель на карте — **Random Forest** (120 деревьев). Основная модель проекта — **LightGBM**
с темпоральным split, калибровкой и SHAP (ноутбук 06).

**Как читать цвет маркера (режим «прогноз»):**
- 🟢 Зелёный — низкий риск нарушения
- 🟡 Жёлтый — средний риск
- 🔴 Красный — высокий риск

> ⚠️ Прогноз модели — **не** официальное заключение Terviseamet.
"""
    )


def _render_about_service(lang: str = "RU") -> None:
    """Standalone info page: what this service is and how it works."""
    _ABOUT_SERVICE: dict[str, str] = {
        "RU": """
## О сервисе

### Зачем этот сервис

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

Все модели обучены на **одних данных** (все годы). `P(нарушение)` — вероятность класса "нарушение"
(0 = безопасно, 1 = точно нарушение). Порог по умолчанию: 0.5.

### Координаты

Координаты в снимке: **OpenCage** (при сборке с ключом), **кэш**, **центроид уезда** и
**приблизительная точка** (`approximate_ee`). Водопроводные точки часто геокодируются грубо.

### Обновление данных

GitHub Actions по расписанию: `citizen-snapshot.yml` (полный снимок с моделями: по понедельникам
05:00 UTC и 1-е число 04:00 UTC).
""",
        "EN": """
## About the service

### What this service does

The map shows **individual sampling points**: swimming locations, **pools / SPA**, **drinking water network** (`veevärk`),
**drinking water sources** (`joogiveeallikas`). Each point displays the sample date, official status,
predictions from **four models**, and the **parameters** of the latest sample.

**Mineral water** (`mineraalvesi`): no annual XML files are available in Terviseamet opendata — not included in the snapshot.

### Four models

| Model | Description |
|-------|-------------|
| **Logistic Regression** | Linear baseline classifier. Interpretable and fast. |
| **Random Forest** | Ensemble of decision trees. Robust to outliers and missing values. |
| **Gradient Boosting** | Sequential boosting. Typically more accurate on imbalanced data. |
| **LightGBM** | Microsoft gradient boosting. Faster, with native NaN handling. |

All models are trained on **the same data** (all years). `P(violation)` is the probability of the "violation" class
(0 = safe, 1 = definite violation). Default threshold: 0.5.

### Coordinates

Coordinates in the snapshot come from: **OpenCage** (when built with an API key), **cache**, **county centroid**, or
**approximate point** (`approximate_ee`). Drinking water network points are often geocoded coarsely.

### Data updates

GitHub Actions on schedule: `citizen-snapshot.yml` (full snapshot with models: Mondays at 05:00 UTC and the 1st of each month at 04:00 UTC).
""",
        "ET": """
## Teenuse kohta

### Mida see teenus teeb

Kaardil on **üksikud proovivõtupunktid**: suplusekohad, **basseinid / SPA**, **ühisveevärk** (`veevärk`),
**joogivee allikad** (`joogiveeallikas`). Igal punktil kuvatakse proovi kuupäev, ametlik staatus,
**nelja mudeli** ennustused ja viimase proovi **parameetrid**.

**Mineraalvesi** (`mineraalvesi`): Terviseameti avalikus andmebaasis puuduvad aasta-XML-failid — hetkel puudub andmekogumisel.

### Neli mudelit

| Mudel | Kirjeldus |
|-------|-----------|
| **Logistic Regression** | Lineaarne baasmudel. Tõlgendatav ja kiire. |
| **Random Forest** | Otsustuspuude ansambel. Vastupidav erindite ja puuduvate väärtuste suhtes. |
| **Gradient Boosting** | Järjestikune võimendamine. Tavaliselt täpsem tasakaalustamata andmetel. |
| **LightGBM** | Microsofti gradientvõimendus. Kiirem, natiivselt toetab NaN-väärtusi. |

Kõik mudelid on treenitud **samadel andmetel** (kõik aastad). `P(rikkumine)` on "rikkumise" klassi tõenäosus
(0 = ohutu, 1 = kindel rikkumine). Vaikimisi lävi: 0.5.

### Koordinaadid

Koordinaadid andmekogumis pärinevad: **OpenCage** (kui ehitatud API-võtmega), **vahemälust**, **maakonna tsentroidist** või
**ligikaudsest punktist** (`approximate_ee`). Ühisveevärgi punktide geokodeerimine on sageli ebatäpne.

### Andmete uuendamine

GitHub Actions ajakaval: `citizen-snapshot.yml` (täielik andmekogum koos mudelitega: esmaspäeviti kell 05:00 UTC ja iga kuu 1. kuupäeval kell 04:00 UTC).
""",
    }
    st.markdown(_ABOUT_SERVICE.get(lang, _ABOUT_SERVICE["RU"]))


def main() -> None:
    # ── session state defaults ─────────────────────────────────────────────
    if "lang" not in st.session_state:
        st.session_state["lang"] = "RU"
    if "info_page" not in st.session_state:
        st.session_state["info_page"] = None

    lang: str = st.session_state["lang"]
    T = TRANSLATIONS.get(lang, TRANSLATIONS["RU"])

    st.set_page_config(
        page_title=T["page_title"],
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    # Inject overlay-sidebar CSS + FAB/backdrop JS
    st.markdown(_PANEL_CSS, unsafe_allow_html=True)
    st.markdown(_PANEL_JS_HTML, unsafe_allow_html=True)

    # ── IBM Plex Sans + header/nav styling ────────────────────────────────
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
  font-family: "IBM Plex Sans", "Segoe UI", Roboto, sans-serif !important;
}
.wq-title {
  font-size: 1.35rem;
  font-weight: 600;
  color: #0c4a6e;
  margin: 0;
  padding: 0.15rem 0;
}
/* language radio → compact pill buttons */
div[data-testid="stRadio"][data-key="lang_radio"] > div {
  flex-direction: row;
  gap: 4px;
  justify-content: flex-end;
}
div[data-testid="stRadio"][data-key="lang_radio"] label {
  border: 1.5px solid #0369a1;
  border-radius: 20px;
  padding: 2px 13px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  color: #0369a1;
  background: transparent;
  white-space: nowrap;
}
div[data-testid="stRadio"][data-key="lang_radio"] label:has(input:checked) {
  background: #0369a1;
  color: #fff;
}
div[data-testid="stRadio"][data-key="lang_radio"] label:hover:not(:has(input:checked)) {
  background: #e0f2fe;
}
div[data-testid="stRadio"][data-key="lang_radio"] p { display: none; }
/* info-page nav buttons */
.info-nav-row .stButton > button {
  background: transparent !important;
  border: 1.5px solid #cbd5e1 !important;
  border-radius: 6px !important;
  color: #475569 !important;
  font-size: 12.5px !important;
  font-weight: 500 !important;
  padding: 4px 14px !important;
  transition: border-color 0.15s, color 0.15s, background 0.15s !important;
  white-space: nowrap;
}
.info-nav-row .stButton > button:hover {
  border-color: #0369a1 !important;
  color: #0369a1 !important;
  background: #f0f9ff !important;
}
.info-nav-active .stButton > button {
  background: #0369a1 !important;
  border-color: #0369a1 !important;
  color: #fff !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # ── header: title (left) + language pills (right) ─────────────────────
    hcol_t, hcol_l = st.columns([8, 2])
    with hcol_t:
        st.markdown(f"<h1 class='wq-title'>💧 {T['title']}</h1>", unsafe_allow_html=True)
    with hcol_l:
        new_lang = st.radio(
            "language",
            ["ET", "EN", "RU"],
            index=["ET", "EN", "RU"].index(lang),
            horizontal=True,
            label_visibility="collapsed",
            key="lang_radio",
        )
        if new_lang != lang:
            st.session_state["lang"] = new_lang
            st.rerun()

    snap = load_snapshot()
    if snap is None:
        st.error(T["no_snap"] + "\n\n"
            "`python citizen-service/scripts/build_citizen_snapshot.py --map-only`\n\n"
            "`python citizen-service/scripts/build_citizen_snapshot.py`")
        return

    _log_snapshot_coordinate_health(snap)

    has_model    = snapshot_has_model_predictions(snap)
    avail_models = _available_models(snap) if has_model else []
    model_labels: dict[str, str] = {**MODEL_LABELS_DEFAULT, **(snap.get("model_labels") or {})}
    places       = snap.get("places", [])
    kind_labels  = {**DEFAULT_PLACE_KIND_LABELS, **(snap.get("place_kinds") or {})}

    # ── geo-location from URL query params (written by fpNearMe JS) ───────────
    map_center: tuple[float, float] | None = None
    map_zoom = 7
    try:
        qp = st.query_params
        gl, gn = qp.get("geo_lat"), qp.get("geo_lon")
        if gl and gn:
            map_center = (float(gl), float(gn))
            map_zoom   = 12
    except Exception:
        pass

    # ── normalise places for the table DataFrame ───────────────────────────────
    rows_for_df = []
    for p in places:
        d = dict(p)
        pk = _place_kind(d)
        d["place_kind"] = pk
        d["Тип места"]  = kind_labels.get(pk, pk)
        rows_for_df.append(d)
    df_full = pd.json_normalize(rows_for_df, sep="_")

    # ── session-state defaults (set once on first render) ─────────────────────
    _ss_defaults = {
        "f_swimming": True, "f_pool_spa": True,
        "f_drinking_water": True, "f_drinking_source": True,
        "f_other": False, "alerts_only": False, "use_cluster": True,
    }
    for k, v in _ss_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ══════════════════════════════════════════════════════════════════════════
    # SIDEBAR — sliding filter panel
    # ══════════════════════════════════════════════════════════════════════════
    with st.sidebar:
        # Header: title + pin button
        st.markdown(
            f'<div class="fp-header">'
            f'<span class="fp-title">⚙ Фильтры</span>'
            f'{_PIN_BTN_HTML}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── action row: Alerts / Near-me / Reset (icon-only) ─────────────────
        alerts_on = bool(st.session_state.get("alerts_only", False))
        ab_col, nb_col, rb_col = st.columns(3)
        with ab_col:
            if st.button(
                "🚨",
                key="btn_alerts",
                help="Только нарушения / высокий риск",
                type="primary" if alerts_on else "secondary",
                use_container_width=True,
            ):
                st.session_state.alerts_only = not alerts_on
                st.rerun()
        with nb_col:
            # Pure-JS button — no Streamlit rerun needed
            st.markdown(_NEAR_ME_BTN_HTML, unsafe_allow_html=True)
        with rb_col:
            if st.button(
                "↺",
                key="btn_reset",
                help="Сбросить все фильтры",
                type="secondary",
                use_container_width=True,
            ):
                for k in list(_ss_defaults.keys()) + ["county_filter", "color_mode"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

        st.divider()

        # ── color mode ────────────────────────────────────────────────────────
        if has_model and avail_models:
            color_fmt = {
                "official": "Офиц. статус",
                **{m: model_labels.get(m, m) for m in avail_models},
            }
            st.radio(
                "Раскраска",
                options=["official"] + avail_models,
                format_func=lambda x: color_fmt.get(x, x),
                key="color_mode",
            )
        else:
            st.markdown("**Раскраска:** только официальный статус.")

        st.divider()

        # ── place-type checkboxes ─────────────────────────────────────────────
        st.markdown("**Типы мест**")
        st.checkbox(kind_labels.get("swimming",        "🏊 Купание"),         value=True,  key="f_swimming")
        st.checkbox(kind_labels.get("pool_spa",        "🏊 Бассейн / СПА"),   value=True,  key="f_pool_spa")
        st.checkbox(kind_labels.get("drinking_water",  "🚰 Водопровод"),       value=True,  key="f_drinking_water")
        st.checkbox(kind_labels.get("drinking_source", "💧 Источник"),         value=True,  key="f_drinking_source")
        st.checkbox(kind_labels.get("other",           "📍 Прочее"),           value=False, key="f_other")

        st.divider()

        # ── county filter ─────────────────────────────────────────────────────
        all_counties = sorted({
            (str(p.get("county") or "").strip() or "Не указан")
            for p in places
        })
        st.multiselect(
            "Уезд",
            options=all_counties,
            default=[],
            key="county_filter",
            placeholder="Все уезды",
        )

        st.divider()

        # ── clustering ────────────────────────────────────────────────────────
        st.checkbox("Кластеризация маркеров", value=True, key="use_cluster")

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN CONTENT
    # ══════════════════════════════════════════════════════════════════════════
    if has_model:
        models_str = ", ".join(model_labels.get(m, m) for m in avail_models)
        st.caption(T["caption_model"].format(models=models_str))
    else:
        st.caption(T["caption_nomodel"])

    st.info(snap.get("disclaimer", ""))

    n_places = len(places)
    n_approx = sum(1 for p in places if p.get("coord_source") == "approximate_ee")
    if n_places and n_approx / n_places >= 0.2:
        st.warning(
            f"У **{n_approx}** из **{n_places}** точек координаты **приблизительные** "
            f"(`coord_source: approximate_ee`). Пересоберите с `--infer-county` и/или `--geocode-limit …`."
        )

    # ── info-page nav buttons (slim row, right-aligned) ────────────────────
    info_page: str | None = st.session_state.get("info_page")

    st.markdown('<div class="info-nav-row">', unsafe_allow_html=True)
    _spacer, nb1, nb2, nb3 = st.columns([5.5, 1.5, 1.5, 1.5])
    with nb1:
        diag_cls = "info-nav-active" if info_page == "diagnostics" else ""
        st.markdown(f'<div class="{diag_cls}">', unsafe_allow_html=True)
        if st.button(T["nav_diagnostics"], key="btn_diag", use_container_width=True):
            st.session_state["info_page"] = None if info_page == "diagnostics" else "diagnostics"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with nb2:
        model_cls = "info-nav-active" if info_page == "about_model" else ""
        st.markdown(f'<div class="{model_cls}">', unsafe_allow_html=True)
        if st.button(T["nav_about_model"], key="btn_model", use_container_width=True):
            st.session_state["info_page"] = None if info_page == "about_model" else "about_model"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with nb3:
        svc_cls = "info-nav-active" if info_page == "about_service" else ""
        st.markdown(f'<div class="{svc_cls}">', unsafe_allow_html=True)
        if st.button(T["nav_about_service"], key="btn_svc", use_container_width=True):
            st.session_state["info_page"] = None if info_page == "about_service" else "about_service"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── route to info pages ────────────────────────────────────────────────
    if info_page == "diagnostics":
        _render_diagnostics(places, has_model, snap)
        return
    if info_page == "about_model":
        _render_about_model()
        return
    if info_page == "about_service":
        _render_about_service(lang)
        return

    # ── main tabs: Map / Table / Compare ──────────────────────────────────
    tab_map, tab_table, tab_compare = st.tabs(
        [T["tab_map"], T["tab_table"], T["tab_compare"]]
    )

    # ── derive filter state from session_state ─────────────────────────────────
    kinds_filter: set[str] = set()
    if st.session_state.get("f_swimming", True):
        kinds_filter.add("swimming")
    if st.session_state.get("f_pool_spa", True):
        kinds_filter.add("pool_spa")
    if st.session_state.get("f_drinking_water", True):
        kinds_filter.add("drinking_water")
    if st.session_state.get("f_drinking_source", True):
        kinds_filter.add("drinking_source")
    if st.session_state.get("f_other", False):
        kinds_filter.add("other")
    if not kinds_filter:
        kinds_filter.add("swimming")

    # Map "Не указан" label back to the "__none__" key used by _filtered_places
    raw_counties = st.session_state.get("county_filter") or []
    counties_filter: set[str] | None = None
    if raw_counties:
        counties_filter = {"__none__" if c == "Не указан" else c for c in raw_counties}

    use_cluster    = bool(st.session_state.get("use_cluster", True))
    color_mode     = st.session_state.get("color_mode", "official") if (has_model and avail_models) else "official"
    selected_model = color_mode if color_mode != "official" else (avail_models[0] if avail_models else "rf")

    # ── alerts-only pre-filter ────────────────────────────────────────────────
    places_for_map = places
    if st.session_state.get("alerts_only", False) and has_model:
        _pc = MODEL_PROB_COLS.get(selected_model, "rf_violation_prob")
        places_for_map = [
            p for p in places
            if p.get("official_compliant") == 0
            or (isinstance(p.get(_pc), (int, float)) and float(p[_pc]) > 0.5)
        ]

    with tab_map:
        # ── map ───────────────────────────────────────────────────────────────
        debug_enabled    = False
        debug_focus_name: str | None = None

        with st.expander("🛠 Debug: переход к локации", expanded=False):
            debug_enabled = st.checkbox("Включить debug-режим", value=False, key="map_debug_on")
            if debug_enabled:
                opt_list = sorted({
                    str(p.get("location") or "").strip()
                    for p in places
                    if p.get("lat") is not None and str(p.get("location") or "").strip()
                })
                debug_focus_name = st.selectbox(
                    "Локация для проверки",
                    options=opt_list,
                    index=0 if opt_list else None,
                    key="map_debug_loc",
                )
                if st.checkbox("Показывать только выбранную локацию", value=False, key="map_debug_only"):
                    places_for_map = [p for p in places if str(p.get("location") or "") == debug_focus_name]
                if debug_focus_name:
                    for p in places:
                        if str(p.get("location") or "") == debug_focus_name and p.get("lat") is not None:
                            map_center = (float(p["lat"]), float(p["lon"]))
                            map_zoom   = 11
                            st.caption(
                                f"DEBUG: `{debug_focus_name}` "
                                f"({float(p['lat']):.6f}, {float(p['lon']):.6f}), "
                                f"source={p.get('coord_source','?')}"
                            )
                            break

        m_map = build_map(
            places_for_map,
            color_mode,
            kinds_filter,
            use_cluster=use_cluster,
            counties_filter=counties_filter,
            has_model_predictions=has_model,
            available_models=avail_models,
            model_labels=model_labels,
            selected_model=selected_model,
            data_catalog_url=snap.get("data_catalog_url"),
            map_center=map_center,
            map_zoom=map_zoom,
            debug_focus_name=debug_focus_name if debug_enabled else None,
            last_measured_label=T["last_measured"],
        )
        st_folium(m_map, width=None, height=580, returned_objects=[])

        # ── stats row ─────────────────────────────────────────────────────────
        _prob_col      = MODEL_PROB_COLS.get(selected_model, "rf_violation_prob")
        _filtered_vis  = _filtered_places(places_for_map, kinds_filter, counties_filter)
        _stats         = _compute_map_stats(_filtered_vis, _prob_col)
        st.markdown(_render_stats_html(_stats), unsafe_allow_html=True)

        # ── legend ────────────────────────────────────────────────────────────
        if color_mode != "official" and has_model:
            st.markdown(
                f"**Прогноз {model_labels.get(selected_model, selected_model)}:** "
                "🟢 низкий риск — 🔴 высокий риск нарушения. "
                f"Снимок: `{snap.get('generated_at', '?')}`."
            )
        else:
            st.markdown(
                "**Легенда:** 🟢 официально соответствует — 🔴 зафиксировано нарушение. "
                f"Снимок: `{snap.get('generated_at', '?')}`."
            )

    with tab_table:
        search = st.text_input("Поиск по названию места", key="table_search")
        view = df_full.copy()
        if search.strip() and "location" in view.columns:
            view = view[view["location"].astype(str).str.contains(search.strip(), case=False, na=False)]
        pref = [
            "location", "Тип места", "domain", "county", "sample_date", "official_compliant",
            "lr_violation_prob", "rf_violation_prob", "gb_violation_prob", "lgbm_violation_prob",
            "coord_source",
        ]
        if not has_model:
            pref = [c for c in pref if "violation_prob" not in c]
        cols = [c for c in pref if c in view.columns]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        st.caption("Полные измерения и сравнение моделей — во всплывающем окне маркера на карте.")

    with tab_compare:
        _render_model_comparison_tab(places, avail_models, model_labels)

if __name__ == "__main__":
    main()
