"""Unit tests for the SQLite build and SQL aggregations (aggregate.py).

Fixtures are tiny hand-built CSVs written to tmp_path, so the SQL is checked against answers
worked out by hand (and against analysis.py's pandas version of the same anomaly).
"""

import json
import sqlite3

import pandas as pd
import pytest

import aggregate
import analysis


def _write_fixtures(tmp_path, monthly: pd.DataFrame, aq: pd.DataFrame | None = None):
    processed = tmp_path / "processed"
    ghcn = tmp_path / "ghcn"
    processed.mkdir()
    ghcn.mkdir()
    monthly.to_csv(processed / "temperature_monthly.csv", index=False)
    annual = (
        monthly.groupby(["city", "year"])
        .agg(temp_c=("temp_c", "mean"), n_months=("month", "size"))
        .reset_index()
    )
    annual.to_csv(processed / "temperature_annual.csv", index=False)
    if aq is None:
        aq = pd.DataFrame(columns=["city", "year", "pm25", "n_months", "n_locations"])
    aq.to_csv(processed / "air_quality_annual.csv", index=False)
    (ghcn / "london.json").write_text(
        json.dumps({"station_id": "UK1", "station_name": "HEATHROW", "distance_km": 23.3})
    )
    return processed, ghcn, annual


def _monthly(city, years, base=10.0, wiggle=True):
    """12 months a year; alternating +/-0.5 year to year so the baseline has a real spread."""
    rows = []
    for y in years:
        shift = (0.5 if y % 2 else -0.5) if wiggle else 0.0
        rows += [
            {"city": city, "year": y, "month": m, "temp_c": base + m + shift}
            for m in range(1, 13)
        ]
    return pd.DataFrame(rows)


@pytest.fixture
def conn(tmp_path):
    monthly = _monthly("london", range(1961, 2001))
    # 2000: make July 20 °C hotter than usual — far beyond 2 sd of a ±0.5 spread, and enough
    # (+1.67 on the annual mean) to make 2000 the single warmest year.
    monthly.loc[(monthly["year"] == 2000) & (monthly["month"] == 7), "temp_c"] += 20
    processed, ghcn, _ = _write_fixtures(tmp_path, monthly)
    connection = aggregate.build_database(tmp_path / "test.sqlite", processed, ghcn)
    yield connection
    connection.close()


def test_baseline_is_mean_of_1961_1990_annual_values(conn):
    base = aggregate.query(conn, "baseline", "london")[0]

    # Annual mean = 10 + 6.5 (mean of months 1..12) ± 0.5 alternating -> exactly 16.5 over 30 yrs.
    assert base["baseline_c"] == pytest.approx(16.5)
    assert base["baseline_years"] == 30


def test_sql_anomaly_matches_pandas_anomaly(tmp_path):
    monthly = _monthly("london", range(1955, 2010))
    monthly.loc[monthly["year"] >= 1995, "temp_c"] += 1.2
    processed, ghcn, annual = _write_fixtures(tmp_path, monthly)
    conn = aggregate.build_database(tmp_path / "t.sqlite", processed, ghcn)

    sql = pd.DataFrame(aggregate.query(conn, "temperature", "london")).set_index("year")
    pandas = analysis.add_anomalies(annual).set_index("year")
    conn.close()

    assert sql["anomaly_c"].to_numpy() == pytest.approx(pandas["anomaly_c"].to_numpy())


def test_extreme_heat_months_flags_only_the_outlier(conn):
    rows = {r["year"]: r["hot_months"] for r in aggregate.query(conn, "extreme_heat", "london")}

    assert rows[2000] == 1
    assert sum(rows.values()) == 1


def test_warmest_years_are_ranked(conn):
    warmest = aggregate.query(conn, "warmest_years", "london")

    assert warmest[0] == {"year": 2000, "anomaly_c": pytest.approx(20 / 12 - 0.5), "rank": 1}
    # The other odd years tie at +0.5: RANK() gives them all rank 2, so the top 5 has >5 rows.
    assert {r["rank"] for r in warmest[1:]} == {2}


def test_decades_need_five_years(tmp_path):
    processed, ghcn, _ = _write_fixtures(tmp_path, _monthly("london", range(1961, 2003)))
    conn = aggregate.build_database(tmp_path / "t.sqlite", processed, ghcn)

    decades = [r["decade"] for r in aggregate.query(conn, "decades", "london")]
    conn.close()

    assert decades == [1960, 1970, 1980, 1990]  # 2000s has only 3 years


def test_schema_rejects_duplicate_city_years(tmp_path):
    processed, ghcn, annual = _write_fixtures(tmp_path, _monthly("london", range(1961, 1965)))
    pd.concat([annual, annual.head(1)]).to_csv(processed / "temperature_annual.csv", index=False)

    # pandas wraps the driver error in its own DatabaseError; the cause is the PK violation.
    with pytest.raises(pd.errors.DatabaseError) as excinfo:
        aggregate.build_database(tmp_path / "t.sqlite", processed, ghcn)
    assert isinstance(excinfo.value.__cause__, sqlite3.IntegrityError)


def test_build_database_replaces_an_existing_file(tmp_path):
    processed, ghcn, _ = _write_fixtures(tmp_path, _monthly("london", range(1961, 1991)))
    db = tmp_path / "t.sqlite"
    aggregate.build_database(db, processed, ghcn).close()
    conn = aggregate.build_database(db, processed, ghcn)  # must not fail on existing tables

    assert aggregate.query(conn, "station", "london")[0]["station_name"] == "HEATHROW"
    conn.close()
