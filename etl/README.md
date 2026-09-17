# etl/

Python pipeline: raw data in, cleaned + modeled JSON out for the frontend to consume.

Modules to be added phase by phase (see `../ROADMAP.md`):

- `cities.py` — the locked list of 10 cities (name -> lat/lon), shared by every download script.
- `download_air_quality.py` — Phase 1. Pull PM2.5 history per city from the OpenAQ API into
  `data/raw/openaq/`.
- `download_temperature.py` — Phase 1. Pull monthly temperature history per city from NOAA
  GHCN-Monthly into `data/raw/ghcn/`.
- `download_sea_level.py` — Phase 1 (not started). Pull PSMSL tide-gauge records for the coastal
  subset (New York, Jakarta, Manila, London) into `data/raw/psmsl/`.
- `clean.py` — Phase 2. Parse, validate, and normalize each raw dataset into a common annual
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
