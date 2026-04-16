#!/usr/bin/env python3
"""
Экспорт frontend-оптимизированного snapshot из citizen-service/artifacts/snapshot.json.

Запуск из корня репозитория:
  python3 citizen-service/scripts/export_frontend_snapshot.py
"""

from __future__ import annotations

import json
import csv
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "citizen-service" / "artifacts" / "snapshot.json"
DST = ROOT / "frontend" / "public" / "data" / "snapshot.frontend.json"
DST_HISTORY = ROOT / "frontend" / "public" / "data" / "snapshot.history.json"
RAW_COMBINED_PATH = ROOT / "data" / "processed" / "raw_combined.csv"
HISTORY_MEASUREMENT_COLUMNS = [
    "e_coli",
    "enterococci",
    "coliforms",
    "pseudomonas",
    "staphylococci",
    "ph",
    "nitrates",
    "nitrites",
    "ammonium",
    "fluoride",
    "manganese",
    "iron",
    "turbidity",
    "color",
    "chlorides",
    "sulfates",
    "free_chlorine",
    "combined_chlorine",
    "oxidizability",
    "colonies_37c",
    "transparency",
]


def risk_from_prob(prob: Any) -> str:
    if not isinstance(prob, (int, float)):
        return "unknown"
    p = float(prob)
    if p >= 0.7:
        return "high"
    if p >= 0.4:
        return "medium"
    return "low"


