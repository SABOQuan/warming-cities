"""Tests for the JSON export (export.py).

Two kinds:
- export() on small fixtures, checking the document shape and JSON-safety.
- Contract tests on the COMMITTED web/public/data/*.json — the files the site actually ships.
  These run in CI too (the JSON is committed even though the raw data isn't), so they catch an
  export that breaks the frontend's expectations, and they hold one city to a published figure.
"""

import json
import math
from pathlib import Path

import pandas as pd
import pytest

import export
from cities import CITIES

SHIPPED = Path(__file__).parent.parent.parent / "web" / "public" / "data"
CITY_KEYS = {
    "schema_version", "id", "name", "lat", "lon", "station", "baseline", "temperature",
    "extreme_heat", "decades", "warmest_years", "air_quality", "stats", "notes",
}


def _fixtures(tmp_path) -> tuple[Path, Path]:
    processed, ghcn = tmp_path / "processed", tmp_path / "ghcn"
    processed.mkdir()
    ghcn.mkdir()
    monthly, annual, aq = [], [], []
    for city in CITIES:
        for year in range(1961, 2026):
            temp = 15 + 0.02 * (year - 1961) + (0.3 if year % 2 else -0.3)
            monthly += [
                {"city": city, "year": year, "month": m, "temp_c": temp + m / 10}
                for m in range(1, 13)
            ]
            annual.append({"city": city, "year": year, "temp_c": temp + 0.65, "n_months": 12})
        aq += [
            {"city": city, "year": y, "pm25": 40.0 - y % 7, "n_months": 12, "n_locations": 2}
            for y in range(2016, 2026)
        ]
        (ghcn / f"{city}.json").write_text(
            json.dumps({"station_id": "S1", "station_name": "STATION", "distance_km": 5.0})
        )
    pd.DataFrame(monthly).to_csv(processed / "temperature_monthly.csv", index=False)
    pd.DataFrame(annual).to_csv(processed / "temperature_annual.csv", index=False)
    pd.DataFrame(aq).to_csv(processed / "air_quality_annual.csv", index=False)
    return processed, ghcn


def _no_nan(value) -> bool:
    if isinstance(value, float):
        return not math.isnan(value)
    if isinstance(value, dict):
        return all(_no_nan(v) for v in value.values())
    if isinstance(value, list):
        return all(_no_nan(v) for v in value)
    return True


def test_export_writes_every_city_and_an_index(tmp_path):
    processed, ghcn = _fixtures(tmp_path)
    out = tmp_path / "out"

    index = export.export(out, tmp_path / "t.sqlite", processed, ghcn)

    assert len(index) == len(CITIES)
    assert {p.stem for p in out.glob("*.json")} == set(CITIES) | {"cities"}
    doc = json.loads((out / "lahore.json").read_text(encoding="utf-8"))
    assert set(doc) == CITY_KEYS
    assert doc["air_quality"][0]["who_multiple"] == pytest.approx(doc["air_quality"][0]["pm25"] / 5)


def test_export_output_is_strict_json(tmp_path):
    """NaN isn't valid JSON (browsers' JSON.parse rejects it) — the rolling mean is NaN at the
    series edges, so export must turn it into null."""
    processed, ghcn = _fixtures(tmp_path)
    out = tmp_path / "out"
    export.export(out, tmp_path / "t.sqlite", processed, ghcn)

    for path in out.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "NaN" not in text
        doc = json.loads(text)
        assert _no_nan(doc)
    edges = json.loads((out / "london.json").read_text(encoding="utf-8"))["temperature"]
    assert edges[-1]["rolling_c"] is None


# --- contract tests on the shipped files -------------------------------------------------------


@pytest.mark.parametrize("city", sorted(CITIES))
def test_shipped_city_file_matches_contract(city):
    doc = json.loads((SHIPPED / f"{city}.json").read_text(encoding="utf-8"))

    assert set(doc) == CITY_KEYS
    assert doc["schema_version"] == export.CITY_SCHEMA_VERSION
    assert doc["temperature"], "every city must have a temperature series"
    years = [r["year"] for r in doc["temperature"]]
    assert years == sorted(years)
    assert all(-60 < r["temp_c"] < 60 for r in doc["temperature"])
    assert all(0 < r["pm25"] <= 1000 for r in doc["air_quality"])
    assert doc["stats"]["temperature_trend"]["per_decade_c"] is not None


def test_shipped_index_lists_every_city():
    index = json.loads((SHIPPED / "cities.json").read_text(encoding="utf-8"))

    assert [c["id"] for c in index["cities"]] == list(CITIES)
    assert index["methodology"]["baseline_period"] == [1961, 1990]


def test_london_baseline_matches_met_office_published_average():
    """Reference check against a published figure. The Met Office's 1961-1990 averages for
    Heathrow give an annual mean max of 14.46 °C and mean min of 6.73 °C, i.e. a mean of
    ~10.6 °C (metoffice.gov.uk UK climate averages, Heathrow). GHCN-M qcf is homogenized —
    older readings adjusted to the station's current state — so a small offset is expected;
    0.3 °C allows for that while still catching a wrong station, wrong units or a bad
    baseline period."""
    london = json.loads((SHIPPED / "london.json").read_text(encoding="utf-8"))

    assert london["station"]["station_name"] == "HEATHROW"
    assert london["baseline"]["baseline_c"] == pytest.approx((14.46 + 6.73) / 2, abs=0.3)
