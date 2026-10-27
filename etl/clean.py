"""Phase 2 — clean and validate the raw downloads into annual series per city.

Inputs (from Phase 1):
    data/raw/ghcn/<city>.json             one GHCN station's monthly mean temperature
    data/raw/openaq/<city>/<sensor>.json  one sensor's monthly PM2.5 means + coverage stats

Outputs (data/processed/, gitignored — rebuild with `python clean.py`):
    temperature_monthly.csv   city, year, month, temp_c
    temperature_annual.csv    city, year, temp_c, n_months
    air_quality_monthly.csv   city, year, month, pm25, n_locations
    air_quality_annual.csv    city, year, pm25, n_months, n_locations
    quality_report.json       per-city coverage, gaps, and dropped-value counts

Methodology decisions, all deliberate:

1. Season-adjusted annual means. A plain average of whatever months a year happens to have is
   biased by which months are missing — a year missing two summer months reads too cold, a PM2.5
   year missing Delhi's winter reads far too clean. So each month is first expressed relative to
   that city's long-term mean for that calendar month, those offsets are averaged over the year,
   and the city's mean annual climatology is added back (see `annualize`). With all 12 months
   present this equals the plain mean exactly.
2. Minimum months per year: 10/12 for temperature, 8/12 for PM2.5. Years below that are dropped
   rather than estimated — including the current, still-incomplete year. PM2.5 is looser because
   OpenAQ's own record has gaps that no threshold fixes (every city is missing ~2 months of 2023,
   an upstream outage); with the season adjustment, 8 months still gives an unbiased annual mean.
3. PM2.5 months need >= 75% coverage (OpenAQ's own observed/expected count). Thinner months are
   too easily dominated by a few unusual days.
4. PM2.5 city value = mean of station values, where a station's value is the mean of its PM2.5
   sensors (some stations have two). The set of stations changes over time (London grows from a
   handful to ~190), which can shift the city mean independently of real air quality; the
   `n_locations` column is kept so this is visible rather than hidden.
5. Physically impossible values are dropped and counted in the report, not silently kept:
   temperature outside -60..60 °C, PM2.5 <= 0 or > 1000 µg/m³.
6. Spike-contaminated PM2.5 months are dropped. US Diplomatic Post monitors report invalid hours
   as error codes (985, 1985, ...) that OpenAQ averages in as real values — Ho Chi Minh City had
   monthly means of 375 and even 985 µg/m³ against a typical 25-35. A sensor-month is dropped if
   its mean is more than 2x its median (a few junk days dominating) or any day in it averages
   above 900 µg/m³ (no real city sustains that for a day). That's ~1% of sensor-months.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from cities import CITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
GHCN_DIR = DATA_DIR / "raw" / "ghcn"
OPENAQ_DIR = DATA_DIR / "raw" / "openaq"
PROCESSED_DIR = DATA_DIR / "processed"

BASELINE = (1961, 1990)
TEMP_RANGE_C = (-60.0, 60.0)
PM25_RANGE = (0.0, 1000.0)  # exclusive lower bound: a monthly mean of exactly 0 is a sensor fault
MIN_PM25_COVERAGE_PCT = 75.0
MAX_MEAN_TO_MEDIAN = 2.0  # see module docstring, point 6
MAX_DAILY_PM25 = 900.0
MIN_TEMP_MONTHS = 10
MIN_PM25_MONTHS = 8


class DataQualityError(ValueError):
    """Raised when the data breaks an invariant that cleaning can't fix (e.g. duplicate rows)."""


def _assert_unique(df: pd.DataFrame, keys: list[str], what: str) -> None:
    dupes = df[df.duplicated(keys, keep=False)]
    if not dupes.empty:
        raise DataQualityError(f"{what}: {len(dupes)} duplicate rows on {keys}:\n{dupes.head()}")


# --- Temperature -------------------------------------------------------------------------------


def load_temperature(raw_dir: Path = GHCN_DIR, cities: list[str] | None = None) -> pd.DataFrame:
    """One row per (city, year, month) from each city's GHCN station file."""
    frames = []
    for city in cities or list(CITIES):
        path = raw_dir / f"{city}.json"
        if not path.exists():
            log.warning("temperature: no raw file for %s", city)
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        df = pd.DataFrame(raw["readings"], columns=["year", "month", "temp_c"])
        df.insert(0, "city", city)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["city", "year", "month", "temp_c"])
    return pd.concat(frames, ignore_index=True)


