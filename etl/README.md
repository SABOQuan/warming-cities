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
- `analysis.py` — Phase 2.5 (`python analysis.py`). Warming trend since 1970 (°C/decade, 95%
  CI), anomalies vs 1961-1990, rolling means, PM2.5 trends, and the raw + detrended
  temperature-vs-PM2.5 correlation. Writes `data/processed/analysis_summary.json` for export.
- `notebooks/exploratory_analysis.ipynb` — Phase 2.5. Charts, findings, and the methodology and
  caveats, built on `analysis.py`. Needs `pip install -r requirements-notebook.txt`.
- `aggregate.py` — Phase 3. Loads the cleaned data into SQLite (`data/warming_cities.sqlite`)
  and does the aggregation in SQL: 1961-1990 baselines, anomalies, extreme-heat months (> 2 sd
  above that calendar month's baseline normal — GHCN-Monthly has no daily data), decade means,
  warmest years.
- `export.py` — Phase 3. Combines the SQL results with `analysis.py`'s statistics and writes
  one JSON per city plus `cities.json` to `../web/public/data/`. That JSON is committed — it's
  what the deployed site serves.

## Rebuilding the data

```bash
python download_temperature.py   # NOAA archive, no key needed
python download_air_quality.py   # needs OPENAQ_API_KEY in .env; rate-limited, resumable
python clean.py && python analysis.py && python export.py
```

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
