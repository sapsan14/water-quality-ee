#!/usr/bin/env python3
"""
Сформировать очередь ручной проверки координат для citizen snapshot.

Источник: citizen-service/artifacts/snapshot.json
Выход:
  - citizen-service/artifacts/coordinate_review_queue.csv
  - citizen-service/artifacts/coordinate_review_queue.json
  - citizen-service/artifacts/coordinate_review_summary.json

По умолчанию в очередь попадают точки с coord_source:
  approximate_ee, county_centroid, geocode_cache, google
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "citizen-service" / "artifacts"
SNAPSHOT_PATH = ARTIFACTS / "snapshot.json"
QUEUE_CSV = ARTIFACTS / "coordinate_review_queue.csv"
QUEUE_JSON = ARTIFACTS / "coordinate_review_queue.json"
SUMMARY_JSON = ARTIFACTS / "coordinate_review_summary.json"
OVERRIDES_TEMPLATE_JSON = ROOT / "citizen-service" / "data" / "coordinate_overrides.template.json"


DEFAULT_REVIEW_SOURCES = {
    "approximate_ee",
    "county_centroid",
    "geocode_cache",
    "google",
}


def _gmaps_link(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return ""
    return f"https://www.google.com/maps?q={lat},{lon}"


def _search_link(query: str) -> str:
    if not query.strip():
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def build_review_rows(places: list[dict], review_sources: set[str]) -> list[dict]:
    rows: list[dict] = []
    for p in places:
        coord_source = str(p.get("coord_source") or "none")
        if coord_source not in review_sources:
            continue
        location = str(p.get("location") or "").strip()
        county = str(p.get("county") or "").strip()
        domain = str(p.get("domain") or "").strip()
        sample_date = str(p.get("sample_date") or "").strip()
        lat = p.get("lat")
        lon = p.get("lon")

        query = ", ".join(x for x in (location, county, "Estonia") if x)
        rows.append(
            {
                "domain": domain,
                "location": location,
                "county": county,
                "sample_date": sample_date,
                "coord_source": coord_source,
                "lat": lat,
                "lon": lon,
                "google_maps_point_url": _gmaps_link(lat, lon),
                "google_maps_search_url": _search_link(query),
                "review_status": "needs_review",
                "review_note": "",
                "action_suggested": "set_manual_or_hide",
                "action": "",
                "manual_lat": "",
                "manual_lon": "",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--snapshot",
        default=str(SNAPSHOT_PATH),
        help="Путь до snapshot.json",
    )
    ap.add_argument(
        "--review-sources",
        default=",".join(sorted(DEFAULT_REVIEW_SOURCES)),
        help="Список coord_source через запятую, требующих ручной проверки",
    )
    args = ap.parse_args()

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"snapshot не найден: {snapshot_path}")

    review_sources = {x.strip() for x in args.review_sources.split(",") if x.strip()}
    with open(snapshot_path, encoding="utf-8") as f:
        snap = json.load(f)
    places = snap.get("places") or []

    rows = build_review_rows(places, review_sources)
    rows.sort(key=lambda r: (r["domain"], r["coord_source"], r["location"]))

    write_csv(QUEUE_CSV, rows)
    with open(QUEUE_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    by_domain = Counter(r["domain"] for r in rows)
    by_source = Counter(r["coord_source"] for r in rows)
    summary = {
        "snapshot_path": str(snapshot_path),
        "snapshot_places": len(places),
        "review_sources": sorted(review_sources),
        "needs_review_total": len(rows),
        "needs_review_by_domain": dict(by_domain),
        "needs_review_by_coord_source": dict(by_source),
        "outputs": {
            "csv": str(QUEUE_CSV),
            "json": str(QUEUE_JSON),
        },
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    overrides_template = {
        "version": 1,
        "items": [
            {
                "domain": r["domain"],
                "location": r["location"],
                "action": "set_manual_or_hide",
                "lat": None,
                "lon": None,
                "note": "",
            }
            for r in rows[:20]
        ],
        "_comment": (
            "Это шаблон. Для применения сохраните в citizen-service/data/coordinate_overrides.json "
            "и замените action на set_manual|hide. Для set_manual укажите lat/lon."
        ),
    }
    OVERRIDES_TEMPLATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDES_TEMPLATE_JSON, "w", encoding="utf-8") as f:
        json.dump(overrides_template, f, ensure_ascii=False, indent=2)

    print(f"[coord-review] snapshot places: {len(places)}")
    print(f"[coord-review] needs review: {len(rows)}")
    print(f"[coord-review] by domain: {dict(by_domain)}")
    print(f"[coord-review] by source: {dict(by_source)}")
    print(f"[coord-review] wrote: {QUEUE_CSV}")
    print(f"[coord-review] wrote: {QUEUE_JSON}")
    print(f"[coord-review] wrote: {SUMMARY_JSON}")
    print(f"[coord-review] wrote: {OVERRIDES_TEMPLATE_JSON}")


if __name__ == "__main__":
    main()
