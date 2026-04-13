"""
data_loader.py — Загрузка и парсинг данных о качестве воды из vtiav.sm.ee

Источник: Terviseamet (Департамент здоровья Эстонии)
Формат: XML
"""

import os
import requests
import pandas as pd
from lxml import etree
from pathlib import Path
from typing import Optional

# ── Конфигурация ──────────────────────────────────────────────────────────────

BASE_URL = "https://vtiav.sm.ee/index.php/"

DOMAINS = {
    "supluskoha": "supluskoha_uuringud",      # места для купания
    "veevark":    "veevargi_uuringud",         # водопроводная вода
    "basseinid":  "basseini_uuringud",         # бассейны
    "joogivesi":  "joogiveeallikas_uuringud",  # источники питьевой воды
    "mineraalvesi": "mineraalvee_uuringud",    # минеральная вода
}

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


# ── Загрузка XML ──────────────────────────────────────────────────────────────

def download_xml(domain_key: str, save: bool = True) -> bytes:
    """
    Скачать XML по ключу домена.

    Параметры:
        domain_key: ключ из DOMAINS ('supluskoha', 'veevark', ...)
        save: сохранять ли в data/raw/

    Возвращает:
        bytes — сырой XML
    """
    if domain_key not in DOMAINS:
        raise ValueError(f"Неизвестный домен: {domain_key}. Доступные: {list(DOMAINS.keys())}")

    params = {
        "active_tab_id": "A",
        "lang": "et",
        "type": "xml",
        "area": DOMAINS[domain_key]
    }

    print(f"[data_loader] Скачиваю {domain_key}...")
    response = requests.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()

    if save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / f"{domain_key}.xml"
        out_path.write_bytes(response.content)
        print(f"[data_loader] Сохранено: {out_path}")

    return response.content


def load_xml(domain_key: str) -> bytes:
    """
    Загрузить XML — сначала из кэша, если нет — скачать.
    """
    cached = DATA_DIR / f"{domain_key}.xml"
    if cached.exists():
        print(f"[data_loader] Загружаю из кэша: {cached}")
        return cached.read_bytes()
    return download_xml(domain_key, save=True)


# ── Парсинг: Supluskohad (места для купания) ─────────────────────────────────

def parse_supluskoha(xml_bytes: bytes) -> pd.DataFrame:
    """
    Парсить XML для домена supluskohad.

    Возвращает DataFrame с колонками:
        sample_id, location, county, sample_date,
        e_coli, enterococci, ph, transparency,
        compliant (1/0)
    """
    tree = etree.fromstring(xml_bytes)
    records = []

    for uuring in tree.findall(".//uuring"):
        record = {
            "domain": "supluskoha",
            "sample_id": _text(uuring, "id"),
            "location":  _text(uuring, "koht") or _text(uuring, "asukoht"),
            "county":    _text(uuring, "maakond"),
            "sample_date": _text(uuring, "kuupaev") or _text(uuring, "proovivotmise_kuupaev"),
        }

        # Числовые параметры
        record["e_coli"]       = _float(uuring, ".//naiturid_e_coli/vaartus")
        record["enterococci"]  = _float(uuring, ".//naiturid_enterokokid/vaartus")
        record["ph"]           = _float(uuring, ".//naiturid_ph/vaartus")
        record["transparency"] = _float(uuring, ".//naiturid_labipaistvus/vaartus")

        # Целевая переменная: vastavus = 'jah' → compliant=1, 'ei' → compliant=0
        # Смотрим все vastavus в записи — если хоть один 'ei' → нарушение
        vastavused = [v.text for v in uuring.findall(".//vastavus") if v.text]
        if not vastavused:
            record["compliant"] = None  # неизвестно
        elif any(v.lower() == "ei" for v in vastavused):
            record["compliant"] = 0
        else:
            record["compliant"] = 1

        records.append(record)

    df = pd.DataFrame(records)
    df["sample_date"] = pd.to_datetime(df["sample_date"], errors="coerce")
    return df


# ── Парсинг: Veevärk (водопроводная вода) ────────────────────────────────────

