"""Парсер opendata joogiveeallika_veeproovid."""

from data_loader import parse_joogivesi

SAMPLE_I = b"""<?xml version="1.0" encoding="utf-8"?>
<joogiveeallika_veeproovid>
  <proovivott>
    <id>99</id>
    <veeallikas>Testi j&#xE4;rv</veeallikas>
    <proovivotu_aeg>01.06.2024 12:00</proovivotu_aeg>
    <proovivotukoht><nimetus>VPJ sissevool</nimetus></proovivotukoht>
    <katseprotokollid>
      <katseprotokoll>
        <hinnang>Kvaliteediklass I</hinnang>
        <naitajad>
          <naitaja><nimetus>pH</nimetus><sisaldus>7,2</sisaldus><yhik>pH uhik</yhik></naitaja>
          <naitaja><nimetus>Nitraat</nimetus><sisaldus>2.1</sisaldus><yhik>mg/l</yhik></naitaja>
        </naitajad>
      </katseprotokoll>
    </katseprotokollid>
  </proovivott>
</joogiveeallika_veeproovid>
"""

SAMPLE_II = SAMPLE_I.replace(b"Kvaliteediklass I", b"Kvaliteediklass II")


def test_parse_joogivesi_quality_class_i():
    df = parse_joogivesi(SAMPLE_I)
    assert len(df) == 1
    assert df.iloc[0]["domain"] == "joogivesi"
    loc = str(df.iloc[0]["location"])
    assert "Testi" in loc and "VPJ" in loc
    assert df.iloc[0]["compliant"] == 1
    assert df.iloc[0]["ph"] == 7.2
    assert df.iloc[0]["nitrates"] == 2.1


def test_parse_joogivesi_quality_class_ii_violation():
    df = parse_joogivesi(SAMPLE_II)
    assert len(df) == 1
    assert df.iloc[0]["compliant"] == 0
