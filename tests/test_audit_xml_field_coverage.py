"""
Smoke tests for scripts/audit_xml_field_coverage.py.

The audit script normally walks `data/raw/{domain}_{year}.xml` produced by
`data_loader.load_all()` and reports which `<proovivott>` child tags are
parsed by the loader vs which are silently ignored. The full check requires
real XML cached on a developer machine — these tests only exercise the
script's logic against a tiny synthetic fixture that mimics the structural
shape of real Terviseamet opendata files.

If the script's parser-parity logic regresses (e.g. a tag is removed from
`_PARSED_TAGS_BY_DOMAIN` without a corresponding removal in `data_loader.py`,
or a new tag appears in real files), these fixtures still let CI catch
the bug shape — but not the specific real-XML drift, which is what the
runbook in `docs/phase_10_findings.md` covers.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "audit_xml_field_coverage.py"


@pytest.fixture(scope="module")
def audit_module():
    """Import the script as a module so its functions can be unit-tested."""
    spec = importlib.util.spec_from_file_location(
        "audit_xml_field_coverage", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_xml_field_coverage"] = mod
    spec.loader.exec_module(mod)
    return mod


SUPLUSKOHA_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<root>
  <proovivott>
    <id>1001</id>
    <supluskoht>Pirita rand</supluskoht>
    <supluskoht_id>123</supluskoht_id>
    <maakond>Harju Maakond</maakond>
    <proovivotu_aeg>01.07.2024 10:00:00</proovivotu_aeg>
    <hinnang>vastab</hinnang>
    <naitaja>
      <nimetus>Escherichia coli</nimetus>
      <sisaldus>10</sisaldus>
    </naitaja>
    <unparsed_extra_tag>some upstream value</unparsed_extra_tag>
  </proovivott>
  <proovivott>
    <id>1002</id>
    <supluskoht>Stroomi rand</supluskoht>
    <supluskoht_id>124</supluskoht_id>
    <maakond>Harju Maakond</maakond>
    <proovivotu_aeg>02.07.2024 10:00:00</proovivotu_aeg>
    <hinnang>ei vasta nõuetele</hinnang>
    <naitaja>
      <nimetus>Soole enterokokid</nimetus>
      <sisaldus>500</sisaldus>
    </naitaja>
  </proovivott>
</root>
"""


class TestInventoryOneFile:
    def test_counts_direct_children_under_proovivott(self, audit_module, tmp_path):
        path = tmp_path / "supluskoha_2024.xml"
        path.write_text(SUPLUSKOHA_FIXTURE, encoding="utf-8")

        records = audit_module._inventory_one_file("supluskoha", path)

        # Expected direct children of <proovivott> across both probes:
        #   id, supluskoht, supluskoht_id, maakond, proovivotu_aeg, hinnang,
        #   naitaja (parsed iterator), unparsed_extra_tag (only in first probe)
        keys = {child for (_parent, child) in records.keys()}
        assert keys == {
            "id",
            "supluskoht",
            "supluskoht_id",
            "maakond",
            "proovivotu_aeg",
            "hinnang",
            "naitaja",
            "unparsed_extra_tag",
        }

        # Counts should reflect occurrences across the two probes.
        assert records[("proovivott", "id")][0] == 2
        assert records[("proovivott", "naitaja")][0] == 2
        assert records[("proovivott", "unparsed_extra_tag")][0] == 1

    def test_sample_value_captured(self, audit_module, tmp_path):
        path = tmp_path / "supluskoha_2024.xml"
        path.write_text(SUPLUSKOHA_FIXTURE, encoding="utf-8")
        records = audit_module._inventory_one_file("supluskoha", path)

        # `unparsed_extra_tag` should carry its text into the sample column —
        # this is the very thing the audit is designed to expose.
        sample = records[("proovivott", "unparsed_extra_tag")][1]
        assert sample == "some upstream value"

    def test_skip_malformed_xml(self, audit_module, tmp_path, capsys):
        path = tmp_path / "supluskoha_2099.xml"
        path.write_bytes(b"<not><closed>")
        records = audit_module._inventory_one_file("supluskoha", path)
        assert records == {}
        out = capsys.readouterr().out
        assert "skip malformed" in out


class TestParsedSetClassification:
    def test_known_tag_is_marked_parsed(self, audit_module):
        parsed = audit_module._PARSED_TAGS_BY_DOMAIN["supluskoha"]
        # All tags in the real loader should remain in the whitelist.
        for tag in (
            "id",
            "supluskoht",
            "supluskoht_id",
            "proovivotukoht",
            "maakond",
            "proovivotu_aeg",
            "naitaja",
            "hinnang",
        ):
            assert tag in parsed, f"{tag} is parsed by data_loader but missing from whitelist"

    def test_unknown_tag_is_not_in_whitelist(self, audit_module):
        parsed = audit_module._PARSED_TAGS_BY_DOMAIN["supluskoha"]
        # Tags we know don't exist must NOT be falsely accepted.
        assert "unparsed_extra_tag" not in parsed
        assert "internal_lab_note" not in parsed


class TestBuildInventoryAgainstFixture:
    """
    End-to-end check: place a synthetic XML in a fake data/raw and confirm
    `build_inventory()` produces the right `(domain, year, parent, child) → (count, sample, parsed)`
    map, with the unknown tag flagged unparsed.
    """

    def test_full_inventory_flags_unparsed_tag(self, audit_module, tmp_path, monkeypatch):
        fake_raw = tmp_path / "data" / "raw"
        fake_raw.mkdir(parents=True)
        (fake_raw / "supluskoha_2024.xml").write_text(SUPLUSKOHA_FIXTURE, encoding="utf-8")
        monkeypatch.setattr(audit_module, "DATA_RAW", fake_raw)

        inventory = audit_module.build_inventory()

        # The unparsed tag must be present and marked parsed=False.
        key = ("supluskoha", 2024, "proovivott", "unparsed_extra_tag")
        assert key in inventory
        count, sample, parsed = inventory[key]
        assert count == 1
        assert sample == "some upstream value"
        assert parsed is False

        # Known tags must be marked parsed=True.
        for known in ("id", "supluskoht", "naitaja", "hinnang"):
            k = ("supluskoha", 2024, "proovivott", known)
            assert k in inventory
            assert inventory[k][2] is True, f"{known} should be parsed=True"

    def test_csv_writer_round_trips(self, audit_module, tmp_path, monkeypatch):
        fake_raw = tmp_path / "data" / "raw"
        fake_raw.mkdir(parents=True)
        (fake_raw / "supluskoha_2024.xml").write_text(SUPLUSKOHA_FIXTURE, encoding="utf-8")
        monkeypatch.setattr(audit_module, "DATA_RAW", fake_raw)

        inventory = audit_module.build_inventory()
        out_path = tmp_path / "inv.csv"
        audit_module.write_csv(inventory, out_path)

        text = out_path.read_text(encoding="utf-8")
        assert "domain,year,parent_tag,xml_tag,occurrences,parsed,sample_value" in text
        assert "unparsed_extra_tag" in text
        # parsed column for the unparsed tag must be 0, for known tags 1.
        for line in text.splitlines()[1:]:
            cols = line.split(",")
            if cols[3] == "unparsed_extra_tag":
                assert cols[5] == "0"
            elif cols[3] in ("id", "supluskoht", "naitaja"):
                assert cols[5] == "1"


def test_summarise_handles_empty_inventory(audit_module, capsys):
    audit_module.summarise({})
    out = capsys.readouterr().out
    assert "No cached XML files in data/raw/" in out
