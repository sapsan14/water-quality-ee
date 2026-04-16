"""EPSG:3301 (L-EST97) из XML Terviseamet: x=northing, y=easting → WGS84."""

import pytest

pytest.importorskip("pyproj")

from terviseamet_reference_coords import est_xml_xy_to_wgs84


def test_est_xml_xy_to_wgs84_tallinn_roundtrip_point():
    # Значения: WGS84 → EPSG:3301 (easting, northing); в XML — x=north, y=east.
    x_north = 6589053.292730683
    y_east = 542292.1538327286
    lat, lon = est_xml_xy_to_wgs84(x_north, y_east)
    assert lat == pytest.approx(59.4372, rel=0, abs=1e-4)
    assert lon == pytest.approx(24.7453, rel=0, abs=1e-4)
