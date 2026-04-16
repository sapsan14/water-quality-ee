import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "citizen-service"))

import geocode_resolve as gr  # noqa: E402


def test_build_geocode_queries_orders_site_before_facility():
    q = gr.build_geocode_queries(
        "veevark",
        "Kaerepere aleviku ühisveevärk",
        "Valtu Põhikool",
        "Kaerepere aleviku ühisveevärk",
        "Rapla maakond",
    )
    assert any("Valtu Põhikool" in x for x in q)
    assert any("Rapla maakond" in x for x in q)


def test_normalize_query_key():
    assert gr.normalize_query_key("  A,  B ") == gr.normalize_query_key("a, b")


def test_geocode_opencage_parses_geometry(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": {"code": 200, "message": "OK"},
                "results": [
                    {
                        "geometry": {"lat": 59.437, "lng": 24.753},
                        "formatted": "Tallinn, Estonia",
                        "confidence": 8,
                        "components": {"city": "Tallinn", "country": "Eesti", "_type": "city"},
                    }
                ],
            }

    def fake_get(url, params=None, headers=None, timeout=None):
        assert "opencagedata.com" in url
        assert params.get("countrycode") == "ee"
        return Resp()

    s = __import__("requests").Session()
    monkeypatch.setattr(s, "get", fake_get)
    out = gr.geocode_opencage("Tallinn", "dummy-key", s)
    assert out is not None
    assert abs(out["lat"] - 59.437) < 1e-6
    assert abs(out["lon"] - 24.753) < 1e-6
    assert out.get("confidence") == 8
    assert out.get("oc_type") == "city"


def test_geocode_opencage_rejects_country_fallback(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": {"code": 200, "message": "OK"},
                "results": [
                    {
                        "geometry": {"lat": 59.0, "lng": 26.0},
                        "formatted": "Eesti",
                        "confidence": 1,
                        "components": {"country": "Eesti", "country_code": "ee", "_type": "country"},
                    }
                ],
            }

    s = __import__("requests").Session()
    monkeypatch.setattr(s, "get", lambda *a, **k: Resp())
    assert gr.geocode_opencage("Some kitchen, Eesti", "k", s) is None


def test_geocode_opencage_rejects_county_centroid(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": {"code": 200, "message": "OK"},
                "results": [
                    {
                        "geometry": {"lat": 58.93, "lng": 23.55},
                        "formatted": "Lääne maakond, Eesti",
                        "confidence": 4,
                        "components": {"county": "Lääne maakond", "country": "Eesti", "_type": "county"},
                    }
                ],
            }

    s = __import__("requests").Session()
    monkeypatch.setattr(s, "get", lambda *a, **k: Resp())
    assert gr.geocode_opencage("Dirhami sadam, Lääne maakond, Eesti", "k", s) is None


def test_geocode_cache_entry_rejects_legacy_centroid():
    assert not gr.geocode_cache_entry_is_precise_enough(
        {"lat": 59.0, "lon": 26.0, "matched_address": None, "miss": False}
    )


def test_geocode_cache_entry_accepts_with_confidence():
    assert gr.geocode_cache_entry_is_precise_enough(
        {
            "lat": 58.39,
            "lon": 24.39,
            "matched_address": "Villa Andropoff, Pärnu",
            "confidence": 7,
            "oc_type": "tourism",
            "miss": False,
        }
    )


def test_geocode_opencage_rejects_outside_estonia(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": {"code": 200, "message": "OK"},
                "results": [{"geometry": {"lat": 52.5, "lng": 13.4}, "formatted": "Berlin"}],
            }

    s = __import__("requests").Session()
    monkeypatch.setattr(s, "get", lambda *a, **k: Resp())
    assert gr.geocode_opencage("Berlin", "k", s) is None
