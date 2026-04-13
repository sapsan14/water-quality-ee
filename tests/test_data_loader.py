"""
Тесты для src/data_loader.py — парсинг XML и логика слияния измерений.

Используются минимальные mock-XML без сетевых запросов.
"""

import textwrap
from lxml import etree
import pandas as pd
import pytest

# Импорт работает после `pip install -e .` или через sys.path (CI устанавливает пакет)
from data_loader import (
    _parse_supluskoha_opendata,
    _parse_veevark_opendata,
    _merge_num,
    _MERGE_LAST_WINS,
    normalize_location,
)


# ── _merge_num ────────────────────────────────────────────────────────────────

class TestMergeNum:
    def test_none_prev_returns_new(self):
        assert _merge_num(None, 5.0) == 5.0

    def test_none_new_returns_prev(self):
        assert _merge_num(3.0, None) == 3.0

    def test_both_none_returns_none(self):
        assert _merge_num(None, None) is None

    def test_contaminant_takes_max(self):
        # E. coli: safety-first → худший случай
        assert _merge_num(100.0, 500.0, "e_coli") == 500.0
        assert _merge_num(500.0, 100.0, "e_coli") == 500.0

    def test_ph_takes_last(self):
        # pH: range-параметр → последнее измерение
        assert _merge_num(7.0, 8.5, "ph") == 8.5
        assert _merge_num(8.5, 7.0, "ph") == 7.0

    def test_free_chlorine_takes_last(self):
        assert _merge_num(0.3, 0.7, "free_chlorine") == 0.7

    def test_combined_chlorine_takes_last(self):
        assert _merge_num(0.5, 0.2, "combined_chlorine") == 0.2

    def test_merge_last_wins_set_contents(self):
        assert "ph" in _MERGE_LAST_WINS
        assert "free_chlorine" in _MERGE_LAST_WINS
        assert "combined_chlorine" in _MERGE_LAST_WINS
        assert "transparency" in _MERGE_LAST_WINS
        # Микробиология должна быть вне LAST_WINS
        assert "e_coli" not in _MERGE_LAST_WINS
        assert "enterococci" not in _MERGE_LAST_WINS


# ── normalize_location ────────────────────────────────────────────────────────

class TestNormalizeLocation:
    def test_strips_supluskoht_suffix(self):
        # Та же точка, разные годы — должны давать одинаковый ключ
        assert normalize_location("Harku järve supluskoht") == normalize_location("Harku järve rand")

    def test_strips_veevaerk_suffix(self):
        assert normalize_location("Abja-Paluoja veevärk") == normalize_location("Abja-Paluoja ühisveevärk")

    def test_normalizes_whitespace(self):
        assert normalize_location("Abja-Paluoja  veevärk") == normalize_location("Abja-Paluoja veevärk")

    def test_case_insensitive(self):
        assert normalize_location("Tootsi Ujumisbassein") == normalize_location("tootsi ujumisbassein")


# ── Парсинг supluskoha XML ────────────────────────────────────────────────────

SUPLUSKOHA_XML = textwrap.dedent("""\
    <supluskoha_veeproovid>
      <proovivott>
        <id>1001</id>
        <supluskoht>Harku järve rand</supluskoht>
        <proovivotukoht><nimetus>Harku põhjarand</nimetus></proovivotukoht>
        <maakond>Harju maakond</maakond>
        <proovivotu_aeg>15.07.2024</proovivotu_aeg>
        <naitaja>
          <nimetus>Escherichia coli</nimetus>
          <sisaldus>120</sisaldus>
          <hinnang>vastab</hinnang>
        </naitaja>
        <naitaja>
          <nimetus>Soole enterokokid</nimetus>
          <sisaldus>45</sisaldus>
          <hinnang>vastab</hinnang>
        </naitaja>
        <hinnang>vastab</hinnang>
      </proovivott>
      <proovivott>
        <id>1002</id>
        <supluskoht>Anne kanal</supluskoht>
        <proovivotukoht><nimetus>Anne kanal</nimetus></proovivotukoht>
        <maakond>Tartu maakond</maakond>
        <proovivotu_aeg>20.07.2024</proovivotu_aeg>
        <naitaja>
          <nimetus>Escherichia coli</nimetus>
          <sisaldus>1500</sisaldus>
          <hinnang>ei vasta</hinnang>
        </naitaja>
        <hinnang>ei vasta</hinnang>
      </proovivott>
    </supluskoha_veeproovid>
""")


