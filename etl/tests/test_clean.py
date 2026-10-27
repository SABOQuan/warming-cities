"""Unit tests for the Phase 2 cleaning step (clean.py).

All fixtures are small hand-built DataFrames / JSON files, not the real downloads, so the tests
run instantly and pin down each methodology rule from clean.py's module docstring.
"""

import json

import pandas as pd
import pytest

import clean

SEASONAL = [10, 12, 15, 19, 23, 27, 30, 29, 25, 20, 15, 11]  # a city's monthly pattern


def _monthly(city: str, year: int, values: list[float | None], col: str = "temp_c"):
    return pd.DataFrame(
        [
            {"city": city, "year": year, "month": m, col: v}
            for m, v in enumerate(values, start=1)
            if v is not None
        ]
    )


# --- annualize ---------------------------------------------------------------------------------


def test_annualize_equals_plain_mean_when_all_months_present():
    df = pd.concat([_monthly("x", 2000, SEASONAL), _monthly("x", 2001, [v + 1 for v in SEASONAL])])

    annual = clean.annualize(df, "temp_c", min_months=10)

    expected = [sum(SEASONAL) / 12, sum(SEASONAL) / 12 + 1]
    assert annual["temp_c"].tolist() == pytest.approx(expected)


def test_annualize_is_not_biased_by_missing_summer_months():
    """2001 is uniformly 1 °C warmer than 2000 but is missing July and August. A plain mean
    would read it as colder (the hottest months are gone); the season adjustment must not."""
    warmer = [v + 1 for v in SEASONAL]
    warmer[6] = warmer[7] = None
    df = pd.concat([_monthly("x", 2000, SEASONAL), _monthly("x", 2001, warmer)])

    annual = clean.annualize(df, "temp_c", min_months=10).set_index("year")["temp_c"]

    assert annual[2001] - annual[2000] == pytest.approx(1.0, abs=0.15)


def test_annualize_drops_years_below_min_months():
    short = SEASONAL[:9] + [None, None, None]
    df = pd.concat([_monthly("x", 2000, SEASONAL), _monthly("x", 2001, short)])

    annual = clean.annualize(df, "temp_c", min_months=10)

    assert annual["year"].tolist() == [2000]
    assert annual["n_months"].tolist() == [12]


def test_annualize_keeps_cities_separate():
    df = pd.concat([_monthly("hot", 2000, [30] * 12), _monthly("cold", 2000, [0] * 12)])

    annual = clean.annualize(df, "temp_c", min_months=10).set_index("city")["temp_c"]

    assert annual["hot"] == pytest.approx(30)
    assert annual["cold"] == pytest.approx(0)


# --- temperature -------------------------------------------------------------------------------


def test_clean_temperature_drops_and_counts_impossible_values():
    df = _monthly("x", 2000, [10, 999.0, 12, -80.0] + [10] * 8)

    cleaned, dropped = clean.clean_temperature(df)

    assert len(cleaned) == 10
    assert dropped == {"x": 2}


def test_clean_temperature_rejects_duplicate_months():
    df = pd.concat([_monthly("x", 2000, [10] * 12), _monthly("x", 2000, [11] + [None] * 11)])

    with pytest.raises(clean.DataQualityError):
        clean.clean_temperature(df)


def test_load_temperature_reads_station_files(tmp_path):
    (tmp_path / "lahore.json").write_text(
        json.dumps({"station_id": "PK1", "readings": [{"year": 2000, "month": 1, "temp_c": 12.5}]})
    )

    df = clean.load_temperature(tmp_path, cities=["lahore", "missing_city"])

    assert df.to_dict("records") == [{"city": "lahore", "year": 2000, "month": 1, "temp_c": 12.5}]


# --- air quality -------------------------------------------------------------------------------


def _sensor_month(sensor, location, month, pm25, coverage=100.0, median=None, max_=None):
    return {
        "city": "x",
        "location_id": location,
        "sensor_id": sensor,
        "year": 2020,
        "month": month,
        "pm25": pm25,
        "daily_median": pm25 if median is None else median,
        "daily_max": pm25 * 1.5 if max_ is None else max_,
        "coverage_pct": coverage,
    }


def test_clean_air_quality_averages_sensors_then_stations():
    """Two sensors at one station must count once: city = mean(station A, station B)."""
    df = pd.DataFrame(
        [
            _sensor_month(1, "A", 1, 10.0),
            _sensor_month(2, "A", 1, 20.0),  # station A -> 15
            _sensor_month(3, "B", 1, 45.0),  # station B -> 45
        ]
    )

    city_monthly, _ = clean.clean_air_quality(df)

    assert city_monthly["pm25"].tolist() == [30.0]
    assert city_monthly["n_locations"].tolist() == [2]


def test_clean_air_quality_drops_low_coverage_months():
    df = pd.DataFrame([_sensor_month(1, "A", 1, 10.0), _sensor_month(1, "A", 2, 99.0, 40.0)])

    city_monthly, dropped = clean.clean_air_quality(df)

    assert city_monthly["month"].tolist() == [1]
    assert dropped["x"]["low_coverage_months"] == 1


def test_clean_air_quality_drops_out_of_range_values():
    df = pd.DataFrame(
        [_sensor_month(1, "A", 1, 10.0), _sensor_month(1, "A", 2, 0.0, median=0.0, max_=0.0)]
    )

    _, dropped = clean.clean_air_quality(df)

    assert dropped["x"]["out_of_range_months"] == 1


def test_clean_air_quality_drops_error_code_spikes():
    """Real case: a US Diplomatic Post month whose mean (375) is dragged up by 985 error codes
    while its median day (25.7) is normal. And a month with a single impossible day > 900."""
    df = pd.DataFrame(
        [
            _sensor_month(1, "A", 1, 30.0),
            _sensor_month(1, "A", 2, 375.0, median=25.7, max_=985.0),
            _sensor_month(1, "A", 3, 60.0, median=45.0, max_=1985.0),
        ]
    )

    city_monthly, dropped = clean.clean_air_quality(df)

    assert city_monthly["month"].tolist() == [1]
    assert dropped["x"]["spike_months"] == 2


def test_load_air_quality_uses_local_month(tmp_path):
    """OpenAQ's monthly window for Lahore starts 2019-04-30T19:00Z = 2019-05-01 local: May."""
    city_dir = tmp_path / "lahore"
    city_dir.mkdir()
    (city_dir / "_locations.json").write_text("[]")
    month = {
        "value": 103.0,
        "period": {
            "datetimeFrom": {"utc": "2019-04-30T19:00:00Z", "local": "2019-05-01T00:00:00+05:00"}
        },
        "summary": {"median": 94.1, "max": 213.8},
        "coverage": {"percentComplete": 100.0},
    }
    (city_dir / "25135.json").write_text(
        json.dumps({"location_id": 8664, "sensor_id": 25135, "results": [month]})
    )

    df = clean.load_air_quality(tmp_path, cities=["lahore"])

    assert (df.loc[0, "year"], df.loc[0, "month"]) == (2019, 5)
    assert df.loc[0, "daily_median"] == 94.1


# --- helpers -----------------------------------------------------------------------------------


def test_longest_gap_years():
    assert clean.longest_gap_years(pd.Series([2000, 2001, 2005, 2006, 2008])) == 3
    assert clean.longest_gap_years(pd.Series([2000])) == 0
