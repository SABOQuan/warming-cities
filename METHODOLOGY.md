# Methodology: How Warming Cities Was Made

This document explains how the project was built, the climate-science and statistical ideas
behind its numbers, and the principles followed when cleaning the data. For the build diary,
including every bug and scope change, see [`PROJECT_LOG.md`](./PROJECT_LOG.md).

---

## 1. How the project was built

The project followed a phase-by-phase plan ([`ROADMAP.md`](./ROADMAP.md)). Each phase was
one git branch and one pull request, with small Conventional Commits and CI checks.

| Phase | Work |
|---|---|
| 0 | Monorepo (`etl/` Python, `web/` React), linting and formatting, GitHub Actions CI |
| 1 | Download temperature (NOAA GHCN-Monthly) and PM2.5 (OpenAQ) for 11 cities |
| 2 | Clean and validate the data into monthly and annual series, with a quality report |
| 2.5 | Statistics (trends, anomalies, correlation) and an exploratory Jupyter notebook |
| 3 | Load into SQLite, aggregate in SQL, export one JSON per city for the site |
| 4 | Frontend scaffold: typed data loader and city selector |
| 5 | Hand-drawn SVG charts: temperature anomaly, PM2.5 and warming stripes |
| 6 | Interactivity: year-range filter and a three-city comparison |
| 7 | Visual design pass (Y2K catalogue look, "fuzzy" display type that sharpens on hover) |
| 9 | Documentation |

**Tools.** Python (pandas, NumPy, SciPy, requests, SQLite, matplotlib, Jupyter; pytest and ruff
for checks). React 19, TypeScript and Vite for the site, with oxlint and Prettier.

**Architecture.** All heavy work happens offline in Python. The site is a static build that
only reads the exported JSON (186 KB for all 11 cities), so it needs no server, database or API
key. The exported JSON is committed to the repo for that reason. The raw downloads are not
(they are gitignored and can be rebuilt by the scripts).

**City choice.** The 11 cities span every inhabited continent, rich and developing economies,
tropical and temperate climates, and both hemispheres. Three planned cities were swapped
because their PM2.5 record was too short for a trend: Manila became Ho Chi Minh City, Cairo
became Addis Ababa, and Santiago was added. Sea level was dropped from scope because local
sea-level change mixes land subsidence with global rise, and separating them honestly needed
more time than the project had.

---

## 2. Data sources

| Data | Source | Why this source |
|---|---|---|
| Monthly mean temperature | **NOAA GHCN-Monthly v4**, `qcf` variant | The standard global station archive. The `qcf` variant is quality-controlled and **homogenized**: NOAA's pairwise algorithm corrects jumps from station moves, new instruments and changed observation times. Public domain, no key. |
| PM2.5 | **OpenAQ v3**, monthly aggregates | One API in front of government networks worldwide (plus US Diplomatic Post monitors). Monthly aggregates arrive with coverage statistics, so data quality can be judged directly. |
| PM2.5 guideline | **WHO Global Air Quality Guidelines (2021)** | 5 µg/m³ annual mean, the current health-based reference |
| Reference check | **Met Office**, Heathrow 1961–1990 averages | An independent figure to test the pipeline against |

---

## 3. Theories and concepts behind the numbers

### Temperature anomalies and a fixed baseline
Climate science compares temperatures with a fixed reference period rather than in absolute
degrees. An **anomaly** is a year's mean minus the average of a baseline period. This project
uses **1961–1990**, the World Meteorological Organization's classic reference period, chosen
because most stations have good records then and it predates most modern warming.

Each city is measured against **its own** baseline. A tropical city at 28 °C and a temperate
one at 11 °C can then be compared fairly: what matters is how far each has moved from its own
normal.

### Trend since 1970 (ordinary least squares)
The warming rate is the slope of an **ordinary least-squares (OLS) regression** of annual mean
temperature on year, reported in °C per decade with a **95% confidence interval**
(slope ± t × standard error). The fit starts in **1970** for every city, for two reasons:

- the station records begin anywhere from 1841 to 1954, so full-record slopes would not be
  comparable between cities;
