"""Кодирование уезда без утечки: словарь только с train."""

import pandas as pd

from features import COUNTY_UNKNOWN, encode_categoricals, engineer_features, fit_county_mapping


def test_unknown_county_in_test_maps_to_bucket():
    train = pd.DataFrame(
        {
            "compliant": [1, 1],
            "county": ["Harju maakond", None],
            "domain": ["veevark", "veevark"],
            "sample_date": pd.to_datetime(["2023-01-01", "2023-02-01"]),
        }
    )
    test = pd.DataFrame(
        {
            "compliant": [1],
            "county": ["Tartu maakond"],
            "domain": ["veevark"],
            "sample_date": pd.to_datetime(["2023-03-01"]),
        }
    )
    df = pd.concat([train, test], ignore_index=True)
    df_eng = engineer_features(df)
    cmap = fit_county_mapping(df_eng.loc[[0, 1], "county"])
    assert COUNTY_UNKNOWN in cmap
    df_enc = encode_categoricals(df_eng, county_mapping=cmap)
    # test row index 2: Tartu not in train → same code as unknown
    unk = cmap[COUNTY_UNKNOWN]
    assert df_enc.loc[2, "county_encoded"] == unk