def clean_temperature(monthly: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop out-of-range months and check for duplicates. Returns (clean, dropped per city)."""
    _assert_unique(monthly, ["city", "year", "month"], "temperature")
    lo, hi = TEMP_RANGE_C
    bad = ~monthly["temp_c"].between(lo, hi)
    dropped = monthly[bad].groupby("city").size().to_dict()
    return monthly[~bad].reset_index(drop=True), dropped


# --- Air quality -------------------------------------------------------------------------------


def load_air_quality(raw_dir: Path = OPENAQ_DIR, cities: list[str] | None = None) -> pd.DataFrame:
    """One row per (city, sensor, month) from every sensor file OpenAQ returned.

    The month is taken from the period's LOCAL start time — OpenAQ's monthly windows are local
    calendar months, so the UTC start can fall on the last day of the previous month.
    """
    rows = []
    for city in cities or list(CITIES):
        city_dir = raw_dir / city
        if not city_dir.is_dir():
            log.warning("air quality: no raw folder for %s", city)
            continue
        for path in sorted(city_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue  # _locations.json etc.
            raw = json.loads(path.read_text(encoding="utf-8"))
            for month in raw.get("results", []):
                start = month["period"]["datetimeFrom"]["local"]
                summary = month.get("summary") or {}
                rows.append(
                    {
                        "city": city,
                        "location_id": raw["location_id"],
                        "sensor_id": raw["sensor_id"],
                        "year": int(start[:4]),
                        "month": int(start[5:7]),
                        "pm25": month.get("value"),
                        "daily_median": summary.get("median"),
                        "daily_max": summary.get("max"),
                        "coverage_pct": (month.get("coverage") or {}).get("percentComplete"),
                    }
                )
    columns = [
        "city", "location_id", "sensor_id", "year", "month",
        "pm25", "daily_median", "daily_max", "coverage_pct",
    ]
    return pd.DataFrame(rows, columns=columns)


def clean_air_quality(
    sensor_monthly: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Filter sensor-months, then average sensors -> stations -> one city value per month.

    Returns (city_monthly, dropped) where dropped[city] counts sensor-months removed for low
    coverage, out-of-range values, and error-code spikes. Each month is counted under the first
    rule that removes it.
    """
    _assert_unique(sensor_monthly, ["city", "sensor_id", "year", "month"], "air quality")
    df = sensor_monthly.dropna(subset=["pm25"])

    low_coverage = df["coverage_pct"].fillna(0) < MIN_PM25_COVERAGE_PCT
    lo, hi = PM25_RANGE
    out_of_range = ~low_coverage & ~((df["pm25"] > lo) & (df["pm25"] <= hi))
    spiky = (df["pm25"] > MAX_MEAN_TO_MEDIAN * df["daily_median"]) | (
        df["daily_max"] > MAX_DAILY_PM25
    )
    spiky &= ~low_coverage & ~out_of_range

    dropped: dict[str, dict[str, int]] = {}
    for city in df["city"].unique():
        in_city = df["city"] == city
        dropped[city] = {
            "low_coverage_months": int((low_coverage & in_city).sum()),
            "out_of_range_months": int((out_of_range & in_city).sum()),
            "spike_months": int((spiky & in_city).sum()),
        }

    kept = df[~low_coverage & ~out_of_range & ~spiky]
    per_location = kept.groupby(["city", "location_id", "year", "month"], as_index=False)[
        "pm25"
    ].mean()
    city_monthly = (
        per_location.groupby(["city", "year", "month"])
        .agg(pm25=("pm25", "mean"), n_locations=("location_id", "nunique"))
        .reset_index()
    )
    return city_monthly, dropped


# --- Shared ------------------------------------------------------------------------------------


def annualize(monthly: pd.DataFrame, value_col: str, min_months: int) -> pd.DataFrame:
    """Season-adjusted annual mean per (city, year); years with < min_months are dropped.

    annual = mean over the year's available months of (value - city's mean for that calendar
    month) + mean of the city's 12 monthly means. Equal to the plain mean when all 12 months are
    present; unbiased by which months are missing when some aren't (module docstring, point 1).
    """
    df = monthly[["city", "year", "month", value_col]].copy()
    climatology = df.groupby(["city", "month"])[value_col].transform("mean")
    df["offset"] = df[value_col] - climatology
    city_normal = df.groupby(["city", "month"])[value_col].mean().groupby("city").mean()

    annual = df.groupby(["city", "year"]).agg(
        offset=("offset", "mean"), n_months=("month", "nunique")
    )
    annual = annual[annual["n_months"] >= min_months].reset_index()
    annual[value_col] = annual["offset"] + annual["city"].map(city_normal)
    return annual[["city", "year", value_col, "n_months"]]


def longest_gap_years(years: pd.Series) -> int:
    """Longest run of missing years between the first and last year present."""
    ordered = sorted(set(years))
    if len(ordered) < 2:
        return 0
    return max(b - a - 1 for a, b in zip(ordered, ordered[1:], strict=False))


def quality_report(
    temp_annual: pd.DataFrame,
    temp_dropped: dict[str, int],
    aq_annual: pd.DataFrame,
    aq_monthly: pd.DataFrame,
    aq_dropped: dict[str, dict[str, int]],
) -> dict[str, dict]:
    report: dict[str, dict] = {}
    for city in CITIES:
        t = temp_annual[temp_annual["city"] == city]
        a = aq_annual[aq_annual["city"] == city]
        baseline_years = t["year"].between(*BASELINE).sum()
        report[city] = {
            "temperature": {
                "first_year": int(t["year"].min()) if len(t) else None,
                "last_year": int(t["year"].max()) if len(t) else None,
                "n_years": int(len(t)),
                "baseline_years": int(baseline_years),
                "baseline_ok": bool(baseline_years >= 20),
                "longest_gap_years": longest_gap_years(t["year"]),
                "dropped_out_of_range_months": int(temp_dropped.get(city, 0)),
            },
            "air_quality": {
                "first_year": int(a["year"].min()) if len(a) else None,
                "last_year": int(a["year"].max()) if len(a) else None,
                "n_years": int(len(a)),
                "longest_gap_years": longest_gap_years(a["year"]),
                "max_locations": int(
                    aq_monthly.loc[aq_monthly["city"] == city, "n_locations"].max()
                )
                if (aq_monthly["city"] == city).any()
                else 0,
                **aq_dropped.get(
                    city, {"low_coverage_months": 0, "out_of_range_months": 0, "spike_months": 0}
                ),
            },
        }
    return report


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    temp_monthly, temp_dropped = clean_temperature(load_temperature())
    temp_annual = annualize(temp_monthly, "temp_c", MIN_TEMP_MONTHS)

    aq_monthly, aq_dropped = clean_air_quality(load_air_quality())
    aq_annual = annualize(aq_monthly, "pm25", MIN_PM25_MONTHS)
    aq_annual = aq_annual.merge(
        aq_monthly.groupby(["city", "year"])["n_locations"].max().reset_index(),
        on=["city", "year"],
    )

    _assert_unique(temp_annual, ["city", "year"], "temperature annual")
    _assert_unique(aq_annual, ["city", "year"], "air quality annual")

    temp_monthly.to_csv(PROCESSED_DIR / "temperature_monthly.csv", index=False)
    temp_annual.round(3).to_csv(PROCESSED_DIR / "temperature_annual.csv", index=False)
    aq_monthly.round(2).to_csv(PROCESSED_DIR / "air_quality_monthly.csv", index=False)
    aq_annual.round(2).to_csv(PROCESSED_DIR / "air_quality_annual.csv", index=False)

    report = quality_report(temp_annual, temp_dropped, aq_annual, aq_monthly, aq_dropped)
    (PROCESSED_DIR / "quality_report.json").write_text(json.dumps(report, indent=2))

    for city, r in report.items():
        t, a = r["temperature"], r["air_quality"]
        log.info(
            "%-17s temp %s-%s (%d yrs, baseline %d/30)   PM2.5 %s-%s (%d yrs, up to %d stations)",
            city, t["first_year"], t["last_year"], t["n_years"], t["baseline_years"],
            a["first_year"], a["last_year"], a["n_years"], a["max_locations"],
        )
        if not t["baseline_ok"]:
            log.warning("%s: only %d baseline years in 1961-1990", city, t["baseline_years"])


if __name__ == "__main__":
    main()