def parse_veevark(xml_bytes: bytes) -> pd.DataFrame:
    """
    Парсить XML для домена veevargi_uuringud.
    Богатый набор параметров: микробиология + химия + физика.
    """
    tree = etree.fromstring(xml_bytes)
    records = []

    for uuring in tree.findall(".//uuring"):
        record = {
            "domain": "veevark",
            "sample_id":   _text(uuring, "id"),
            "location":    _text(uuring, "asukoht") or _text(uuring, "koht"),
            "county":      _text(uuring, "maakond"),
            "sample_date": _text(uuring, "kuupaev") or _text(uuring, "proovivotmise_kuupaev"),
        }

        # Микробиологические параметры
        record["e_coli"]         = _float(uuring, ".//e_coli/vaartus")
        record["coliforms"]      = _float(uuring, ".//koliformid/vaartus")
        record["enterococci"]    = _float(uuring, ".//enterokokid/vaartus")

        # Химические параметры
        record["nitrates"]       = _float(uuring, ".//nitraadid/vaartus")
        record["nitrites"]       = _float(uuring, ".//nitritid/vaartus")
        record["ammonium"]       = _float(uuring, ".//ammoonium/vaartus")
        record["fluoride"]       = _float(uuring, ".//fluoriid/vaartus")
        record["manganese"]      = _float(uuring, ".//mangaan/vaartus")
        record["iron"]           = _float(uuring, ".//raud/vaartus")
        record["chlorides"]      = _float(uuring, ".//kloriidid/vaartus")
        record["sulfates"]       = _float(uuring, ".//sulfaadid/vaartus")

        # Физические параметры
        record["ph"]             = _float(uuring, ".//ph/vaartus")
        record["turbidity"]      = _float(uuring, ".//hägusus/vaartus")
        record["color"]          = _float(uuring, ".//varvus/vaartus")

        # Целевая переменная
        vastavused = [v.text for v in uuring.findall(".//vastavus") if v.text]
        if not vastavused:
            record["compliant"] = None
        elif any(v.lower() == "ei" for v in vastavused):
            record["compliant"] = 0
        else:
            record["compliant"] = 1

        records.append(record)

    df = pd.DataFrame(records)
    df["sample_date"] = pd.to_datetime(df["sample_date"], errors="coerce")
    return df


# ── Универсальная загрузка ────────────────────────────────────────────────────

PARSERS = {
    "supluskoha": parse_supluskoha,
    "veevark":    parse_veevark,
}


def load_domain(domain_key: str, use_cache: bool = True) -> pd.DataFrame:
    """
    Загрузить домен как DataFrame.

    Параметры:
        domain_key: ключ из DOMAINS
        use_cache: использовать кэшированный XML если есть

    Возвращает:
        pd.DataFrame
    """
    if domain_key not in PARSERS:
        raise NotImplementedError(
            f"Парсер для '{domain_key}' ещё не реализован. "
            f"Реализовано: {list(PARSERS.keys())}"
        )

    xml = load_xml(domain_key) if use_cache else download_xml(domain_key)
    df = PARSERS[domain_key](xml)
    print(f"[data_loader] {domain_key}: {len(df)} проб, "
          f"{df['compliant'].notna().sum()} с известным статусом")
    return df


def load_all(domains: Optional[list] = None, use_cache: bool = True) -> pd.DataFrame:
    """
    Загрузить несколько доменов и объединить в один DataFrame.

    Параметры:
        domains: список ключей (по умолчанию ['supluskoha', 'veevark'])
        use_cache: использовать кэш

    Возвращает:
        pd.DataFrame — объединённый датасет
    """
    if domains is None:
        domains = ["supluskoha", "veevark"]

    dfs = []
    for domain_key in domains:
        try:
            df = load_domain(domain_key, use_cache=use_cache)
            dfs.append(df)
        except Exception as e:
            print(f"[data_loader] ОШИБКА при загрузке {domain_key}: {e}")

    if not dfs:
        raise RuntimeError("Не удалось загрузить ни один домен.")

    combined = pd.concat(dfs, ignore_index=True)
    print(f"[data_loader] Итого: {len(combined)} проб из {len(dfs)} доменов")
    return combined


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _text(element, path: str) -> Optional[str]:
    """Безопасное извлечение текста по XPath."""
    found = element.find(path)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _float(element, path: str) -> Optional[float]:
    """Безопасное извлечение числа по XPath."""
    val = _text(element, path)
    if val is None:
        return None
    # Заменить запятую на точку (эстонский формат чисел)
    val = val.replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return None


# ── Быстрая проверка ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Тест загрузки: supluskohad")
    df = load_domain("supluskoha")
    print(df.head())
    print(f"\nФормат: {df.shape}")
    print(f"\nРаспределение compliant:\n{df['compliant'].value_counts()}")
