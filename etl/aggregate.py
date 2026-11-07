"""Phase 3 — load the cleaned data into SQLite and do the aggregation in SQL.

Builds data/warming_cities.sqlite (gitignored, rebuilt by `python aggregate.py`) from clean.py's
CSVs plus each temperature station's metadata, then exposes the aggregations as named queries
that export.py runs.

Tables:   stations, temperature_monthly, temperature_annual, air_quality_annual
Views:    baseline                 per city: 1961-1990 mean annual temperature + years present
          temperature_anomaly      annual temperature minus that baseline
          monthly_normals          per city and calendar month: 1961-1990 mean and std dev
          extreme_heat_months      per city-year: months > 2 std devs above that month's normal

"Extreme-heat months" stand in for the roadmap's extreme-heat-day counts: GHCN-Monthly has no
daily data, so the closest honest measure is a month far hotter than that calendar month's own
1961-1990 normal. With normally distributed months, > 2 sd should happen ~2.3% of the time —
about 0.3 months a year — so a rising count is a direct, baseline-anchored sign of more heat.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from cities import CITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
GHCN_DIR = DATA_DIR / "raw" / "ghcn"
DB_PATH = DATA_DIR / "warming_cities.sqlite"

EXTREME_SD = 2.0

SCHEMA = """
CREATE TABLE stations (
    city            TEXT PRIMARY KEY,
    station_id      TEXT NOT NULL,
    station_name    TEXT NOT NULL,
    distance_km     REAL NOT NULL
);
CREATE TABLE temperature_monthly (
    city    TEXT NOT NULL,
    year    INTEGER NOT NULL,
    month   INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    temp_c  REAL NOT NULL,
    PRIMARY KEY (city, year, month)
);
CREATE TABLE temperature_annual (
    city      TEXT NOT NULL,
    year      INTEGER NOT NULL,
    temp_c    REAL NOT NULL,
    n_months  INTEGER NOT NULL,
    PRIMARY KEY (city, year)
);
CREATE TABLE air_quality_annual (
    city         TEXT NOT NULL,
    year         INTEGER NOT NULL,
    pm25         REAL NOT NULL,
    n_months     INTEGER NOT NULL,
    n_locations  INTEGER NOT NULL,
    PRIMARY KEY (city, year)
);

CREATE VIEW baseline AS
SELECT city, AVG(temp_c) AS baseline_c, COUNT(*) AS baseline_years
FROM temperature_annual
WHERE year BETWEEN 1961 AND 1990
GROUP BY city;

CREATE VIEW temperature_anomaly AS
SELECT t.city, t.year, t.temp_c, t.n_months, t.temp_c - b.baseline_c AS anomaly_c
FROM temperature_annual AS t
JOIN baseline AS b USING (city);

-- SQLite has no STDEV(); sample std dev = sqrt((sum(x^2) - n*mean^2) / (n - 1)).
CREATE VIEW monthly_normals AS
SELECT city, month, AVG(temp_c) AS normal_c, COUNT(*) AS n,
       SQRT((SUM(temp_c * temp_c) - COUNT(*) * AVG(temp_c) * AVG(temp_c)) / (COUNT(*) - 1))
           AS sd_c
FROM temperature_monthly
WHERE year BETWEEN 1961 AND 1990
GROUP BY city, month
HAVING COUNT(*) >= 10;

CREATE VIEW extreme_heat_months AS
SELECT m.city, m.year,
       SUM(CASE WHEN m.temp_c > n.normal_c + {sd} * n.sd_c THEN 1 ELSE 0 END) AS hot_months,
       COUNT(*) AS months_observed
FROM temperature_monthly AS m
JOIN monthly_normals AS n USING (city, month)
GROUP BY m.city, m.year;
""".replace("{sd}", str(EXTREME_SD))

# Named queries export.py runs. Each takes :city.
QUERIES = {
    "station": "SELECT station_id, station_name, distance_km FROM stations WHERE city = :city",
    "baseline": "SELECT baseline_c, baseline_years FROM baseline WHERE city = :city",
    "temperature": """
        SELECT year, temp_c, anomaly_c, n_months
        FROM temperature_anomaly WHERE city = :city ORDER BY year
    """,
    "extreme_heat": """
        SELECT year, hot_months, months_observed
        FROM extreme_heat_months
        WHERE city = :city AND months_observed >= 10
        ORDER BY year
    """,
    "decades": """
        SELECT (year / 10) * 10 AS decade, AVG(anomaly_c) AS anomaly_c, COUNT(*) AS n_years
        FROM temperature_anomaly WHERE city = :city
        GROUP BY decade HAVING COUNT(*) >= 5 ORDER BY decade
    """,
    "warmest_years": """
        SELECT year, anomaly_c, rank FROM (
            SELECT year, anomaly_c, RANK() OVER (ORDER BY anomaly_c DESC) AS rank
            FROM temperature_anomaly WHERE city = :city
        ) WHERE rank <= 5 ORDER BY rank, year
    """,
    "air_quality": """
        SELECT year, pm25, n_months, n_locations
        FROM air_quality_annual WHERE city = :city ORDER BY year
    """,
}


def _station_rows(ghcn_dir: Path) -> pd.DataFrame:
    rows = []
    for city in CITIES:
        path = ghcn_dir / f"{city}.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "city": city,
                    "station_id": raw["station_id"],
                    "station_name": raw["station_name"],
                    "distance_km": raw["distance_km"],
                }
            )
    return pd.DataFrame(rows, columns=["city", "station_id", "station_name", "distance_km"])


def build_database(
    db_path: Path = DB_PATH, processed_dir: Path = PROCESSED_DIR, ghcn_dir: Path = GHCN_DIR
) -> sqlite3.Connection:
    """(Re)create the SQLite database from the processed CSVs and return an open connection.

    Rebuilt from scratch every time — it's a derived artifact, never edited by hand.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    tables = {
        "stations": _station_rows(ghcn_dir),
        "temperature_monthly": pd.read_csv(processed_dir / "temperature_monthly.csv"),
        "temperature_annual": pd.read_csv(processed_dir / "temperature_annual.csv"),
        "air_quality_annual": pd.read_csv(processed_dir / "air_quality_annual.csv"),
    }
    for name, frame in tables.items():
        # append into the tables created above, so the schema's keys and CHECKs are enforced
        frame.to_sql(name, conn, if_exists="append", index=False)
    conn.commit()
    return conn


def query(conn: sqlite3.Connection, name: str, city: str) -> list[dict]:
    """Run one of QUERIES for a city; rows as plain dicts."""
    return [dict(row) for row in conn.execute(QUERIES[name], {"city": city})]


def main() -> None:
    conn = build_database()
    for city in CITIES:
        base = query(conn, "baseline", city)
        hot = query(conn, "extreme_heat", city)
        recent = [r["hot_months"] for r in hot if r["year"] >= 2016]
        log.info(
            "%-17s baseline %.2f °C (%d yrs)  extreme-heat months/yr: 1961-90 %.2f, 2016+ %.2f",
            city,
            base[0]["baseline_c"] if base else float("nan"),
            base[0]["baseline_years"] if base else 0,
            _mean([r["hot_months"] for r in hot if 1961 <= r["year"] <= 1990]),
            _mean(recent),
        )
    conn.close()
    log.info("wrote %s", DB_PATH)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


if __name__ == "__main__":
    main()
