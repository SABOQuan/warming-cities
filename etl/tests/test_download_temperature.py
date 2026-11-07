"""Unit tests for the NOAA GHCN-Monthly temperature download client (download_temperature.py).

These parse small hand-built fixture text files matching GHCN's fixed-width format, not the real
~44MB global archive — so tests run instantly and offline.
"""

import download_temperature as dt


def _inv_line(station_id: str, lat: float, lon: float, elev: float, name: str) -> str:
    """Build one fixed-width .inv line: ID 1-11, LAT 13-20, LON 22-30, ELEV 32-37, NAME 39-68
    (1-indexed, matching parse_inventory's column slices exactly, including the single-space
    separators between fields)."""
    return (
        f"{station_id:<11}"
        f" {lat:>8.4f}"
        f" {lon:>9.4f}"
        f" {elev:>6.1f}"
        f" {name:<30}"
        "\n"
    )


def _dat_line(station_id: str, year: int, values_c: list[float | None]) -> str:
    """Build one fixed-width .dat line for 12 months. values_c in degrees C, None = missing."""
    line = f"{station_id:<11}{year:04d}TAVG"
    for v in values_c:
        raw = dt.MISSING_VALUE if v is None else round(v * 100)
        line += f"{raw:>5d}   "  # value + 3 blank flag columns
    return line + "\n"


def test_haversine_zero_distance_for_same_point():
    assert dt._haversine_km(40.0, -74.0, 40.0, -74.0) == 0.0


def test_haversine_known_distance_new_york_to_london():
    # Real great-circle distance is ~5570km; wide tolerance since this is just a sanity check.
    km = dt._haversine_km(40.7128, -74.0060, 51.5074, -0.1278)
    assert 5400 < km < 5750


def test_parse_inventory_reads_expected_fields(tmp_path):
    inv_path = tmp_path / "stations.inv"
    inv_path.write_text(
        _inv_line("US000123456", 40.7128, -74.0060, 10.0, "NEW YORK CITY")
        + _inv_line("UK000654321", 51.5074, -0.1278, 25.0, "LONDON")
    )

    stations = dt.parse_inventory(inv_path)

    assert set(stations) == {"US000123456", "UK000654321"}
    assert stations["US000123456"]["name"] == "NEW YORK CITY"
    assert stations["US000123456"]["lat"] == 40.7128
    assert stations["US000123456"]["lon"] == -74.0060


def test_find_best_station_picks_the_closer_one_when_both_are_current():
    stations = {
        "FAR": {"lat": 0.0, "lon": 0.0, "elevation_m": 0.0, "name": "Far away"},
        "NEAR": {"lat": 40.70, "lon": -74.00, "elevation_m": 0.0, "name": "Nearby"},
    }
    current_year = dt.date.today().year
    last_year = {"FAR": current_year, "NEAR": current_year}

    station_id, distance = dt.find_best_station(stations, last_year, 40.7128, -74.0060)

    assert station_id == "NEAR"
    assert distance < 10


def test_find_best_station_prefers_currency_over_proximity():
    # Regression test for the real London case: the nearest station (STALE) stopped reporting
    # years ago, while a station a bit further out (CURRENT) is still reporting today.
    stations = {
        "STALE": {"lat": 40.70, "lon": -74.00, "elevation_m": 0.0, "name": "Nearby but dead"},
        "CURRENT": {"lat": 40.90, "lon": -74.20, "elevation_m": 0.0, "name": "Further but live"},
    }
    last_year = {"STALE": 2011, "CURRENT": dt.date.today().year}

    station_id, _distance = dt.find_best_station(stations, last_year, 40.7128, -74.0060)

    assert station_id == "CURRENT"


def test_find_best_station_falls_back_to_nearest_when_none_are_current(caplog):
    stations = {"ONLY": {"lat": 0.0, "lon": 0.0, "elevation_m": 0.0, "name": "Origin"}}
    last_year = {"ONLY": 1990}

    with caplog.at_level("WARNING"):
        station_id, _distance = dt.find_best_station(stations, last_year, 40.7128, -74.0060)

    assert station_id == "ONLY"
    assert "falling back to nearest station" in caplog.text


def test_find_best_station_warns_past_sanity_threshold(caplog):
    stations = {"ONLY": {"lat": 0.0, "lon": 0.0, "elevation_m": 0.0, "name": "Origin"}}
    last_year = {"ONLY": dt.date.today().year}

    with caplog.at_level("WARNING"):
        dt.find_best_station(stations, last_year, 40.7128, -74.0060)

    assert "may not represent local climate" in caplog.text


