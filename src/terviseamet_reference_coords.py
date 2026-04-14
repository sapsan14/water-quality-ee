"""
Координаты из справочных XML Terviseamet (opendata), не из файлов *_veeproovid_YYYY.

В XML Terviseamet в блоке koordinaadid традиционно:
  <x>…</x> — север (northing, ~6.5e6 м),
  <y>…</y> — восток (easting, ~5e5 м)
в системе EPSG:3301 (L-EST97). В pyproj для EPSG:3301 ожидается порядок (easting, northing),
поэтому преобразование: transform(y, x).

Файлы (кэш в data/raw/):
  supluskohad.xml, veevargid.xml, basseinid.xml, joogiveeallikad.xml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests
from lxml import etree

_log = logging.getLogger(__name__)

OPENDATA_BASE = "https://vtiav.sm.ee/index.php/opendata/"
DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

REF_FILES = {
    "supluskohad": "supluskohad.xml",
    "veevargid": "veevargid.xml",
    "basseinid": "basseinid.xml",
    "joogiveeallikad": "joogiveeallikad.xml",
}


def _text(elem: Optional[etree._Element], path: str) -> Optional[str]:
    if elem is None:
        return None
    found = elem.find(path)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _first_xy_from_koordinaadid(k_root: Optional[etree._Element]) -> Optional[Tuple[float, float]]:
    """Первый koordinaat: x (N), y (E) как float."""
    if k_root is None:
        return None
    kc = k_root.find("koordinaat")
    if kc is None:
        return None
    xs = _text(kc, "x")
    ys = _text(kc, "y")
    if not xs or not ys:
        return None
    try:
        x = float(xs.replace(",", "."))
        y = float(ys.replace(",", "."))
    except ValueError:
        return None
    return x, y


def est_xml_xy_to_wgs84(x_north: float, y_east: float) -> Tuple[float, float]:
    """
    x,y из XML (север, восток в метрах L-EST97) → (lat, lon) WGS84.
    """
    try:
        from pyproj import Transformer
    except ImportError as e:
        raise RuntimeError("Нужен пакет pyproj: pip install pyproj") from e
    tr = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(y_east, x_north)
    return float(lat), float(lon)


def _wgs_from_koord_elem(k_root: Optional[etree._Element]) -> Optional[Tuple[float, float]]:
    xy = _first_xy_from_koordinaadid(k_root)
    if xy is None:
        return None
    xn, ye = xy
    try:
        return est_xml_xy_to_wgs84(xn, ye)
    except Exception as e:
        _log.debug("Координаты: пропуск пары %s,%s: %s", xn, ye, e)
        return None


@dataclass
class ReferenceCoordIndex:
    """Индексы id → (lat, lon) для джойна с пробами."""

    supluskoht_by_pt: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    supluskoht_by_sk: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    veevark_by_pt: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    veevark_by_vv: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    bassein_by_pt: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    bassein_by_bs: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    joogi_by_allikas: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    joogi_by_pt: Dict[str, Tuple[float, float]] = field(default_factory=dict)


def _download_ref(cache_name: str, use_cache: bool, session: Optional[requests.Session]) -> bytes:
    fname = REF_FILES[cache_name]
    path = DATA_RAW / f"ref_{fname}"
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    if use_cache and path.is_file() and path.stat().st_size > 500:
        return path.read_bytes()
    url = OPENDATA_BASE + fname
    _log.info("Скачиваю справочник координат: %s", url)
    sess = session or requests.Session()
    r = sess.get(url, timeout=120)
    r.raise_for_status()
    path.write_bytes(r.content)
    return r.content


def build_reference_index(use_cache: bool = True, session: Optional[requests.Session] = None) -> ReferenceCoordIndex:
    idx = ReferenceCoordIndex()
    for key in REF_FILES:
        try:
            raw = _download_ref(key, use_cache, session)
        except (requests.RequestException, OSError, ValueError) as e:
            _log.warning("Справочник %s недоступен: %s", key, e)
            continue
        tree = etree.fromstring(raw)
        tag = etree.QName(tree).localname
        if key == "supluskohad" and tag == "supluskohad":
            for sk in tree.findall("supluskoht"):
                sid = (_text(sk, "id") or "").strip()
                wgs = _wgs_from_koord_elem(sk.find("koordinaadid"))
                if sid and wgs:
                    idx.supluskoht_by_sk[sid] = wgs
                for pk in sk.findall("./proovivotukohad/proovivotukoht"):
                    pid = (_text(pk, "id") or "").strip()
                    wgs2 = _wgs_from_koord_elem(pk.find("koordinaadid"))
                    if pid and wgs2:
                        idx.supluskoht_by_pt[pid] = wgs2
        elif key == "veevargid" and tag == "veevargid":
            for vv in tree.findall("veevark"):
                vid = (_text(vv, "id") or "").strip()
                wgs = _wgs_from_koord_elem(vv.find("koordinaadid"))
                if vid and wgs:
                    idx.veevark_by_vv[vid] = wgs
                for pk in vv.findall("./proovivotukohad/proovivotukoht"):
                    pid = (_text(pk, "id") or "").strip()
                    wgs2 = _wgs_from_koord_elem(pk.find("koordinaadid"))
                    if pid and wgs2:
                        idx.veevark_by_pt[pid] = wgs2
        elif key == "basseinid" and tag == "basseinid":
            for bs in tree.findall("bassein"):
                bid = (_text(bs, "id") or "").strip()
                wgs = _wgs_from_koord_elem(bs.find("koordinaadid"))
                if bid and wgs:
                    idx.bassein_by_bs[bid] = wgs
                for pk in bs.findall("./proovivotukohad/proovivotukoht"):
                    pid = (_text(pk, "id") or "").strip()
                    wgs2 = _wgs_from_koord_elem(pk.find("koordinaadid"))
                    if pid and wgs2:
                        idx.bassein_by_pt[pid] = wgs2
        elif key == "joogiveeallikad" and tag == "joogiveeallikad":
            for ja in tree.findall("joogiveeallikas"):
                jid = (_text(ja, "id") or "").strip()
                wgs = _wgs_from_koord_elem(ja.find("koordinaadid"))
                if jid and wgs:
                    idx.joogi_by_allikas[jid] = wgs
                for pk in ja.findall("./proovivotukohad/proovivotukoht"):
                    pid = (_text(pk, "id") or "").strip()
                    wgs2 = _wgs_from_koord_elem(pk.find("koordinaadid"))
                    if pid and wgs2:
                        idx.joogi_by_pt[pid] = wgs2
        else:
            _log.warning("Неизвестный корень XML для %s: %s", key, tag)
    return idx


_ref_cache: Optional[ReferenceCoordIndex] = None


def get_reference_index(
    use_cache: bool = True,
    session: Optional[requests.Session] = None,
    *,
    force_reload: bool = False,
) -> ReferenceCoordIndex:
    global _ref_cache
    if _ref_cache is not None and not force_reload:
        return _ref_cache
    _ref_cache = build_reference_index(use_cache=use_cache, session=session)
    return _ref_cache


def _norm_id(v: Any) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _apply_pt_then_facility(
    pid: pd.Series,
    fid: pd.Series,
    d_pt: Dict[str, Tuple[float, float]],
    d_f: Dict[str, Tuple[float, float]],
    src_pt: str,
    src_facility: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    pid_n = pid.map(_norm_id)
    fid_n = fid.map(_norm_id)
    hit_pt = pid_n.map(d_pt)
    lat = hit_pt.map(lambda t: t[0] if isinstance(t, tuple) else pd.NA)
    lon = hit_pt.map(lambda t: t[1] if isinstance(t, tuple) else pd.NA)
    src = hit_pt.map(lambda t: src_pt if isinstance(t, tuple) else pd.NA)
    miss = lat.isna()
    fac_hit = fid_n[miss].map(d_f)
    lat_f = pd.Series(pd.NA, index=pid_n.index, dtype="Float64")
    lon_f = pd.Series(pd.NA, index=pid_n.index, dtype="Float64")
    src_fac = pd.Series(pd.NA, index=pid_n.index, dtype=object)
    lat_f.loc[miss] = fac_hit.map(lambda t: t[0] if isinstance(t, tuple) else pd.NA)
    lon_f.loc[miss] = fac_hit.map(lambda t: t[1] if isinstance(t, tuple) else pd.NA)
    src_fac.loc[miss] = fac_hit.map(lambda t: src_facility if isinstance(t, tuple) else pd.NA)
    lat = lat.astype("Float64").fillna(lat_f)
    lon = lon.astype("Float64").fillna(lon_f)
    src = src.where(src.notna(), src_fac)
    return lat, lon, src


def attach_official_coords_to_df(
    df: pd.DataFrame,
    domain_key: str,
    *,
    use_cache: bool = True,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """
    Добавить official_lat, official_lon, official_coord_source (или NaN, если нет pyproj/данных).
    """
    out = df.copy()
    if len(out) == 0:
        for c in ("official_lat", "official_lon", "official_coord_source"):
            if c not in out.columns:
                out[c] = pd.NA
        return out

    try:
        idx = get_reference_index(use_cache=use_cache, session=session)
    except Exception as e:
        _log.warning("Справочники координат не загружены: %s", e)
        out["official_lat"] = pd.NA
        out["official_lon"] = pd.NA
        out["official_coord_source"] = pd.NA
        return out

    try:
        import pyproj  # noqa: F401
    except ImportError:
        _log.warning("Пакет pyproj не установлен — official_lat/lon пропущены")
        out["official_lat"] = pd.NA
        out["official_lon"] = pd.NA
        out["official_coord_source"] = pd.NA
        return out

    if domain_key == "supluskoha":
        if "proovivotukoht_id" not in out.columns or "supluskoht_id" not in out.columns:
            out["official_lat"] = pd.NA
            out["official_lon"] = pd.NA
            out["official_coord_source"] = pd.NA
            return out
        la, lo, sr = _apply_pt_then_facility(
            out["proovivotukoht_id"],
            out["supluskoht_id"],
            idx.supluskoht_by_pt,
            idx.supluskoht_by_sk,
            "terviseamet_proovivotukoht",
            "terviseamet_supluskoht",
        )
    elif domain_key == "veevark":
        if "proovivotukoht_id" not in out.columns or "veevark_id" not in out.columns:
            out["official_lat"] = pd.NA
            out["official_lon"] = pd.NA
            out["official_coord_source"] = pd.NA
            return out
        la, lo, sr = _apply_pt_then_facility(
            out["proovivotukoht_id"],
            out["veevark_id"],
            idx.veevark_by_pt,
            idx.veevark_by_vv,
            "terviseamet_proovivotukoht",
            "terviseamet_veevark",
        )
    elif domain_key == "basseinid":
        if "proovivotukoht_id" not in out.columns or "bassein_id" not in out.columns:
            out["official_lat"] = pd.NA
            out["official_lon"] = pd.NA
            out["official_coord_source"] = pd.NA
            return out
        la, lo, sr = _apply_pt_then_facility(
            out["proovivotukoht_id"],
            out["bassein_id"],
            idx.bassein_by_pt,
            idx.bassein_by_bs,
            "terviseamet_proovivotukoht",
            "terviseamet_bassein",
        )
    elif domain_key == "joogivesi":
        if "proovivotukoht_id" not in out.columns or "veeallikas_id" not in out.columns:
            out["official_lat"] = pd.NA
            out["official_lon"] = pd.NA
            out["official_coord_source"] = pd.NA
            return out
        la, lo, sr = _apply_pt_then_facility(
            out["proovivotukoht_id"],
            out["veeallikas_id"],
            idx.joogi_by_pt,
            idx.joogi_by_allikas,
            "terviseamet_proovivotukoht",
            "terviseamet_joogiveeallikas",
        )
    else:
        out["official_lat"] = pd.NA
        out["official_lon"] = pd.NA
        out["official_coord_source"] = pd.NA
        return out

    out["official_lat"] = la
    out["official_lon"] = lo
    out["official_coord_source"] = sr
    return out


__all__ = [
    "ReferenceCoordIndex",
    "build_reference_index",
    "get_reference_index",
    "attach_official_coords_to_df",
    "est_xml_xy_to_wgs84",
    "OPENDATA_BASE",
]
