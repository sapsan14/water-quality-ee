"""Нормализация названий уездов для центроидов карты."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "citizen-service"))

import county_centroids as cc  # noqa: E402


def test_county_to_latlon_full_name():
    lat, lon = cc.county_to_latlon("Harju maakond")
    assert lat is not None and lon is not None


def test_county_to_latlon_without_maakond_suffix():
    assert cc.county_to_latlon("harju") == cc.county_to_latlon("harju maakond")
    assert cc.county_to_latlon("Ida-Viru") == cc.county_to_latlon("ida-viru maakond")
