"""build_dataset_with_meta согласован с build_dataset по размеру."""

import pandas as pd

from features import build_dataset, build_dataset_with_meta


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
