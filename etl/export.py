"""Phase 3 — export the site's data: one JSON per city plus an index.

Combines aggregate.py's SQL results with analysis.py's statistics into web/public/data/:

    cities.json      index: every city's name, coordinates, and headline numbers + methodology
    <city>.json      full series for one city (see CITY_SCHEMA_VERSION / build_city)

The JSON is committed to the repo (unlike everything under etl/data/): the deployed site is
built from the repo, and rebuilding it needs the raw downloads and an OpenAQ key it won't have.

Run the pipeline in order:
    python clean.py && python analysis.py && python export.py
(export.py rebuilds the SQLite database itself via aggregate.build_database.)
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

import pandas as pd

import aggregate
import analysis
from cities import CITIES, CITY_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
CITY_SCHEMA_VERSION = 1
WHO_PM25_ANNUAL_GUIDELINE = 5.0  # µg/m³, WHO 2021 air quality guidelines

# City-specific caveats shown next to that city's charts. Kept with the export so the site
# can't show a number without its limitation.
NOTES: dict[str, list[str]] = {
    "lahore": ["PM2.5 comes from a single monitor (US Diplomatic Post) and starts in 2020."],
    "beijing": [],
    "sao_paulo": ["PM2.5 is available only from 2021, too short to estimate a trend."],
    "addis_ababa": ["PM2.5 comes from a few monitors, mainly the US Embassy."],
    "new_york": [
        "Temperature is from Newark Airport (14 km), which has a complete 1961-1990 baseline."
    ],
    "delhi": [
        "Delhi warms slowest of the eleven; heavy particulate pollution may be masking part of "
        "the warming by reflecting sunlight (aerosol dimming).",
    ],
    "ho_chi_minh_city": [
        "PM2.5 comes from a single monitor (US Diplomatic Post); its readings became faulty in "
        "2022 and those years are excluded.",
    ],
    "jakarta": [
        "The temperature record has almost no data from 1985 to 2008 and resumes about 1.5 °C "
        "warmer; part of that step may be a station change. Only 14 of 30 baseline years exist, "
        "so Jakarta's anomalies are the least certain of the eleven cities.",
    ],
    "london": ["The number of PM2.5 monitors grows over time (up to ~80)."],
    "sydney": ["PM2.5 has only 4 usable years (2018-2022), too short to estimate a trend."],
    "santiago": ["Only 21 of 30 baseline years exist for temperature."],
}

METHODOLOGY = {
    "baseline_period": list(analysis.BASELINE),
    "trend_start_year": analysis.TREND_START,
    "rolling_window_years": analysis.ROLLING_WINDOW,
    "extreme_heat_month": (
        f"A month more than {aggregate.EXTREME_SD:g} standard deviations above that calendar "
        "month's 1961-1990 mean."
    ),
    "who_pm25_guideline": WHO_PM25_ANNUAL_GUIDELINE,
    "sources": {
        "temperature": "NOAA GHCN-Monthly v4 (quality-controlled, homogenized)",
        "air_quality": "OpenAQ v3, monthly PM2.5 aggregates from reference monitors",
    },
    "caveat": (
        "Temperature and PM2.5 are shown side by side, not as cause and effect: warming is driven "
        "by global greenhouse gases, PM2.5 by local emissions and weather."
    ),
}


def _round(value, digits: int = 3):
    """Round floats for compact JSON; NaN -> None (JSON has no NaN)."""
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, digits)
    return value


def _rows(rows: list[dict], digits: int = 3) -> list[dict]:
    return [{k: _round(v, digits) for k, v in row.items()} for row in rows]


def build_city(conn, city: str, summary: dict, rolling: dict[int, float]) -> dict:
    """Assemble one city's JSON document."""
    lat, lon = CITIES[city]
    station = aggregate.query(conn, "station", city)
    baseline = aggregate.query(conn, "baseline", city)
    temperature = aggregate.query(conn, "temperature", city)
    for row in temperature:
        row["rolling_c"] = rolling.get(row["year"])
    air = aggregate.query(conn, "air_quality", city)
    for row in air:
        row["who_multiple"] = row["pm25"] / WHO_PM25_ANNUAL_GUIDELINE

    return {
        "schema_version": CITY_SCHEMA_VERSION,
        "id": city,
        "name": CITY_NAMES[city],
        "lat": lat,
        "lon": lon,
        "station": station[0] if station else None,
        "baseline": {"period": list(analysis.BASELINE), **_rows(baseline)[0]}
        if baseline
        else None,
        "temperature": _rows(temperature),
        "extreme_heat": aggregate.query(conn, "extreme_heat", city),
        "decades": _rows(aggregate.query(conn, "decades", city)),
        "warmest_years": _rows(aggregate.query(conn, "warmest_years", city)),
        "air_quality": _rows(air, 2),
        "stats": summary,
        "notes": NOTES.get(city, []),
    }


def headline(doc: dict) -> dict:
    """The few numbers the index (and the city picker) needs."""
    stats = doc["stats"]
    t = stats.get("temperature_trend") or {}
    a = stats.get("pm25_trend") or {}
    return {
        "id": doc["id"],
        "name": doc["name"],
        "lat": doc["lat"],
        "lon": doc["lon"],
        "warming_per_decade_c": t.get("per_decade_c"),
        "recent_anomaly_c": stats.get("recent_anomaly_c"),
        "temperature_years": [doc["temperature"][0]["year"], doc["temperature"][-1]["year"]]
        if doc["temperature"]
        else None,
        "mean_pm25": a.get("mean_pm25"),
        "pm25_pct_per_year": a.get("pct_per_year") if a.get("sufficient") else None,
        "pm25_years": [doc["air_quality"][0]["year"], doc["air_quality"][-1]["year"]]
        if doc["air_quality"]
        else None,
    }


def export(
    out_dir: Path = OUT_DIR,
    db_path: Path = aggregate.DB_PATH,
    processed_dir: Path = aggregate.PROCESSED_DIR,
    ghcn_dir: Path = aggregate.GHCN_DIR,
) -> list[dict]:
    """Write every city's JSON and the index. Returns the index entries."""
    conn = aggregate.build_database(db_path, processed_dir, ghcn_dir)
    temp, aq = analysis.load_processed(processed_dir)
    summary = analysis.summarize(temp, aq)
    rolled = analysis.add_rolling_mean(analysis.add_anomalies(temp), "anomaly_c")

    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for city in CITIES:
        city_rolling = rolled[rolled["city"] == city].set_index("year")["anomaly_c_rolling"]
        rolling = {int(y): _round(float(v)) for y, v in city_rolling.items() if pd.notna(v)}
        doc = build_city(conn, city, summary[city], rolling)
        (out_dir / f"{city}.json").write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        index.append(headline(doc))
    conn.close()

    (out_dir / "cities.json").write_text(
        json.dumps(
            {
                "generated": date.today().isoformat(),
                "methodology": METHODOLOGY,
                "cities": index,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return index


def main() -> None:
    index = export()
    total_kb = sum(p.stat().st_size for p in OUT_DIR.glob("*.json")) / 1024
    log.info("exported %d cities to %s (%.0f KB)", len(index), OUT_DIR, total_kb)


if __name__ == "__main__":
    main()
