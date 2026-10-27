# etl/

Python pipeline: raw data in, cleaned + modeled JSON out for the frontend to consume.

Modules to be added phase by phase (see `../ROADMAP.md`):

- `cities.py` — the locked list of 11 cities (name -> lat/lon), shared by every download script.
- `download_air_quality.py` — Phase 1. Pull monthly PM2.5 aggregates per station from the OpenAQ
  v3 API into `data/raw/openaq/`, through a rate limiter set to half of OpenAQ's limits (30/min,
  1,000/hour, tracked across runs). Run `--city lahore` first to confirm the key works.
- `download_temperature.py` — Phase 1. Pull monthly temperature history per city from NOAA
  GHCN-Monthly into `data/raw/ghcn/`.
- `download_sea_level.py` — deferred to v2. Local sea-level change mixes land subsidence and
  global rise, which is out of scope for this version.
- `clean.py` — Phase 2 (`python clean.py`). Season-adjusted annual temperature and PM2.5 per
  city in `data/processed/`, plus `quality_report.json` (coverage, baseline, dropped months).
  Drops PM2.5 months with < 75% coverage or error-code spikes. Methodology is in its docstring.
  Originally planned as: parse, validate, and normalize each raw dataset into a common annual
  granularity per city.
- `notebooks/exploratory_analysis.ipynb` — Phase 2.5. Trend regression, rolling averages,
  temperature-vs-air-quality correlation analysis (with the causation caveat documented in
  `../ROADMAP.md`), written findings.
- `aggregate.py` — Phase 3. Load cleaned data into SQLite, run the SQL aggregation queries
  (annual mean, anomaly vs. 1961-1990 baseline, extreme-heat-day counts).
- `export.py` — Phase 3. Write the final per-city JSON to `../web/public/data/`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running checks

```bash
ruff check .
pytest
```
