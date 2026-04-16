"""
data_loader.py — Загрузка и парсинг данных о качестве воды из vtiav.sm.ee

Источник: Terviseamet (Департамент здоровья Эстонии)
Формат: XML (каталог opendata: * _veeproovid_YYYY.xml)
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests
from lxml import etree

# ── Конфигурация ──────────────────────────────────────────────────────────────

BASE_URL = "https://vtiav.sm.ee/index.php/"

# Старые query-параметры (сайт часто отдаёт HTML-страницу каталога, не сырой XML)
DOMAINS = {
    "supluskoha": "supluskoha_uuringud",
    "veevark": "veevargi_uuringud",
    "basseinid": "basseini_uuringud",
    "joogivesi": "joogiveeallikas_uuringud",
    "mineraalvesi": "mineraalvee_uuringud",
}

# Актуальные полные XML: https://vtiav.sm.ee/index.php/opendata/…
OPENDATA_BASE = "https://vtiav.sm.ee/index.php/opendata/"
OPENDATA_PREFIX = {
    "supluskoha": "supluskoha_veeproovid",
    "veevark": "veevargi_veeproovid",
    "basseinid": "basseini_veeproovid",
    "joogivesi": "joogiveeallika_veeproovid",
    "mineraalvesi": "mineraalvee_veeproovid",
}

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


# ── Загрузка (legacy + opendata) ─────────────────────────────────────────────

def download_xml(domain_key: str, save: bool = True) -> bytes:
    """
    Скачать ответ по старым параметрам area=… (часто это HTML, не данные).
    """
    if domain_key not in DOMAINS:
        raise ValueError(f"Неизвестный домен: {domain_key}. Доступные: {list(DOMAINS.keys())}")

    params = {
        "active_tab_id": "A",
        "lang": "et",
        "type": "xml",
        "area": DOMAINS[domain_key],
    }

    print(f"[data_loader] Скачиваю {domain_key} (legacy URL)...")
    response = requests.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()

    if save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / f"{domain_key}.xml"
        out_path.write_bytes(response.content)
        print(f"[data_loader] Сохранено: {out_path}")

    return response.content


def _looks_like_data_xml(content: bytes) -> bool:
    head = content[:500].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return False
    return b"<proovivott" in content or b"<uuring" in content


def download_opendata_year(domain_key: str, year: int) -> bytes:
    """Скачать один годовой файл opendata XML."""
    if domain_key not in OPENDATA_PREFIX:
        raise ValueError(f"Нет opendata-префикса для: {domain_key}")
    url = f"{OPENDATA_BASE}{OPENDATA_PREFIX[domain_key]}_{year}.xml"
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    if not _looks_like_data_xml(r.content):
        raise ValueError(f"Не похоже на XML проб: {url}")
    return r.content


def default_years() -> List[int]:
    y = datetime.now().year
    return [y - i for i in range(6)]


def load_domain_xml_blobs(
    domain_key: str,
    years: Optional[List[int]] = None,
    use_cache: bool = True,
) -> List[bytes]:
    """Загрузить XML по годам (кэш: data/raw/{domain}_{year}.xml)."""
    if years is None:
        years = default_years()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    blobs: List[bytes] = []

    for year in years:
        path = DATA_DIR / f"{domain_key}_{year}.xml"
        data: Optional[bytes] = None
        if use_cache and path.exists():
            cached = path.read_bytes()
            if _looks_like_data_xml(cached):
                data = cached
                print(f"[data_loader] Кэш: {path.name}")
        if data is None:
            try:
                print(f"[data_loader] Скачиваю {domain_key} за {year}…")
                data = download_opendata_year(domain_key, year)
                path.write_bytes(data)
                print(f"[data_loader] Сохранено: {path}")
            except Exception as e:
                print(f"[data_loader] Год {year} недоступен: {e}")
                continue
        blobs.append(data)

    if not blobs:
        raise RuntimeError(
            f"Не удалось загрузить opendata XML для '{domain_key}'. "
            "Проверьте сеть и наличие файлов на vtiav.sm.ee."
        )
    return blobs


def load_xml(domain_key: str) -> bytes:
    """Один сырой XML (первый доступный год из default_years). Для отладки."""
    return load_domain_xml_blobs(domain_key, years=default_years()[:1], use_cache=True)[0]


# ── Нормализация названий мест ───────────────────────────────────────────────

def normalize_location(name: str, domain: str = "") -> str:
    """
    Нормализовать название места отбора пробы.

    ПРОБЛЕМА (обнаружена при анализе данных апреля 2026):
    Terviseamet переименовывал объекты между годовыми XML файлами. Одно и то же
    физическое место получало разные строки в поле location:

        'Harku järve supluskoht'  (2021) → 'Harku järve rand'  (2025)
        'Haaslava küla veevärk'   (2022) → 'Haaslava küla ühisveevärk'  (2026)
        'Tootsi Ujumisbassein'    (2021) → 'Tootsi ujumisbassein'  (2026, регистр)
        'Abja-Paluoja  veevärk'   (2022) → 'Abja-Paluoja veevärk'  (2026, двойной пробел)

    Без нормализации любая агрегация по location (группировка, дедупликация,
    подсчёт проб на место) даёт ложные дубли: место выглядит как два разных объекта,
    одному из которых годами не берут проб.

    РЕШЕНИЕ: убираем суффиксы типа объекта и нормализуем пунктуацию/регистр.
    Нормализованный ключ используется только для группировки; в DataFrame сохраняется
    оригинальное актуальное название (из последней по дате пробы).

    Применяется:
        - В load_domain() / load_all() — добавляется столбец `location_key`
        - В build_citizen_snapshot.py — для дедупликации последней пробы на место
        - В анализе ноутбуков — для корректного подсчёта уникальных мест

    Args:
        name:   сырое название из XML (поле location в DataFrame)
        domain: домен ('supluskoha', 'veevark', 'basseinid', 'joogivesi') —
                позволяет убирать суффиксы, специфичные для домена

    Returns:
        Нормализованная строка в нижнем регистре без суффиксов типа объекта.
    """
    import re as _re
    n = name.strip().lower()
    # Суффиксы купальных мест (менялись между годами)
    n = _re.sub(r"\bsupluskoht\b", "", n)
    n = _re.sub(r"\bsupluskoha\b", "", n)
    n = _re.sub(r"\brand\b", "", n)
    n = _re.sub(r"\bsuplusala\b", "", n)
    # Суффиксы водопровода
    n = _re.sub(r"\bühistveevärk\b", "", n)
    n = _re.sub(r"\bühisveevärk\b", "", n)
    n = _re.sub(r"\bveevärk\b", "", n)
    n = _re.sub(r"\bveevõrk\b", "", n)
    n = _re.sub(r"\bveevork\b", "", n)
    # Нормализация пунктуации и пробелов
    n = _re.sub(r"[-–—]+", " ", n)
    n = _re.sub(r"[,;]+", " ", n)
    n = _re.sub(r"\s+", " ", n).strip()
    return n


# ── Парсинг: opendata proovivott ────────────────────────────────────────────

def _parse_float_text(val: Optional[str]) -> Optional[float]:
    if val is None:
        return None
    s = val.strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _compliant_from_hinnang(elem: etree._Element) -> Optional[int]:
    """Любой hinnang с «ei vasta» → нарушение (0)."""
    seen = False
    for h in elem.findall(".//hinnang"):
        if not h.text:
            continue
        seen = True
        t = h.text.strip().lower()
        if "ei vasta" in t:
            return 0
    if not seen:
        return None
    return 1


def _compliant_joogiveeallika(elem: etree._Element) -> Optional[int]:
    """
    Источники питьевой воды (joogiveeallika): протокол даёт «Kvaliteediklass I/II/…»
    или «vastab» / «ei vasta» на показателях.
    """
    for h in elem.findall(".//hinnang"):
        if not h.text:
            continue
        t = h.text.strip().lower()
        if "ei vasta" in t:
            return 0

    seen_klass = False
    worst = 1
    for h in elem.findall(".//katseprotokoll/hinnang"):
        if not h.text:
            continue
        tl = h.text.strip().lower()
        if "kvaliteediklass" not in tl:
            continue
        seen_klass = True
        if re.search(r"kvaliteediklass\s+iii\b", tl):
            worst = 0
        elif re.search(r"kvaliteediklass\s+ii\b", tl):
            worst = min(worst, 0)
        elif re.search(r"kvaliteediklass\s+i\b", tl):
            worst = min(worst, 1)
        else:
            worst = min(worst, 0)

    if seen_klass:
        return worst

    return _compliant_from_hinnang(elem)


# Параметры, для которых берётся последнее измерение (не максимум):
# pH, свободный/связанный хлор, прозрачность — диапазонные нормы, max не отражает нарушение.
# Для всех остальных (микробиология, химия) — max: safety-first (худший случай важнее).
_MERGE_LAST_WINS = frozenset({"ph", "free_chlorine", "combined_chlorine", "transparency"})


def _merge_num(
    prev: Optional[float], new: Optional[float], col: Optional[str] = None
) -> Optional[float]:
    """Объединить два измерения одного параметра в одной пробе.

    col in _MERGE_LAST_WINS  → последнее значение (range-параметры: pH, хлор, прозрачность).
    Остальные               → max (safety-first: хуже = важнее для микробиологии/химии).
    """
    if new is None:
        return prev
    if prev is None:
        return new
    if col in _MERGE_LAST_WINS:
        return new
    return max(prev, new)


def _ugl_to_mgl(yhik: Optional[str]) -> bool:
    if not yhik:
        return False
    y = yhik.lower().replace("µ", "u").replace("μ", "u")
    return "ug/l" in y or "µg/l" in y or "μg/l" in y


def _supluskoha_naitaja_col(nimetus: str) -> Optional[str]:
    n = nimetus.lower()
    if "escherichia coli" in n:
        return "e_coli"
    if "coli-laadsed" in n:
        return None
    # "Soole enterokokid" / "Enterokokid" / "Enterokokkid" / "intestinal enterococci"
    if "enterokoki" in n or "enterokokk" in n or "enterococc" in n or "enterokokid" in n:
        return "enterococci"
    if re.match(r"^ph\b", n) or n.startswith("ph "):
        return "ph"
    if "läbipaistvus" in n or "labipaistvus" in n:
        return "transparency"
    return None


def _parse_supluskoha_opendata(tree: etree._Element) -> pd.DataFrame:
    records = []
    for pv in tree.findall(".//proovivott"):
        facility = (_text(pv, "supluskoht") or "").strip()
        site = _proovivotukoht_nimetus(pv)
        loc = facility or site
        rec = {
            "domain": "supluskoha",
            "sample_id": _text(pv, "id"),
            "proovivotukoht_id": _proovivotukoht_id(pv),
            "supluskoht_id": _text(pv, "supluskoht_id"),
            "location": loc,
            "geocode_facility": facility,
            "geocode_site": site,
            "county": _text(pv, "maakond"),
            "sample_date": _text(pv, "proovivotu_aeg"),
        }
        for k in ("e_coli", "enterococci", "ph", "transparency"):
            rec[k] = None

        for n_el in pv.findall(".//naitaja"):
            nm = _text(n_el, "nimetus")
            if not nm:
                continue
            col = _supluskoha_naitaja_col(nm)
            if not col:
                continue
            val = _parse_float_text(_text(n_el, "sisaldus"))
            rec[col] = _merge_num(rec[col], val, col)

        rec["compliant"] = _compliant_from_hinnang(pv)
        records.append(rec)

    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["sample_date"] = pd.to_datetime(df["sample_date"], dayfirst=True, errors="coerce")
    for col in ("e_coli", "enterococci", "ph", "transparency"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _veevark_naitaja_col(nimetus: str) -> Optional[str]:
    n = nimetus.lower()
    if "escherichia coli" in n:
        return "e_coli"
    if "coli-laadsed" in n:
        return "coliforms"
    # "Soole enterokokid" / "Enterokokid" / "Enterokokkid"
    if "enterokoki" in n or "enterokokk" in n or "enterococc" in n or "enterokokid" in n:
        return "enterococci"
    if "nitraat" in n and "nitrit" not in n:
        return "nitrates"
    if "nitrit" in n:
        return "nitrites"
    if "ammoonium" in n or "amiin" in n:
        return "ammonium"
    if "fluoriid" in n:
        return "fluoride"
    if "mangaan" in n:
        return "manganese"
    # "Raud" / "Üldraud" — exclude "kloriid" to avoid "raudkloriid" false match
    if "raud" in n and "kloriid" not in n:
        return "iron"
    if "hägusus" in n or "hagusus" in n:
        return "turbidity"
    if "värvus" in n and ("pt" in n or "kraadid" in n):
        return "color"
    if "kloriid" in n and "sulfaat" not in n:
        return "chlorides"
    if "sulfaat" in n:
        return "sulfates"
    if re.match(r"^ph\b", n) or n.startswith("ph "):
        return "ph"
    return None


def _parse_veevark_opendata(tree: etree._Element) -> pd.DataFrame:
    records = []
    for pv in tree.findall(".//proovivott"):
        facility = (_text(pv, "veevark") or "").strip()
        site = _proovivotukoht_nimetus(pv)
        loc = facility or site or ""
        rec = {
            "domain": "veevark",
            "sample_id": _text(pv, "id"),
            "proovivotukoht_id": _proovivotukoht_id(pv),
            "veevark_id": _text(pv, "veevark_id"),
            "location": loc,
            "geocode_facility": facility,
            "geocode_site": site,
            "county": _text(pv, "maakond"),
            "sample_date": _text(pv, "proovivotu_aeg"),
        }
        keys = (
            "e_coli", "coliforms", "enterococci", "nitrates", "nitrites",
            "ammonium", "fluoride", "manganese", "iron", "chlorides",
            "sulfates", "ph", "turbidity", "color",
        )
        for k in keys:
            rec[k] = None

        for n_el in pv.findall(".//naitaja"):
            nm = _text(n_el, "nimetus")
            if not nm:
                continue
            col = _veevark_naitaja_col(nm)
            if not col:
                continue
            val = _parse_float_text(_text(n_el, "sisaldus"))
            yhik = _text(n_el, "yhik")
            if col in ("iron", "manganese") and _ugl_to_mgl(yhik):
                val = val / 1000.0 if val is not None else None
            rec[col] = _merge_num(rec[col], val, col)

        rec["compliant"] = _compliant_from_hinnang(pv)
        records.append(rec)

    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["sample_date"] = pd.to_datetime(df["sample_date"], dayfirst=True, errors="coerce")
    num_cols = [
        "e_coli", "coliforms", "enterococci", "nitrates", "nitrites",
        "ammonium", "fluoride", "manganese", "iron", "chlorides",
        "sulfates", "ph", "turbidity", "color",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _parse_mineraalvesi_opendata(tree: etree._Element) -> pd.DataFrame:
    """
    Opendata: корень mineraalvee_veeproovid (если доступен), структура близка к veevärk.
    Поддерживаем несколько вариантов названий полей объекта.
    """
    records = []
    for pv in tree.findall(".//proovivott"):
        facility = (
            _text(pv, "mineraalvesi")
            or _text(pv, "mineraalvesi_asutus")
            or _text(pv, "veevark")
            or _text(pv, "veeallikas")
            or ""
        ).strip()
        site = _proovivotukoht_nimetus(pv)
        loc = facility or site or ""
        rec = {
            "domain": "mineraalvesi",
            "sample_id": _text(pv, "id"),
            "proovivotukoht_id": _proovivotukoht_id(pv),
            "mineraalvesi_id": _text(pv, "mineraalvesi_id") or _text(pv, "veevark_id"),
            "location": loc,
            "geocode_facility": facility,
            "geocode_site": site,
            "county": _text(pv, "maakond"),
            "sample_date": _text(pv, "proovivotu_aeg"),
        }
        keys = (
            "e_coli", "coliforms", "enterococci", "nitrates", "nitrites",
            "ammonium", "fluoride", "manganese", "iron", "chlorides",
            "sulfates", "ph", "turbidity", "color",
        )
        for k in keys:
            rec[k] = None

        for n_el in pv.findall(".//naitaja"):
            nm = _text(n_el, "nimetus")
            if not nm:
                continue
            col = _veevark_naitaja_col(nm)
            if not col:
                continue
            val = _parse_float_text(_text(n_el, "sisaldus"))
            yhik = _text(n_el, "yhik")
            if col in ("iron", "manganese") and _ugl_to_mgl(yhik):
                val = val / 1000.0 if val is not None else None
            rec[col] = _merge_num(rec[col], val, col)

        rec["compliant"] = _compliant_from_hinnang(pv)
        records.append(rec)

    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["sample_date"] = pd.to_datetime(df["sample_date"], dayfirst=True, errors="coerce")
    num_cols = [
        "e_coli", "coliforms", "enterococci", "nitrates", "nitrites",
        "ammonium", "fluoride", "manganese", "iron", "chlorides",
        "sulfates", "ph", "turbidity", "color",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _basseinid_naitaja_col(nimetus: str) -> Optional[str]:
    """Маппинг эстонских названий показателей бассейна → колонки DataFrame."""
    n = nimetus.strip().lower()
    if "escherichia coli" in n:
        return "e_coli"
    if "coli-laadsed" in n:
        return "coliforms"
    if "enterokok" in n:
        return "enterococci"
    if "pseudomonas" in n:
        return "pseudomonas"
    if "stafül" in n or "staphylococcus" in n:
        return "staphylococci"
    if "kolooniate arv" in n:
        return "colonies_37c"
    if "nitraatioon" in n:
        return "nitrates"
    if "oksüdeeritavus" in n or "oksudeeritavus" in n:
        return "oxidizability"
    if "vaba kloor" in n:
        return "free_chlorine"
    if "seotud kloor" in n:
        return "combined_chlorine"
    if "hägusus" in n or "hagusus" in n:
        return "turbidity"
    if "värvus" in n:
        return "color"
    if "ammoonium" in n:
        return "ammonium"
    if re.match(r"^ph\b", n) or n.startswith("ph "):
        return "ph"
    return None


def _parse_basseinid_opendata(tree: etree._Element) -> pd.DataFrame:
    """Opendata: корень basseini_veeproovid, записи proovivott (бассейны, SPA)."""
    records = []
    for pv in tree.findall(".//proovivott"):
        facility = (_text(pv, "bassein") or "").strip()
        site = _proovivotukoht_nimetus(pv)
        loc = facility or site or _text(pv.find("proovivotukoht"), "nimetus")
        rec = {
            "domain": "basseinid",
            "sample_id": _text(pv, "id"),
            "proovivotukoht_id": _proovivotukoht_id(pv),
            "bassein_id": _text(pv, "bassein_id"),
            "location": loc,
            "geocode_facility": facility,
            "geocode_site": site,
            "county": _text(pv, "maakond"),
            "sample_date": _text(pv, "proovivotu_aeg"),
        }
        keys = (
            "e_coli", "coliforms", "enterococci", "ph", "turbidity", "color",
            "ammonium", "nitrates", "pseudomonas", "staphylococci",
            "free_chlorine", "combined_chlorine", "oxidizability", "colonies_37c",
        )
        for k in keys:
            rec[k] = None

        for n_el in pv.findall(".//naitaja"):
            nm = _text(n_el, "nimetus")
            if not nm:
                continue
            col = _basseinid_naitaja_col(nm)
            if not col:
                continue
            val = _parse_float_text(_text(n_el, "sisaldus"))
            yhik = _text(n_el, "yhik")
            if col in ("iron", "manganese") and _ugl_to_mgl(yhik):
                val = val / 1000.0 if val is not None else None
            rec[col] = _merge_num(rec[col], val, col)

        rec["compliant"] = _compliant_from_hinnang(pv)
        records.append(rec)

    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["sample_date"] = pd.to_datetime(df["sample_date"], dayfirst=True, errors="coerce")
    num_cols = [
        "e_coli", "coliforms", "enterococci", "ph", "turbidity", "color",
        "ammonium", "nitrates", "pseudomonas", "staphylococci",
        "free_chlorine", "combined_chlorine", "oxidizability", "colonies_37c",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _parse_joogiveeallika_opendata(tree: etree._Element) -> pd.DataFrame:
    """Opendata: корень joogiveeallika_veeproovid — структура как у veevärk (proovivott + naitaja)."""
    records = []
    for pv in tree.findall(".//proovivott"):
        src = (_text(pv, "veeallikas") or "").strip()
        spot = _proovivotukoht_nimetus(pv)
        if src and spot:
            loc = f"{src} — {spot}"
        else:
            loc = src or spot or ""
        rec = {
            "domain": "joogivesi",
            "sample_id": _text(pv, "id"),
            "proovivotukoht_id": _proovivotukoht_id(pv),
            "veeallikas_id": _text(pv, "veeallikas_id"),
            "location": loc,
            "geocode_facility": src,
            "geocode_site": spot,
            "county": _text(pv, "maakond"),
            "sample_date": _text(pv, "proovivotu_aeg"),
        }
        keys = (
            "e_coli", "coliforms", "enterococci", "nitrates", "nitrites",
            "ammonium", "fluoride", "manganese", "iron", "chlorides",
            "sulfates", "ph", "turbidity", "color",
        )
        for k in keys:
            rec[k] = None

        for n_el in pv.findall(".//naitaja"):
            nm = _text(n_el, "nimetus")
            if not nm:
                continue
            col = _veevark_naitaja_col(nm)
            if not col:
                continue
            val = _parse_float_text(_text(n_el, "sisaldus"))
            yhik = _text(n_el, "yhik")
            if col in ("iron", "manganese") and _ugl_to_mgl(yhik):
                val = val / 1000.0 if val is not None else None
            rec[col] = _merge_num(rec[col], val, col)

        rec["compliant"] = _compliant_joogiveeallika(pv)
        records.append(rec)

    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["sample_date"] = pd.to_datetime(df["sample_date"], dayfirst=True, errors="coerce")
    num_cols = [
        "e_coli", "coliforms", "enterococci", "nitrates", "nitrites",
        "ammonium", "fluoride", "manganese", "iron", "chlorides",
        "sulfates", "ph", "turbidity", "color",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def parse_basseinid(xml_bytes: bytes) -> pd.DataFrame:
    tree = etree.fromstring(xml_bytes)
    root_tag = etree.QName(tree).localname
    if root_tag == "basseini_veeproovid":
        return _parse_basseinid_opendata(tree)
    return pd.DataFrame()


# ── Парсинг: старый формат (uuring) ─────────────────────────────────────────

def _parse_supluskoha_legacy(tree: etree._Element) -> pd.DataFrame:
    records = []
    for uuring in tree.findall(".//uuring"):
        record = {
            "domain": "supluskoha",
            "sample_id": _text(uuring, "id"),
            "location": _text(uuring, "koht") or _text(uuring, "asukoht"),
            "county": _text(uuring, "maakond"),
            "sample_date": _text(uuring, "kuupaev") or _text(uuring, "proovivotmise_kuupaev"),
            "e_coli": _float(uuring, ".//naiturid_e_coli/vaartus"),
            "enterococci": _float(uuring, ".//naiturid_enterokokid/vaartus"),
            "ph": _float(uuring, ".//naiturid_ph/vaartus"),
            "transparency": _float(uuring, ".//naiturid_labipaistvus/vaartus"),
        }
        vastavused = [v.text for v in uuring.findall(".//vastavus") if v.text]
        if not vastavused:
            record["compliant"] = None
        elif any(v.lower() == "ei" for v in vastavused):
            record["compliant"] = 0
        else:
            record["compliant"] = 1
        records.append(record)
    df = pd.DataFrame(records)
    if len(df) and "sample_date" in df.columns:
        df["sample_date"] = pd.to_datetime(df["sample_date"], errors="coerce")
    return df


def _parse_veevark_legacy(tree: etree._Element) -> pd.DataFrame:
    records = []
    for uuring in tree.findall(".//uuring"):
        record = {
            "domain": "veevark",
            "sample_id": _text(uuring, "id"),
            "location": _text(uuring, "asukoht") or _text(uuring, "koht"),
            "county": _text(uuring, "maakond"),
            "sample_date": _text(uuring, "kuupaev") or _text(uuring, "proovivotmise_kuupaev"),
            "e_coli": _float(uuring, ".//e_coli/vaartus"),
            "coliforms": _float(uuring, ".//koliformid/vaartus"),
            "enterococci": _float(uuring, ".//enterokokid/vaartus"),
            "nitrates": _float(uuring, ".//nitraadid/vaartus"),
            "nitrites": _float(uuring, ".//nitritid/vaartus"),
            "ammonium": _float(uuring, ".//ammoonium/vaartus"),
            "fluoride": _float(uuring, ".//fluoriid/vaartus"),
            "manganese": _float(uuring, ".//mangaan/vaartus"),
            "iron": _float(uuring, ".//raud/vaartus"),
            "chlorides": _float(uuring, ".//kloriidid/vaartus"),
            "sulfates": _float(uuring, ".//sulfaadid/vaartus"),
            "ph": _float(uuring, ".//ph/vaartus"),
            "turbidity": _float(uuring, ".//hägusus/vaartus"),
            "color": _float(uuring, ".//varvus/vaartus"),
        }
        vastavused = [v.text for v in uuring.findall(".//vastavus") if v.text]
        if not vastavused:
            record["compliant"] = None
        elif any(v.lower() == "ei" for v in vastavused):
            record["compliant"] = 0
        else:
            record["compliant"] = 1
        records.append(record)
    df = pd.DataFrame(records)
    if len(df) and "sample_date" in df.columns:
        df["sample_date"] = pd.to_datetime(df["sample_date"], errors="coerce")
    return df


# ── Публичные parse_* (автоопределение схемы) ─────────────────────────────────

def parse_supluskoha(xml_bytes: bytes) -> pd.DataFrame:
    tree = etree.fromstring(xml_bytes)
    root_tag = etree.QName(tree).localname
    if root_tag == "supluskoha_veeproovid":
        return _parse_supluskoha_opendata(tree)
    if tree.findall(".//uuring"):
        return _parse_supluskoha_legacy(tree)
    return pd.DataFrame()


def parse_veevark(xml_bytes: bytes) -> pd.DataFrame:
    tree = etree.fromstring(xml_bytes)
    root_tag = etree.QName(tree).localname
    if root_tag == "veevargi_veeproovid":
        return _parse_veevark_opendata(tree)
    if tree.findall(".//uuring"):
        return _parse_veevark_legacy(tree)
    return pd.DataFrame()


def parse_joogivesi(xml_bytes: bytes) -> pd.DataFrame:
    tree = etree.fromstring(xml_bytes)
    root_tag = etree.QName(tree).localname
    if root_tag == "joogiveeallika_veeproovid":
        return _parse_joogiveeallika_opendata(tree)
    return pd.DataFrame()


def parse_mineraalvesi(xml_bytes: bytes) -> pd.DataFrame:
    tree = etree.fromstring(xml_bytes)
    root_tag = etree.QName(tree).localname
    if root_tag == "mineraalvee_veeproovid":
        return _parse_mineraalvesi_opendata(tree)
    if tree.findall(".//uuring"):
        df = _parse_veevark_legacy(tree)
        if len(df):
            df["domain"] = "mineraalvesi"
        return df
    return pd.DataFrame()


# ── Универсальная загрузка ───────────────────────────────────────────────────

PARSERS = {
    "supluskoha": parse_supluskoha,
    "veevark": parse_veevark,
    "basseinid": parse_basseinid,
    "joogivesi": parse_joogivesi,
    "mineraalvesi": parse_mineraalvesi,
}


def load_domain(
    domain_key: str,
    use_cache: bool = True,
    years: Optional[List[int]] = None,
    infer_county: bool = True,
    geocode_county: bool = False,
    geocode_limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Загрузить домен: несколько годов opendata, объединить в один DataFrame.

    Параметры:
        domain_key: supluskoha | veevark | basseinid | joogivesi | mineraalvesi
        use_cache: читать data/raw/{domain}_{year}.xml
        years: список лет (по умолчанию текущий и 5 предыдущих)
        infer_county: заполнить пустой maakond из overrides + кэша (+ опционально OpenCage)
        geocode_county: HTTP к OpenCage (медленно; см. geocode_limit; ключ OPENCAGE_API_KEY из env)
        geocode_limit: макс. новых геозапросов за вызов (None по умолчанию = все отсутствующие в кэше; для лимита укажите число)
    """
    if domain_key not in PARSERS:
        raise NotImplementedError(
            f"Парсер для '{domain_key}' ещё не реализован. "
            f"Реализовано: {list(PARSERS.keys())}"
        )

    blobs = load_domain_xml_blobs(domain_key, years=years, use_cache=use_cache)
    parts = [PARSERS[domain_key](b) for b in blobs]
    parts = [p for p in parts if len(p) > 0]
    if not parts:
        df = pd.DataFrame()
    else:
        df = pd.concat(parts, ignore_index=True)

    # Нормализованный ключ места: убирает суффиксы типа объекта и нормализует
    # пунктуацию/регистр, чтобы 'Harku järve supluskoht' и 'Harku järve rand'
    # считались одним местом при агрегации. Подробности: normalize_location().
    if len(df) > 0 and "location" in df.columns:
        df["location_key"] = df["location"].fillna("").apply(
            lambda s: normalize_location(s, domain_key)
        )

    if len(df) > 0 and domain_key in ("supluskoha", "veevark", "basseinid", "joogivesi", "mineraalvesi"):
        from terviseamet_reference_coords import attach_official_coords_to_df

        df = attach_official_coords_to_df(df, domain_key, use_cache=use_cache)

    print(
        f"[data_loader] {domain_key}: {len(df)} проб, "
        f"{df['compliant'].notna().sum() if len(df) else 0} с известным статусом"
    )
    if infer_county and len(df) > 0:
        from county_infer import enrich_county_column

        df = enrich_county_column(
            df,
            geocode=geocode_county,
            geocode_limit=geocode_limit,
            opencage_api_key=(
                (os.environ.get("OPENCAGE_API_KEY") or "").strip() or None
                if geocode_county
                else None
            ),
        )
    return df