- 1970 is roughly where the modern, greenhouse-gas-driven warming signal emerges in global
  records.

A confidence interval that excludes zero means the warming is very unlikely to be chance
year-to-year variation. All 11 cities pass that test. The trends describe the past and are not
used to forecast.

### Rolling means
Year-to-year weather noise hides the long-term signal, so the charts add a **centred 10-year
rolling mean** of the anomaly. It respects calendar gaps (a missing year is not skipped over)
and needs at least 70% of the years in its window. Otherwise it is left blank instead of
being drawn from too little data.

### Extreme-heat months (standard deviations)
GHCN-Monthly has no daily data, so heatwave-day counts are impossible. The project uses
**unusually hot months** instead: a month more than **2 standard deviations** above that
calendar month's 1961–1990 mean. If monthly temperatures are roughly normally distributed, that
happens about **2.3%** of the time, or about 0.3 months a year by chance. The measured
1961–1990 rate (0.1–0.4 a year) matches that, so the jump to 2–10 a year since 2016 is a clear,
baseline-anchored sign of more heat.

This also explains why the tropics lead the count. Their natural month-to-month variation is
small, so a modest shift in the mean pushes many months past 2 standard deviations.

### Warming stripes
The stripes follow **Ed Hawkins' "warming stripes"**: one bar per year, coloured on a diverging
blue-white-red scale (ColorBrewer RdBu) by anomaly. Each city's colours are scaled to its own
range, so the stripes show how a city changed over time, not how cities compare with each other.

### PM2.5 trends
PM2.5 trends are also OLS slopes, in µg/m³ per year and as a percentage of the city's mean per
year, with p-values. Records shorter than **5 years** are marked "insufficient" rather than
given a slope, because a line through three or four points is mostly noise.

### Correlation is not causation, and why the data is detrended
The project checks whether warmer years are also more polluted years (Pearson correlation, *r*).
Two series that both drift over the same years correlate even with no year-to-year link: a
warming trend and a falling pollution trend produce a negative *r* on their own. So each series'
linear trend is removed first, and the **detrended *r*** is the one reported.

The likely physical link is **weather**: hot, stagnant air traps pollution. It is not that
pollution causes warming. Warming is driven by global greenhouse gases, while PM2.5 comes from
local emissions. With nine cities tested at the 5% level, about one "significant" result is
expected by chance (the **multiple-comparisons** problem), so the results are framed as weak
evidence. Each city's JSON carries this caveat, so the site cannot show the number without it.

### Aerosol dimming (context, not a model)
Delhi warms slowest of the 11 cities. A known contributor in heavily polluted regions is
**aerosol dimming**: particulates reflect sunlight and mask part of the greenhouse warming. The
project notes this as a possible explanation but does not adjust for it.

---

## 4. Data cleaning principles

The cleaning rules live in `etl/clean.py`. Each one is tested and documented in its docstring.
They follow a small set of principles.

### Principle 1: Drop and count, never silently fix
Bad values are removed, and every removal is counted in `quality_report.json`. Nothing is
quietly patched or interpolated.
- Temperatures outside **−60 to 60 °C** are physically impossible at these stations and are
  dropped.
- PM2.5 values **≤ 0 or > 1,000 µg/m³** are dropped. A monthly mean of exactly 0 is a sensor
  fault.

### Principle 2: Don't invent data; set minimum-coverage rules
Missing data is never filled in. Instead, a period counts only if enough of it is present:
- a temperature year needs **10 of 12 months**;
- a PM2.5 year needs **8 of 12 months** (looser because every city lost about 2 months of 2023
  to an OpenAQ outage, and Principle 3 removes the seasonal bias);
- a PM2.5 month needs **≥ 75% coverage**, using OpenAQ's own observed versus expected counts;
- the current, incomplete year is always dropped.

### Principle 3: Remove seasonal bias from incomplete years
A plain average of whatever months exist is biased by which months are missing. A year missing
two summer months reads too cold, and a Delhi year missing its smoggy winter reads far too
clean. So each annual mean is **season-adjusted**:

1. express each month as an offset from the city's long-term mean for that calendar month;
2. average the offsets over the year;
3. add the city's mean annual climatology back.

