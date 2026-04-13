#!/usr/bin/env python3
"""
Дозаполнить data/processed/county_geocode_cache.json через Nominatim.

Запуск из корня репозитория (нужен интернет, ~1 запрос/сек):
  pip install -r requirements.txt
  python scripts/warm_county_geocode_cache.py
  python scripts/warm_county_geocode_cache.py --limit 500

Повторные запуски пропускают уже закэшированные ключи.

По умолчанию загружаются три домена (в т.ч. **basseinid** / SPA) — больше уникальных `location` для кэша.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_loader import load_all  # noqa: E402
from county_infer import enrich_county_column, GEOCODE_CACHE_PATH  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Геокодирование location → county (кэш)")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Макс. число новых HTTP-запросов (по умолчанию — без лимита)",
    )
    p.add_argument("--no-veevark", action="store_true", help="Только supluskoha")
    p.add_argument(
        "--no-basseinid",
        action="store_true",
        help="Без бассейнов: только supluskoha + veevark",
    )
    args = p.parse_args()

    if args.no_veevark:
        domains = ["supluskoha"]
    elif args.no_basseinid:
        domains = ["supluskoha", "veevark"]
    else:
        domains = ["supluskoha", "veevark", "basseinid"]
    print(f"Загрузка доменов: {domains} …")
    df = load_all(domains=domains, use_cache=True, infer_county=False)
    print(f"Строк: {len(df)}; кэш: {GEOCODE_CACHE_PATH}")
    enrich_county_column(
        df,
        geocode=True,
        geocode_limit=args.limit,
        verbose=True,
    )
    print("Готово.")


if __name__ == "__main__":
    main()
