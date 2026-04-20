"""Затравка county_geocode_cache из локальных источников без HTTP."""

import json

import pytest

import county_infer as ci


def test_canonicalize_county_forms():
    assert ci._canonicalize_county("Tartu Maakond") == "Tartu maakond"
    assert ci._canonicalize_county("tartu maakond") == "Tartu maakond"
    assert ci._canonicalize_county("TARTU MAAKOND") == "Tartu maakond"
    assert ci._canonicalize_county("IDA-VIRU MAAKOND") == "Ida-Viru maakond"
    assert ci._canonicalize_county("ida-viru maakond") == "Ida-Viru maakond"
    assert ci._canonicalize_county("Lääne-Viru Maakond") == "Lääne-Viru maakond"
    assert ci._canonicalize_county("lääne-viru maakond") == "Lääne-Viru maakond"
    # Английская форма попадает через _normalize_county_name
    assert ci._canonicalize_county("Tartu county") == "Tartu maakond"
    # Пустое / None
    assert ci._canonicalize_county(None) is None
    assert ci._canonicalize_county("") is None
    assert ci._canonicalize_county("   ") is None


def test_point_in_county_known_cities():
    polygons = ci._load_counties_polygons()
    if not polygons:
        pytest.skip("counties geojson not available")
    # Tartu (~26.72E, 58.38N)
    assert ci._point_in_county(26.72, 58.38, polygons) == "Tartu maakond"
    # Tallinn (~24.75E, 59.43N)
    assert ci._point_in_county(24.75, 59.43, polygons) == "Harju maakond"
    # Pärnu (~24.50E, 58.38N)
    assert ci._point_in_county(24.50, 58.38, polygons) == "Pärnu maakond"
    # Открытое Балтийское море
    assert ci._point_in_county(20.0, 60.0, polygons) is None


def test_seed_put_respects_existing_real_hit():
    cache = {"foo": {"county": "Harju maakond", "query": "x", "provider": "google"}}
    assert ci._seed_put(cache, "foo", "Tartu maakond", "fake", "seed_snapshot") is False
    # Реальный хит не затронут
    assert cache["foo"]["county"] == "Harju maakond"
    assert cache["foo"]["provider"] == "google"


def test_seed_put_first_seed_wins():
    cache = {}
    assert ci._seed_put(cache, "bar", "Tartu maakond", "q1", "seed_snapshot") is True
    # Второй seed-источник не перезаписывает первый
    assert ci._seed_put(cache, "bar", "Harju maakond", "q2", "seed_coord_cache") is False
    assert cache["bar"]["county"] == "Tartu maakond"
    assert cache["bar"]["provider"] == "seed_snapshot"


def test_seed_from_snapshot_populates_cache(tmp_path, monkeypatch):
    fixture = {
        "places": [
            {"location": "Тест локация 1", "county": "Tartu Maakond"},
            {"location": "Test 2", "county": "Harju maakond"},
            {"location": "Без county", "county": None},
            {"location": None, "county": "Pärnu maakond"},
        ]
    }
    p = tmp_path / "snapshot.json"
    p.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ci, "SNAPSHOT_JSON", p)

    cache = {}
    n = ci._seed_from_snapshot(cache)
    assert n == 2
    k1 = ci.normalize_location("Тест локация 1")
    k2 = ci.normalize_location("Test 2")
    assert cache[k1]["county"] == "Tartu maakond"
    assert cache[k1]["provider"] == "seed_snapshot"
    assert cache[k2]["county"] == "Harju maakond"


def test_seed_from_snapshot_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "SNAPSHOT_JSON", tmp_path / "nonexistent.json")
    cache = {}
    assert ci._seed_from_snapshot(cache) == 0
    assert cache == {}


def test_seed_cache_from_local_sources_end_to_end(tmp_path, monkeypatch):
    # snapshot с двумя записями
    snap = {
        "places": [
            {"location": "Loc A", "county": "Tartu Maakond"},
            {"location": "Loc B", "county": "Harju maakond"},
        ]
    }
    snap_p = tmp_path / "snapshot.json"
    snap_p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ci, "SNAPSHOT_JSON", snap_p)
    # отключим координатные файлы
    monkeypatch.setattr(ci, "COORD_OVERRIDES_JSON", tmp_path / "no_ovr.json")
    monkeypatch.setattr(ci, "COORD_RESOLVE_CACHE_JSON", tmp_path / "no_res.json")
    monkeypatch.setattr(ci, "GEOCODE_CACHE_SIMPLE_JSON", tmp_path / "no_gc.json")

    # Пре-популяция реальным HTTP-хитом — он не должен быть перезаписан.
    cache = {
        ci.normalize_location("Loc A"): {
            "county": "Pärnu maakond",
            "query": "Loc A",
            "provider": "google",
        }
    }
    changed = ci._seed_cache_from_local_sources(cache, verbose=False)
    assert changed is True
    # Loc A сохранён как был
    assert cache[ci.normalize_location("Loc A")]["county"] == "Pärnu maakond"
    assert cache[ci.normalize_location("Loc A")]["provider"] == "google"
    # Loc B засеян из snapshot
    assert cache[ci.normalize_location("Loc B")]["county"] == "Harju maakond"
    assert cache[ci.normalize_location("Loc B")]["provider"] == "seed_snapshot"
