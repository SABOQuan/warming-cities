# Project Log — Warming Cities

What has been built so far, the decisions behind it, what went wrong and how it was fixed, and
every source the project relies on. `ROADMAP.md` is the plan; this file is the record.

*Last updated: 2026-10-27.*

---

## 1. Status at a glance

| Phase | What | Branch | PR | State |
|---|---|---|---|---|
| 0 | Repo, tooling, CI | `chore/repo-setup` | — | Merged to `main` |
| 1 | Data download (temperature + air quality) | `feat/data-download` | [#1](https://github.com/SABOQuan/warming-cities/pull/1) | Open, CI green |
| 2 | Cleaning & validation | `feat/etl-cleaning` | [#2](https://github.com/SABOQuan/warming-cities/pull/2) | Open, stacked on #1 |
| 2.5 | Statistics + analysis notebook | `feat/eda-modeling` | [#3](https://github.com/SABOQuan/warming-cities/pull/3) | Open, stacked on #2 |
| 3 | SQLite aggregation + JSON export | `feat/aggregate-export` | [#4](https://github.com/SABOQuan/warming-cities/pull/4) | Open, stacked on #3 |
| 4–7 | Frontend (scaffold, charts, interactivity, Y2K design) | — | — | Not started |
| 8 | Deployment | — | — | Not started |
| 9 | Final README / write-up | — | — | Not started |

The PRs are stacked: merge them in order (#1 → #2 → #3 → #4). CI runs only on PRs into `main`,
so each later PR gets its CI run once the one before it is merged and GitHub retargets it.

**The data side of the project is complete.** The site's data is exported and committed in
`web/public/data/` (one JSON per city plus a `cities.json` index, 186 KB). 79 automated tests
pass.

---

## 2. Scope changes from the original roadmap

| Change | Why |
|---|---|
| **Sea level dropped** (deferred to v2) | Local sea-level change mixes land subsidence (dominant in Jakarta), tectonics and global sea-level rise. Doing it honestly was out of scope for the deadline. |
| **Manila → Ho Chi Minh City** | OpenAQ only has PM2.5 for Manila from 2023, too short for a trend. Bangkok was tried first, but its monitors only have usable data from 2021, even though their metadata said 2016. Ho Chi Minh City has a monitor covering 2016–2021. |
| **Cairo → Addis Ababa** | Cairo's PM2.5 also only starts in 2023. Addis Ababa has PM2.5 from 2017 and one of the longest temperature records (from 1902). |
| **Santiago added** (11 cities, was 10) | A second southern-hemisphere city with PM2.5 from 2016 to the present and temperature from 1948. |
| **Extreme-heat *days* → extreme-heat *months*** | GHCN-Monthly has no daily data, so daily counts are impossible. The replacement: months more than 2 standard deviations above that calendar month's 1961–1990 normal. |
| **WHO Ambient Air Quality Database not used** | OpenAQ alone covered all 11 cities from 2016. The WHO database is a possible v2 addition for earlier years. |

**Final city list:** Lahore, Beijing, São Paulo, Addis Ababa, New York, Delhi, Ho Chi Minh City,
Jakarta, London, Sydney, Santiago.

---

## 3. What each phase did

### Phase 0 — Repo setup (merged)
- Monorepo: `etl/` (Python) and `web/` (React + TypeScript + Vite).
- CI (`.github/workflows/ci.yml`): Python lint (`ruff`) and tests (`pytest`); frontend lint, type check and build.
- `ROADMAP.md` with the full plan.

### Phase 1 — Data download (PR #1)

**Temperature** (`etl/download_temperature.py`)
- Downloads NOAA's single global GHCN-Monthly v4 archive (about 44 MB). No API key and no rate limit.
- Uses the quality-controlled, homogenized `qcf` variant. NOAA has corrected it for station moves, instrument changes and observation-time changes.
- Picks one station per city. It must still be reporting (within the last 5 years). Within 50 km, the station with the most complete 1961–1990 baseline wins, and the nearest wins on ties. See section 5 for why the baseline rule was added.

**Air quality** (`etl/download_air_quality.py`)
- OpenAQ v3. A radius search (25 km) finds reference-grade monitors around each city. Low-cost community sensors are used only if a city has no reference monitor.
- Downloads **monthly PM2.5 aggregates** (`/sensors/{id}/days/monthly`) rather than raw hourly readings. That's about 1 request per sensor, and every month comes with coverage statistics.
- **Rate limiting:** every request goes through one `RateLimiter`, capped at half of OpenAQ's limits (30/minute and 1,000/hour), with at least 2.5 seconds between requests.
  - Its request history is saved to disk, so re-running the script can't reset the hourly budget.
  - It pauses when OpenAQ reports few requests remaining.
  - A second "too many requests" (429) response aborts the run.
  - A rejected key (401/403) stops immediately.
  - Each run is hard-capped at 900 requests.
- Resumable: completed sensors are skipped on re-runs.
- Full run: **372 requests, zero 429s, 15 MB** (the old hourly approach had produced 847 MB).

### Phase 2 — Cleaning & validation (PR #2)

`etl/clean.py` turns the raw downloads into monthly and annual CSVs plus `quality_report.json`.

- **Season-adjusted annual means.** Each month is measured against the city's normal for that calendar month, the year's offsets are averaged, and the normal is added back. A year missing its hottest or smoggiest months is therefore not biased. With all 12 months present, this equals the plain mean.
- **Minimum months per year:** 10/12 for temperature and 8/12 for PM2.5.
- **PM2.5 filters:**
  - A month needs at least 75% coverage.
  - Values must be above 0 and at most 1,000 µg/m³.
  - **Error-code spikes are dropped.** A sensor-month is removed if its mean is more than 2× its median, or if any day averages above 900 µg/m³. This removed about 1% of sensor-months.
- **Averaging order:** sensors → station → city. `n_locations` is kept, so changes in the monitor network stay visible.
- **Integrity checks:** duplicate rows raise an error, and impossible temperatures (outside −60 to 60 °C) are dropped and counted.

### Phase 2.5 — Statistics & notebook (PR #3)

`etl/analysis.py` is a tested module; the export takes its numbers from here.
- **Warming trend:** OLS slope of annual temperature since **1970**, in °C/decade, with a 95% confidence interval. Every city starts in 1970 because records begin anywhere from 1841 to 1954, so full-record slopes wouldn't be comparable.
- **Anomalies** are measured against each city's own **1961–1990** mean, the WMO-standard reference period.
- **10-year rolling means** that respect calendar gaps.
- **PM2.5 trends** in µg/m³ and %/year. Records under 5 years are marked insufficient.
- **Temperature vs PM2.5 correlation,** both raw and **detrended.**

`etl/notebooks/exploratory_analysis.ipynb` (executed, with outputs saved) holds the charts, findings, methodology and limitations.

### Phase 3 — SQLite & export (PR #4)

- `etl/aggregate.py` rebuilds `data/warming_cities.sqlite` from the CSVs, with primary keys and CHECK constraints. The SQL views cover baselines, anomalies, monthly normals and extreme-heat months. Named queries cover decade means and the 5 warmest years (`RANK()`).
- `etl/export.py` writes `web/public/data/<city>.json` and `cities.json`. Each city's **caveats ship inside its JSON**, so the site can't show a number without its limitation.
- The exported JSON is **committed on purpose**. The deployed site builds from the repo, and the repo has no raw data or OpenAQ key to regenerate it.

**Rebuild everything:**
```bash
cd etl
python download_temperature.py   # NOAA archive, no key needed
python download_air_quality.py   # needs OPENAQ_API_KEY in etl/.env
python clean.py && python analysis.py && python export.py
```

---

## 4. Results

| City | Temp station | Temp years | Baseline yrs | Warming °C/decade since 1970 (95% CI) | Last decade vs 1961–90 | PM2.5 years | Mean PM2.5 | PM2.5 trend | Extreme-heat months/yr, 1961–90 → 2016+ |
|---|---|---|---|---|---|---|---|---|---|
| Lahore | Lahore City (1 km) | 1876–2025 | 25/30 | +0.27 (+0.18 to +0.35) | +1.30 °C | 2020–2024 | 122 µg/m³ | +3.9%/yr (p=0.18) | 0.1 → 2.6 |
| Beijing | Beijing (11 km) | 1841–2025 | 28/30 | +0.37 (+0.30 to +0.44) | +1.54 °C | 2016–2024 | 45 µg/m³ | −6.2%/yr (p=0.013) | 0.1 → 4.0 |
| São Paulo | São Paulo (6 km) | 1887–2025 | 27/30 | +0.42 (+0.35 to +0.50) | +1.88 °C | 2021–2024 | 14 µg/m³ | too short | 0.3 → 4.4 |
| Addis Ababa | Addis Ababa Bole (1 km) | 1902–2025 | 27/30 | +0.29 (+0.23 to +0.34) | +1.18 °C | 2017–2025 | 28 µg/m³ | −3.6%/yr (p=0.014) | 0.4 → 5.9 |
| New York | Newark Intl Airport (14 km) | 1846–2025 | 30/30 | +0.35 (+0.25 to +0.44) | +1.66 °C | 2016–2026 | 8 µg/m³ | −1.2%/yr (p=0.3) | 0.2 → 2.5 |
| Delhi | New Delhi Safdarjung (16 km) | 1931–2025 | 30/30 | +0.12 (+0.05 to +0.19) | +0.53 °C | 2016–2026 | 106 µg/m³ | −2.7%/yr (p=0.002) | 0.1 → 0.7 |
| Ho Chi Minh City | Tan Son Hoa (4 km) | 1954–2024 | 26/30 | +0.34 (+0.28 to +0.40) | +1.37 °C | 2016–2021 | 29 µg/m³ | −5.3%/yr (p=0.08) | 0.3 → 8.1 |
| Jakarta | Jakarta Observatory (3 km) | 1866–2025 | 14/30 | +0.29 (+0.24 to +0.34) | +1.49 °C | 2016–2025 | 39 µg/m³ | −2.1%/yr (p=0.25) | 0.2 → 10.0 |
| London | Heathrow (23 km) | 1948–2025 | 30/30 | +0.34 (+0.26 to +0.43) | +1.62 °C | 2016–2026 | 11 µg/m³ | −3.6%/yr (p=0.006) | 0.3 → 2.5 |
| Sydney | Sydney Observatory Hill (1 km) | 1859–2025 | 30/30 | +0.20 (+0.14 to +0.26) | +1.12 °C | 2018–2022 | 7 µg/m³ | too short | 0.3 → 3.0 |
| Santiago | Quinta Normal (2 km) | 1948–2025 | 21/30 | +0.15 (+0.09 to +0.21) | +0.65 °C | 2016–2026 | 29 µg/m³ | +1.9%/yr (p=0.12) | 0.3 → 1.9 |

**Headline findings**
- **Every city has warmed since 1970**, and every 95% confidence interval excludes zero.
- **Extreme-heat months** were rare in 1961–1990 (0.1–0.4 a year, close to the ~0.3 expected by chance) and are now common. Tropical cities lead (Jakarta 10/yr, Ho Chi Minh City 8/yr), because their normal year-to-year variation is small, so modest warming pushes most months past the threshold.
- **Every city is above the WHO PM2.5 guideline** (5 µg/m³ annual mean) in every year. Lahore and Delhi are over 20× it.
- **PM2.5 is falling significantly** in Beijing, London, Addis Ababa and Delhi.
- **Temperature vs PM2.5.** After removing the trends, Delhi (r ≈ 0.72, p ≈ 0.02) and Beijing (r ≈ 0.72, p ≈ 0.03) show warmer years tending to be more polluted, most likely because of weather (stagnant air traps pollution). Beijing's raw r is −0.10, because its falling PM2.5 hides the link. **This is not causation,** and with 9 cities tested, about one "significant" result is expected by chance.
- **Reference check:** London's 1961–1990 baseline from GHCN (10.78 °C) is within 0.2 °C of the Met Office's published Heathrow average (~10.6 °C). This is enforced by a test.

---

## 5. Problems found and how they were fixed

| Problem | How it showed up | Fix |
|---|---|---|
| **OpenAQ API key suspended** | The first downloader pulled raw hourly data (>10,000 requests). The sustained volume broke OpenAQ's 2,000/hour limit. | Rewrote the client to use monthly aggregates (~1 request/sensor) behind a persistent, conservative rate limiter (see Phase 1). New key, zero 429s. |
| **CI couldn't import the modules** | Tests passed locally (`python -m pytest`) but failed in CI (bare `pytest`). This was in the original repo. | `pythonpath = ["."]` in `etl/pyproject.toml`. |
| **Delhi and New York had hollow baselines** | The quality report showed Delhi 0/30 baseline years (Palam station starts 1997) and New York 10/30. | Station choice now ranks by baseline coverage within 50 km: Delhi → Safdarjung (30/30), New York → Newark Airport (30/30). The other 9 cities are unchanged. |
| **Impossible PM2.5 values** | Ho Chi Minh City averaged 65 µg/m³, about 2× normal. Some months showed 375 and even 985 µg/m³. | US Diplomatic Post monitors report invalid hours as error codes (985, 1985…), which got averaged in as real values. The spike filter (Phase 2) removed them, and Ho Chi Minh City now reads 24–33 µg/m³. |
| **Station metadata overstated data** | Bangkok's monitors were listed as starting in 2016, but actual monthly data only exists from 2021. | Candidate cities were checked against real monthly data, not metadata. Ho Chi Minh City was chosen instead. |
| **Misleading raw correlation** | Delhi's raw r = 0.82 looked like it might come from two trends moving together. | Added a detrended correlation. It showed the link is real year to year, and that Beijing has a link its raw r hides. |
| **Jakarta's record gap** | The anomaly chart showed almost no data from 1985 to 2008, with the record resuming about 1.5 °C warmer. | No better nearby station exists. Documented as the least certain city, in the notebook and in Jakarta's JSON notes. |

---

## 6. Known limitations

- **One station per city.** Each temperature series is one thermometer. GHCN's homogenization corrects station moves and instrument changes, not urban growth around the station.
- **Jakarta:** 14/30 baseline years and a 1985–2008 gap. Its anomalies are the least certain.
- **Short, uneven PM2.5 records:** 2016 at the earliest. São Paulo starts in 2021. Sydney ends in 2022. Ho Chi Minh City's monitor ends in 2021, after a period of faulty readings. Lahore has a single monitor and starts in 2020.
- **2023 gap:** every city is missing about 2 months of PM2.5 data, because of a gap on OpenAQ's side.
- **Changing monitor networks:** London grows from a handful of monitors to ~80, so city means can shift as stations come and go.
- **Delhi warms slowest.** One possible contributor is aerosol "dimming": heavy particulate pollution reflects sunlight and masks part of the warming. The number is reported as measured.
- **Linear trends describe the past; they aren't forecasts.** No projections are made.

---

## 7. Sources

### Data
- **NOAA GHCN-Monthly v4** (temperature, `qcf` quality-controlled and homogenized variant).
  NOAA National Centers for Environmental Information.
  Product page: <https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-monthly>
  Archive used: <https://www.ncei.noaa.gov/pub/data/ghcn/v4/ghcnm.tavg.latest.qcf.tar.gz> (release `v4.0.1.20260914`).
  Citation: Menne, M. J., et al. (2018), *The Global Historical Climatology Network Monthly
  Temperature Dataset, Version 4*, Journal of Climate. US-government work, public domain.
- **OpenAQ v3 API** (PM2.5 monthly aggregates). <https://openaq.org>, API docs <https://docs.openaq.org>.
  - Endpoints used: `/v3/locations` (radius search) and `/v3/sensors/{id}/days/monthly`.
  - OpenAQ redistributes data from its original providers under their terms.
  - Lahore and Ho Chi Minh City depend entirely on **US Department of State "US Diplomatic Post"** monitors (AirNow program), and Addis Ababa mainly does. The other cities mostly use their own government monitoring networks.
  - Rate limits followed: <https://docs.openaq.org/using-the-api/rate-limits>.

### Reference figures and standards
- **Met Office UK climate averages, Heathrow, 1961–1990** (annual mean max 14.46 °C, min 6.73 °C). Used as the published reference check for London's baseline.
  <https://www.metoffice.gov.uk/research/climate/maps-and-data/uk-climate-averages/gcpsvg3nc>
- **WHO Global Air Quality Guidelines (2021):** PM2.5 annual mean guideline of 5 µg/m³.
- **WMO standard reference period, 1961–1990:** used as the anomaly baseline.

### Software
- Python: pandas, NumPy, SciPy (`linregress`, `pearsonr`), requests, python-dotenv, SQLite (standard library), matplotlib and Jupyter (notebook only), pytest and ruff.
- Frontend (planned): React, TypeScript, Vite.

### Inspiration
- **ssorkin/climate**, <https://github.com/ssorkin/climate>: a mature NOAA-station climate explorer for Los Angeles. Ideas worth adopting are tracked in our planning (data-quality report, known-issues registry, analysis config, stat tiles and warming stripes on the site).
