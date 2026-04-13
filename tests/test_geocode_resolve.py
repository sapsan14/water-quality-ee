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
