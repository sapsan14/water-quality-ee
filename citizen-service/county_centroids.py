"""
Приблизительные центроиды уездов Эстонии (WGS84) для карты, если нет точного геокода.
Ключ — нормализованное имя maakond (нижний регистр).
"""

COUNTY_CENTROIDS: dict[str, tuple[float, float]] = {
    "harju maakond": (59.43, 24.74),
    "tartu maakond": (58.38, 26.72),
    "ida-viru maakond": (59.40, 27.28),
    "pärnu maakond": (58.39, 24.50),
    "lääne-viru maakond": (59.35, 26.36),
    "viljandi maakond": (58.37, 25.59),
    "rapla maakond": (58.94, 24.79),
    "järva maakond": (58.99, 25.57),
    "jõgeva maakond": (58.75, 26.39),
    "valga maakond": (57.78, 26.05),
    "võru maakond": (57.83, 27.00),
    "saare maakond": (58.44, 22.49),
    "hiiu maakond": (58.92, 22.67),
    "lääne maakond": (58.92, 23.54),
    "põlva maakond": (58.06, 27.07),
}


def county_to_latlon(county: str | None) -> tuple[float, float] | None:
    if not county or not isinstance(county, str):
        return None
    key = county.strip().lower()
    return COUNTY_CENTROIDS.get(key)