With all 12 months present, this equals the plain mean exactly. With gaps, it no longer
depends on which months are missing.

### Principle 4: Detect and remove sensor artefacts
US Diplomatic Post monitors record invalid hours as error codes (985, 1985 and so on), and
OpenAQ averaged them in as real readings. Ho Chi Minh City showed months of 375 and even
985 µg/m³ against a typical 25–35. A sensor-month is dropped when:
- its **mean is more than 2× its median**, meaning a few extreme days dominate the month; or
- **any single day averages above 900 µg/m³**, which no real city sustains for a whole day.

This removed about 1% of sensor-months. It was found by checking the output for implausible
values, not assumed in advance.

### Principle 5: Aggregate in a fixed, visible order
PM2.5 is averaged **sensor → station → city**, so a station with two sensors doesn't count
twice. The number of stations behind each year (`n_locations`) is kept, because a growing
monitor network (London grows from a handful of monitors to many dozens) can move the city mean on its own.

### Principle 6: Fail loudly on broken invariants
Some problems can't be cleaned away. **Duplicate rows** raise a `DataQualityError` and stop the
pipeline instead of being deduplicated without anyone noticing. The SQLite tables add primary
keys and `CHECK` constraints as a second line of defence.

### Principle 7: Choose sources by data actually present, not by metadata
- **Temperature station:** one station per city, which must still be reporting (data within the
  last 5 years). Among stations within 50 km, the one with the **most complete 1961–1990
  baseline** wins, then the nearest. This rule was added after the first pass gave Delhi a
  station with 0 of 30 baseline years.
- **PM2.5 monitors:** reference-grade monitors within 25 km. Low-cost sensors are used only if a
  city has none.
- Candidate cities were checked against the monthly data that actually exists. Bangkok's
  metadata claimed 2016, but its data started in 2021.

### Principle 8: Validate against an independent reference
A test checks that London's 1961–1990 baseline from the pipeline (10.78 °C) is within 0.2 °C of
the Met Office's published Heathrow figure (about 10.6 °C). If the pipeline drifts, CI fails.

### Principle 9: Ship the caveats with the numbers
Each city's limitations (a short baseline, a record gap, a short PM2.5 series) are written into
that city's JSON by `export.py` and shown next to its charts. A number cannot reach the site
without its caveat.

---

## 5. Responsible data collection

OpenAQ is a free, shared service. The first downloader pulled raw hourly data, more than 10,000
requests, and the API key was suspended. The rewrite follows these rules:
- download **monthly aggregates**, about 1 request per sensor instead of thousands;
- a single rate limiter set to **half of OpenAQ's published limits** (30/minute, 1,000/hour,
  with at least 2.5 s between requests);
- the request history is **saved to disk**, so restarting the script can't reset the budget;
- it backs off when the API reports few requests left, **aborts** on a second 429 response and
  stops immediately on a rejected key;
- each run is **hard-capped at 900 requests**, and finished sensors are skipped on re-runs.

The full download took 372 requests, with zero rate-limit errors, and produced 15 MB instead of
the 847 MB of the hourly approach.

---

## 6. Testing

79 pytest tests cover the downloaders (with mocked HTTP), the rate limiter, every cleaning rule,
the statistics, the SQL aggregation and the export schema, including the Met Office reference
check. The frontend is linted (oxlint), type-checked (TypeScript) and built in CI.

---

## 7. Limitations

- **One station per city.** Homogenization corrects station moves and instrument changes, not
  the urban heat island growing around a station.
- **Jakarta** has only 14 of 30 baseline years and a 1985–2008 gap, so its anomalies are the
  least certain.
- **Short PM2.5 records.** They start in 2016 at the earliest. São Paulo starts in 2021, Sydney
  ends in 2022, Ho Chi Minh City's monitor ends in 2021, and Lahore has a single monitor from
  2020.
- **Changing monitor networks** can shift a city's PM2.5 mean independently of real air quality.
- **Correlation is not causation**, and many cities were tested, so individual correlations
  are weak evidence.
- **Linear trends describe the past.** No projections are made.
