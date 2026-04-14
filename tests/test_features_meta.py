"""build_dataset_with_meta согласован с build_dataset по размеру."""

import pandas as pd

from features import build_citizen_meta_frame, build_dataset, build_dataset_with_meta


def _tiny_frame():
    return pd.DataFrame(
        {
            "domain": ["supluskoha", "veevark"],
            "location": ["A", "B"],
            "sample_date": pd.to_datetime(["2023-06-01", "2023-06-02"]),
            "compliant": [1, 0],
            "e_coli": [10.0, None],
            "county": [None, None],
        }
    )


def test_build_dataset_with_meta_aligns_xy():
    df = _tiny_frame()
    X1, y1 = build_dataset(df)
    X2, y2, meta = build_dataset_with_meta(df)
    assert len(X1) == len(X2) == len(y1) == len(y2) == len(meta)
    assert list(y1) == list(y2)
    assert "location" in meta.columns
    assert "domain" in meta.columns


def test_build_citizen_meta_frame_matches_meta_part():
    df = _tiny_frame()
    _, _, meta = build_dataset_with_meta(df)
    meta_only = build_citizen_meta_frame(df)
    assert len(meta_only) == len(meta)
    assert list(meta_only.columns) == list(meta.columns)
    pd.testing.assert_frame_equal(
        meta_only.reset_index(drop=True),
        meta.reset_index(drop=True),
        check_dtype=False,
    )


def test_official_coords_in_meta_when_present():
    df = _tiny_frame()
    df["official_lat"] = [59.4, 58.3]
    df["official_lon"] = [24.7, 26.7]
    df["official_coord_source"] = ["terviseamet_proovivotukoht"] * 2
    _, _, meta = build_dataset_with_meta(df)
    assert "official_lat" in meta.columns
    assert "official_lon" in meta.columns
    assert "official_coord_source" in meta.columns