class TestSupluskohaParser:
    def setup_method(self):
        tree = etree.fromstring(SUPLUSKOHA_XML.encode())
        self.df = _parse_supluskoha_opendata(tree)

    def test_row_count(self):
        assert len(self.df) == 2

    def test_columns_present(self):
        for col in ("e_coli", "enterococci", "compliant", "sample_date", "location", "county"):
            assert col in self.df.columns, f"Отсутствует колонка: {col}"

    def test_compliant_values(self):
        row_ok = self.df[self.df["location"] == "Harku järve rand"].iloc[0]
        assert row_ok["compliant"] == 1
        row_viol = self.df[self.df["location"] == "Anne kanal"].iloc[0]
        assert row_viol["compliant"] == 0

    def test_e_coli_parsed(self):
        row_ok = self.df[self.df["location"] == "Harku järve rand"].iloc[0]
        assert row_ok["e_coli"] == pytest.approx(120.0)
        row_viol = self.df[self.df["location"] == "Anne kanal"].iloc[0]
        assert row_viol["e_coli"] == pytest.approx(1500.0)

    def test_enterococci_parsed(self):
        row_ok = self.df[self.df["location"] == "Harku järve rand"].iloc[0]
        assert row_ok["enterococci"] == pytest.approx(45.0)

    def test_sample_date_is_datetime(self):
        assert pd.api.types.is_datetime64_any_dtype(self.df["sample_date"])

    def test_domain_column(self):
        assert (self.df["domain"] == "supluskoha").all()

    def test_county(self):
        row = self.df[self.df["location"] == "Harku järve rand"].iloc[0]
        assert row["county"] == "Harju maakond"


# ── Парсинг veevark XML ───────────────────────────────────────────────────────

VEEVARK_XML = textwrap.dedent("""\
    <veevargi_veeproovid>
      <proovivott>
        <id>2001</id>
        <veevark>Tallinn veevärk</veevark>
        <proovivotukoht><nimetus>Mustamäe pump</nimetus></proovivotukoht>
        <maakond>Harju maakond</maakond>
        <proovivotu_aeg>10.03.2024</proovivotu_aeg>
        <naitaja>
          <nimetus>Raud (Fe)</nimetus>
          <sisaldus>0,18</sisaldus>
          <yhik>mg/l</yhik>
          <hinnang>vastab</hinnang>
        </naitaja>
        <naitaja>
          <nimetus>Mangaan (Mn)</nimetus>
          <sisaldus>0,03</sisaldus>
          <yhik>mg/l</yhik>
          <hinnang>vastab</hinnang>
        </naitaja>
        <hinnang>vastab</hinnang>
      </proovivott>
      <proovivott>
        <id>2002</id>
        <veevark>Tartu veevärk</veevark>
        <proovivotukoht><nimetus>Annelinn</nimetus></proovivotukoht>
        <maakond>Tartu maakond</maakond>
        <proovivotu_aeg>12.03.2024</proovivotu_aeg>
        <naitaja>
          <nimetus>Raud (Fe)</nimetus>
          <sisaldus>0,45</sisaldus>
          <yhik>mg/l</yhik>
          <hinnang>ei vasta</hinnang>
        </naitaja>
        <hinnang>ei vasta</hinnang>
      </proovivott>
    </veevargi_veeproovid>
""")


class TestVeevarkParser:
    def setup_method(self):
        tree = etree.fromstring(VEEVARK_XML.encode())
        self.df = _parse_veevark_opendata(tree)

    def test_row_count(self):
        assert len(self.df) == 2

    def test_compliant_values(self):
        ok = self.df[self.df["iron"].round(2) == 0.18].iloc[0]
        assert ok["compliant"] == 1
        viol = self.df[self.df["iron"].round(2) == 0.45].iloc[0]
        assert viol["compliant"] == 0

    def test_iron_comma_decimal(self):
        # Эстонский числовой формат: 0,18 → 0.18
        ok = self.df.dropna(subset=["iron"])
        assert any(abs(ok["iron"] - 0.18) < 0.001)

    def test_manganese_parsed(self):
        row = self.df[self.df["iron"].round(2) == 0.18].iloc[0]
        assert row["manganese"] == pytest.approx(0.03)

    def test_domain_column(self):
        assert (self.df["domain"] == "veevark").all()
