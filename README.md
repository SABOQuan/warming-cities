# Warming Cities

How much hotter, and how much smoggier, have eleven of the world's big cities become?

Warming Cities is a climate data project in two halves. A tested **Python pipeline** downloads
up to 180 years of station temperature records (NOAA GHCN) and a decade of PM2.5 air-quality
readings (OpenAQ), cleans and validates them, aggregates them in SQLite and fits the statistics.
A **React + TypeScript site** turns the exported JSON into a city catalogue, per-city charts,
warming stripes and a side-by-side comparison, styled with a Y2K look.

**Cities:** Lahore · Beijing · São Paulo · Addis Ababa · New York · Delhi · Ho Chi Minh City ·
Jakarta · London · Sydney · Santiago

---

## Key findings

- **Every city has warmed since 1970**, from +0.12 °C/decade (Delhi) to +0.42 °C/decade
  (São Paulo). Every 95% confidence interval excludes zero.
- The last decade (2016–2025) ran **+0.5 to +1.9 °C** above each city's own 1961–1990 average.
- **Unusually hot months**, more than 2 standard deviations above that month's 1961–1990
  normal, went from about 0.1–0.4 a year to **2–10 a year**. Jakarta (10/yr) and Ho Chi Minh
  City (8/yr) lead.
- **Every city is above the WHO PM2.5 guideline** (5 µg/m³) in every year on record. Lahore
  (~122 µg/m³) and Delhi (~106 µg/m³) are over 20× it.
- PM2.5 is **falling significantly** in Beijing, London, Addis Ababa and Delhi.

The full results table is in [`PROJECT_LOG.md`](./PROJECT_LOG.md#4-results).

---

## The site

| Page | What it shows |
|---|---|
| **Index** (`#/`) | A catalogue of all 11 cities with warming stripes and headline numbers, sortable by warming rate, recent anomaly, PM2.5 or length of record |
| **City** (`#/city/<id>`) | Stat tiles, warming stripes, the annual temperature anomaly with a 10-year rolling mean, PM2.5 against the WHO guideline, warmest years, the station used and the city's caveats. A year-range filter zooms every chart. |
| **Compare** (`#/compare`) | Up to three cities' temperature anomalies on one chart |
| **Methods** (`#/methods`) | How every number is made, in plain language |

The charts are hand-drawn SVG, with no chart library. The site uses hash routes, so the static
build works on any host without server rewrites.

---

## How it works

```
NOAA GHCN-Monthly v4 ─┐
                      ├─► clean.py ─► analysis.py ─► aggregate.py (SQLite) ─► export.py ─► web/public/data/*.json ─► React site
OpenAQ v3 (PM2.5) ────┘
```

| Step | Script | What it does |
|---|---|---|
| Download | `etl/download_temperature.py` | Picks one GHCN station per city and pulls its monthly mean temperature |
| Download | `etl/download_air_quality.py` | Pulls monthly PM2.5 aggregates from OpenAQ behind a conservative, persistent rate limiter |
| Clean | `etl/clean.py` | Range checks, PM2.5 spike filter, coverage rules, season-adjusted annual means, a quality report |
| Analyse | `etl/analysis.py` | Warming trends with confidence intervals, anomalies, rolling means, PM2.5 trends, detrended correlation |
| Aggregate | `etl/aggregate.py` | Loads everything into SQLite; baselines, extreme-heat months, decade means and warmest years in SQL |
| Export | `etl/export.py` | One JSON per city plus a `cities.json` index, with each city's caveats shipped inside |

The theory behind the numbers and the data-cleaning principles are written up in
**[`METHODOLOGY.md`](./METHODOLOGY.md)**.

---

## Running it

**Prerequisites:** Python 3.12+ and Node 20+.

### The site

The exported data is committed, so the site runs without the pipeline:

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # static build in web/dist/
```

### The data pipeline

```bash
cd etl
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python download_temperature.py   # NOAA archive (~44 MB), no key needed
cp .env.example .env             # then add your OPENAQ_API_KEY (free at openaq.org)
python download_air_quality.py   # rate-limited and resumable
python clean.py && python analysis.py && python export.py
```

`export.py` writes straight into `web/public/data/`. To open the analysis notebook
(`etl/notebooks/exploratory_analysis.ipynb`), also run
`pip install -r requirements-notebook.txt`.

### Checks

```bash
cd etl && ruff check . && pytest                      # 79 tests
cd web && npm run lint && npm run typecheck && npm run build
```

GitHub Actions runs both sets of checks on every pull request into `main`.

---

## Repository layout

```
etl/                    Python pipeline
  cities.py             the 11 cities and their coordinates
  download_*.py         data download (temperature, air quality)
  clean.py              cleaning and validation
  analysis.py           statistics
  aggregate.py          SQLite aggregation
  export.py             JSON export for the site
  notebooks/            exploratory analysis notebook
  tests/                pytest suite
  data/                 raw and processed data (gitignored; rebuilt by the scripts)
web/                    React + TypeScript + Vite site
  public/data/          exported JSON (committed: the deployed site is built from it)
  src/pages/            index, city and methods pages
  src/components/       SVG charts, warming stripes, comparison, year filter
METHODOLOGY.md          how the project was made, the theory, the cleaning principles
PROJECT_LOG.md          build record: decisions, problems and fixes, results, sources
ROADMAP.md              the original phase-by-phase plan
```

---

## Limitations

Each city's temperature comes from **one station**, and PM2.5 records only start in 2016 at
the earliest. Jakarta has a 1985–2008 gap in its record, which makes it the least certain city.
Temperature and PM2.5 are shown side by side, **not as cause and effect**. The trends describe
the past and are not forecasts. The full list is in
[`METHODOLOGY.md`](./METHODOLOGY.md#7-limitations).

## Data sources

- **NOAA GHCN-Monthly v4**, quality-controlled and homogenized. Menne et al. (2018), *Journal of
  Climate*. Public domain.
- **OpenAQ v3 API**: monthly PM2.5 from government and US Diplomatic Post reference monitors.
- **WHO Global Air Quality Guidelines (2021)** for the 5 µg/m³ PM2.5 guideline.
- Warming stripes after **Ed Hawkins**, [showyourstripes.info](https://showyourstripes.info).

## License

MIT. See [`LICENSE`](./LICENSE).