def test_find_best_station_prefers_baseline_coverage_over_proximity():
    # Regression test for the real Delhi case: the nearest current station (PALAM) starts in
    # 1997, so it has no 1961-1990 baseline; SAFDARJUNG, slightly further, has all 30 years.
    stations = {
        "PALAM": {"lat": 40.72, "lon": -74.00, "elevation_m": 0.0, "name": "Near, no baseline"},
        "SAFDARJUNG": {"lat": 40.80, "lon": -74.05, "elevation_m": 0.0, "name": "Full baseline"},
    }
    current_year = dt.date.today().year
    last_year = {"PALAM": current_year, "SAFDARJUNG": current_year}
    baseline_years = {"SAFDARJUNG": 30}

    station_id, _distance = dt.find_best_station(
        stations, last_year, 40.7128, -74.0060, baseline_years
    )

    assert station_id == "SAFDARJUNG"


def test_find_best_station_breaks_baseline_ties_by_distance():
    stations = {
        "NEAR": {"lat": 40.72, "lon": -74.00, "elevation_m": 0.0, "name": "Near"},
        "FAR": {"lat": 40.90, "lon": -74.20, "elevation_m": 0.0, "name": "Far"},
    }
    current_year = dt.date.today().year
    last_year = {"NEAR": current_year, "FAR": current_year}

    station_id, _distance = dt.find_best_station(
        stations, last_year, 40.7128, -74.0060, {"NEAR": 30, "FAR": 30}
    )

    assert station_id == "NEAR"


def test_find_best_station_ignores_baseline_beyond_search_radius():
    # A perfect baseline 100+km away shouldn't beat the city's own station.
    stations = {
        "CITY": {"lat": 40.72, "lon": -74.00, "elevation_m": 0.0, "name": "In the city"},
        "DISTANT": {"lat": 42.00, "lon": -74.00, "elevation_m": 0.0, "name": "Upstate"},
    }
    current_year = dt.date.today().year
    last_year = {"CITY": current_year, "DISTANT": current_year}

    station_id, _distance = dt.find_best_station(
        stations, last_year, 40.7128, -74.0060, {"CITY": 5, "DISTANT": 30}
    )

    assert station_id == "CITY"


def test_scan_baseline_years_counts_only_full_baseline_years(tmp_path):
    dat_path = tmp_path / "data.dat"
    dat_path.write_text(
        _dat_line("US000111111", 1960, [1.0] * 12)  # before the baseline
        + _dat_line("US000111111", 1961, [1.0] * 12)
        + _dat_line("US000111111", 1975, [1.0] * 9 + [None] * 3)  # only 9 months
        + _dat_line("US000111111", 1990, [1.0] * 10 + [None] * 2)
        + _dat_line("US000222222", 2000, [1.0] * 12)  # after the baseline
    )

    assert dt.scan_baseline_years(dat_path) == {"US000111111": 2}


def test_scan_station_last_years(tmp_path):
    dat_path = tmp_path / "data.dat"
    dat_path.write_text(
        _dat_line("US000111111", 2015, [1.0] * 12)
        + _dat_line("US000111111", 2020, [1.0] * 12)
        + _dat_line("US000222222", 1999, [2.0] * 12)
    )

    last_year = dt.scan_station_last_years(dat_path)

    assert last_year == {"US000111111": 2020, "US000222222": 1999}


def test_parse_station_series_extracts_values_and_skips_missing(tmp_path):
    dat_path = tmp_path / "data.dat"
    values = [1.23, -4.56, None, 7.89] + [10.0] * 8  # 12 months, one missing
    dat_path.write_text(_dat_line("US000123456", 2020, values))

    readings = dt.parse_station_series(dat_path, "US000123456")

    assert len(readings) == 11  # 12 months minus the one missing
    assert readings[0] == {"year": 2020, "month": 1, "temp_c": 1.23}
    assert readings[1] == {"year": 2020, "month": 2, "temp_c": -4.56}
    # month 3 (missing) is skipped entirely
    assert readings[2] == {"year": 2020, "month": 4, "temp_c": 7.89}


def test_parse_station_series_ignores_other_stations(tmp_path):
    dat_path = tmp_path / "data.dat"
    dat_path.write_text(
        _dat_line("US000111111", 2020, [1.0] * 12)
        + _dat_line("US000222222", 2020, [2.0] * 12)
    )

    readings = dt.parse_station_series(dat_path, "US000222222")

    assert len(readings) == 12
    assert all(r["temp_c"] == 2.0 for r in readings)


def test_download_city_skips_when_output_already_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "RAW_DIR", tmp_path)
    existing = tmp_path / "testcity.json"
    existing.write_text('{"station_id": "OLD", "readings": []}')

    dt.download_city(
        "testcity", 0.0, 0.0,
        stations={}, last_year={}, dat_path=tmp_path / "unused.dat", overwrite=False,
    )

    # Untouched — find_best_station would have raised on the empty stations dict if this ran.
    assert existing.read_text() == '{"station_id": "OLD", "readings": []}'
