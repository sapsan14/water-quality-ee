#!/usr/bin/env python
"""
audit_xml_field_coverage.py — Enumerate every XML tag under <proovivott>
in cached Terviseamet open-data files and flag which ones the parsers in
`src/data_loader.py` currently extract.

Purpose
-------
Before blaming upstream for "partially missing parameters" (see
`docs/data_gaps.md` and `reflect/2026-04-15_health-data-gaps.md`), rule out
the trivial explanation: the parser drops a field that IS published.

Any row in the inventory with `parsed=False` and a non-empty `sample_value`
is a parser-side gap to fix in-repo before drafting the engineering inquiry
to Terviseamet.

Usage
-----
    python scripts/audit_xml_field_coverage.py
    python scripts/audit_xml_field_coverage.py --out data/audit/xml_fields.csv

Reads every cached file `data/raw/{domain}_{year}.xml`. Prints a summary and
writes a CSV with columns:
    domain, year, parent_tag, xml_tag, occurrences, parsed, sample_value

The `parsed` column is determined by whether the parser in `data_loader.py`
produces a DataFrame column that corresponds to the XML tag, via the
`_PARSED_TAGS_BY_DOMAIN` whitelist below (which mirrors the parser literals).
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, Set, Tuple

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "data" / "audit" / "xml_field_inventory.csv"


# Tags the data_loader.py parsers explicitly read for each domain. Any XML
# child tag appearing in the cached files that is NOT in this set is an
# "unparsed" field (possibly fine, possibly a gap).
#
# Pulled by reading src/data_loader.py: the parser reaches for these keys
# via _text(pv, ...) or by iterating <naitaja><nimetus> strings that map to
# canonical column names through _<domain>_naitaja_col().
_PARSED_TAGS_BY_DOMAIN: Dict[str, Set[str]] = {
    "supluskoha": {
        "id",
        "supluskoht",
        "supluskoht_id",
        "proovivotukoht",
        "maakond",
        "proovivotu_aeg",
        "naitaja",
        "hinnang",
    },
    "veevark": {
        "id",
        "veevark",
        "veevark_id",
        "proovivotukoht",
        "maakond",
        "proovivotu_aeg",
        "naitaja",
        "hinnang",
    },
    "basseinid": {
        "id",
        "bassein",
        "bassein_id",
        "proovivotukoht",
        "maakond",
        "proovivotu_aeg",
        "naitaja",
        "hinnang",
    },
    "joogivesi": {
        "id",
        "veeallikas",
        "veeallikas_id",
        "proovivotukoht",
        "maakond",
        "proovivotu_aeg",
        "naitaja",
        "hinnang",
        "katseprotokoll",
    },
    "mineraalvesi": {
        "id",
        "mineraalvesi",
        "mineraalvesi_asutus",
        "mineraalvesi_id",
        "veevark",
        "veevark_id",
        "veeallikas",
        "proovivotukoht",
        "maakond",
        "proovivotu_aeg",
        "naitaja",
        "hinnang",
    },
}


def _iter_cached_files() -> Iterable[Tuple[str, int, Path]]:
    if not DATA_RAW.exists():
        return
    for path in sorted(DATA_RAW.glob("*.xml")):
        stem = path.stem  # e.g. supluskoha_2024
        # Split on the last underscore to separate domain from year.
        if "_" not in stem:
            continue
        domain, year_s = stem.rsplit("_", 1)
        try:
            year = int(year_s)
        except ValueError:
            continue
        yield domain, year, path


def _direct_children(parent: etree._Element) -> Iterable[etree._Element]:
    for child in parent:
        if isinstance(child.tag, str):
            yield child


def _inventory_one_file(
    domain: str, path: Path
) -> Dict[Tuple[str, str], Tuple[int, str]]:
    """
    Walk the XML tree and collect, per (parent_tag, child_tag), the number
    of occurrences and one sample of the child's text.
    """
    try:
        tree = etree.fromstring(path.read_bytes())
    except etree.XMLSyntaxError as exc:
        print(f"[audit_xml] skip malformed {path.name}: {exc}")
        return {}

    # Look at everything under <proovivott> (opendata) and <uuring> (legacy)
    # because either may be present.
    records: Dict[Tuple[str, str], Tuple[int, str]] = {}
    targets = tree.findall(".//proovivott") + tree.findall(".//uuring")
    for probe in targets:
        parent_tag = probe.tag
        for child in _direct_children(probe):
            key = (parent_tag, child.tag)
            prev = records.get(key)
            count = (prev[0] if prev else 0) + 1
            sample = prev[1] if prev else ""
            if not sample:
                text = (child.text or "").strip()
                if text:
                    sample = text[:80]
            records[key] = (count, sample)

    return records


def build_inventory() -> Dict[Tuple[str, int, str, str], Tuple[int, str, bool]]:
    """
    Returns: {(domain, year, parent_tag, child_tag): (count, sample, parsed)}
    """
    out: Dict[Tuple[str, int, str, str], Tuple[int, str, bool]] = {}
    for domain, year, path in _iter_cached_files():
        parsed_set = _PARSED_TAGS_BY_DOMAIN.get(domain, set())
        per_file = _inventory_one_file(domain, path)
        for (parent_tag, child_tag), (count, sample) in per_file.items():
            parsed = child_tag in parsed_set
            out[(domain, year, parent_tag, child_tag)] = (count, sample, parsed)
    return out


def write_csv(
    inventory: Dict[Tuple[str, int, str, str], Tuple[int, str, bool]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["domain", "year", "parent_tag", "xml_tag", "occurrences", "parsed", "sample_value"]
        )
        for (domain, year, parent, child), (count, sample, parsed) in sorted(
            inventory.items()
        ):
            w.writerow([domain, year, parent, child, count, int(parsed), sample])


def summarise(
    inventory: Dict[Tuple[str, int, str, str], Tuple[int, str, bool]],
) -> None:
    if not inventory:
        print(
            "[audit_xml] No cached XML files in data/raw/. "
            "Run `python src/data_loader.py` or load a domain first."
        )
        return

    by_domain: Dict[str, Counter] = defaultdict(Counter)
    unparsed_by_domain: Dict[str, Set[str]] = defaultdict(set)
    for (domain, _year, _parent, child), (_count, _sample, parsed) in inventory.items():
        by_domain[domain][child] += 1
        if not parsed:
            unparsed_by_domain[domain].add(child)

    print("\n=== XML field inventory ===")
    for domain in sorted(by_domain):
        total_tags = len(by_domain[domain])
        unparsed = sorted(unparsed_by_domain[domain])
        print(f"\n[{domain}] {total_tags} distinct child tags")
        if unparsed:
            print(f"  unparsed: {', '.join(unparsed)}")
        else:
            print("  (all direct child tags are parsed)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="CSV output path")
    args = ap.parse_args()

    inventory = build_inventory()
    summarise(inventory)
    if inventory:
        write_csv(inventory, args.out)
        print(f"\nWrote {len(inventory)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