def load_all(
    domains: Optional[list] = None,
    use_cache: bool = True,
    infer_county: bool = True,
    geocode_county: bool = False,
    geocode_limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Загрузить несколько доменов и объединить в один DataFrame.

    infer_county выполняется один раз по объединённой таблице. При geocode_county=True и
    geocode_limit=None (по умолчанию) к OpenCage идут все уникальные локации без county в кэше.
    """
    if domains is None:
        domains = ["supluskoha", "veevark", "basseinid", "joogivesi"]

    dfs = []
    for domain_key in domains:
        try:
            df = load_domain(
                domain_key,
                use_cache=use_cache,
                infer_county=False,
            )
            dfs.append(df)
        except Exception as e:
            print(f"[data_loader] ОШИБКА при загрузке {domain_key}: {e}")

    if not dfs:
        raise RuntimeError("Не удалось загрузить ни один домен.")

    combined = pd.concat(dfs, ignore_index=True)
    print(f"[data_loader] Итого: {len(combined)} проб из {len(dfs)} доменов")
    if infer_county and len(combined) > 0:
        from county_infer import enrich_county_column

        combined = enrich_county_column(
            combined,
            geocode=geocode_county,
            geocode_limit=geocode_limit,
            opencage_api_key=(
                (os.environ.get("OPENCAGE_API_KEY") or "").strip() or None
                if geocode_county
                else None
            ),
        )
    return combined


def save_combined_csv(df: pd.DataFrame, filename: str = "raw_combined.csv") -> Path:
    """Сохранить объединённый DataFrame в data/processed/."""
    out_dir = Path(__file__).parent.parent / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    df.to_csv(path, index=False)
    print(f"[data_loader] Сохранено: {path}")
    return path


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _text(element: Optional[etree._Element], path: str) -> Optional[str]:
    if element is None:
        return None
    found = element.find(path)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _float(element: etree._Element, path: str) -> Optional[float]:
    val = _text(element, path)
    if val is None:
        return None
    val = val.replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return None


def _proovivotukoht_nimetus(pv: etree._Element) -> str:
    """Название места отбора пробы (proovivotukoht/nimetus), если есть в XML."""
    pk = pv.find("proovivotukoht")
    if pk is None:
        return ""
    t = _text(pk, "nimetus")
    return (t or "").strip()


def _proovivotukoht_id(pv: etree._Element) -> Optional[str]:
    """Идентификатор proovivotukoht (для джойна со справочником координат Terviseamet)."""
    pk = pv.find("proovivotukoht")
    if pk is None:
        return None
    return _text(pk, "id")


# ── Быстрая проверка ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Тест загрузки: supluskoha")
    df = load_domain("supluskoha")
    print(df.head())
    print(f"\nФормат: {df.shape}")
    print(f"\nРаспределение compliant:\n{df['compliant'].value_counts()}")
