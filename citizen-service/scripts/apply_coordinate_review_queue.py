#!/usr/bin/env python3
"""
Применить решения из coordinate_review_queue.csv в coordinate_overrides.json.

Ожидаемые поля CSV:
  - domain
  - location
  - action: set_manual | hide | (пусто = пропуск)
  - manual_lat
  - manual_lon
  - review_note (опционально)
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUEUE_CSV = ROOT / "citizen-service" / "artifacts" / "coordinate_review_queue.csv"
OVERRIDES_JSON = ROOT / "citizen-service" / "data" / "coordinate_overrides.json"


def load_overrides(path: Path) -> dict:
    if not path.is_file():
        return {"version": 1, "items": []}
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": []}
    if not isinstance(payload, dict):
        return {"version": 1, "items": []}
    items = payload.get("items")
    if not isinstance(items, list):
        payload["items"] = []
    payload.setdefault("version", 1)
    return payload


def key_of(domain: str, location: str) -> str:
    return f"{domain.strip().lower()}::{location.strip().lower()}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=str(QUEUE_CSV), help="Путь к coordinate_review_queue.csv")
    ap.add_argument("--overrides", default=str(OVERRIDES_JSON), help="Путь к coordinate_overrides.json")
    args = ap.parse_args()

    queue_path = Path(args.queue)
    overrides_path = Path(args.overrides)
    if not queue_path.is_file():
        raise FileNotFoundError(f"Queue CSV не найден: {queue_path}")

    payload = load_overrides(overrides_path)
    existing = payload.get("items", [])
    by_key: dict[str, dict] = {}
    for it in existing:
        if not isinstance(it, dict):
            continue
        d = str(it.get("domain") or "").strip()
        l = str(it.get("location") or "").strip()
        if not d or not l:
            continue
        by_key[key_of(d, l)] = it

    applied = 0
    hidden = 0
    manual = 0
    skipped = 0

    with open(queue_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = str(row.get("domain") or "").strip()
            location = str(row.get("location") or "").strip()
            action = str(row.get("action") or "").strip().lower()
            note = str(row.get("review_note") or "").strip()
            if not domain or not location or not action:
                skipped += 1
                continue
            if action not in {"set_manual", "hide"}:
                skipped += 1
                continue
            k = key_of(domain, location)
            item = by_key.get(k, {"domain": domain, "location": location})
            item["action"] = action
            if note:
                item["note"] = note

            if action == "hide":
                item.pop("lat", None)
                item.pop("lon", None)
                hidden += 1
            else:
                lat_raw = str(row.get("manual_lat") or "").strip()
                lon_raw = str(row.get("manual_lon") or "").strip()
                try:
                    item["lat"] = float(lat_raw)
                    item["lon"] = float(lon_raw)
                except ValueError:
                    skipped += 1
                    continue
                manual += 1

            by_key[k] = item
            applied += 1

    out = {"version": 1, "items": sorted(by_key.values(), key=lambda x: (x.get("domain", ""), x.get("location", "")))}
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    with open(overrides_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[coord-apply] queue: {queue_path}")
    print(f"[coord-apply] overrides: {overrides_path}")
    print(f"[coord-apply] applied: {applied} (manual={manual}, hide={hidden}, skipped={skipped})")
    print(f"[coord-apply] total overrides now: {len(out['items'])}")


if __name__ == "__main__":
    main()