def _num_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _measurement_dict_from_row(row: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for col in HISTORY_MEASUREMENT_COLUMNS:
        raw = row.get(col)
        if raw in (None, ""):
            continue
        if isinstance(raw, str):
            raw = raw.replace(",", ".").strip()
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val != val:  # NaN
            continue
        out[col] = val
    return out


def _build_history_index() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """
    История по (domain, location) из data/processed/raw_combined.csv.
    Возвращает последние пробы в порядке убывания даты.
    """
    history: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if not RAW_COMBINED_PATH.is_file():
        return history

    with open(RAW_COMBINED_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = str(row.get("domain") or "").strip()
            location = str(row.get("location") or "").strip()
            if not domain or not location:
                continue
            sample_date = str(row.get("sample_date") or "").strip()
            if not sample_date:
                continue
            compliant_raw = row.get("compliant")
            compliant: int | None = None
            if compliant_raw in ("0", "1"):
                compliant = int(compliant_raw)
            key = (domain, location)
            history.setdefault(key, []).append(
                {
                    "sample_date": sample_date.replace(" ", "T"),
                    "official_compliant": compliant,
                    "measurements": _measurement_dict_from_row(row),
                }
            )

    for k, items in history.items():
        items.sort(key=lambda x: str(x["sample_date"]), reverse=True)
        history[k] = items[:30]
    return history


def _normalize_location_for_history(domain: str, location: str) -> str:
    """
    Нормализация имени локации для устойчивого матчингa истории:
    - lower + trim
    - удаление типичных доменных суффиксов
    - нормализация пробелов/пунктуации
    """
    n = (location or "").lower().strip()
    n = re.sub(r"\bsupluskoht\b", "", n)
    n = re.sub(r"\bsupluskoha\b", "", n)
    n = re.sub(r"\brand\b", "", n)
    n = re.sub(r"\bsuplusala\b", "", n)
    n = re.sub(r"\bühistveevärk\b", "", n)
    n = re.sub(r"\bühisveevärk\b", "", n)
    n = re.sub(r"\bveevärk\b", "", n)
    n = re.sub(r"\bveevõrk\b", "", n)
    n = re.sub(r"\bveevork\b", "", n)
    n = re.sub(r"[-–—]+", " ", n)
    n = re.sub(r"[,;]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return f"{domain}|{n}"


def main() -> None:
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    places = payload.get("places") or []
    history_index = _build_history_index()
    history_index_norm: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for (domain, location), items in history_index.items():
        key = (domain, _normalize_location_for_history(domain, location))
        prev = history_index_norm.get(key, [])
        merged = prev + items
        merged.sort(key=lambda x: str(x["sample_date"]), reverse=True)
        history_index_norm[key] = merged[:30]
    out_places = []

    for idx, p in enumerate(places):
        lat, lon = p.get("lat"), p.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        lr_prob = _num_or_none(p.get("lr_violation_prob"))
        rf_prob = _num_or_none(p.get("rf_violation_prob"))
        gb_prob = _num_or_none(p.get("gb_violation_prob"))
        lgbm_prob = _num_or_none(p.get("lgbm_violation_prob"))
        model_prob = _num_or_none(p.get("model_violation_prob"))
        if model_prob is None:
            # fallback: prefer RF for generic map layer
            model_prob = rf_prob
        location = str(p.get("location") or "").strip()
        county = p.get("county")
        domain = str(p.get("domain") or "other")
        place_kind = str(p.get("place_kind") or "other")
        # History priority: 1) snapshot.json (built by build_citizen_snapshot),
        # 2) raw_combined.csv exact match, 3) raw_combined.csv normalized match.
        sample_history = p.get("sample_history") or []
        if not sample_history:
            history_key = (domain, location)
            sample_history = history_index.get(history_key, [])
        if not sample_history:
            history_key_norm = (domain, _normalize_location_for_history(domain, location))
            sample_history = history_index_norm.get(history_key_norm, [])
        search_text = " ".join(
            [
                location.lower(),
                str(county or "").lower(),
                domain.lower(),
                place_kind.lower(),
            ]
        ).strip()

        measurements = p.get("measurements") or {}
        if not isinstance(measurements, dict):
            measurements = {}

        out_places.append(
            {
                "id": str(p.get("sample_id") or f"place-{idx}"),
                "location": location,
                "domain": domain,
                "place_kind": place_kind,
                "county": county,
                "sample_date": p.get("sample_date"),
                "official_compliant": p.get("official_compliant"),
                "coord_source": p.get("coord_source"),
                "lat": float(lat),
                "lon": float(lon),
                "model_violation_prob": model_prob,
                "lr_violation_prob": lr_prob,
                "rf_violation_prob": rf_prob,
                "gb_violation_prob": gb_prob,
                "lgbm_violation_prob": lgbm_prob,
                "risk_level": risk_from_prob(model_prob),
                "has_model_prob": model_prob is not None,
                "search_text": search_text,
                "measurements_count": len(measurements),
                "measurements": measurements,
                "sample_history": sample_history[:12],
            }
        )

    official_known = [x for x in out_places if isinstance(x.get("official_compliant"), int)]
    official_compliant_share = None
    official_violation_share = None
    if official_known:
        compliant = sum(1 for x in official_known if x.get("official_compliant") == 1)
        violation = sum(1 for x in official_known if x.get("official_compliant") == 0)
        official_compliant_share = compliant / len(official_known)
        official_violation_share = violation / len(official_known)

    model_cols = {
        "lr": "lr_violation_prob",
        "rf": "rf_violation_prob",
        "gb": "gb_violation_prob",
        "lgbm": "lgbm_violation_prob",
    }
    mean_model_probabilities: dict[str, float | None] = {}
    for key, col in model_cols.items():
        vals = [x[col] for x in out_places if isinstance(x.get(col), (int, float))]
        mean_model_probabilities[key] = (sum(vals) / len(vals)) if vals else None

    model_covered = sum(1 for x in out_places if x.get("has_model_prob"))
    model_coverage_share = (model_covered / len(out_places)) if out_places else 0.0

    out_payload = {
        "generated_at": payload.get("generated_at"),
        "data_fetched_at": payload.get("data_fetched_at"),
        "model_trained_at": payload.get("model_trained_at"),
        "has_model_predictions": bool(payload.get("has_model_predictions")),
        "available_models": payload.get("available_models") or [],
        "model_labels": payload.get("model_labels") or {},
        "data_catalog_url": payload.get("data_catalog_url"),
        "disclaimer": payload.get("disclaimer"),
        "places_count": len(out_places),
        "place_kinds": payload.get("place_kinds") or {},
        "domains": sorted({x["domain"] for x in out_places}),
        "diagnostics": {
            "official_compliant_share": official_compliant_share,
            "official_violation_share": official_violation_share,
            "model_coverage_share": model_coverage_share,
            "mean_model_probabilities": mean_model_probabilities,
        },
        "places": out_places,
    }

    # Split sample_history into a separate lazy-loaded file (saves ~3 MB from initial load)
    history_map: dict[str, list] = {}
    for p in out_places:
        h = p.pop("sample_history", [])
        if h:
            history_map[p["id"]] = h

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(out_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    DST_HISTORY.write_text(json.dumps(history_map, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(out_places)} places to {DST}")
    print(f"Exported {len(history_map)} place histories to {DST_HISTORY} ({DST_HISTORY.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
