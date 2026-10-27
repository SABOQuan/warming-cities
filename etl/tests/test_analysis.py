"""Unit tests for the Phase 2.5 statistics (analysis.py).

Fixtures are synthetic series with a known answer — e.g. a city warming at exactly 0.3 °C per
decade — so each test checks the arithmetic, not the real data.
"""

import numpy as np
import pandas as pd
import pytest

import analysis


def _temp(city: str, years, base: float = 15.0, per_decade: float = 0.0, noise=None):
    years = list(years)
    values = [base + per_decade * (y - years[0]) / 10 for y in years]
    if noise is not None:
        values = [v + n for v, n in zip(values, noise, strict=True)]
    return pd.DataFrame({"city": city, "year": years, "temp_c": values})


def test_linear_trend_recovers_exact_slope():
    fit = analysis.linear_trend(pd.Series([2000, 2001, 2002, 2003]), pd.Series([1, 3, 5, 7]))

    assert fit["slope"] == pytest.approx(2.0)
    assert fit["ci95_low"] == pytest.approx(2.0)
    assert fit["ci95_high"] == pytest.approx(2.0)
    assert fit["n"] == 4


def test_linear_trend_needs_three_points():
    assert analysis.linear_trend(pd.Series([2000, 2001]), pd.Series([1.0, 2.0])) is None


def test_temperature_trend_is_per_decade_and_starts_at_trend_start():
    rng = np.random.default_rng(0)
    # Flat before 1970, then warming 0.3 °C/decade: a full-record fit would understate it.
    early = _temp("x", range(1900, 1970), base=14.0)
    late = _temp("x", range(1970, 2026), base=14.0, per_decade=0.3, noise=rng.normal(0, 0.1, 56))
    trends = analysis.temperature_trends(pd.concat([early, late]))

    row = trends.iloc[0]
    assert row["first_year"] == 1970
    assert row["per_decade_c"] == pytest.approx(0.3, abs=0.03)
    assert row["ci95_low_c"] < 0.3 < row["ci95_high_c"]


def test_add_anomalies_uses_each_citys_own_baseline():
    df = pd.concat(
        [_temp("hot", range(1961, 2001), base=30.0), _temp("cold", range(1961, 2001), base=0.0)]
    )
    df.loc[(df["city"] == "hot") & (df["year"] == 2000), "temp_c"] = 31.5

    out = analysis.add_anomalies(df).set_index(["city", "year"])

    assert out.loc[("hot", 2000), "anomaly_c"] == pytest.approx(1.5)
    assert out.loc[("cold", 1975), "anomaly_c"] == pytest.approx(0.0)
    assert out.loc[("hot", 1975), "baseline_years"] == 30


def test_rolling_mean_respects_calendar_gaps():
    """A 10-year window must not treat 1990 and 2010 as neighbours just because 1991-2009 are
    missing rows — with a big gap, the window falls below 70% coverage and yields NaN."""
    df = pd.concat([_temp("x", range(1981, 1991), base=10.0), _temp("x", [2010], base=20.0)])

    out = analysis.add_rolling_mean(df, "temp_c", window=10).set_index("year")

    assert out.loc[1986, "temp_c_rolling"] == pytest.approx(10.0)
    assert np.isnan(out.loc[2010, "temp_c_rolling"])


def test_pm25_trend_marks_short_records_insufficient():
    aq = pd.DataFrame(
        {
            "city": ["long"] * 6 + ["short"] * 3,
            "year": list(range(2016, 2022)) + [2020, 2021, 2022],
            "pm25": [60, 55, 50, 45, 40, 35] + [10, 11, 12],
        }
    )

    trends = analysis.pm25_trends(aq, min_years=5).set_index("city")

    assert trends.loc["long", "per_year"] == pytest.approx(-5.0)
    assert trends.loc["long", "pct_per_year"] == pytest.approx(-5.0 / 47.5 * 100)
    assert not trends.loc["short", "sufficient"]
    assert np.isnan(trends.loc["short", "per_year"])


def test_correlation_only_over_overlapping_years():
    temp = analysis.add_anomalies(_temp("x", range(1961, 2026), base=15.0))
    temp.loc[temp["year"] >= 2016, "anomaly_c"] = [0.1, 0.5, 0.2, 0.9, 0.4, 0.3, 0.8, 0.6, 0.7, 1.0]
    aq = pd.DataFrame(
        {"city": "x", "year": range(2016, 2026), "pm25": [10, 50, 20, 90, 40, 30, 80, 60, 70, 100]}
    )

    corr = analysis.temp_pm25_correlation(temp, aq).iloc[0]

    assert corr["n_years"] == 10
    assert corr["r"] == pytest.approx(1.0)


def test_summarize_is_json_ready_with_integer_years(monkeypatch):
    monkeypatch.setattr(analysis, "CITIES", {"x": (0.0, 0.0)})
    temp = _temp("x", range(1961, 2026), base=15.0, per_decade=0.2)
    aq = pd.DataFrame({"city": "x", "year": range(2016, 2026), "pm25": range(50, 40, -1)})

    summary = analysis.summarize(temp, aq)["x"]

    assert summary["baseline_ok"] is True
    assert isinstance(summary["temperature_trend"]["first_year"], int)
    assert summary["temperature_trend"]["per_decade_c"] == pytest.approx(0.2)
    assert summary["pm25_trend"]["per_year"] == pytest.approx(-1.0)
