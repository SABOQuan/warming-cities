# etl/

Python pipeline: raw data in, cleaned + modeled JSON out for the frontend to consume.

Modules to be added phase by phase (see `../ROADMAP.md`):

- `download.py` — Phase 1. Pull raw temperature (NOAA GHCN-Monthly), air quality (OpenAQ), and
  sea-level (PSMSL, coastal cities only) data per city into `data/raw/`.
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
